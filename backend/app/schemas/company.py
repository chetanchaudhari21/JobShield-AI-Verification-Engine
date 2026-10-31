"""Pydantic schemas for Company Entity API (GET /api/v1/companies/{id}).

Conforms to Feature F2 and Section 8 & 9 of PROJECT_SPECIFICATION.md:
- Detailed sourced company profile with provenance and registry statuses
- Explicit separation between MCA registration and DPIIT startup recognition
- Verified and observed company domains
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.analysis import CompanyVerificationSummary


class CompanySourceRecordOut(BaseModel):
    id: int
    source_name: str
    source_url: Optional[str] = None
    source_record_id: Optional[str] = None
    source_status: Optional[str] = None
    retrieved_at: datetime
    source_updated_at: Optional[datetime] = None
    match_method: str
    match_confidence: float
    raw_metadata: Optional[Dict[str, Any]] = None


class StartupRecognitionOut(BaseModel):
    id: int
    recognition_status: str
    recognition_id: Optional[str] = None
    source_url: Optional[str] = None
    checked_at: datetime
    status_details: Optional[Dict[str, Any]] = None


class CompanyDomainOut(BaseModel):
    id: int
    domain: str
    source_url: Optional[str] = None
    verification_status: str
    evidence_summary: Optional[str] = None
    checked_at: datetime
    is_primary: bool


class CompanyDetailResponse(BaseModel):
    """Detailed company verification response for GET /api/v1/companies/{id}."""

    id: int
    legal_name: str
    normalized_name: str
    cin: Optional[str] = None
    entity_type: Optional[str] = None
    registry_status: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    source_records: List[CompanySourceRecordOut] = Field(default_factory=list)
    startup_recognitions: List[StartupRecognitionOut] = Field(default_factory=list)
    domains: List[CompanyDomainOut] = Field(default_factory=list)
    verification_summary: CompanyVerificationSummary
    disclaimer: str = Field(
        default=(
            "MCA registration and DPIIT recognition validate entity existence only. "
            "Neither status validates or authenticates a specific recruiter, vacancy, or offer."
        )
    )
