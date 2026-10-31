"""Pydantic schemas for Feature F7: Offer Letter Analyzer."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.analysis import (
    CompanyVerificationSummary,
    DomainCheckSummary,
    JobTextAnalysisResponse,
)


class ExtractedFieldItem(BaseModel):
    """Structured representation of an extracted offer letter field."""

    value: Optional[str] = Field(default=None, description="Extracted textual value or sanitized representation.")
    page: Optional[int] = Field(default=None, description="1-indexed source page number where the field was located.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score for field extraction.")
    snippet: Optional[str] = Field(default=None, description="Safe context snippet surrounding the field.")
    is_present: bool = Field(default=False, description="Whether the field was identified in the document.")


class ExtractedFeeDemand(BaseModel):
    """Specific monetary, registration, training, or equipment payment demand identified in document."""

    category: str = Field(..., description="Category: 'TRAINING_FEE', 'SECURITY_DEPOSIT', 'LAPTOP_FEE', 'REGISTRATION_FEE', 'DOCUMENTATION_FEE', etc.")
    amount: Optional[str] = Field(default=None, description="Extracted currency and numeric amount (e.g. '$150', '₹5,000').")
    clause_text: str = Field(..., description="Exact textual clause extracted from the offer letter.")
    page: int = Field(..., description="1-indexed source page number.")
    is_refundable_claimed: bool = Field(default=False, description="Whether the clause falsely promises refundability.")
    warning: str = Field(..., description="Actionable advisory warning explaining why upfront fee demands are fraudulent.")


class ExtractedSensitiveRequest(BaseModel):
    """Demands for sensitive financial credentials, OTPs, or original documents."""

    request_type: str = Field(..., description="Request type: 'BANK_ACCOUNT_DETAILS', 'PASSWORD_OR_OTP', 'ORIGINAL_CERTIFICATES', 'GOVERNMENT_ID_DOCS'.")
    clause_text: str = Field(..., description="Exact textual clause extracted from the document.")
    page: int = Field(..., description="1-indexed source page number.")
    warning: str = Field(..., description="Advisory warning explaining the privacy or security risk.")


class OfferLetterExtractedData(BaseModel):
    """Comprehensive fields extracted from the offer letter."""

    company_name: Optional[ExtractedFieldItem] = None
    candidate_name: Optional[ExtractedFieldItem] = None
    job_title: Optional[ExtractedFieldItem] = None
    salary_compensation: Optional[ExtractedFieldItem] = None
    offer_date: Optional[ExtractedFieldItem] = None
    joining_date: Optional[ExtractedFieldItem] = None
    deadline_date: Optional[ExtractedFieldItem] = None
    recruiter_contacts: List[str] = Field(default_factory=list, description="Masked recruiter emails and phone numbers.")
    domains_or_urls: List[str] = Field(default_factory=list, description="Extracted domains or public web links.")
    company_address: Optional[ExtractedFieldItem] = None
    fee_demands: List[ExtractedFeeDemand] = Field(default_factory=list)
    sensitive_requests: List[ExtractedSensitiveRequest] = Field(default_factory=list)
    has_fee_demand: bool = False
    has_sensitive_request: bool = False
    raw_character_count: int = 0


class OfferLetterAnalysisResponse(JobTextAnalysisResponse):
    """Complete analysis outcome for an offer letter PDF upload."""

    file_name: str = Field(..., description="Sanitized original filename.")
    file_size_bytes: int = Field(..., description="Uploaded document size in bytes.")
    page_count: int = Field(..., description="Total pages processed.")
    is_scanned: bool = Field(default=False, description="Whether document contained scanned or image-only pages.")
    ocr_applied: bool = Field(default=False, description="Whether Tesseract OCR was executed on scanned pages.")
    ocr_engine: Optional[str] = Field(default=None, description="OCR engine identifier and version.")
    extracted_fields: OfferLetterExtractedData = Field(..., description="Structured extracted document fields.")
    suspicious_indicators: List[str] = Field(default_factory=list, description="Specific red flags or anomaly codes.")
    domain_checks: List[DomainCheckSummary] = Field(default_factory=list, description="Technical domain authentication for contact domains.")
    summary: str = Field(..., description="Human-readable synthesis of offer letter assessment.")
    disclaimer: str = Field(
        default="Automated offer letter assessment provides risk signals and pattern corroboration. It does not constitute legal certification or definitive authentication of employment documents.",
        description="Statutory legal and technical limitation disclaimer.",
    )
