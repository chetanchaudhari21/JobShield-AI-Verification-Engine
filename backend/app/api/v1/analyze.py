"""API Route for Job Text Analysis (POST /api/v1/analyze/job-text).

Implements Section 4 & Section 9 of PROJECT_SPECIFICATION.md:
- Accepts validated job description text (rejects empty or oversized inputs).
- Evaluates rule signals, calibrated ML inference, and composite risk score.
- Persists scan requests, verification evidence, and prediction records.
- Enforces strict privacy: NEVER logs or persists the raw submitted text.
"""

from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
from typing import Optional
import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user_optional
from app.db.session import get_db
from app.models.prediction import PredictionHistory
from app.models.recruiter import RecruiterEmailScan
from app.models.scan import ScanRequest
from app.models.user import User
from app.models.verification import VerificationEvidence
from app.schemas.offer import OfferLetterAnalysisResponse, OfferLetterExtractedData
from app.services.job_relevance_validator import (
    JobRelevanceResult,
    validate_job_text,
    validate_job_url,
    validate_offer_letter,
    validate_recruiter_email,
)
from app.schemas.analysis import (
    CommunitySummary,
    CompanyVerificationSummary,
    DomainCheckSummary,
    EvidenceItem,
    JobTextAnalysisRequest,
    JobTextAnalysisResponse,
    JobUrlAnalysisRequest,
    JobUrlAnalysisResponse,
    ProvisionalThresholds,
    RecruiterCheckSummary,
    RecruiterEmailAnalysisRequest,
    RecruiterEmailAnalysisResponse,
)
from app.services.domain_checker import check_domain_security
from app.services.html_extractor import extract_job_posting_from_html
from app.services.ml_inference import MLServiceError
from app.services.recruiter_checker import hash_email, verify_recruiter_email
from app.services.risk_engine import get_provisional_threshold_ranges, get_risk_engine
from app.services.safe_fetch import (
    FetchNetworkError,
    FetchTimeoutError,
    InvalidContentTypeError,
    OversizedBodyError,
    SafeFetchError,
    SSRFBlockedError,
    safe_fetch_url,
)
from app.services.pdf_extractor import (
    EncryptedPDFError,
    ExcessivePagesError,
    InvalidPDFError,
    OCRTimeoutError,
    OversizedFileError,
    PDFProcessingError,
    extract_text_and_ocr,
)
from app.services.offer_letter_analyzer import (
    DatabasePersistenceError as OfferPersistenceError,
    analyze_offer_letter,
    persist_offer_letter_scan,
)

logger = logging.getLogger("jobshield.api.analyze")

router = APIRouter(prefix="/analyze", tags=["Analysis"])


class DatabasePersistenceError(Exception):
    """Raised when scan records cannot be saved to the database."""
    pass


def persist_scan_records(
    db: Session,
    result: JobTextAnalysisResponse,
    text_sha256: str,
    input_type: str = "job_text",
    input_reference: Optional[str] = None,
    user_id: Optional[str] = None,
) -> None:
    """Safely persists scan metadata, evidence signals, and prediction history.

    PRIVACY GUARANTEE: Never logs or stores the raw input text.
    Only non-reversible cryptographic hashes (SHA-256) and derived risk scores are persisted.
    """
    try:
        # 1. Create ScanRequest record
        scan_record = ScanRequest(
            id=result.report_id,
            user_id=user_id,
            input_type=input_type,
            input_reference=input_reference or f"sha256:{text_sha256}",
            status="completed",
            completed_at=result.timestamp,
        )
        db.add(scan_record)

        # 2. Persist Evidence Items
        for item in result.evidence:
            source_url = getattr(item, "source_url", None)
            if not source_url and hasattr(result, "job_url"):
                source_url = result.job_url
            evidence_record = VerificationEvidence(
                scan_id=result.report_id,
                evidence_type=item.evidence_type,
                source_name=item.source_name,
                source_url=source_url,
                observed_at=result.timestamp,
                status=item.status,
                confidence=item.confidence,
                summary=item.summary,
                limitations=item.limitations,
                raw_metadata=item.details,
            )
            db.add(evidence_record)

        # 3. Assemble complete report explanation metadata
        common_report_meta = {
            "warning": result.warning,
            "override_floor_applied": getattr(result, "override_floor_applied", None),
            "override_floor_reason": getattr(result, "override_floor_reason", None),
            "recommended_safe_actions": result.recommended_safe_actions,
            "limitations": result.limitations,
            "disclaimer": result.disclaimer,
            "community_summary": result.community_summary.model_dump(mode="json") if result.community_summary else None,
            "company_verification": result.company_verification.model_dump(mode="json") if getattr(result, "company_verification", None) else None,
            "duplicate_analysis": result.duplicate_analysis.model_dump(mode="json") if getattr(result, "duplicate_analysis", None) else None,
            "extracted_title": getattr(result, "extracted_title", None),
            "extracted_company": getattr(result, "extracted_company", None),
            "page_type": getattr(result, "page_type", None),
            "fetch_status_code": getattr(result, "fetch_status_code", None),
            "domain_check": result.domain_check.model_dump(mode="json") if getattr(result, "domain_check", None) else None,
            "recruiter_checks": result.recruiter_checks.model_dump(mode="json") if getattr(result, "recruiter_checks", None) else None,
        }

        # 4. Persist Prediction History
        if result.ml_analysis is not None:
            explanation_payload = {
                **common_report_meta,
                "calibration_method": result.ml_analysis.calibration_method,
                "primary_threshold": result.ml_analysis.primary_threshold,
                "calibrated_threshold": result.ml_analysis.calibrated_threshold,
                "decision_threshold": result.ml_analysis.decision_threshold,
                "calibrated_prediction": result.ml_analysis.calibrated_prediction,
                "explanation_method": result.ml_analysis.explanation_method,
                "score_type": result.ml_analysis.score_type,
                "target_class": result.ml_analysis.target_class,
                "intercept": result.ml_analysis.intercept,
                "decision_score": result.ml_analysis.decision_score,
                "reconciled_score": result.ml_analysis.reconciled_score,
                "is_reconciled": result.ml_analysis.is_reconciled,
                "active_feature_count": getattr(result.ml_analysis, "active_feature_count", None),
                "total_feature_contribution": getattr(result.ml_analysis, "total_feature_contribution", None),
                "explanation_available": result.ml_analysis.explanation_available,
                "explanation_unavailable_reason": result.ml_analysis.explanation_unavailable_reason,
                "explanation_disclaimer": result.ml_analysis.explanation_disclaimer,
                "top_features": [f.model_dump(mode="json") for f in result.ml_analysis.top_features],
                "top_positive_features": [f.model_dump(mode="json") for f in result.ml_analysis.top_positive_features],
                "top_negative_features": [f.model_dump(mode="json") for f in result.ml_analysis.top_negative_features],
            }
            pred_record = PredictionHistory(
                scan_id=result.report_id,
                model_version=result.ml_analysis.model_version,
                predicted_class=result.ml_analysis.primary_prediction,
                model_probability=result.ml_analysis.calibrated_probability,
                risk_score=result.risk_score if result.risk_score is not None else -1.0,
                risk_category=result.risk_category,
                threshold_version=result.provisional_thresholds.version if result.provisional_thresholds else "provisional_v1.0.0",
                explanation=explanation_payload,
            )
            db.add(pred_record)

        db.commit()
    except Exception as exc:
        db.rollback()
        # Log failure with generic exception type — never expose user content or DB passwords
        logger.error(
            "Failed to persist scan records for report_id=%s: %s",
            result.report_id,
            type(exc).__name__,
        )
        raise DatabasePersistenceError(
            f"Failed to persist scan records: {type(exc).__name__}"
        ) from exc


@router.post(
    "/job-text",
    response_model=JobTextAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze Job Text",
    description=(
        "Analyzes raw job posting text for recruitment fraud patterns. "
        "Returns composite risk score, rule-based signals, calibrated ML prediction, "
        "tailored safe actions, and limitations. Raw submitted text is never logged."
    ),
)
async def analyze_job_text(
    payload: JobTextAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> JobTextAnalysisResponse:
    # 1. Compute non-reversible SHA-256 digest for correlation/deduplication
    raw_bytes = payload.text.encode("utf-8")
    text_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    # PRIVACY ENFORCEMENT: Never log payload.text!
    logger.info(
        "Received job-text scan request [input_bytes=%d, sha256_prefix=%s]",
        len(raw_bytes),
        text_sha256[:12],
    )

    # 1.5 Validate Job-Relevance before running downstream fraud analysis
    relevance_result = validate_job_text(payload.text)
    if relevance_result.status != "VALID":
        logger.info(
            "Rejected non-job text input [status=%s, reason_code=%s]",
            relevance_result.status,
            relevance_result.reason_code,
        )
        report_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        thresholds_doc = ProvisionalThresholds(
            version=settings.RISK_THRESHOLD_VERSION,
            ranges=get_provisional_threshold_ranges(),
        )
        from app.schemas.analysis import CompanyVerificationSummary
        return JobTextAnalysisResponse(
            report_id=report_id,
            timestamp=now,
            risk_score=None,
            risk_category="INVALID_INPUT" if relevance_result.status == "INVALID" else "INSUFFICIENT_EVIDENCE",
            warning=relevance_result.user_message,
            provisional_thresholds=thresholds_doc,
            evidence=[],
            ml_analysis=None,
            company_verification=CompanyVerificationSummary(
                status="UNVERIFIED",
                summary="Company entity verification skipped for non-job input.",
            ),
            recruiter_checks=RecruiterCheckSummary(
                status="SKIPPED",
                summary="Recruiter contact checks skipped for non-job input.",
            ),
            community_summary=CommunitySummary(),
            recommended_safe_actions=[
                "Submit a valid job description, recruitment posting, or vacancy announcement to assess potential employment risks."
            ],
            limitations=[
                "JobShield AI evaluates recruitment postings and employment offers; non-job content is not assessed for fraud."
            ],
            is_job_related=False,
            relevance=relevance_result,
        )

    # 2. Execute Risk Engine Pipeline (fails fast if required ML component is unavailable)
    engine = get_risk_engine()
    try:
        result = engine.analyze_job_text(
            payload.text,
            company_name=payload.company_name,
            cin=payload.cin,
            db=db,
            explanation_method=payload.explanation_method or "auto",
        )
        result.is_job_related = True
        result.relevance = relevance_result
    except MLServiceError as exc:
        logger.error("ML service failure during analysis: %s", type(exc).__name__)
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML inference service is currently unavailable. Analysis cannot be completed without required ML component.",
        )

    # 2.5 Duplicate & Impersonation Detection (Feature F5)
    try:
        from app.services.duplicate_detector import analyze_duplicate_job
        dup_summary = analyze_duplicate_job(
            text=payload.text,
            company_name=payload.company_name,
            cin=payload.cin,
            db=db,
        )
        result.duplicate_analysis = dup_summary
        if dup_summary and dup_summary.status == "POTENTIAL_SUSPICIOUS_COPY":
            result.evidence.append(
                EvidenceItem(
                    evidence_type="duplicate_impersonation_signal",
                    source_name="Duplicate & Impersonation Engine",
                    status="SUSPICIOUS_COPY",
                    confidence=0.85,
                    summary=dup_summary.summary,
                    details={
                        "highest_similarity": dup_summary.highest_similarity_score,
                        "matches_count": dup_summary.total_matches_found,
                        "impersonation_warning": dup_summary.impersonation_warning,
                    },
                )
            )
            if not result.warning and dup_summary.impersonation_warning:
                result.warning = f"Impersonation Notice: {dup_summary.impersonation_warning}"
    except Exception as exc:
        logger.debug("Duplicate analysis during job-text scan skipped: %s", exc)

    # 3. Persist Scan Metadata, Evidence, and Predictions in Database (fails fast if DB is down)
    try:
        persist_scan_records(
            db=db,
            result=result,
            text_sha256=text_sha256,
            user_id=current_user.id if current_user else None,
        )
    except DatabasePersistenceError:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database persistence failed. Scan record could not be saved.",
        )

    # PRIVACY ENFORCEMENT: Only log outcome metadata
    logger.info(
        "Completed job-text scan [report_id=%s, risk_category=%s, risk_score=%s]",
        result.report_id,
        result.risk_category,
        result.risk_score,
    )

    return result


@router.post(
    "/job-url",
    response_model=JobUrlAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze Public Job URL",
    description=(
        "Safely fetches and analyzes a public job posting URL for recruitment fraud patterns. "
        "Enforces strict SSRF protections, performs technical domain verification (DNS, MX, SPF, DMARC, DKIM), "
        "detects lookalike domains, extracts job content safely, and evaluates composite risk."
    ),
)
async def analyze_job_url(
    payload: JobUrlAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> JobUrlAnalysisResponse:
    # 1. Fetch URL using SSRF-safe fetcher
    logger.info("Received job-url scan request")
    try:
        fetch_result = safe_fetch_url(payload.url)
    except SSRFBlockedError as exc:
        logger.warning("SSRF blocked for URL: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"URL rejected by security policy: {exc}",
        )
    except OversizedBodyError as exc:
        logger.warning("Oversized body for URL: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Webpage size exceeds maximum allowed limit (1 MB): {exc}",
        )
    except InvalidContentTypeError as exc:
        logger.warning("Invalid content type for URL: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported document format: {exc}",
        )
    except FetchTimeoutError as exc:
        logger.warning("Fetch timeout for URL: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Network request timed out while fetching URL: {exc}",
        )
    except FetchNetworkError as exc:
        logger.warning("Network failure for URL: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to reach destination host: {exc}",
        )
    except SafeFetchError as exc:
        logger.warning("Safe fetch error for URL: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch job URL: {exc}",
        )

    # 2. Check for non-2xx HTTP status codes other than 403/429
    if fetch_result.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target webpage not found (HTTP 404) at destination: {fetch_result.final_url}",
        )
    elif fetch_result.status_code >= 500:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Remote server returned HTTP {fetch_result.status_code} error: {fetch_result.final_url}",
        )
    elif fetch_result.status_code >= 400 and fetch_result.status_code not in (403, 429):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Remote server returned HTTP {fetch_result.status_code} error: {fetch_result.final_url}",
        )

    # 3. Extract job posting content and metadata safely using BeautifulSoup
    extracted = extract_job_posting_from_html(fetch_result.content, url=fetch_result.final_url)

    # 4. Perform Technical Domain Verification & Lookalike Detection
    domain_result = check_domain_security(fetch_result.final_url, db=db)
    domain_summary = DomainCheckSummary(
        domain=domain_result.domain,
        dns_status=domain_result.dns_status,
        mx_status=domain_result.mx_status,
        spf_status=domain_result.spf_status,
        dkim_status=domain_result.dkim_status,
        dmarc_status=domain_result.dmarc_status,
        lookalike_flags=domain_result.lookalike_flags,
        source_details=domain_result.source_details,
        checked_at=domain_result.checked_at,
        summary=(
            f"Domain security checks for '{domain_result.domain}': "
            f"DNS {domain_result.dns_status}, MX {domain_result.mx_status}, "
            f"SPF {domain_result.spf_status}, DMARC {domain_result.dmarc_status}."
        ),
        limitations=(
            "Technical domain checks evaluate email and DNS infrastructure; "
            "they do not guarantee authorization of specific individuals."
        ),
    )

    # 5. Resolve claimed company entity (payload takes priority over extracted HTML metadata)
    resolved_company = payload.company_name or extracted.company_name
    engine = get_risk_engine()
    now = datetime.now(timezone.utc)
    report_id = str(uuid.uuid4())
    thresholds_doc = ProvisionalThresholds(
        version=settings.RISK_THRESHOLD_VERSION,
        ranges=get_provisional_threshold_ranges(),
    )

    is_access_restricted = fetch_result.status_code in (403, 429)
    is_sparse_content = not is_access_restricted and len(extracted.clean_text) < 20

    # Handle ACCESS_RESTRICTED and JS_REQUIRED_OR_SPARSE_CONTENT gracefully
    if is_access_restricted or is_sparse_content:
        page_outcome = "ACCESS_RESTRICTED" if is_access_restricted else "JS_REQUIRED_OR_SPARSE_CONTENT"

        # Verify company if available
        company_match = engine.company_verifier.verify_company(
            query_name=resolved_company,
            cin=payload.cin,
            db=db,
        )
        company_evidence = engine.company_verifier.to_evidence_item(company_match)
        company_summary = engine.company_verifier.to_summary_schema(company_match)

        evidence_items: list[EvidenceItem] = []
        safe_actions: list[str] = []
        limitations: list[str] = [
            "Technical domain checks evaluate email and DNS infrastructure; they do not guarantee authorization of specific individuals.",
            "MCA-21 registration and DPIIT recognition confirm entity existence only, but do not authenticate specific recruiters or job postings.",
        ]

        if is_access_restricted:
            warning = (
                f"Web server returned HTTP {fetch_result.status_code} bot protection / WAF access restriction. "
                "Full job text could not be extracted automatically. This does NOT indicate fraud."
            )
            evidence_items.append(
                EvidenceItem(
                    evidence_type="access_restriction",
                    source_name=f"HTTP Fetcher (HTTP {fetch_result.status_code})",
                    status="INSUFFICIENT_EVIDENCE",
                    confidence=1.0,
                    summary=(
                        f"Destination server returned HTTP {fetch_result.status_code} "
                        f"({'Forbidden / Bot Protection' if fetch_result.status_code == 403 else 'Rate Limited / Too Many Requests'}). "
                        "The website's automated protection (e.g., Cloudflare, Akamai, or AWS WAF) blocked automated scraping. "
                        "This is standard security posture for major corporate portals and does NOT indicate fraud."
                    ),
                    limitations="Server-side bot protection prevents automated static HTML analysis.",
                    details={"status_code": fetch_result.status_code, "final_url": fetch_result.final_url},
                )
            )
            safe_actions.append(
                "Copy and paste the job posting description directly into the 'Job Text' analysis tab for complete text and ML fraud screening."
            )
            safe_actions.append(
                "Verify that you navigated to the employer's official careers portal directly rather than using links in unsolicited emails or chat messages."
            )
            limitations.insert(
                0,
                f"Remote web server blocked automated inspection via HTTP {fetch_result.status_code} protection. Risk score is withheld due to insufficient text evidence.",
            )
        else:
            warning = (
                "The fetched webpage contains minimal or no static text (< 20 characters). "
                "The page likely requires client-side JavaScript rendering or authentication. This does NOT indicate fraud."
            )
            evidence_items.append(
                EvidenceItem(
                    evidence_type="data_quality",
                    source_name="Static HTML Extractor",
                    status="INSUFFICIENT_EVIDENCE",
                    confidence=1.0,
                    summary=(
                        f"Extracted only {len(extracted.clean_text)} characters of readable static text. "
                        "Modern Single Page Applications (SPAs built with React, Angular, Vue, Workday, etc.) "
                        "render content dynamically using client-side JavaScript, which is safely disallowed for security reasons. "
                        "This does NOT indicate fraud."
                    ),
                    limitations="Static scraping cannot execute dynamic JavaScript or render client-side applicant tracking systems.",
                    details={"text_length": len(extracted.clean_text), "has_schema_job_posting": extracted.has_schema_job_posting},
                )
            )
            safe_actions.append(
                "Open this job posting URL in your web browser, copy the visible text, and paste it into the 'Job Text' tab for analysis."
            )
            safe_actions.append(
                "Verify that the careers page domain belongs to the authentic corporate employer."
            )
            limitations.insert(
                0,
                "Static HTML analysis could not extract vacancy details because the page requires client-side JavaScript rendering.",
            )

        # Lookalike warning
        if domain_result.lookalike_flags.get("is_lookalike"):
            target_legit = domain_result.lookalike_flags.get("matched_legitimate_domain", "verified company domain")
            evidence_items.append(
                EvidenceItem(
                    evidence_type="domain_lookalike_warning",
                    source_name=f"Lookalike Detector: {domain_result.domain}",
                    status="DETECTED",
                    confidence=domain_result.lookalike_flags.get("confidence", 0.85),
                    summary=domain_result.lookalike_flags.get(
                        "warning",
                        f"Domain '{domain_result.domain}' mimics legitimate corporate domain '{target_legit}'.",
                    ),
                    limitations="Lookalike flags indicate textual resemblance to verified company domains and warrant manual confirmation.",
                    details=domain_result.lookalike_flags,
                )
            )
            safe_actions.insert(0, f"Verify whether '{domain_result.domain}' is the authentic corporate domain for '{target_legit}'.")

        # Domain technical auth evidence
        evidence_items.append(
            EvidenceItem(
                evidence_type="domain_technical_auth",
                source_name=f"Domain Security: {domain_result.domain}",
                status="DETECTED" if domain_result.dns_status == "PASS" else "INSUFFICIENT_EVIDENCE",
                confidence=1.0,
                summary=(
                    f"Domain '{domain_result.domain}' evaluated: DNS {domain_result.dns_status}, "
                    f"MX {domain_result.mx_status}, SPF {domain_result.spf_status}, DMARC {domain_result.dmarc_status}."
                ),
                limitations="Email authentication parameters indicate sender security posture, not employment vacancy authenticity.",
                details={
                    "dns_status": domain_result.dns_status,
                    "mx_status": domain_result.mx_status,
                    "spf_status": domain_result.spf_status,
                    "dkim_status": domain_result.dkim_status,
                    "dmarc_status": domain_result.dmarc_status,
                },
            )
        )

        # Company verification evidence
        evidence_items.append(company_evidence)

        relevance_result = validate_job_url(
            clean_text=extracted.clean_text,
            title=extracted.title,
            status_code=fetch_result.status_code,
            url=fetch_result.final_url,
        )

        # Build response
        url_response = JobUrlAnalysisResponse(
            report_id=report_id,
            timestamp=now,
            risk_score=None,
            risk_category="INSUFFICIENT_EVIDENCE",
            warning=warning,
            provisional_thresholds=thresholds_doc,
            evidence=evidence_items,
            ml_analysis=None,
            company_verification=company_summary,
            recruiter_checks=RecruiterCheckSummary(
                status=page_outcome,
                detected_emails=extracted.detected_emails,
                summary=f"Page outcome: {page_outcome}. Extracted contact emails if present.",
            ),
            community_summary=CommunitySummary(),
            recommended_safe_actions=safe_actions,
            limitations=limitations,
            disclaimer=(
                "JobShield AI provides informational risk assessments based on technical domain checks "
                "and static text heuristics. It does not provide legal advice or definitive determinations of fraud."
            ),
            is_job_related=False,
            relevance=relevance_result,
            job_url=payload.url,
            extracted_title=extracted.title,
            extracted_company=resolved_company,
            domain_check=domain_summary,
            page_type=page_outcome,
            fetch_status_code=fetch_result.status_code,
            fetched_at=now,
        )

        # Persist scan records
        raw_bytes = (extracted.clean_text or payload.url).encode("utf-8")
        text_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        try:
            persist_scan_records(
                db=db,
                result=url_response,
                text_sha256=text_sha256,
                input_type="job_url",
                input_reference=payload.url,
                user_id=current_user.id if current_user else None,
            )
        except DatabasePersistenceError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database persistence failed. Scan record could not be saved.",
            )

        logger.info(
            "Completed partial job-url scan [%s, report_id=%s, domain=%s]",
            page_outcome,
            url_response.report_id,
            domain_result.domain,
        )
        return url_response

    # 5.5 Validate Job Relevance of Extracted Webpage Content
    relevance_result = validate_job_url(
        clean_text=extracted.clean_text,
        title=extracted.title,
        status_code=fetch_result.status_code,
        url=fetch_result.final_url,
        page_type=extracted.page_type,
    )
    if relevance_result.status != "VALID":
        logger.info(
            "Rejected non-job URL content [status=%s, reason_code=%s]",
            relevance_result.status,
            relevance_result.reason_code,
        )
        return JobUrlAnalysisResponse(
            report_id=report_id,
            timestamp=now,
            risk_score=None,
            risk_category="INVALID_INPUT" if relevance_result.status == "INVALID" else "UNCERTAIN",
            warning=relevance_result.user_message,
            provisional_thresholds=thresholds_doc,
            evidence=[],
            ml_analysis=None,
            company_verification=CompanyVerificationSummary(
                status="UNVERIFIED",
                summary="Company entity verification skipped for non-job URL.",
            ),
            recruiter_checks=RecruiterCheckSummary(
                status="SKIPPED",
                summary="Recruiter contact checks skipped for non-job URL.",
            ),
            community_summary=CommunitySummary(),
            recommended_safe_actions=[
                "Submit a link to an active job vacancy, employment opening, or careers portal."
            ],
            limitations=[
                "The fetched webpage does not appear to be an employment posting or vacancy announcement."
            ],
            is_job_related=False,
            relevance=relevance_result,
            job_url=payload.url,
            extracted_title=extracted.title,
            extracted_company=resolved_company,
            domain_check=domain_summary,
            page_type="INVALID_INPUT",
            fetch_status_code=fetch_result.status_code,
            fetched_at=now,
        )

    # 6. Execute Risk Engine Pipeline for pages with sufficient static text
    try:
        base_result = engine.analyze_job_text(
            extracted.clean_text,
            company_name=resolved_company,
            cin=payload.cin,
            db=db,
        )
    except MLServiceError as exc:
        logger.error("ML service failure during URL analysis: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML inference service is currently unavailable. Analysis cannot be completed without required ML component.",
        )

    # 7. Augment Evidence with Domain Security & Lookalike Findings
    evidence_items = list(base_result.evidence)
    safe_actions = list(base_result.recommended_safe_actions)
    limitations = list(base_result.limitations)
    warning = base_result.warning

    # Handle CAREERS_HOMEPAGE classification
    page_type = extracted.page_type  # "CAREERS_HOMEPAGE" or "JOB_POSTING"
    if page_type == "CAREERS_HOMEPAGE":
        careers_notice = EvidenceItem(
            evidence_type="careers_homepage_notice",
            source_name="Page Type Classifier",
            status="DETECTED",
            confidence=1.0,
            summary=(
                "This URL appears to be a general corporate careers portal or job search landing page, "
                "rather than a specific, individual job vacancy posting."
            ),
            limitations=(
                "Corroborating a legitimate corporate careers portal does NOT prove that an unverified "
                "job offer, interview invite, or communication received via email/messaging is genuine."
            ),
            details={
                "page_type": "CAREERS_HOMEPAGE",
                "has_schema_job_posting": extracted.has_schema_job_posting,
            },
        )
        evidence_items.insert(0, careers_notice)
        safe_actions.insert(0, "Search for the specific Job ID or Requisition Number directly within this official careers portal.")
        safe_actions.insert(1, "Do not accept job offers or pay fees based on unverified messages that merely link to this general company careers portal.")
        if not warning:
            warning = "Note: Analyzed page is a general corporate careers landing page, not a specific job vacancy posting."

    # Lookalike warning
    if domain_result.lookalike_flags.get("is_lookalike"):
        target_legit = domain_result.lookalike_flags.get("matched_legitimate_domain", "verified company domain")
        evidence_items.append(
            EvidenceItem(
                evidence_type="domain_lookalike_warning",
                source_name=f"Lookalike Detector: {domain_result.domain}",
                status="DETECTED",
                confidence=domain_result.lookalike_flags.get("confidence", 0.85),
                summary=domain_result.lookalike_flags.get(
                    "warning",
                    f"Domain '{domain_result.domain}' mimics legitimate corporate domain '{target_legit}'.",
                ),
                limitations="Lookalike flags indicate textual resemblance to verified company domains and warrant manual confirmation.",
                details=domain_result.lookalike_flags,
            )
        )
        safe_actions.insert(
            0,
            f"Verify whether '{domain_result.domain}' is the authentic corporate domain for '{target_legit}'.",
        )
        if not warning:
            warning = f"Caution: The job URL domain '{domain_result.domain}' closely mimics verified domain '{target_legit}'."

    # Domain Technical Auth Evidence
    evidence_items.append(
        EvidenceItem(
            evidence_type="domain_technical_auth",
            source_name=f"Domain Security: {domain_result.domain}",
            status="DETECTED" if domain_result.dns_status == "PASS" else "INSUFFICIENT_EVIDENCE",
            confidence=1.0,
            summary=(
                f"Domain '{domain_result.domain}' evaluated: DNS {domain_result.dns_status}, "
                f"MX {domain_result.mx_status}, SPF {domain_result.spf_status}, DMARC {domain_result.dmarc_status}."
            ),
            limitations="Email authentication parameters indicate sender security posture, not employment vacancy authenticity.",
            details={
                "dns_status": domain_result.dns_status,
                "mx_status": domain_result.mx_status,
                "spf_status": domain_result.spf_status,
                "dkim_status": domain_result.dkim_status,
                "dmarc_status": domain_result.dmarc_status,
            },
        )
    )

    limitations.append(
        "Job URL analysis processes static HTML; pages that rely on dynamic client-side JavaScript rendering may omit content."
    )

    # 8. Merge Extracted Contact Emails
    recruiter_checks = base_result.recruiter_checks
    if extracted.detected_emails:
        all_emails = list(dict.fromkeys(recruiter_checks.detected_emails + extracted.detected_emails))
        recruiter_checks = RecruiterCheckSummary(
            status="TEXT_AND_URL_EXTRACTED",
            detected_emails=all_emails,
            free_email_detected=recruiter_checks.free_email_detected,
            summary="Contact emails extracted from job text and webpage source.",
        )

    # 9. Assemble JobUrlAnalysisResponse
    url_response = JobUrlAnalysisResponse(
        report_id=base_result.report_id,
        timestamp=base_result.timestamp,
        risk_score=base_result.risk_score,
        risk_category=base_result.risk_category,
        warning=warning,
        provisional_thresholds=base_result.provisional_thresholds,
        evidence=evidence_items,
        ml_analysis=base_result.ml_analysis,
        company_verification=base_result.company_verification,
        recruiter_checks=recruiter_checks,
        community_summary=base_result.community_summary,
        recommended_safe_actions=safe_actions,
        limitations=limitations,
        disclaimer=base_result.disclaimer,
        is_job_related=True,
        relevance=relevance_result,
        job_url=payload.url,
        extracted_title=extracted.title,
        extracted_company=resolved_company,
        domain_check=domain_summary,
        page_type=page_type,
        fetch_status_code=fetch_result.status_code,
        fetched_at=datetime.now(timezone.utc),
    )

    # 9.5 Evaluate Duplicate & Impersonation Detection (Feature F5)
    try:
        from app.services.duplicate_detector import analyze_duplicate_job
        dup_summary = analyze_duplicate_job(
            text=extracted.clean_text,
            title=extracted.title,
            company_name=resolved_company,
            cin=payload.cin,
            source_url=payload.url,
            location=extracted.location,
            db=db,
        )
        url_response.duplicate_analysis = dup_summary
        if dup_summary and dup_summary.status == "POTENTIAL_SUSPICIOUS_COPY":
            url_response.evidence.append(
                EvidenceItem(
                    evidence_type="duplicate_impersonation_signal",
                    source_name="Duplicate & Impersonation Engine",
                    status="SUSPICIOUS_COPY",
                    confidence=0.85,
                    summary=dup_summary.summary,
                    details={
                        "highest_similarity": dup_summary.highest_similarity_score,
                        "matches_count": dup_summary.total_matches_found,
                        "impersonation_warning": dup_summary.impersonation_warning,
                    },
                )
            )
            if not url_response.warning and dup_summary.impersonation_warning:
                url_response.warning = f"Impersonation Notice: {dup_summary.impersonation_warning}"
    except Exception as exc:
        logger.debug("Duplicate analysis during job-url scan skipped: %s", exc)

    # 10. Persist Scan Records
    raw_bytes = extracted.clean_text.encode("utf-8")
    text_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    try:
        persist_scan_records(
            db=db,
            result=url_response,
            text_sha256=text_sha256,
            input_type="job_url",
            input_reference=payload.url,
            user_id=current_user.id if current_user else None,
        )
    except DatabasePersistenceError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database persistence failed. Scan record could not be saved.",
        )

    logger.info(
        "Completed job-url scan [page_type=%s, report_id=%s, domain=%s, risk_category=%s, risk_score=%s]",
        url_response.page_type,
        url_response.report_id,
        domain_result.domain,
        url_response.risk_category,
        url_response.risk_score,
    )

    return url_response


@router.post(
    "/recruiter-email",
    response_model=RecruiterEmailAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze Recruiter Email & Communication",
    description=(
        "Safely analyzes a recruiter email address and optional recruitment message for fraud patterns. "
        "Performs technical domain security verification (DNS, MX, SPF, DMARC, DKIM), "
        "corroborates claimed company entity existence via official MCA-21/DPIIT registries, "
        "detects lookalike domains and free webmail usage, and evaluates message heuristics. "
        "Strictly privacy-preserving: masks email addresses and never probes mailboxes via SMTP."
    ),
)
async def analyze_recruiter_email_endpoint(
    payload: RecruiterEmailAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> RecruiterEmailAnalysisResponse:
    logger.info("Received recruiter-email scan request")
    relevance_result = validate_recruiter_email(email=payload.email, message_text=payload.message_text)
    if payload.message_text and relevance_result.status != "VALID":
        logger.info(
            "Rejected non-job recruiter message [status=%s, reason_code=%s]",
            relevance_result.status,
            relevance_result.reason_code,
        )
        report_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        thresholds_doc = ProvisionalThresholds(
            version=settings.RISK_THRESHOLD_VERSION,
            ranges=get_provisional_threshold_ranges(),
        )
        from app.services.recruiter_checker import mask_email
        masked = mask_email(payload.email)
        _, domain = payload.email.split("@", 1)
        domain = domain.strip().lower()
        return RecruiterEmailAnalysisResponse(
            report_id=report_id,
            timestamp=now,
            risk_score=None,
            risk_category="INVALID_INPUT" if relevance_result.status == "INVALID" else "UNCERTAIN",
            warning=relevance_result.user_message,
            provisional_thresholds=thresholds_doc,
            evidence=[],
            ml_analysis=None,
            company_verification=CompanyVerificationSummary(
                status="UNVERIFIED",
                summary="Company entity verification skipped for non-job message input.",
            ),
            recruiter_checks=RecruiterCheckSummary(
                status="SKIPPED",
                summary="Recruiter contact checks skipped for non-job message input.",
            ),
            community_summary=CommunitySummary(),
            recommended_safe_actions=[
                "Provide an authentic job description, vacancy announcement, or recruitment outreach message."
            ],
            limitations=[
                "The submitted message text is not related to recruitment or employment."
            ],
            is_job_related=False,
            relevance=relevance_result,
            email_masked=masked,
            domain=domain,
            email_status="IDENTITY_UNVERIFIED",
            is_free_email=False,
            domain_check=None,
            extracted_title=None,
            extracted_company=payload.company_name,
        )

    try:
        response = verify_recruiter_email(
            email=payload.email,
            company_name=payload.company_name,
            cin=payload.cin,
            message_text=payload.message_text,
            db=db,
        )
        response.is_job_related = relevance_result.is_job_related
        response.relevance = relevance_result
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Persist in scan_requests and verification_evidence
    email_hash_val = hash_email(payload.email)
    text_sha256 = hashlib.sha256((payload.message_text or payload.email).encode("utf-8")).hexdigest()
    try:
        persist_scan_records(
            db=db,
            result=response,
            text_sha256=text_sha256,
            input_type="recruiter_email",
            input_reference=f"email_hash:{email_hash_val}",
            user_id=current_user.id if current_user else None,
        )

        # Persist recruiter_email_scans audit record
        claimed_company_id = response.company_verification.company_id if response.company_verification else None
        recruiter_rec = RecruiterEmailScan(
            id=str(uuid.uuid4()),
            scan_id=response.report_id,
            claimed_company_id=int(claimed_company_id) if claimed_company_id and str(claimed_company_id).isdigit() else None,
            email_masked=response.email_masked,
            email_hash=email_hash_val,
            domain=response.domain,
            status=response.email_status,
        )
        db.add(recruiter_rec)
        db.commit()
    except DatabasePersistenceError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database persistence failed. Scan record could not be saved.",
        )
    except Exception as exc:
        db.rollback()
        logger.warning("Could not persist recruiter_email_scan record: %s", exc)

    logger.info(
        "Completed recruiter-email scan [report_id=%s, domain=%s, status=%s, risk_category=%s]",
        response.report_id,
        response.domain,
        response.email_status,
        response.risk_category,
    )

    return response


@router.post(
    "/offer-letter",
    response_model=OfferLetterAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze Offer Letter PDF",
    description=(
        "Safely analyzes an offer letter PDF using PyMuPDF and Tesseract OCR for recruitment fraud patterns. "
        "Enforces strict upload security, page limits, magic bytes validation, and resource timeouts. "
        "Extracts structured compensation, fee clauses, and employer claims, corroborating against MCA-21 "
        "company registry and domain intelligence. Strictly privacy-preserving: never logs document contents."
    ),
)
async def analyze_offer_letter_endpoint(
    file: UploadFile = File(..., description="Offer letter PDF document"),
    company_name: Optional[str] = Form(None, description="Optional claimed employer name"),
    cin: Optional[str] = Form(None, description="Optional Corporate Identification Number (CIN)"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> OfferLetterAnalysisResponse:
    # 1. Sanitize filename
    clean_filename = Path(file.filename or "offer_letter.pdf").name

    # 2. Read file bytes with size enforcement
    try:
        file_bytes = await file.read()
    except Exception as exc:
        logger.error("Error reading uploaded file: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read uploaded file payload.",
        ) from exc

    # 3. Process PDF & selective OCR
    try:
        doc = extract_text_and_ocr(
            file_bytes=file_bytes,
            file_name=clean_filename,
        )
    except OversizedFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except ExcessivePagesError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except EncryptedPDFError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except InvalidPDFError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except OCRTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc
    except PDFProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # 3.5 Validate Job Relevance of Offer Letter Document
    relevance_result = validate_offer_letter(text=doc.full_text, file_name=clean_filename)
    if relevance_result.status != "VALID":
        logger.info(
            "Rejected non-job offer letter [status=%s, reason_code=%s]",
            relevance_result.status,
            relevance_result.reason_code,
        )
        report_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        thresholds_doc = ProvisionalThresholds(
            version=settings.RISK_THRESHOLD_VERSION,
            ranges=get_provisional_threshold_ranges(),
        )
        return OfferLetterAnalysisResponse(
            report_id=report_id,
            timestamp=now,
            risk_score=None,
            risk_category="INVALID_INPUT" if relevance_result.status == "INVALID" else "UNCERTAIN",
            warning=relevance_result.user_message,
            provisional_thresholds=thresholds_doc,
            evidence=[],
            ml_analysis=None,
            company_verification=CompanyVerificationSummary(
                status="UNVERIFIED",
                summary="Company entity verification skipped for non-offer document.",
            ),
            recruiter_checks=RecruiterCheckSummary(
                status="SKIPPED",
                summary="Recruiter contact checks skipped for non-offer document.",
            ),
            community_summary=CommunitySummary(),
            recommended_safe_actions=[
                "Upload an official employment offer letter, appointment letter, or internship contract to evaluate recruitment fraud risks."
            ],
            limitations=[
                "Document does not contain employment offer terms. Risk assessment withheld."
            ],
            is_job_related=False,
            relevance=relevance_result,
            file_name=clean_filename,
            file_size_bytes=len(file_bytes),
            page_count=doc.page_count,
            is_scanned=doc.is_scanned,
            ocr_applied=doc.ocr_applied,
            ocr_engine=doc.ocr_engine,
            extracted_fields=OfferLetterExtractedData(),
            suspicious_indicators=[],
            domain_checks=[],
            summary=relevance_result.supporting_message,
        )

    # 4. Perform structured analysis & entity corroboration
    response = analyze_offer_letter(
        doc=doc,
        claimed_company_name=company_name,
        cin=cin,
        db=db,
    )
    response.is_job_related = True
    response.relevance = relevance_result

    # 5. Persist audit metadata
    try:
        persist_offer_letter_scan(
            db=db,
            response=response,
            file_hash=doc.file_hash,
            user_id=current_user.id if current_user else None,
        )
    except (DatabasePersistenceError, OfferPersistenceError) as exc:
        logger.error("Audit persistence failed for offer scan %s: %s", response.report_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database persistence failed. Scan record could not be saved.",
        ) from exc
    except Exception as exc:
        logger.error("Audit persistence failed for offer scan %s: %s", response.report_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database persistence failed. Scan record could not be saved.",
        ) from exc

    # PRIVACY ENFORCEMENT: Never log document body, text, or candidate personal names
    logger.info(
        "Completed offer-letter scan [report_id=%s, pages=%d, is_scanned=%s, ocr_applied=%s, risk_category=%s, risk_score=%.1f]",
        response.report_id,
        response.page_count,
        response.is_scanned,
        response.ocr_applied,
        response.risk_category,
        response.risk_score,
    )

    return response


