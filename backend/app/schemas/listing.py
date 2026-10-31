"""Pydantic schemas for Job Listings, Similarity Matches, and Duplicate Analysis.

Conforms to Section 8 (Tables 5 & 6) and Feature F4/F5 of PROJECT_SPECIFICATION.md:
- Exact and near-duplicate job listing detection
- Explainable match classifications and confidence scoring
- Impersonation evidence and syndication recognition
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class JobSimilarityMatchItem(BaseModel):
    """Details of a single similarity match against an existing job listing."""

    match_id: Optional[str] = Field(default=None, description="Unique ID of the similarity match record.")
    matched_listing_id: str = Field(..., description="ID of the matching job listing in the repository.")
    is_exact_match: bool = Field(default=False, description="Whether the normalized content hash matches exactly.")
    similarity_score: float = Field(..., description="TF-IDF cosine similarity score between 0.0 and 1.0.")
    match_classification: str = Field(
        ...,
        description="One of: 'EXACT_DUPLICATE', 'LIKELY_REPOST', 'NEAR_DUPLICATE', 'POTENTIAL_SUSPICIOUS_COPY', 'INSUFFICIENT_EVIDENCE'.",
    )
    confidence: float = Field(..., description="Rule-calibrated confidence level between 0.0 and 1.0.")
    matched_title: Optional[str] = Field(default=None, description="Job title of the matched listing.")
    matched_company_name: Optional[str] = Field(default=None, description="Claimed company name of the matched listing.")
    matched_source_url: Optional[str] = Field(default=None, description="Source URL of the matched listing.")
    matched_domain: Optional[str] = Field(default=None, description="Domain host where the matched listing was observed.")
    matched_location: Optional[str] = Field(default=None, description="Location of the matched listing.")
    matched_collected_at: Optional[datetime] = Field(default=None, description="Timestamp when matched listing was recorded.")
    supporting_evidence: List[Dict[str, Any]] = Field(default_factory=list, description="Evidence supporting the classification.")
    contradictory_evidence: List[Dict[str, Any]] = Field(default_factory=list, description="Contradictory or mitigating evidence.")
    reasons: List[str] = Field(default_factory=list, description="Documented reasons for the match classification.")
    impersonation_signals: List[str] = Field(default_factory=list, description="Specific impersonation warnings if detected.")


class DuplicateAnalysisSummary(BaseModel):
    """Aggregate duplicate and impersonation detection results for a job listing."""

    status: str = Field(
        default="UNIQUE_LISTING",
        description="Overall duplicate status: 'UNIQUE_LISTING', 'EXACT_DUPLICATE', 'LIKELY_REPOST', 'NEAR_DUPLICATE', 'POTENTIAL_SUSPICIOUS_COPY', 'INSUFFICIENT_EVIDENCE'.",
    )
    total_matches_found: int = Field(default=0, description="Total number of matching listings found.")
    highest_similarity_score: float = Field(default=0.0, description="Highest similarity score among all matches.")
    top_matches: List[JobSimilarityMatchItem] = Field(default_factory=list, description="Top similarity matches.")
    impersonation_warning: Optional[str] = Field(
        default=None,
        description="Prominent warning banner if duplicate content exhibits company impersonation or lookalike signals.",
    )
    summary: str = Field(
        default="No duplicate listings identified in the current repository snapshot.",
        description="Human-readable explanation of duplicate analysis findings.",
    )
    limitations: str = Field(
        default="Duplicate detection compares against currently indexed listings; unindexed job portals or external sites are not covered.",
        description="Operational boundaries of the duplicate detection engine.",
    )


class JobListingCreate(BaseModel):
    """Input payload to register or analyze a job listing."""

    job_title: Optional[str] = Field(default=None, description="Optional job title.")
    job_description: str = Field(..., description="Job posting body or description text.")
    claimed_company_name: Optional[str] = Field(default=None, description="Optional employer or company name.")
    cin: Optional[str] = Field(default=None, description="Optional Corporate Identification Number (CIN).")
    source_url: Optional[str] = Field(default=None, description="Optional source or career page URL.")
    job_location: Optional[str] = Field(default=None, description="Optional geographic location.")
    employment_type: Optional[str] = Field(default=None, description="Optional employment type (Full-time, Remote, etc.).")
    source_type: Optional[str] = Field(default="DIRECT_INPUT", description="Provenance channel (URL_INGESTION, MANUAL_TEXT, etc.).")

    @field_validator("job_description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        trimmed = v.strip() if isinstance(v, str) else ""
        if not trimmed:
            raise ValueError("Job description cannot be empty or whitespace.")
        return trimmed


class JobListingResponse(BaseModel):
    """Output representation of a registered job listing with duplicate analysis."""

    id: str = Field(..., description="Unique UUID listing identifier.")
    job_title: Optional[str] = Field(default=None)
    job_description: Optional[str] = Field(default=None)
    claimed_company_name: Optional[str] = Field(default=None)
    company_id: Optional[int] = Field(default=None)
    source_url: Optional[str] = Field(default=None)
    normalized_url: Optional[str] = Field(default=None)
    content_hash: str = Field(..., description="SHA-256 hash of normalized job description text.")
    source_domain: Optional[str] = Field(default=None)
    job_location: Optional[str] = Field(default=None)
    employment_type: Optional[str] = Field(default=None)
    source_type: str = Field(default="DIRECT_INPUT")
    extraction_status: str = Field(default="COMPLETED")
    collected_at: datetime = Field(..., description="Timestamp when listing was collected/ingested.")
    duplicate_analysis: Optional[DuplicateAnalysisSummary] = Field(default=None)


class JobDuplicateCheckRequest(BaseModel):
    """Ad-hoc query to check a job description for duplicate postings without permanently storing it."""

    text: str = Field(..., description="Job posting text to search against existing listings.")
    title: Optional[str] = Field(default=None, description="Optional job title.")
    company_name: Optional[str] = Field(default=None, description="Optional company name.")
    cin: Optional[str] = Field(default=None, description="Optional Corporate Identification Number (CIN).")
    source_url: Optional[str] = Field(default=None, description="Optional source URL.")
    location: Optional[str] = Field(default=None, description="Optional location.")
