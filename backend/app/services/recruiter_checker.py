"""Recruiter Email and Communication Verification Service.

Conforms to Section 6 (F3/F4) & Section 11 of PROJECT_SPECIFICATION.md:
- Technical domain verification (DNS, MX, SPF, DMARC, DKIM) via existing domain_checker
- Corroborates sender domain against official verified company records via existing CompanyVerifier
- Privacy-first: strictly masks email addresses and computes cryptographic SHA-256 hashes
- NEVER performs unsolicited SMTP probing or attempts mailbox existence tests
- Enforces clear limitations: a domain match NEVER proves individual sender identity
- Evaluates optional user-pasted recruitment communication text for heuristic fraud indicators
"""

from datetime import datetime, timezone
import hashlib
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.company import Company, CompanyDomain
from app.schemas.analysis import (
    CommunitySummary,
    DomainCheckSummary,
    EvidenceItem,
    MLAnalysisResult,
    ProvisionalThresholds,
    RecruiterCheckSummary,
    RecruiterEmailAnalysisResponse,
)
from app.services.domain_checker import (
    WELL_KNOWN_LEGITIMATE_DOMAINS,
    check_domain_security,
    extract_domain_from_url_or_host,
)
from app.services.ml_inference import get_ml_service
from app.services.risk_engine import (
    classify_risk_score,
    count_informative_words,
    get_provisional_threshold_ranges,
    get_risk_engine,
)
from app.services.rules import FREE_WEBMAIL_DOMAINS, run_all_rules
from app.verification.company_verifier import CompanyVerifier, VerificationStatus

logger = logging.getLogger("jobshield.verification.recruiter_checker")

EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9_.+-]+@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)$"
)


def validate_email_syntax(email: str) -> Tuple[bool, str, str]:
    """Validates email syntax strictly using regex without network or SMTP probes.

    PRIVACY & SAFETY: Never connects to SMTP port 25 or sends VRFY/RCPT commands.
    """
    trimmed = email.strip() if isinstance(email, str) else ""
    if not trimmed or len(trimmed) > 254:
        return False, "", ""

    match = EMAIL_REGEX.match(trimmed)
    if not match:
        return False, "", ""

    local_part, domain = trimmed.split("@", 1)
    if len(local_part) > 64 or not domain or "." not in domain:
        return False, "", ""

    return True, local_part, domain.lower().rstrip(".")


def mask_email(email: str) -> str:
    """Masks local-part of an email to protect privacy while preserving domain.

    Examples:
    - 'recruiter.john@tcs.com' -> 'r***n@tcs.com'
    - 'hr@infosys.com'         -> 'h*@infosys.com'
    - 'bob@company.com'        -> 'b*b@company.com'
    """
    trimmed = email.strip() if isinstance(email, str) else ""
    if "@" not in trimmed:
        return "***"

    local, domain = trimmed.split("@", 1)
    domain_clean = domain.strip().lower()

    if len(local) <= 1:
        masked_local = "*"
    elif len(local) == 2:
        masked_local = f"{local[0]}*"
    elif len(local) == 3:
        masked_local = f"{local[0]}*{local[-1]}"
    else:
        masked_local = f"{local[0]}***{local[-1]}"

    return f"{masked_local}@{domain_clean}"


def hash_email(email: str) -> str:
    """Computes deterministic SHA-256 digest of normalized email for audit/deduplication."""
    clean = email.strip().lower().encode("utf-8")
    return hashlib.sha256(clean).hexdigest()


def is_free_webmail_domain(domain: str) -> bool:
    """Checks whether the domain belongs to a known public/free webmail provider."""
    d = domain.strip().lower()
    return d in FREE_WEBMAIL_DOMAINS or any(d.endswith(f".{fwd}") for fwd in FREE_WEBMAIL_DOMAINS)


WELL_KNOWN_COMPANY_DOMAINS: Dict[str, List[str]] = {
    "tcs.com": ["tcs", "tata consultancy services", "tata consultancy", "tata"],
    "infosys.com": ["infosys"],
    "wipro.com": ["wipro"],
    "capgemini.com": ["capgemini"],
    "hcltech.com": ["hcl", "hcl tech", "hcl technologies"],
    "techmahindra.com": ["tech mahindra", "mahindra"],
    "accenture.com": ["accenture"],
    "cognizant.com": ["cognizant"],
    "google.com": ["google", "alphabet"],
    "microsoft.com": ["microsoft"],
    "amazon.com": ["amazon", "aws"],
    "apple.com": ["apple"],
    "ibm.com": ["ibm", "international business machines"],
    "meta.com": ["meta", "facebook"],
}


def domain_matches_company(
    domain: str,
    company_name: Optional[str],
    company_obj: Optional[Company],
    db: Optional[Session],
) -> bool:
    """Checks whether the domain aligns with official verified company records."""
    d = domain.strip().lower()

    # 1. Direct database lookup in company_domains table
    if db is not None and company_obj is not None:
        matched_cd = (
            db.query(CompanyDomain)
            .filter(
                CompanyDomain.company_id == company_obj.id,
                func.lower(CompanyDomain.domain) == d,
            )
            .first()
        )
        if matched_cd:
            return True

    # Combine company_name and legal_name if available for thorough checks
    names_to_check: List[str] = []
    if company_name:
        names_to_check.append(company_name.strip().lower())
    if company_obj and company_obj.legal_name:
        names_to_check.append(company_obj.legal_name.strip().lower())

    for cn_lower in names_to_check:
        # 2. Match against well-known legitimate domain and alias mappings
        for legit_domain, aliases in WELL_KNOWN_COMPANY_DOMAINS.items():
            if d == legit_domain or d.endswith(f".{legit_domain}"):
                if any(alias in cn_lower or cn_lower in alias for alias in aliases):
                    return True

        # 3. Check well-known domain stems
        for legit in WELL_KNOWN_LEGITIMATE_DOMAINS:
            stem = legit.split(".")[0]
            if stem in cn_lower or cn_lower in stem:
                if d == legit or d.endswith(f".{legit}"):
                    return True

        # 4. Acronym heuristic (e.g. "Tata Consultancy Services" -> "tcs")
        significant_words = [
            w
            for w in re.split(r"\W+", cn_lower)
            if w and w not in {"limited", "ltd", "private", "pvt", "llp", "corp", "corporation", "inc", "co"}
        ]
        if len(significant_words) >= 2:
            acronym = "".join(w[0] for w in significant_words if w)
            if acronym and (d == f"{acronym}.com" or d.startswith(f"{acronym}.") or d.split(".")[0] == acronym):
                return True

        # 5. Word stem heuristic (e.g. "wipro" in "wipro limited")
        words = [w for w in significant_words if len(w) > 3]
        for w in words:
            if w in d.split(".")[0] or d.split(".")[0] in w:
                return True

    return False


def verify_recruiter_email(
    email: str,
    company_name: Optional[str] = None,
    cin: Optional[str] = None,
    message_text: Optional[str] = None,
    db: Optional[Session] = None,
) -> RecruiterEmailAnalysisResponse:
    """Performs comprehensive recruiter email, domain security, entity, and message analysis."""
    is_valid, local_part, domain = validate_email_syntax(email)
    if not is_valid:
        raise ValueError(f"Invalid email address syntax: '{email}'")

    masked = mask_email(email)
    email_digest = hash_email(email)
    is_free = is_free_webmail_domain(domain)
    now = datetime.now(timezone.utc)
    report_id = str(uuid.uuid4())

    thresholds_doc = ProvisionalThresholds(
        version=settings.RISK_THRESHOLD_VERSION,
        ranges=get_provisional_threshold_ranges(),
    )

    # 1. Technical Domain Verification & Lookalike Detection (reused service)
    domain_result = check_domain_security(domain, db=db)
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

    # 2. Company Entity Verification (reused service)
    engine = get_risk_engine()
    company_match = engine.company_verifier.verify_company(
        query_name=company_name,
        cin=cin,
        db=db,
    )
    company_evidence = engine.company_verifier.to_evidence_item(company_match)
    company_summary = engine.company_verifier.to_summary_schema(company_match)

    # 3. Determine Email & Domain Status
    company_name_val = company_match.company.legal_name if company_match.company else (company_name or company_match.queried_name or "")
    is_lookalike = bool(domain_result.lookalike_flags and domain_result.lookalike_flags.get("is_lookalike"))
    is_matched_domain = domain_matches_company(
        domain=domain,
        company_name=company_name_val,
        company_obj=company_match.company,
        db=db,
    )

    if is_lookalike:
        email_status = "LOOKALIKE_WARNING"
    elif is_free:
        email_status = "FREE_EMAIL_PROVIDER"
    elif is_matched_domain:
        email_status = "DOMAIN_MATCH"
    elif company_name:
        email_status = "MISMATCH_DETECTED"
    else:
        email_status = "IDENTITY_UNVERIFIED"

    # 4. Evidence Accumulation
    evidence_items: List[EvidenceItem] = []
    safe_actions: List[str] = []
    limitations: List[str] = [
        "A domain match or passing email security record confirms domain infrastructure alignment only; it does NOT prove the sender's individual identity.",
        "Mailbox existence is never tested by sending probe emails, ensuring job seeker privacy and ethical server standards.",
        "MCA-21 registration and DPIIT recognition confirm entity existence only, but do not authenticate specific recruiters.",
    ]

    # Email Status Evidence Item
    if email_status == "FREE_EMAIL_PROVIDER":
        summary_msg = (
            f"Recruiter email uses a free public webmail provider ('@{domain}'). "
            + (
                f"Official hiring representatives for registered entities like '{company_name_val}' "
                "typically communicate via official corporate domains rather than free webmail."
                if company_name_val
                else "Recruiter is using a free public webmail service."
            )
        )
        evidence_items.append(
            EvidenceItem(
                evidence_type="recruiter_email_signal",
                source_name="Email Domain Analyzer",
                status="DETECTED",
                confidence=0.85 if company_name else 0.60,
                summary=summary_msg,
                limitations="Legitimate small businesses or independent recruiters occasionally use free webmail, but major corporations do not.",
                details={"domain": domain, "is_free_email": True, "masked_email": masked},
            )
        )
        safe_actions.append(
            "Request official correspondence from the employer's official corporate email domain."
        )
        safe_actions.append(
            "Cross-check open vacancies directly on the company's verified careers portal."
        )
    elif email_status == "LOOKALIKE_WARNING":
        target = domain_result.lookalike_flags.get("matched_legitimate_domain", "official corporate domain")
        evidence_items.append(
            EvidenceItem(
                evidence_type="domain_lookalike_warning",
                source_name=f"Lookalike Detector: {domain}",
                status="DETECTED",
                confidence=0.90,
                summary=f"Sender domain '@{domain}' closely mimics legitimate corporate domain '{target}'.",
                limitations="Lookalike flags indicate textual resemblance to verified domains and warrant manual confirmation.",
                details=domain_result.lookalike_flags,
            )
        )
        safe_actions.append(
            f"Do not respond to this email. Verify whether '@{domain}' is authentic compared to official '{target}'."
        )
    elif email_status == "DOMAIN_MATCH":
        evidence_items.append(
            EvidenceItem(
                evidence_type="recruiter_email_signal",
                source_name="Email Domain Analyzer",
                status="DETECTED",
                confidence=0.80,
                summary=(
                    f"Sender domain '@{domain}' matches the official domain of verified employer "
                    f"'{company_name_val}'."
                ),
                limitations="Domain match confirms domain ownership only; email spoofing or account compromise remains possible if SPF/DMARC fail.",
                details={"domain": domain, "matched_company": company_name_val},
            )
        )
        safe_actions.append(
            "Check for official digital signatures or verify the recruiter's profile on official corporate channels."
        )
    elif email_status == "MISMATCH_DETECTED":
        evidence_items.append(
            EvidenceItem(
                evidence_type="recruiter_email_signal",
                source_name="Email Domain Analyzer",
                status="DETECTED",
                confidence=0.75,
                summary=(
                    f"Sender domain '@{domain}' does not match the registered corporate domain for claimed employer "
                    f"'{company_name_val}'."
                ),
                limitations="Third-party recruitment agencies or staffing consultancies may legitimately recruit on behalf of clients.",
                details={"domain": domain, "claimed_company": company_name_val},
            )
        )
        safe_actions.append(
            f"Verify whether the sender is an authorized external recruiting agency for '{company_name_val}'."
        )
    else:  # IDENTITY_UNVERIFIED
        evidence_items.append(
            EvidenceItem(
                evidence_type="recruiter_email_signal",
                source_name="Email Domain Analyzer",
                status="INSUFFICIENT_EVIDENCE",
                confidence=0.50,
                summary=(
                    f"Sender domain '@{domain}' is active, but could not be correlated with a verified corporate entity."
                ),
                limitations="Unverified company identity does not inherently indicate fraud.",
                details={"domain": domain},
            )
        )
        safe_actions.append(
            "Request the recruiter's official company name and Corporate Identification Number (CIN) for verification."
        )

    # Domain Technical Auth Evidence
    evidence_items.append(
        EvidenceItem(
            evidence_type="domain_technical_auth",
            source_name=f"Domain Security: {domain}",
            status="DETECTED" if domain_result.dns_status == "PASS" else "INSUFFICIENT_EVIDENCE",
            confidence=1.0,
            summary=(
                f"Domain '@{domain}' evaluated: DNS {domain_result.dns_status}, "
                f"MX {domain_result.mx_status}, SPF {domain_result.spf_status}, DMARC {domain_result.dmarc_status}."
            ),
            limitations="Email authentication parameters indicate sender infrastructure security posture, not individual recruiter authorization.",
            details={
                "dns_status": domain_result.dns_status,
                "mx_status": domain_result.mx_status,
                "spf_status": domain_result.spf_status,
                "dkim_status": domain_result.dkim_status,
                "dmarc_status": domain_result.dmarc_status,
            },
        )
    )

    # Company Verification Evidence
    evidence_items.append(company_evidence)

    # 5. Message Content Evaluation (if user pasted communication text)
    ml_result: Optional[MLAnalysisResult] = None
    warning: Optional[str] = None
    extracted_title: Optional[str] = None

    if message_text and len(message_text.strip()) >= 20:
        clean_msg = message_text.strip()
        rule_evals, rule_score, rule_evidence, extracted_emails, free_email_in_body = run_all_rules(clean_msg)
        evidence_items.extend(rule_evidence)

        # Informative word count check for ML
        if count_informative_words(clean_msg) >= settings.MIN_INFORMATIVE_WORDS:
            ml_svc = get_ml_service()
            ml_result = ml_svc.analyze_text(clean_msg)
            ml_detected = ml_result.calibrated_prediction == "FRAUDULENT"
            evidence_items.append(
                EvidenceItem(
                    evidence_type="ml_prediction",
                    source_name=f"Baseline ML Classifier ({ml_result.model_version})",
                    status="DETECTED" if ml_detected else "NOT_DETECTED",
                    confidence=ml_result.calibrated_probability,
                    summary=(
                        f"Calibrated ML model estimated fraud probability at "
                        f"{ml_result.calibrated_probability * 100:.1f}% based on message wording."
                    ),
                    limitations="Reflects linguistic similarity to historical recruitment scam training data.",
                    details={
                        "model_version": ml_result.model_version,
                        "calibrated_prob": ml_result.calibrated_probability,
                    },
                )
            )

        # Composite score calculation incorporating message heuristics
        base_ml_score = (ml_result.calibrated_probability * 100.0) if ml_result else 20.0
        composite_score = (
            settings.RISK_SCORE_WEIGHT_ML * base_ml_score
            + settings.RISK_SCORE_WEIGHT_RULES * rule_score
        )

        # Escalate if free webmail is combined with upfront fees
        detected_rule_names = [r.rule_name for r in rule_evals if r.detected]
        if is_free and any("Upfront Fees" in r for r in detected_rule_names):
            composite_score = max(composite_score, 88.0)
            warning = "CRITICAL: Free webmail sender soliciting upfront fees or deposits. Do NOT transfer funds."
        elif is_lookalike:
            composite_score = max(composite_score, 85.0)
            warning = f"Caution: Sender domain '@{domain}' is a lookalike mimicking legitimate corporate infrastructure."
        elif is_free and company_name:
            composite_score = max(composite_score, 65.0)
            warning = f"Notice: Free webmail address claimed to represent registered company '{company_name}'."

        final_score = round(max(0.0, min(100.0, composite_score)), 1)
        risk_category = classify_risk_score(final_score)
    else:
        # No message text provided: composite risk derived purely from domain and entity posture
        if is_lookalike:
            final_score = 85.0
            risk_category = "CRITICAL"
            warning = f"Caution: Sender domain '@{domain}' mimics legitimate corporate infrastructure."
        elif is_free and company_name:
            final_score = 65.0
            risk_category = "HIGH"
            warning = f"Notice: Sender is using a free webmail address while claiming to represent '{company_name}'."
        elif is_free:
            final_score = 45.0
            risk_category = "MODERATE"
            warning = "Sender is using a free public webmail address. Verify employer credentials before engaging."
        elif email_status == "MISMATCH_DETECTED":
            final_score = 50.0
            risk_category = "MODERATE"
            warning = f"Sender domain '@{domain}' does not match official domain of '{company_name}'."
        elif email_status == "DOMAIN_MATCH":
            final_score = 15.0
            risk_category = "LOW"
        else:
            final_score = 25.0
            risk_category = "LOW"

        limitations.append(
            "No message text was submitted for linguistic analysis; risk score is based strictly on domain configuration and entity corroboration."
        )

    # General safe actions
    safe_actions.append(
        "NEVER pay or transfer money for interviews, application fees, uniforms, or laptop security deposits."
    )
    safe_actions.append(
        "Do not disclose sensitive banking credentials, OTPs, or identity documents before formal verified onboarding."
    )

    return RecruiterEmailAnalysisResponse(
        report_id=report_id,
        timestamp=now,
        risk_score=final_score,
        risk_category=risk_category,
        warning=warning,
        provisional_thresholds=thresholds_doc,
        evidence=evidence_items,
        ml_analysis=ml_result,
        company_verification=company_summary,
        recruiter_checks=RecruiterCheckSummary(
            status=email_status,
            detected_emails=[masked],
            free_email_detected=is_free,
            summary=f"Recruiter email: {masked} evaluated. Status: {email_status}.",
        ),
        community_summary=CommunitySummary(),
        recommended_safe_actions=list(dict.fromkeys(safe_actions)),
        limitations=limitations,
        disclaimer=(
            "JobShield AI provides informational risk assessments based on technical domain checks "
            "and text heuristics. It does NOT definitively verify individual identity or prove fraud."
        ),
        email_masked=masked,
        domain=domain,
        email_status=email_status,
        is_free_email=is_free,
        domain_check=domain_summary,
        extracted_title=extracted_title,
        extracted_company=company_name_val or None,
    )
