"""Pydantic Request and Response Schemas for Job Text Analysis.

Conforms to Section 4 & Feature F1 of PROJECT_SPECIFICATION.md:
- Structured evidence separation (rules vs ML findings)
- Configurable provisional risk scores and categories
- ML probability kept strictly separate from composite risk score
- Tailored safe actions, limitations, and operational disclaimers
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

from app.schemas.listing import DuplicateAnalysisSummary
from app.services.job_relevance_validator import JobRelevanceResult


class JobTextAnalysisRequest(BaseModel):
    """Input payload for POST /api/v1/analyze/job-text."""

    text: str = Field(
        ...,
        description="Raw job posting text or description to be analyzed.",
    )
    company_name: Optional[str] = Field(
        default=None,
        description="Optional claimed employer name for MCA-21 and DPIIT registry corroboration.",
    )
    cin: Optional[str] = Field(
        default=None,
        description="Optional Corporate Identification Number (CIN) for direct registry verification.",
    )
    explanation_method: Optional[str] = Field(
        default="auto",
        description="Optional explanation method: 'auto', 'coefficients', or 'shap'.",
    )

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        trimmed = v.strip() if isinstance(v, str) else ""
        if not trimmed:
            raise ValueError("Job text cannot be empty or contain only whitespace.")
        if len(trimmed) < 20:
            raise ValueError("Job text is too short to analyze (minimum 20 characters required).")
        if len(trimmed) > 50000:
            raise ValueError("Job text exceeds maximum allowed size (maximum 50,000 characters).")
        return trimmed

    @field_validator("company_name", "cin", mode="before")
    @classmethod
    def clean_optional_strings(cls, v: Any) -> Optional[str]:
        if isinstance(v, str):
            trimmed = v.strip()
            return trimmed if trimmed else None
        return v


class EvidenceItem(BaseModel):
    """Individual evidence record detailing a rule signal or ML finding."""

    evidence_type: str = Field(
        ...,
        description="Type of evidence: 'rule_signal', 'ml_prediction', 'entity_check', etc.",
    )
    source_name: str = Field(
        ...,
        description="Descriptive identifier of the detector or rule (e.g., 'Rule: Upfront Fees Request').",
    )
    status: str = Field(
        ...,
        description="Detection status: 'DETECTED', 'NOT_DETECTED', 'UNVERIFIED', 'INSUFFICIENT_EVIDENCE'.",
    )
    confidence: Optional[float] = Field(
        None,
        description="Confidence or severity weight between 0.0 and 1.0.",
    )
    summary: str = Field(
        ...,
        description="Human-readable explanation of the finding.",
    )
    limitations: Optional[str] = Field(
        None,
        description="Caveats and contextual limitations of the specific evidence signal.",
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional structured metadata supporting the finding.",
    )


class FeatureContribution(BaseModel):
    """Explainable keyword / feature weight from model prediction (Feature F6)."""

    feature: str
    weight: float
    direction: str = Field(
        ...,
        description="'fraud_indicative' or 'legitimate_indicative'",
    )
    feature_value: Optional[float] = Field(
        default=None,
        description="Transformed input feature value (e.g. TF-IDF weight).",
    )
    coefficient: Optional[float] = Field(
        default=None,
        description="Fitted model coefficient for this feature in the target class.",
    )
    contribution: Optional[float] = Field(
        default=None,
        description="Exact feature contribution to model log-odds (coef * value).",
    )
    direction_label: Optional[str] = Field(
        default=None,
        description="'increases model score' or 'decreases model score'.",
    )
    sign: Optional[str] = Field(
        default=None,
        description="'+' or '-'.",
    )


class MLAnalysisResult(BaseModel):
    """Machine learning model classification output kept separate from composite score."""

    model_version: str = Field(..., description="Version of the model artifact used (e.g. 'v1.1.0').")
    model_name: str = Field(
        default="JobShield AI Text Fraud Classifier Baseline",
        description="Human-readable model name.",
    )
    primary_prediction: str = Field(..., description="'FRAUDULENT' or 'LEGITIMATE' from primary balanced classifier.")
    calibrated_prediction: str = Field(default="LEGITIMATE", description="'FRAUDULENT' or 'LEGITIMATE' from calibrated classifier.")
    calibrated_probability: Optional[float] = Field(
        None,
        description="Calibrated posterior probability P(fraud|text) between 0.0 and 1.0.",
    )
    uncalibrated_probability: Optional[float] = Field(
        None,
        description="Raw output probability from base logistic regression.",
    )
    primary_threshold: float = Field(
        default=0.62,
        description="Validation-tuned decision threshold applied to primary balanced model (0.62).",
    )
    calibrated_threshold: float = Field(
        default=0.40,
        description="Validation-tuned decision threshold applied to calibrated model probability (0.40).",
    )
    decision_threshold: float = Field(
        default=0.40,
        description="Operational threshold applied to the calibrated probability (0.40).",
    )
    calibration_method: str = Field(
        ...,
        description="Calibration algorithm applied (e.g. 'Platt Scaling (Sigmoid) via FrozenEstimator').",
    )
    score_type: str = Field(
        default="log_odds_decision_score",
        description="Score type: 'log_odds_decision_score' or 'calibrated_probability'.",
    )
    target_class: str = Field(
        default="FRAUDULENT",
        description="The target class whose score is explained.",
    )
    intercept: Optional[float] = Field(
        default=None,
        description="Model intercept (bias term) for the target class.",
    )
    decision_score: Optional[float] = Field(
        default=None,
        description="Model decision score (log-odds) for the target class.",
    )
    reconciled_score: Optional[float] = Field(
        default=None,
        description="Sum of all feature contributions plus intercept.",
    )
    is_reconciled: bool = Field(
        default=True,
        description="Whether sum of feature contributions and intercept equals decision score within tolerance.",
    )
    explanation_method: str = Field(
        default="LOGISTIC_REGRESSION_COEFFICIENTS",
        description="Method used for explanation (e.g. 'LOGISTIC_REGRESSION_COEFFICIENTS' or 'SHAP_LINEAR_EXPLAINER').",
    )
    explanation_available: bool = Field(
        default=True,
        description="Whether explanation is available for this model and input.",
    )
    explanation_unavailable_reason: Optional[str] = Field(
        default=None,
        description="Reason why explanation is unavailable, if applicable.",
    )
    top_features: List[FeatureContribution] = Field(
        default_factory=list,
        description="Top linguistic tokens influencing model prediction (by magnitude).",
    )
    top_positive_features: List[FeatureContribution] = Field(
        default_factory=list,
        description="Top features that increase the model's fraud score.",
    )
    top_negative_features: List[FeatureContribution] = Field(
        default_factory=list,
        description="Top features that decrease the model's fraud score.",
    )
    active_feature_count: Optional[int] = Field(
        default=None,
        description="Total number of non-zero active vocabulary tokens in the input text.",
    )
    total_feature_contribution: Optional[float] = Field(
        default=None,
        description="Sum of all feature contributions across the entire active vocabulary.",
    )
    explanation_disclaimer: str = Field(
        default=(
            "These contributions describe how input features influenced this model's output. "
            "They do not establish intent, prove fraud, or independently verify the authenticity of a job offer."
        ),
        description="Mandatory disclaimer for feature contributions per Section 3.",
    )
    disclaimer: str = Field(
        default=(
            "Linguistic ML predictions reflect text similarity to historical recruitment scam training data "
            "and must not be interpreted as standalone proof of fraud or legitimacy."
        )
    )


class ThresholdRange(BaseModel):
    min_score: float
    max_score: float
    category: str
    description: str


class ProvisionalThresholds(BaseModel):
    """Documentation of active provisional composite thresholds."""

    version: str = Field(..., description="Identifier of the provisional threshold ruleset.")
    status: str = Field(
        default="provisional",
        description="Always labeled 'provisional'; thresholds are heuristic and not statistically calibrated.",
    )
    ranges: List[ThresholdRange]
    disclaimer: str = Field(
        default=(
            "Thresholds are provisional heuristics and are not statistically calibrated. "
            "A low score is not proof of authenticity, and a high score is not a legal finding of fraud."
        )
    )


class CompanyVerificationSummary(BaseModel):
    """Summary of entity corroboration against sourced MCA-21 and DPIIT registries."""

    status: str = Field(
        default="UNVERIFIED",
        description="Status: 'MATCHED', 'AMBIGUOUS_MATCH', 'NO_MATCH', 'UNKNOWN', 'STALE', 'SOURCE_UNAVAILABLE', 'UNVERIFIED'.",
    )
    company_id: Optional[int] = Field(default=None, description="Internal database ID of matched company entity.")
    queried_name: Optional[str] = Field(
        default=None,
        description="The company name that was extracted from text or explicitly supplied for verification.",
    )
    matched_name: Optional[str] = Field(default=None, description="Official legal name in the registry.")
    cin: Optional[str] = Field(default=None, description="Corporate Identification Number (CIN) if available.")
    match_method: Optional[str] = Field(default=None, description="Algorithm/method applied during lookup.")
    match_confidence: Optional[float] = Field(default=None, description="Confidence score between 0.0 and 1.0.")
    mca_status: Optional[str] = Field(default=None, description="MCA registry standing (Active, Strike Off, etc.).")
    dpiit_status: Optional[str] = Field(default=None, description="DPIIT / Startup India recognition standing.")
    source: Optional[str] = Field(default=None, description="Registry source identifier (e.g. MCA_COMPANY_MASTER).")
    dataset_version: Optional[str] = Field(default=None, description="Dataset snapshot date or release version.")
    checked_at: Optional[datetime] = Field(default=None, description="Timestamp when verification was evaluated.")
    summary: str = Field(
        default="Company entity verification requires separate MCA-21 and DPIIT registry checks."
    )
    limitations: Optional[str] = Field(
        default="MCA registration validates entity existence only; it does not validate a specific recruiter or vacancy."
    )
    is_fraud_signal: bool = Field(
        default=False,
        description="Always false. Neither NO_MATCH nor AMBIGUOUS_MATCH is presented as fraud.",
    )
    candidate_entities: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Candidate entities when status is AMBIGUOUS_MATCH.",
    )


class RecruiterCheckSummary(BaseModel):
    """Summary of recruiter email and contact checks extracted from text."""

    status: str = Field(default="TEXT_EXTRACTED_ONLY")
    detected_emails: List[str] = Field(default_factory=list)
    free_email_detected: bool = Field(default=False)
    summary: str = Field(
        default="Email addresses identified in text must be verified against official company domains."
    )


class CommunitySummary(BaseModel):
    """Summary of community feedback and ratings."""

    status: str = Field(default="NO_COMMUNITY_DATA")
    review_count: int = 0
    summary: str = Field(default="No community ratings or verified reports linked to this scan.")


class JobTextAnalysisResponse(BaseModel):
    """Comprehensive analysis result complying with Section 4 of project specification."""

    report_id: str = Field(..., description="Unique UUID scan identifier.")
    timestamp: datetime = Field(..., description="Timestamp of analysis.")
    risk_score: Optional[float] = Field(
        None,
        description="Composite risk score from 0 to 100. Null when evidence is insufficient.",
    )
    risk_category: str = Field(
        ...,
        description="'LOW', 'MODERATE', 'HIGH', 'CRITICAL', or 'INSUFFICIENT_EVIDENCE'.",
    )
    warning: Optional[str] = Field(
        None,
        description="Prominent warning banner displayed when risk warrants candidate caution.",
    )
    override_floor_applied: Optional[str] = Field(
        default=None,
        description="Indicates if a high-severity rule safety override floor was applied to the composite risk score.",
    )
    override_floor_reason: Optional[str] = Field(
        default=None,
        description="Human-readable rationale for the safety override floor.",
    )
    provisional_thresholds: ProvisionalThresholds
    evidence: List[EvidenceItem] = Field(
        default_factory=list,
        description="Disclosed evidence signals (rules and ML findings labeled distinctly).",
    )
    ml_analysis: Optional[MLAnalysisResult] = Field(
        None,
        description="Machine learning model analysis results kept distinct from composite score.",
    )
    company_verification: CompanyVerificationSummary = Field(
        default_factory=CompanyVerificationSummary
    )
    recruiter_checks: RecruiterCheckSummary = Field(
        default_factory=RecruiterCheckSummary
    )
    community_summary: CommunitySummary = Field(
        default_factory=CommunitySummary
    )
    recommended_safe_actions: List[str] = Field(
        default_factory=list,
        description="Tailored, actionable safety steps for the job seeker.",
    )
    limitations: List[str] = Field(
        default_factory=list,
        description="Transparent caveats and boundaries of the analysis.",
    )
    disclaimer: str = Field(
        default=(
            "JobShield AI provides informational risk assessments based on textual pattern recognition "
            "and heuristics. It does not provide legal advice or definitive legal determinations of fraud."
        )
    )
    duplicate_analysis: Optional[DuplicateAnalysisSummary] = Field(
        default=None,
        description="Duplicate posting and impersonation signals if identified against indexed listings.",
    )
    is_job_related: bool = Field(
        default=True,
        description="Whether the submitted input was validated as employment or recruitment related.",
    )
    relevance: Optional[JobRelevanceResult] = Field(
        default=None,
        description="Detailed job-relevance validation outcome.",
    )


class JobUrlAnalysisRequest(BaseModel):
    """Input payload for POST /api/v1/analyze/job-url."""

    url: str = Field(
        ...,
        description="Public job posting URL to analyze.",
    )
    company_name: Optional[str] = Field(
        default=None,
        description="Optional claimed employer name for MCA-21 and DPIIT registry corroboration.",
    )
    cin: Optional[str] = Field(
        default=None,
        description="Optional Corporate Identification Number (CIN) for direct registry verification.",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        trimmed = v.strip() if isinstance(v, str) else ""
        if not trimmed:
            raise ValueError("Job URL cannot be empty.")
        if not (trimmed.startswith("http://") or trimmed.startswith("https://")):
            raise ValueError("Job URL must start with http:// or https://")
        if len(trimmed) > 2048:
            raise ValueError("Job URL exceeds maximum allowed length of 2048 characters.")
        return trimmed

    @field_validator("company_name", "cin", mode="before")
    @classmethod
    def clean_optional_strings(cls, v: Any) -> Optional[str]:
        if isinstance(v, str):
            trimmed = v.strip()
            return trimmed if trimmed else None
        return v


class DomainCheckSummary(BaseModel):
    """Summary of technical domain authentication, MX, SPF, DMARC, DKIM, and lookalike checks."""

    domain: str = Field(..., description="Target domain evaluated.")
    dns_status: str = Field(default="UNKNOWN", description="DNS resolution status (PASS, NO_RECORDS, NXDOMAIN, etc.).")
    mx_status: str = Field(default="UNKNOWN", description="Mail exchange status (PASS, NO_MX, etc.).")
    spf_status: str = Field(default="UNKNOWN", description="SPF authentication record status.")
    dkim_status: str = Field(default="UNKNOWN", description="DKIM common selector probe status.")
    dmarc_status: str = Field(default="UNKNOWN", description="DMARC authentication policy status.")
    lookalike_flags: Optional[Dict[str, Any]] = Field(default=None, description="Typosquatting/homoglyph signals.")
    source_details: Optional[Dict[str, Any]] = Field(default=None, description="Detailed DNS/MX/Auth findings.")
    checked_at: Optional[datetime] = Field(default=None, description="Timestamp when domain checks were executed.")
    summary: str = Field(
        default="Domain and email authentication checks evaluate technical delivery routes and typosquatting risk."
    )
    limitations: Optional[str] = Field(
        default="Technical domain checks evaluate email and DNS infrastructure; they do not guarantee authorization of specific individuals."
    )


class JobUrlAnalysisResponse(JobTextAnalysisResponse):
    """Comprehensive URL analysis result combining extracted content analysis with domain security."""

    job_url: str = Field(..., description="The analyzed job posting URL.")
    extracted_title: Optional[str] = Field(default=None, description="Extracted web page or job title.")
    extracted_company: Optional[str] = Field(default=None, description="Extracted employer or company name from page.")
    domain_check: Optional[DomainCheckSummary] = Field(
        default=None,
        description="Domain security, email auth (DNS/MX/SPF/DMARC/DKIM), and lookalike warnings.",
    )
    page_type: str = Field(
        default="JOB_POSTING",
        description="Classification: 'JOB_POSTING', 'CAREERS_HOMEPAGE', 'ACCESS_RESTRICTED', or 'JS_REQUIRED_OR_SPARSE_CONTENT'.",
    )
    fetch_status_code: int = Field(
        default=200,
        description="HTTP status code received from target server (e.g. 200, 403, 429).",
    )
    fetched_at: Optional[datetime] = Field(default=None, description="Timestamp when the URL was fetched.")


class RecruiterEmailAnalysisRequest(BaseModel):
    """Input payload for POST /api/v1/analyze/recruiter-email."""

    email: str = Field(
        ...,
        description="Recruiter or sender email address to analyze.",
    )
    company_name: Optional[str] = Field(
        default=None,
        description="Optional claimed employer name for MCA-21 and DPIIT registry corroboration.",
    )
    cin: Optional[str] = Field(
        default=None,
        description="Optional Corporate Identification Number (CIN) for direct registry verification.",
    )
    message_text: Optional[str] = Field(
        default=None,
        description="Optional user-pasted recruitment communication, email body, or job message.",
    )

    @field_validator("email")
    @classmethod
    def validate_email_address(cls, v: str) -> str:
        trimmed = v.strip() if isinstance(v, str) else ""
        if not trimmed:
            raise ValueError("Email address cannot be empty.")
        if len(trimmed) > 254:
            raise ValueError("Email address exceeds maximum allowed length (254 characters).")
        if "@" not in trimmed or trimmed.startswith("@") or trimmed.endswith("@"):
            raise ValueError("Invalid email address format.")
        local, domain = trimmed.split("@", 1)
        if len(local) > 64 or not domain or "." not in domain:
            raise ValueError("Invalid email address format.")
        return trimmed

    @field_validator("company_name", "cin", "message_text", mode="before")
    @classmethod
    def clean_optional_strings(cls, v: Any) -> Optional[str]:
        if isinstance(v, str):
            trimmed = v.strip()
            return trimmed if trimmed else None
        return v


class RecruiterEmailAnalysisResponse(JobTextAnalysisResponse):
    """Comprehensive recruiter email analysis result combining domain checks, company verification, and message heuristics."""

    email_masked: str = Field(..., description="Masked recruiter email address (e.g. 'c***s@tcs.com').")
    domain: str = Field(..., description="The sender email domain evaluated.")
    email_status: str = Field(
        ...,
        description="Classification: 'DOMAIN_MATCH', 'IDENTITY_UNVERIFIED', 'MISMATCH_DETECTED', 'FREE_EMAIL_PROVIDER', or 'LOOKALIKE_WARNING'.",
    )
    is_free_email: bool = Field(default=False, description="Whether the sender domain is a free public webmail provider.")
    domain_check: Optional[DomainCheckSummary] = Field(
        default=None,
        description="Domain security, email auth (DNS/MX/SPF/DMARC/DKIM), and lookalike warnings.",
    )
    extracted_title: Optional[str] = Field(default=None, description="Optional job title if mentioned in message.")
    extracted_company: Optional[str] = Field(default=None, description="Claimed or extracted company name.")


