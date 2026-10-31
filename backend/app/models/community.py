"""Community Feedback, Fraud Reports, Moderation & Training Labels ORM Models.

Conforms to Feature F8, F9 & Sections 5, 8 (Tables 11-14), 10 of PROJECT_SPECIFICATION.md:
- user_reviews: Community service-experience ratings (1-5 stars) and reviews.
- recruiter_reports: Allegations of suspected recruitment fraud, upfront fees, or impersonation.
- review_moderation: Audit trail of human/automated moderation decisions and appeals.
- training_labels: Explicitly validated, independently approved training data.

CRITICAL ARCHITECTURAL GUARANTEE:
Community reviews and recruiter reports NEVER automatically create, modify,
approve, or promote records in training_labels. Training labels must be explicitly
reviewed and separately approved by authorized reviewers.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.job import JobListing
    from app.models.scan import ScanRequest
    from app.models.user import ModerationAppeal, User

json_type = JSON().with_variant(JSONB, "postgresql")


class UserReview(Base):
    """
    Community service-experience reviews and 1-5 star ratings.
    Table 11 of PROJECT_SPECIFICATION.md (Feature F9).
    """

    __tablename__ = "user_reviews"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    company_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("job_listings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    scan_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("scan_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Non-reversible cryptographic hash of IP + server secret salt for rate limiting and duplicate prevention
    submitter_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # 1-5 star rating
    rating: Mapped[int] = mapped_column(
        Integer,
        CheckConstraint("rating >= 1 AND rating <= 5", name="check_user_review_rating_range"),
        nullable=False,
        index=True,
    )
    experience_category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="GENERAL_EXPERIENCE",
        index=True,
    )
    review_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Moderation state: PENDING, APPROVED, REJECTED, FLAGGED
    moderation_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PENDING",
        index=True,
    )
    moderation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # SHA-256 hash of normalized text + company + rating for duplicate detection
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_verified_experience: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    company: Mapped[Optional["Company"]] = relationship("Company", back_populates="reviews")
    job_listing: Mapped[Optional["JobListing"]] = relationship("JobListing")
    scan_request: Mapped[Optional["ScanRequest"]] = relationship("ScanRequest", back_populates="reviews")
    user: Mapped[Optional["User"]] = relationship("User", back_populates="reviews")
    moderation_records: Mapped[List["ReviewModeration"]] = relationship(
        "ReviewModeration",
        back_populates="review",
        cascade="all, delete-orphan",
    )


class RecruiterReport(Base):
    """
    Community reports of suspected fraud, advance fees, or impersonation.
    Table 12 of PROJECT_SPECIFICATION.md (Feature F8).
    """

    __tablename__ = "recruiter_reports"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    company_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    claimed_company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    recruiter_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    recruiter_domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    job_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("job_listings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    scan_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("scan_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Non-reversible hash of IP + salt
    submitter_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    report_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(json_type, nullable=True)

    # Moderation state: PENDING, APPROVED, REJECTED, FLAGGED
    moderation_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PENDING",
        index=True,
    )
    moderation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # SHA-256 hash of report contents for duplicate detection
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    company: Mapped[Optional["Company"]] = relationship("Company", back_populates="recruiter_reports")
    job_listing: Mapped[Optional["JobListing"]] = relationship("JobListing")
    scan_request: Mapped[Optional["ScanRequest"]] = relationship("ScanRequest", back_populates="recruiter_reports")
    user: Mapped[Optional["User"]] = relationship("User", back_populates="reports")
    moderation_records: Mapped[List["ReviewModeration"]] = relationship(
        "ReviewModeration",
        back_populates="report",
        cascade="all, delete-orphan",
    )


class ReviewModeration(Base):
    """
    Audit log of moderation decisions and appeals on reviews and reports.
    Table 13 of PROJECT_SPECIFICATION.md.
    """

    __tablename__ = "review_moderation"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    target_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # 'review' or 'report'
    review_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("user_reviews.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    report_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("recruiter_reports.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    moderator_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(30), nullable=False)  # APPROVE, REJECT, FLAG, APPEAL_UPHELD, APPEAL_DISMISSED
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    appeal_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="NONE",
        index=True,
    )  # NONE, PENDING_APPEAL, APPEAL_UPHELD, APPEAL_DISMISSED
    audit_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(json_type, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    review: Mapped[Optional["UserReview"]] = relationship("UserReview", back_populates="moderation_records")
    report: Mapped[Optional["RecruiterReport"]] = relationship("RecruiterReport", back_populates="moderation_records")


class TrainingLabel(Base):
    """
    Explicitly validated, independently approved training labels.
    Table 14 of PROJECT_SPECIFICATION.md.

    CRITICAL SAFETY CONSTRAINT:
    Never populated or modified automatically by community reviews or reports.
    Only approved via explicit, authorized moderator review.
    """

    __tablename__ = "training_labels"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    scan_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("scan_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("job_listings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # FRAUDULENT, LEGITIMATE
    label_source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    validation_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PENDING_REVIEW",
        index=True,
    )  # PENDING_REVIEW, APPROVED, REJECTED
    reviewed_by: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    evidence_reference: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    validation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    approved_for_training_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # Relationships
    scan_request: Mapped[Optional["ScanRequest"]] = relationship("ScanRequest", back_populates="training_labels")
    job_listing: Mapped[Optional["JobListing"]] = relationship("JobListing")
