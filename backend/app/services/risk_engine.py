"""Composite Risk Engine for JobShield AI.

Implements Sections 4, 5 (F1, F2) and 10 of PROJECT_SPECIFICATION.md:
- Computes a documented, configurable 0-100 composite risk score.
- Keeps ML probability separate from the composite score.
- Returns 'INSUFFICIENT_EVIDENCE' when input text lacks substantive job details.
- Integrates sourced company verification (MCA-21 and DPIIT registries).
- Enforces strict mandate: NO_MATCH is never presented as fraud.
- Generates evidence breakdown, tailored safe actions, and limitations.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.analysis import (
    CompanyVerificationSummary,
    EvidenceItem,
    JobTextAnalysisResponse,
    MLAnalysisResult,
    ProvisionalThresholds,
    RecruiterCheckSummary,
    ThresholdRange,
)
from app.services.ml_inference import get_ml_service
from app.services.rules import run_all_rules
from app.verification.company_verifier import CompanyVerifier, VerificationStatus
from app.verification.extraction import extract_company_info

WORD_SPLIT_RE = re.compile(r"\b[A-Za-z0-9_-]{2,}\b")

# Common non-informative stop words for adequacy checks
COMMON_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "you", "are",
    "will", "have", "job", "hiring", "work", "needed", "looking", "apply",
}


def count_informative_words(text: str) -> int:
    """Counts meaningful distinct words to verify minimum evidence threshold."""
    tokens = [w.lower() for w in WORD_SPLIT_RE.findall(text)]
    informative = [w for w in tokens if w not in COMMON_STOPWORDS]
    return len(informative)


def get_provisional_threshold_ranges() -> List[ThresholdRange]:
    """Returns the active documented provisional threshold definitions."""
    return [
        ThresholdRange(
            min_score=0.0,
            max_score=settings.RISK_THRESHOLD_LOW - 0.01,
            category="LOW",
            description="Linguistic and rule indicators show low scam risk. Still verify company through official channels.",
        ),
        ThresholdRange(
            min_score=settings.RISK_THRESHOLD_LOW,
            max_score=settings.RISK_THRESHOLD_MODERATE - 0.01,
            category="MODERATE",
            description="Moderate risk detected (e.g. urgency, free webmail, or slight textual anomaly). Caution advised.",
        ),
        ThresholdRange(
            min_score=settings.RISK_THRESHOLD_MODERATE,
            max_score=settings.RISK_THRESHOLD_HIGH - 0.01,
            category="HIGH",
            description="High probability of recruitment fraud (e.g. upfront fee request, urgent payment, or sensitive details required).",
        ),
        ThresholdRange(
            min_score=settings.RISK_THRESHOLD_HIGH,
            max_score=100.0,
            category="CRITICAL",
            description="Compound critical fraud signals detected (direct fee solicitation, personal banking requests). Do not engage.",
        ),
    ]


def classify_risk_score(score: float) -> str:
    """Assigns category label according to provisional thresholds."""
    if score >= settings.RISK_THRESHOLD_HIGH:
        return "CRITICAL"
    if score >= settings.RISK_THRESHOLD_MODERATE:
        return "HIGH"
    if score >= settings.RISK_THRESHOLD_LOW:
        return "MODERATE"
    return "LOW"


def build_safe_actions(detected_signals: List[str], category: str) -> List[str]:
    """Provides prioritized, actionable next steps for job seekers."""
    actions = []
    has_fees = any("Fee" in s for s in detected_signals)
    has_contact = any("Contact" in s or "WhatsApp" in s or "Telegram" in s for s in detected_signals)
    has_sensitive = any("Sensitive" in s or "Bank" in s for s in detected_signals)

    if has_fees:
        actions.append("NEVER PAY or transfer funds for job offers, training, registration, uniforms, or laptop security deposits.")
    if has_sensitive:
        actions.append("Do not disclose bank account details, PAN card, Aadhaar, OTPs, or passwords before an official onboarding process.")
    if has_contact:
        actions.append("Insist on official corporate communication channels and verify the sender's domain independently.")

    actions.append("Check the employer's official careers portal directly rather than using links sent in unverified messages.")
    actions.append("Cross-check company registration on the Ministry of Corporate Affairs (MCA-21) portal.")
    return actions


def build_limitations() -> List[str]:
    """Documents active methodological and operational constraints."""
    return [
        "ML predictions are probabilistic estimates derived from historical text datasets; they are not legal findings of fraud.",
        "Scam operators frequently impersonate legitimate corporate brands using lookalike domains or stolen credentials.",
        "MCA-21 registration and DPIIT recognition confirm entity existence only, but do not authenticate specific recruiters or job postings.",
        "Rule heuristics evaluate explicit text patterns; sophisticated scams without obvious linguistic cues may evade heuristic detection.",
    ]


class RiskEngine:
    """Coordinates ML classification, heuristic rule evaluation, entity verification, and composite scoring."""

    def __init__(self):
        self.company_verifier = CompanyVerifier()

    @property
    def ml_service(self):
        return get_ml_service()

    def analyze_job_text(
        self,
        text: str,
        company_name: Optional[str] = None,
        cin: Optional[str] = None,
        db: Optional[Session] = None,
        explanation_method: str = "auto",
    ) -> JobTextAnalysisResponse:
        report_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        thresholds_doc = ProvisionalThresholds(
            version=settings.RISK_THRESHOLD_VERSION,
            ranges=get_provisional_threshold_ranges(),
        )

        # 1. Evidence Adequacy Check
        informative_word_count = count_informative_words(text)
        if informative_word_count < settings.MIN_INFORMATIVE_WORDS:
            return JobTextAnalysisResponse(
                report_id=report_id,
                timestamp=now,
                risk_score=None,
                risk_category="INSUFFICIENT_EVIDENCE",
                warning="Submitted text contains insufficient informative words for dependable fraud detection.",
                provisional_thresholds=thresholds_doc,
                evidence=[
                    EvidenceItem(
                        evidence_type="data_quality",
                        source_name="Input Adequacy Validator",
                        status="INSUFFICIENT_EVIDENCE",
                        confidence=1.0,
                        summary=f"Found only {informative_word_count} informative words (minimum {settings.MIN_INFORMATIVE_WORDS} required).",
                        limitations="Short, generic snippets do not contain enough semantic structure for model inference.",
                        details={"informative_words": informative_word_count},
                    )
                ],
                ml_analysis=None,
                company_verification=CompanyVerificationSummary(
                    status="UNKNOWN",
                    summary="Cannot verify company from insufficient text.",
                    limitations="Provide adequate job details including claimed employer.",
                ),
                recruiter_checks=RecruiterCheckSummary(status="INSUFFICIENT_TEXT"),
                recommended_safe_actions=[
                    "Please submit the full job posting description, including responsibilities, requirements, and contact instructions."
                ],
                limitations=[
                    "Cannot evaluate text with fewer than 10 informative words.",
                    "Provide comprehensive vacancy text for reliable rule and ML analysis.",
                ],
            )

        # 2. Rule-Based Signal Evaluation
        (
            rule_evals,
            rule_score,
            rule_evidence,
            extracted_emails,
            free_email_detected,
        ) = run_all_rules(text)

        # 3. ML Model Inference
        ml_result = self.ml_service.analyze_text(text, explanation_method=explanation_method)

        # 4. Composite Score Calculation (0 to 100)
        # S_composite = w_ML * S_ML + w_rules * S_rules
        evidence_items: List[EvidenceItem] = list(rule_evidence)

        # Scale calibrated probability to 0-100 scale
        ml_score = ml_result.calibrated_probability * 100.0

        composite_score = (
            settings.RISK_SCORE_WEIGHT_ML * ml_score
            + settings.RISK_SCORE_WEIGHT_RULES * rule_score
        )

        # High severity escalation: If high-severity rules are active, apply floor
        override_floor_applied: Optional[str] = None
        override_floor_reason: Optional[str] = None
        detected_names = [r.rule_name for r in rule_evals if r.detected]
        if any("Upfront Fees" in r for r in detected_names) and any(
            "Suspicious Contact" in r or "Sensitive Information" in r for r in detected_names
        ):
            if composite_score < 85.0:
                override_floor_applied = "CRITICAL_COMPOUND_FEE_OVERRIDE_85"
                override_floor_reason = (
                    "High-severity compound safety override: Upfront fee solicitation combined with suspicious contact "
                    "or sensitive banking/identity request enforces a minimum risk score of 85.0 (CRITICAL)."
                )
            composite_score = max(composite_score, 85.0)
        elif any("Upfront Fees" in r for r in detected_names):
            if composite_score < 65.0:
                override_floor_applied = "HIGH_UPFRONT_FEE_OVERRIDE_65"
                override_floor_reason = (
                    "High-severity safety override: Upfront fee solicitation enforces a minimum risk score of 65.0 (HIGH)."
                )
            composite_score = max(composite_score, 65.0)

        final_score = round(max(0.0, min(100.0, composite_score)), 1)

        # Add ML finding to evidence list distinctly
        ml_detected = ml_result.calibrated_prediction == "FRAUDULENT"
        evidence_items.append(
            EvidenceItem(
                evidence_type="ml_prediction",
                source_name=f"Baseline ML Classifier ({ml_result.model_version})",
                status="DETECTED" if ml_detected else "NOT_DETECTED",
                confidence=ml_result.calibrated_probability,
                summary=(
                    f"Calibrated ML model estimated fraud probability at "
                    f"{ml_result.calibrated_probability * 100:.1f}% "
                    f"(calibrated decision threshold: {ml_result.calibrated_threshold * 100:.1f}%, "
                    f"primary screening threshold: {ml_result.primary_threshold * 100:.1f}%)."
                ),
                limitations="Reflects linguistic similarity to historical recruitment scam training data.",
                details={
                    "model_version": ml_result.model_version,
                    "calibrated_prob": ml_result.calibrated_probability,
                    "uncalibrated_prob": ml_result.uncalibrated_probability,
                    "calibrated_pred": ml_result.calibrated_prediction,
                    "primary_pred": ml_result.primary_prediction,
                    "calibrated_threshold": ml_result.calibrated_threshold,
                    "primary_threshold": ml_result.primary_threshold,
                },
            )
        )

        # 5. Company Entity Verification (F2)
        extracted_info = extract_company_info(
            text=text,
            explicit_company_name=company_name,
            explicit_cin=cin,
        )

        # Run company verifier (independent of fraud score calculation)
        company_match = self.company_verifier.verify_company(
            query_name=extracted_info.company_name,
            cin=extracted_info.cin,
            db=db,
            is_ambiguous=extracted_info.is_name_ambiguous,
            candidate_names=extracted_info.candidate_names,
        )
        company_evidence = self.company_verifier.to_evidence_item(company_match)
        evidence_items.append(company_evidence)
        company_summary = self.company_verifier.to_summary_schema(company_match)

        category = classify_risk_score(final_score)

        # Warning banner
        warning_msg: Optional[str] = None
        if category in ("HIGH", "CRITICAL"):
            warning_msg = (
                f"POTENTIAL FRAUD ALERT: This listing scored {final_score}/100 ({category} risk). "
                f"Exercise extreme caution and do not pay fees or share bank details."
            )
        elif category == "MODERATE":
            warning_msg = (
                f"CAUTION ADVISED: This listing scored {final_score}/100 ({category} risk). "
                f"Verify the recruiter and company before proceeding."
            )

        detected_rule_names = [r.rule_name for r in rule_evals if r.detected]
        safe_actions = build_safe_actions(detected_rule_names, category)
        limitations = build_limitations()

        recruiter_checks = RecruiterCheckSummary(
            status="FREE_EMAIL_FLAGGED" if free_email_detected else "TEXT_EXTRACTED_ONLY",
            detected_emails=extracted_emails,
            free_email_detected=free_email_detected,
            summary=(
                "Detected free public email domain in recruiter contact."
                if free_email_detected
                else "Extracted contact details from text; domain authentication required."
            ),
        )

        return JobTextAnalysisResponse(
            report_id=report_id,
            timestamp=now,
            risk_score=final_score,
            risk_category=category,
            warning=warning_msg,
            override_floor_applied=override_floor_applied,
            override_floor_reason=override_floor_reason,
            provisional_thresholds=thresholds_doc,
            evidence=evidence_items,
            ml_analysis=ml_result,
            company_verification=company_summary,
            recruiter_checks=recruiter_checks,
            recommended_safe_actions=safe_actions,
            limitations=limitations,
        )


_risk_engine: Optional[RiskEngine] = None


def get_risk_engine() -> RiskEngine:
    global _risk_engine
    if _risk_engine is None:
        _risk_engine = RiskEngine()
    return _risk_engine
