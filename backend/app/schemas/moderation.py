"""Pydantic schemas for Moderation Queue, Decisions, Appeals, and Audit Trail."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ModerationQueueItem(BaseModel):
    """Normalized item in the moderator review queue."""
    id: str
    target_type: str  # 'review' or 'report'
    status: str
    created_at: datetime
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    rating: Optional[int] = None
    category: Optional[str] = None
    report_type: Optional[str] = None
    text_snippet: Optional[str] = None
    evidence_summary: Optional[str] = None
    recruiter_email_masked: Optional[str] = None
    submitter_user_id: Optional[str] = None


class ModerationQueueResponse(BaseModel):
    """Paginated list of queue items."""
    items: List[ModerationQueueItem]
    total: int
    limit: int
    offset: int


class AppealCreateRequest(BaseModel):
    """Authenticated user appeal against a moderation decision."""
    moderation_id: str = Field(..., description="UUID of the review_moderation record")
    appeal_reason: str = Field(..., min_length=10, max_length=2000, description="Detailed basis for appealing the decision")


class AppealResponse(BaseModel):
    """Appeal status and audit details."""
    id: str
    moderation_id: str
    user_id: Optional[str] = None
    appeal_reason: str
    status: str  # 'PENDING', 'UPHELD', 'DISMISSED'
    reviewer_id: Optional[str] = None
    resolution_notes: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AppealResolveRequest(BaseModel):
    """Moderator/admin resolution of an appeal."""
    action: str = Field(..., description="'UPHELD' (reverses rejection) or 'DISMISSED' (maintains decision)")
    resolution_notes: str = Field(..., min_length=5, max_length=2000)


class ModerationAuditItem(BaseModel):
    """Immutable audit trail record of a moderation action."""
    id: str
    target_type: str
    review_id: Optional[str] = None
    report_id: Optional[str] = None
    moderator_id: str
    action: str
    reason: str
    appeal_status: str
    created_at: datetime
    audit_metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class ModerationAuditListResponse(BaseModel):
    items: List[ModerationAuditItem]
    total: int
    limit: int
    offset: int
