"""Pydantic schemas for F8 & F9: Community Feedback, Moderation & Company Reputation.

Conforms to Section 8 (Tables 11-14) & Section 9 of PROJECT_SPECIFICATION.md:
- user_reviews: Community service-experience ratings (1-5 stars) and reviews
- recruiter_reports: Allegations of suspected recruitment fraud, upfront fees, or impersonation
- review_moderation: Moderation decisions, audit trail, and appeals
- training_labels: Explicit authorized training data curation (strictly isolated)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


# ==============================================================================
# Sensitive Content Detection Helper
# ==============================================================================
SENSITIVE_KEYWORDS = [
    "password", "passwd", "otp", "one-time password", "cvv", "cvc",
    "credit card", "debit card", "atm pin", "bank account number",
    "netbanking", "secret key", "private key"
]


def check_no_sensitive_info(text: Optional[str]) -> None:
    if not text:
        return
    text_lower = text.lower()
    for kw in SENSITIVE_KEYWORDS:
        if kw in text_lower:
            raise ValueError(
                f"Submission contains prohibited sensitive term or credential indicator: '{kw}'. "
                "Do not include passwords, OTPs, bank credentials, or sensitive secrets in reviews or reports."
            )


# ==============================================================================
# User Review Schemas (1 - 5 Star Service Experience)
# ==============================================================================
class UserReviewCreate(BaseModel):
    company_id: Optional[int] = None
    company_name: Optional[str] = Field(None, max_length=255)
    recruiter_email: Optional[str] = Field(None, max_length=255)
    scan_id: Optional[str] = Field(None, max_length=36)
    job_id: Optional[str] = Field(None, max_length=36)
    rating: int = Field(..., ge=1, le=5, description="Service experience rating from 1 to 5")
    category: str = Field("GENERAL_EXPERIENCE", max_length=50, description="Experience category")
    review_text: Optional[str] = Field(None, max_length=2000, description="Constructive feedback (max 2000 chars)")

    @field_validator("review_text")
    @classmethod
    def validate_review_text(cls, v: Optional[str]) -> Optional[str]:
        if v:
            check_no_sensitive_info(v)
            return v.strip()
        return v

    @field_validator("recruiter_email")
    @classmethod
    def validate_recruiter_email(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return v.strip().lower()
        return v


class UserReviewResponse(BaseModel):
    id: str
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    recruiter_email_masked: Optional[str] = None
    scan_id: Optional[str] = None
    rating: int
    category: str
    review_text: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ==============================================================================
# Recruiter / Fraud Report Schemas
# ==============================================================================
class RecruiterReportCreate(BaseModel):
    company_id: Optional[int] = None
    company_name: Optional[str] = Field(None, max_length=255)
    recruiter_email: Optional[str] = Field(None, max_length=255)
    scan_id: Optional[str] = Field(None, max_length=36)
    job_id: Optional[str] = Field(None, max_length=36)
    report_type: str = Field(
        ...,
        max_length=50,
        description="Type: impersonation, fake_offer, fee_demand, phishing, suspicious_domain, other"
    )
    details: str = Field(..., min_length=10, max_length=3000, description="Detailed account of suspicious activity")
    evidence_summary: Optional[str] = Field(None, max_length=2000, description="Evidence references, headers, or payment links")

    @field_validator("details")
    @classmethod
    def validate_details(cls, v: str) -> str:
        check_no_sensitive_info(v)
        return v.strip()

    @field_validator("evidence_summary")
    @classmethod
    def validate_evidence(cls, v: Optional[str]) -> Optional[str]:
        if v:
            check_no_sensitive_info(v)
            return v.strip()
        return v

    @field_validator("recruiter_email")
    @classmethod
    def validate_recruiter_email(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return v.strip().lower()
        return v


class RecruiterReportResponse(BaseModel):
    id: str
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    recruiter_email_masked: Optional[str] = None
    scan_id: Optional[str] = None
    report_type: str
    details: str
    evidence_summary: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ==============================================================================
# Bayesian Company Reputation Schemas
# ==============================================================================
class CompanyReputationResponse(BaseModel):
    company_id: int
    company_name: str
    total_approved_reviews: int = Field(..., description="Count of approved reviews n")
    raw_mean_rating: Optional[float] = Field(None, description="Arithmetic mean r_bar of approved ratings")
    bayesian_rating: float = Field(..., description="Damped Bayesian reputation R = (n*r_bar + m*C)/(n + m)")
    prior_strength_m: float = Field(..., description="Prior weight parameter m")
    prior_mean_c: float = Field(..., description="Prior mean rating parameter C")
    confidence_score: float = Field(..., description="Confidence weight n / (n + m) in range [0, 1)")
    rating_distribution: Dict[str, int] = Field(
        default_factory=lambda: {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
        description="Distribution of 1 to 5 star ratings"
    )
    fraud_reports_count: int = Field(..., description="Total recruiter/fraud allegations (kept separate from star rating)")
    fraud_reports_by_type: Dict[str, int] = Field(
        default_factory=dict,
        description="Breakdown of fraud allegations by type"
    )
    recent_reviews: List[UserReviewResponse] = Field(default_factory=list)


# ==============================================================================
# Moderation Schemas
# ==============================================================================
class ModerationDecisionRequest(BaseModel):
    target_type: Optional[str] = Field(None, description="'review' or 'report'")
    target_id: Optional[str] = None
    item_type: Optional[str] = None
    item_id: Optional[str] = None
    action: str = Field(..., description="'approve', 'reject', 'flag', 'appeal_upheld', 'appeal_dismissed'")
    moderator_id: Optional[str] = Field(None, max_length=100)
    reason: str = Field(..., min_length=3, max_length=500)
    audit_metadata: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "item_type" in data and not data.get("target_type"):
                data["target_type"] = data["item_type"]
            if "item_id" in data and not data.get("target_id"):
                data["target_id"] = data["item_id"]
            if not data.get("moderator_id"):
                data["moderator_id"] = "moderator"
        return data


class ModerationDecisionResponse(BaseModel):
    id: str
    target_type: str
    target_id: str
    action: str
    moderator_id: str
    reason: str
    new_status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ModerationAppealRequest(BaseModel):
    moderation_id: str
    appeal_reason: str = Field(..., min_length=5, max_length=2000)


class ModerationAppealResponse(BaseModel):
    moderation_id: str
    appeal_status: str
    message: str
    appealed_at: datetime


# ==============================================================================
# Training Label Isolation Schema (Explicit Authorized Curation Only)
# ==============================================================================
class TrainingLabelCreateRequest(BaseModel):
    scan_id: Optional[str] = None
    job_id: Optional[str] = None
    label: str = Field(..., description="'FRAUDULENT' or 'LEGITIMATE'")
    label_source: str = Field(..., description="Curation provenance source (e.g. 'EXPERT_CURATION')")
    reviewed_by: str = Field(..., min_length=2, max_length=100)
    evidence_reference: str = Field(..., min_length=5, max_length=2000)
    validation_notes: Optional[str] = Field(None, max_length=2000)
    dataset_version: Optional[str] = Field("v1.0.0", max_length=50)

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "label" in data and isinstance(data["label"], str):
                data["label"] = data["label"].strip().upper()
            if not data.get("label_source"):
                data["label_source"] = "EXPERT_CURATION"
            if not data.get("reviewed_by"):
                data["reviewed_by"] = "admin"
            if not data.get("evidence_reference"):
                data["evidence_reference"] = data.get("text") or data.get("curator_notes") or "Expert ground-truth curation"
        return data


class TrainingLabelResponse(BaseModel):
    id: str
    scan_id: Optional[str] = None
    job_id: Optional[str] = None
    label: str
    label_source: str
    validation_status: str
    reviewed_by: str
    evidence_reference: str
    dataset_version: Optional[str] = None
    validation_notes: Optional[str] = None
    is_active_for_training: bool
    created_at: datetime
    approved_for_training_at: Optional[datetime] = None

    class Config:
        from_attributes = True
