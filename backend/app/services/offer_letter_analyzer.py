"""Offer Letter Analysis and Verification Engine.

Conforms to Feature F7 & Sections 5, 6, 11 of PROJECT_SPECIFICATION.md:
- Extracts structured fields: employer, candidate (masked), role, salary, dates, contacts, fees, sensitive requests.
- Corroborates employer identity against official MCA-21 registry records.
- Verifies contact domains for lookalikes, free webmail abuse, and email authentication.
- Evaluates rule-based signals and composite recruitment fraud risk.
- Strictly privacy-preserving: masks PII and never logs raw extracted text.
"""

from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse
import uuid

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.offer import OfferLetterScan
from app.models.prediction import PredictionHistory
from app.models.scan import ScanRequest
from app.models.verification import VerificationEvidence


class DatabasePersistenceError(Exception):
    """Raised when offer scan records cannot be saved to the database."""
    pass
from app.schemas.analysis import (
    CompanyVerificationSummary,
    DomainCheckSummary,
    EvidenceItem,
    MLAnalysisResult,
    ProvisionalThresholds,
)
from app.schemas.offer import (
    ExtractedFeeDemand,
    ExtractedFieldItem,
    ExtractedSensitiveRequest,
    OfferLetterAnalysisResponse,
    OfferLetterExtractedData,
)
from app.services.domain_checker import (
    WELL_KNOWN_LEGITIMATE_DOMAINS,
    check_domain_security,
    detect_lookalikes,
    extract_domain_from_url_or_host,
)
from app.services.pdf_extractor import ExtractedDocument
from app.services.recruiter_checker import (
    domain_matches_company,
    is_free_webmail_domain,
    mask_email,
)
from app.services.risk_engine import get_provisional_threshold_ranges
from app.verification.company_verifier import CompanyVerifier

logger = logging.getLogger("jobshield.services.offer_analyzer")


def mask_person_name(name: str) -> str:
    """Masks personal candidate names to preserve privacy in audit logs and outputs."""
    parts = name.strip().split()
    if not parts:
        return ""
    masked_parts = []
    for part in parts:
        if len(part) <= 2:
            masked_parts.append(f"{part[0]}*")
        else:
            masked_parts.append(f"{part[0]}{'*' * (len(part) - 1)}")
    return " ".join(masked_parts)


def mask_phone_number(phone: str) -> str:
    """Masks middle digits of contact phone numbers."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) >= 10:
        return f"{digits[:2]}{'*' * (len(digits) - 6)}{digits[-4:]}"
    return f"{phone[:3]}***{phone[-2:]}" if len(phone) > 5 else "***"


# Regex Patterns for Offer Letter Field Extraction
RE_COMPANY_PREFIX = re.compile(
    r"(?:company|employer|organization|corporate\s+entity|from|on\s+behalf\s+of)[:\s]+([A-Z][A-Za-z0-9&.,\s-]{2,60}(?:Pvt\.?|Ltd\.?|Limited|LLP|Inc\.?|Corp\.?|Solutions|Technologies|Infotech|Corporation|Enterprises?|Services?))",
    re.IGNORECASE,
)

RE_CORPORATE_SUFFIX = re.compile(
    r"\b([A-Z][A-Za-z0-9&.,\s-]{2,50}\s+(?:Private\s+Limited|Pvt\.?\s*Ltd\.?|Limited|LLP|Inc\.?|Corp\.?|Corporation))\b",
)

RE_CANDIDATE = re.compile(
    r"(?:dear|candidate(?:\s+name)?|offered\s+to|name\s+of\s+candidate|mr\.|ms\.|mrs\.)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
    re.IGNORECASE,
)

RE_JOB_TITLE = re.compile(
    r"(?:position|designation|role|job\s+title|offered\s+the\s+position\s+of|offered\s+the\s+role\s+of)[:\s]+([A-Za-z0-9/& -]{3,60})",
    re.IGNORECASE,
)

RE_SALARY = re.compile(
    r"(?:ctc|gross\s+salary|salary|compensation|remuneration|stipend|package)[:\s]*([^\n;]{3,60})|((?:\$|₹|rs\.?|inr|usd|eur|gbp|£|€)\s*[0-9,]+(?:\s*(?:lakhs?|lpa|per\s+annum|p\.a\.|per\s+month|monthly|\/-\s*))?)",
    re.IGNORECASE,
)

RE_OFFER_DATE = re.compile(
    r"(?:offer\s+date|date\s+of\s+offer|issued\s+on|date)[:\s]+([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4}|[A-Za-z]{3,9}\s+[0-9]{1,2},?\s+[0-9]{4}|[0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+[0-9]{4})",
    re.IGNORECASE,
)

RE_JOINING_DATE = re.compile(
    r"(?:joining\s+date|date\s+of\s+joining|start\s+date|commencement\s+date|reporting\s+date|report\s+on)[:\s]+([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4}|[A-Za-z]{3,9}\s+[0-9]{1,2},?\s+[0-9]{4}|[0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+[0-9]{4})",
    re.IGNORECASE,
)

RE_DEADLINE = re.compile(
    r"(?:accept(?:ance)?\s+(?:by|deadline|within)|valid\s+(?:until|till)|respond\s+by|offer\s+expires)[:\s]+([^\n.,;]+)",
    re.IGNORECASE,
)

RE_EMAILS = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
RE_PHONES = re.compile(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\+91[-.\s]?[6-9]\d{9}")
RE_URLS = re.compile(r"https?://[^\s<>\"']+|www\.[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

# Specific Fee & Deposit Demand Patterns (Definitive Fraud Signals)
FEE_PATTERNS = [
    ("SECURITY_DEPOSIT", re.compile(r"(?:refundable\s+)?security\s+deposit", re.IGNORECASE)),
    ("TRAINING_FEE", re.compile(r"(?:training|orientation|induction)\s+(?:fee|charges|deposit|cost)", re.IGNORECASE)),
    ("REGISTRATION_FEE", re.compile(r"(?:registration|processing|application|enrolment)\s+(?:fee|charges|cost)", re.IGNORECASE)),
    ("LAPTOP_FEE", re.compile(r"(?:laptop|hardware|equipment|device)\s+(?:deposit|fee|charge|security)", re.IGNORECASE)),
    ("BACKGROUND_CHECK_FEE", re.compile(r"(?:background|verification|screening|document)\s+(?:fee|charges|cost)", re.IGNORECASE)),
    ("UNIFORM_FEE", re.compile(r"(?:uniform|id\s*card|badge)\s+(?:fee|charges|cost)", re.IGNORECASE)),
    ("UPFRONT_PAYMENT", re.compile(r"(?:pay|deposit|transfer|remit)\s+(?:an?\s+upfront|before\s+joining|prior\s+to\s+shipping)", re.IGNORECASE)),
]

# Sensitive Information Demands (High Risk)
SENSITIVE_PATTERNS = [
    ("PASSWORD_OR_OTP", re.compile(r"\b(?:otp|one[- ]time[- ]password|net[- ]banking\s+password|login\s+credentials|atm\s+pin)\b", re.IGNORECASE)),
    ("BANK_CREDENTIALS", re.compile(r"\b(?:credit\s+card\s+cvv|card\s+expiry|debit\s+card\s+pin|bank\s+account\s+password)\b", re.IGNORECASE)),
    ("ORIGINAL_CERTIFICATES", re.compile(r"\b(?:submit\s+original|surrender\s+original|retain\s+original)\s+(?:certificate|degree|mark\s*sheet|passport)", re.IGNORECASE)),
    ("GOVERNMENT_ID_DOCS", re.compile(r"\b(?:send\s+aadhaar\s+card|send\s+pan\s+card|passport\s+copy\s+for\s+processing)\b", re.IGNORECASE)),
]


def extract_offer_letter_data(doc: ExtractedDocument) -> OfferLetterExtractedData:
    """Extracts structured fields, fee demands, and contact information across all pages."""
    data = OfferLetterExtractedData()
    total_chars = 0

    seen_emails: Set[str] = set()
    seen_phones: Set[str] = set()
    seen_domains: Set[str] = set()

    for page_num in sorted(doc.pages_text.keys()):
        text = doc.pages_text[page_num]
        total_chars += len(text)

        lines = [line.strip() for line in text.split("\n") if line.strip()]

        # 1. Company Name extraction (primarily page 1)
        if not data.company_name and page_num <= 2:
            m_comp = RE_COMPANY_PREFIX.search(text)
            if m_comp:
                val = m_comp.group(1).strip()
                data.company_name = ExtractedFieldItem(
                    value=val,
                    page=page_num,
                    snippet=text[max(0, m_comp.start() - 20) : min(len(text), m_comp.end() + 20)].strip(),
                    is_present=True,
                )
            else:
                # Look for corporate suffixes in top 12 lines
                for line in lines[:12]:
                    m_suf = RE_CORPORATE_SUFFIX.search(line)
                    if m_suf:
                        val = m_suf.group(1).strip()
                        data.company_name = ExtractedFieldItem(
                            value=val,
                            page=page_num,
                            snippet=line,
                            is_present=True,
                        )
                        break

        # 2. Candidate Name extraction
        if not data.candidate_name and page_num <= 2:
            m_cand = RE_CANDIDATE.search(text)
            if m_cand:
                raw_name = m_cand.group(1).strip()
                data.candidate_name = ExtractedFieldItem(
                    value=mask_person_name(raw_name),
                    page=page_num,
                    snippet=text[max(0, m_cand.start() - 10) : min(len(text), m_cand.end() + 10)].strip(),
                    is_present=True,
                )

        # 3. Job Title extraction
        if not data.job_title:
            m_title = RE_JOB_TITLE.search(text)
            if m_title:
                val = m_title.group(1).strip()
                data.job_title = ExtractedFieldItem(
                    value=val,
                    page=page_num,
                    snippet=text[max(0, m_title.start() - 15) : min(len(text), m_title.end() + 15)].strip(),
                    is_present=True,
                )

        # 4. Salary & Compensation
        if not data.salary_compensation:
            m_sal = RE_SALARY.search(text)
            if m_sal:
                val = (m_sal.group(1) or m_sal.group(2) or "").strip()
                if val:
                    data.salary_compensation = ExtractedFieldItem(
                        value=val,
                        page=page_num,
                        snippet=text[max(0, m_sal.start() - 20) : min(len(text), m_sal.end() + 20)].strip(),
                        is_present=True,
                    )

        # 5. Dates
        if not data.offer_date:
            m_od = RE_OFFER_DATE.search(text)
            if m_od:
                data.offer_date = ExtractedFieldItem(
                    value=m_od.group(1).strip(),
                    page=page_num,
                    snippet=m_od.group(0),
                    is_present=True,
                )

        if not data.joining_date:
            m_jd = RE_JOINING_DATE.search(text)
            if m_jd:
                data.joining_date = ExtractedFieldItem(
                    value=m_jd.group(1).strip(),
                    page=page_num,
                    snippet=m_jd.group(0),
                    is_present=True,
                )

        if not data.deadline_date:
            m_dd = RE_DEADLINE.search(text)
            if m_dd:
                data.deadline_date = ExtractedFieldItem(
                    value=m_dd.group(1).strip(),
                    page=page_num,
                    snippet=m_dd.group(0),
                    is_present=True,
                )

        # 6. Emails and Phone Numbers
        emails = RE_EMAILS.findall(text)
        for em in emails:
            clean_em = em.lower().rstrip(".,;")
            if clean_em not in seen_emails:
                seen_emails.add(clean_em)
                data.recruiter_contacts.append(mask_email(clean_em))
                # Track domain
                dom = clean_em.split("@")[-1]
                seen_domains.add(dom)

        phones = RE_PHONES.findall(text)
        for ph in phones:
            clean_ph = ph.strip().rstrip(".,;")
            if len(clean_ph) >= 10 and clean_ph not in seen_phones:
                seen_phones.add(clean_ph)
                data.recruiter_contacts.append(mask_phone_number(clean_ph))

        # 7. URLs and Domains
        urls = RE_URLS.findall(text)
        for u in urls:
            dom = extract_domain_from_url_or_host(u)
            if dom and dom not in seen_domains:
                seen_domains.add(dom)

        # 8. Fee and Deposit Demands (Red Flag Detection)
        for cat, pat in FEE_PATTERNS:
            for m in pat.finditer(text):
                clause = text[max(0, m.start() - 40) : min(len(text), m.end() + 60)].replace("\n", " ").strip()
                is_refundable = bool(re.search(r"refundable", clause, re.IGNORECASE))
                # Search for amount in vicinity
                m_amt = re.search(r"(?:\$|₹|rs\.?|inr|usd|eur|gbp|£|€)\s*[0-9,]+", clause, re.IGNORECASE)
                amt_str = m_amt.group(0) if m_amt else None

                data.fee_demands.append(
                    ExtractedFeeDemand(
                        category=cat,
                        amount=amt_str,
                        clause_text=clause,
                        page=page_num,
                        is_refundable_claimed=is_refundable,
                        warning=(
                            f"Payment or deposit demand identified ({cat}). Genuine employers "
                            "never require job candidates to pay upfront fees, registration deposits, "
                            "or hardware charges as a condition of employment."
                        ),
                    )
                )

        # 9. Sensitive Information Requests
        for cat, pat in SENSITIVE_PATTERNS:
            for m in pat.finditer(text):
                clause = text[max(0, m.start() - 30) : min(len(text), m.end() + 50)].replace("\n", " ").strip()
                data.sensitive_requests.append(
                    ExtractedSensitiveRequest(
                        request_type=cat,
                        clause_text=clause,
                        page=page_num,
                        warning=f"Request for sensitive personal or security credentials ({cat}) detected in document.",
                    )
                )

    data.domains_or_urls = sorted(seen_domains)
    data.has_fee_demand = len(data.fee_demands) > 0
    data.has_sensitive_request = len(data.sensitive_requests) > 0
    data.raw_character_count = total_chars
    return data


def analyze_offer_letter(
    doc: ExtractedDocument,
    claimed_company_name: Optional[str] = None,
    cin: Optional[str] = None,
    db: Optional[Session] = None,
) -> OfferLetterAnalysisResponse:
    """Performs comprehensive verification, corroboration, and fraud risk assessment on an offer letter."""
    # 1. Extract fields
    data = extract_offer_letter_data(doc)

    effective_company = (
        claimed_company_name.strip()
        if (claimed_company_name and claimed_company_name.strip())
        else (data.company_name.value if data.company_name else None)
    )

    evidence: List[EvidenceItem] = []
    suspicious_indicators: List[str] = []
    domain_checks: List[DomainCheckSummary] = []
    limitations: List[str] = list(doc.limitations)
    safe_actions: List[SafeActionItem] = []

    # 2. Corroborate Company Entity via MCA-21 Registry
    company_verification = CompanyVerificationSummary()
    if effective_company or cin:
        try:
            verifier = CompanyVerifier()
            match_res = verifier.verify_company(
                query_name=effective_company,
                cin=cin,
                db=db,
            )
            company_verification = verifier.to_summary_schema(match_res)

            if match_res.status == "NO_MATCH":
                evidence.append(
                    EvidenceItem(
                        evidence_type="company_verification",
                        source_name="Ministry of Corporate Affairs (MCA-21)",
                        status="NO_MATCH",
                        confidence=match_res.confidence,
                        summary=f"No corporate entity matching '{effective_company}' found in MCA official registry.",
                        limitations="Absence from MCA registry indicates no matching registered corporate entity was found. It does not solely prove fraud.",
                    )
                )
                suspicious_indicators.append("COMPANY_NOT_IN_MCA_REGISTRY")
            elif match_res.status in ("ACTIVE", "EXACT_LEGAL_NAME", "TRADE_NAME_EXACT"):
                evidence.append(
                    EvidenceItem(
                        evidence_type="company_verification",
                        source_name="Ministry of Corporate Affairs (MCA-21)",
                        status="MATCHED",
                        confidence=match_res.confidence,
                        summary=f"Employer verified against MCA registry: '{match_res.company.legal_name}' (CIN: {match_res.company.cin}, Status: {match_res.company.registry_status}).",
                    )
                )
            elif match_res.status == "AMBIGUOUS_MATCH":
                evidence.append(
                    EvidenceItem(
                        evidence_type="company_verification",
                        source_name="Ministry of Corporate Affairs (MCA-21)",
                        status="AMBIGUOUS",
                        confidence=match_res.confidence,
                        summary=f"Query '{effective_company}' matches multiple ({len(match_res.candidates)}) registered corporate entities.",
                    )
                )
        except Exception as exc:
            logger.debug("Company verification skipped during offer letter analysis: %s", exc)
            limitations.append("Official registry corroboration was unavailable during scan.")

    # 3. Check Contact Domains
    for domain in data.domains_or_urls:
        # A. Lookalike detection
        lookalike = detect_lookalikes(domain, WELL_KNOWN_LEGITIMATE_DOMAINS)
        if lookalike.get("is_lookalike"):
            suspicious_indicators.append("LOOKALIKE_DOMAIN_DETECTED")
            evidence.append(
                EvidenceItem(
                    evidence_type="domain_lookalike_spoof",
                    source_name="Domain Threat Intelligence",
                    status="FLAGGED",
                    confidence=lookalike.get("confidence", 0.85),
                    summary=lookalike.get("warning", f"Domain '{domain}' resembles a legitimate brand."),
                )
            )

        # B. Free webmail detection for enterprise employer
        is_free = is_free_webmail_domain(domain)
        if is_free and effective_company:
            suspicious_indicators.append("FREE_EMAIL_FOR_ENTERPRISE")
            evidence.append(
                EvidenceItem(
                    evidence_type="recruiter_email_provider",
                    source_name="Email Domain Analyzer",
                    status="SUSPICIOUS",
                    confidence=0.85,
                    summary=f"Contact domain '{domain}' is a free public webmail provider used for claimed corporate employer '{effective_company}'.",
                )
            )

        # C. Domain security check if db is provided
        if db is not None:
            try:
                dom_sec = check_domain_security(domain, db=db)
                domain_checks.append(dom_sec.to_summary())
            except Exception as e:
                logger.debug("Domain check for '%s' failed: %s", domain, e)

    # 4. Fee Demand Evaluation (Primary Fraud Vector)
    if data.has_fee_demand:
        suspicious_indicators.append("UPFRONT_FEE_DEMAND_DETECTED")
        for fee in data.fee_demands:
            evidence.append(
                EvidenceItem(
                    evidence_type="monetary_fee_demand",
                    source_name="Offer Letter Clause Extractor",
                    status="CRITICAL_FLAG",
                    confidence=0.98,
                    summary=f"Upfront payment clause identified on Page {fee.page} ({fee.category}): '{fee.clause_text}'",
                )
            )

    # 5. Sensitive Request Evaluation
    if data.has_sensitive_request:
        suspicious_indicators.append("SENSITIVE_CREDENTIAL_REQUEST")
        for req in data.sensitive_requests:
            evidence.append(
                EvidenceItem(
                    evidence_type="sensitive_credential_request",
                    source_name="Offer Letter Clause Extractor",
                    status="HIGH_RISK_FLAG",
                    confidence=0.95,
                    summary=f"Demands sensitive credentials on Page {req.page} ({req.request_type}): '{req.clause_text}'",
                )
            )

    # 6. Composite Risk Scoring & Category Determination
    # Rules: Upfront fee demands represent definitive fraudulent patterns under Indian and global labor norms
    base_score = 15.0
    if data.has_fee_demand:
        base_score = max(base_score, 88.0)
    if "LOOKALIKE_DOMAIN_DETECTED" in suspicious_indicators:
        base_score = max(base_score, 85.0)
    if "FREE_EMAIL_FOR_ENTERPRISE" in suspicious_indicators:
        base_score = max(base_score, 70.0)
    if data.has_sensitive_request:
        base_score = max(base_score, 80.0)
    if "COMPANY_NOT_IN_MCA_REGISTRY" in suspicious_indicators:
        base_score += 15.0

    risk_score = min(100.0, round(base_score, 1))

    if risk_score >= 75.0:
        risk_category = "HIGH"
        warning = "CRITICAL ALERT: This offer letter exhibits significant recruitment fraud indicators (upfront fees, lookalike domains, or sensitive credential requests)."
    elif risk_score >= 40.0:
        risk_category = "MODERATE"
        warning = "CAUTION: Unverified communication channels or identity discrepancies detected. Verify independently before proceeding."
    else:
        risk_category = "LOW"
        warning = None

    # Safe Actions
    safe_actions: List[str] = []
    if data.has_fee_demand:
        safe_actions.append(
            "Do Not Pay Any Fees: Legitimate employers never demand payment for application processing, security deposits, laptops, or training."
        )
    if "LOOKALIKE_DOMAIN_DETECTED" in suspicious_indicators:
        safe_actions.append(
            "Verify via Official Website: Navigate independently to the company's official corporate portal rather than following links in this document."
        )
    safe_actions.append(
        "Corroborate Legal Entity: Confirm official company CIN and incorporation status on the Ministry of Corporate Affairs (MCA-21) portal."
    )

    limitations.append(
        "Automated offer letter analysis provides evidence-backed risk indicators; it does not replace independent legal or corporate verification."
    )

    summary_text = (
        f"Offer letter analyzed across {doc.page_count} page(s). "
        f"Risk Category: {risk_category} (Score: {risk_score}/100). "
        f"{'Fee demands detected. ' if data.has_fee_demand else ''}"
        f"{'Contact domain lookalike detected. ' if 'LOOKALIKE_DOMAIN_DETECTED' in suspicious_indicators else ''}"
        f"{'Free webmail used for corporate claims. ' if 'FREE_EMAIL_FOR_ENTERPRISE' in suspicious_indicators else ''}"
    ).strip()

    report_id = str(uuid.uuid4())

    return OfferLetterAnalysisResponse(
        report_id=report_id,
        timestamp=datetime.now(timezone.utc),
        risk_score=risk_score,
        risk_category=risk_category,
        warning=warning,
        file_name=doc.file_name,
        file_size_bytes=doc.file_size_bytes,
        page_count=doc.page_count,
        is_scanned=doc.is_scanned,
        ocr_applied=doc.ocr_applied,
        ocr_engine=doc.ocr_engine,
        extracted_fields=data,
        suspicious_indicators=suspicious_indicators,
        evidence=evidence,
        company_verification=company_verification,
        domain_checks=domain_checks,
        recommended_safe_actions=safe_actions,
        limitations=limitations,
        summary=summary_text,
        provisional_thresholds=ProvisionalThresholds(
            version="offer_v1.0.0",
            ranges=get_provisional_threshold_ranges(),
        ),
        ml_analysis=MLAnalysisResult(
            model_version="offer_v1.0.0",
            primary_prediction="FRAUDULENT" if risk_score >= 75.0 else "LEGITIMATE",
            calibrated_prediction="FRAUDULENT" if risk_score >= 75.0 else "LEGITIMATE",
            calibrated_probability=risk_score / 100.0,
            uncalibrated_probability=risk_score / 100.0,
            calibration_method="heuristic_corroboration",
            decision_threshold=0.75,
            primary_threshold=0.75,
            calibrated_threshold=0.75,
            top_features=[],
        ),
    )


def persist_offer_letter_scan(
    db: Session,
    response: OfferLetterAnalysisResponse,
    file_hash: str,
    user_id: Optional[str] = None,
) -> None:
    """Persists audit record of offer letter scan into scan_requests, evidence, prediction_history, and offer_letter_scans."""
    try:
        now_ts = datetime.now(timezone.utc)
        # 1. Create ScanRequest with exact report_id
        scan_req = ScanRequest(
            id=response.report_id,
            user_id=user_id,
            input_type="offer_letter",
            input_reference=f"offer:{file_hash[:16]}",
            status="completed",
            completed_at=now_ts,
        )
        db.add(scan_req)
        # Crucial flush: guarantees scan_requests row exists in DB before child rows referencing scan_requests.id are inserted
        db.flush()

        # 2. Persist Evidence Items
        for item in response.evidence:
            evidence_record = VerificationEvidence(
                scan_id=response.report_id,
                evidence_type=item.evidence_type,
                source_name=item.source_name,
                source_url=getattr(item, "source_url", None),
                observed_at=now_ts,
                status=item.status,
                confidence=item.confidence,
                summary=item.summary,
                limitations=item.limitations,
                raw_metadata=item.details,
            )
            db.add(evidence_record)

        # 3. Persist Prediction History
        claimed_comp = (
            response.extracted_fields.company_name.value
            if response.extracted_fields.company_name
            else None
        )
        extracted_job_title = (
            response.extracted_fields.job_title.value
            if response.extracted_fields.job_title
            else None
        )
        primary_domain_check = (
            response.domain_checks[0].model_dump(mode="json")
            if response.domain_checks
            else None
        )

        explanation_payload = {
            "warning": response.warning,
            "recommended_safe_actions": response.recommended_safe_actions,
            "limitations": response.limitations,
            "disclaimer": response.disclaimer,
            "summary": response.summary,
            "extracted_title": extracted_job_title,
            "extracted_company": claimed_comp,
            "extracted_fields": response.extracted_fields.model_dump(mode="json"),
            "suspicious_indicators": response.suspicious_indicators,
            "company_verification": response.company_verification.model_dump(mode="json") if response.company_verification else None,
            "domain_checks": [d.model_dump(mode="json") for d in response.domain_checks] if response.domain_checks else [],
            "domain_check": primary_domain_check,
        }
        pred_record = PredictionHistory(
            scan_id=response.report_id,
            model_version=response.ml_analysis.model_version if response.ml_analysis else "offer_v1.0.0",
            predicted_class=response.ml_analysis.primary_prediction if response.ml_analysis else "UNVERIFIED",
            model_probability=response.ml_analysis.calibrated_probability if response.ml_analysis else None,
            risk_score=response.risk_score if response.risk_score is not None else -1.0,
            risk_category=response.risk_category,
            threshold_version=response.provisional_thresholds.version if response.provisional_thresholds else "offer_v1.0.0",
            explanation=explanation_payload,
        )
        db.add(pred_record)

        # 4. Create OfferLetterScan
        comp_id = response.company_verification.company_id if response.company_verification else None
        if comp_id is not None:
            # Verify company_id exists in database before foreign key assignment
            exists = db.query(Company.id).filter(Company.id == comp_id).scalar()
            if not exists:
                comp_id = None

        summary_dict = {
            "job_title": extracted_job_title,
            "salary": (
                response.extracted_fields.salary_compensation.value
                if response.extracted_fields.salary_compensation
                else None
            ),
            "fee_demands_count": len(response.extracted_fields.fee_demands),
            "domains": response.extracted_fields.domains_or_urls,
            "suspicious_indicators": response.suspicious_indicators,
        }

        offer_record = OfferLetterScan(
            scan_id=response.report_id,
            file_hash=file_hash,
            file_name=response.file_name,
            file_size_bytes=response.file_size_bytes,
            page_count=response.page_count,
            is_scanned=response.is_scanned,
            ocr_applied=response.ocr_applied,
            ocr_engine=response.ocr_engine,
            claimed_company_name=claimed_comp,
            company_id=comp_id,
            extracted_summary=summary_dict,
            risk_category=response.risk_category,
            risk_score=response.risk_score if response.risk_score is not None else 0.0,
            has_fee_demand=response.extracted_fields.has_fee_demand,
            has_sensitive_request=response.extracted_fields.has_sensitive_request,
        )
        db.add(offer_record)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(
            "Failed to persist offer letter scan audit record for report_id=%s: %s",
            response.report_id,
            exc,
            exc_info=True,
        )
        raise DatabasePersistenceError(
            f"Failed to persist offer scan audit record: {type(exc).__name__}"
        ) from exc
