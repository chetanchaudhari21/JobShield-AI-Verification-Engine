import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.community import RecruiterReport, TrainingLabel, UserReview
    from app.models.offer import OfferLetterScan
    from app.models.recruiter import RecruiterEmailScan
    from app.models.user import User


class ScanRequest(Base):
    """
    Represents an analysis request for a job posting, recruiter email, or offer letter.
    """
    __tablename__ = "scan_requests"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    input_type: Mapped[str] = mapped_column(String(50), nullable=False)
    input_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    retention_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    evidence_records: Mapped[List["VerificationEvidence"]] = relationship(
        "VerificationEvidence",
        back_populates="scan_request",
        cascade="all, delete-orphan",
    )
    prediction_records: Mapped[List["PredictionHistory"]] = relationship(
        "PredictionHistory",
        back_populates="scan_request",
        cascade="all, delete-orphan",
    )
    offer_scan: Mapped[Optional["OfferLetterScan"]] = relationship(
        "OfferLetterScan",
        back_populates="scan_request",
        uselist=False,
        cascade="all, delete-orphan",
    )
    recruiter_scan: Mapped[Optional["RecruiterEmailScan"]] = relationship(
        "RecruiterEmailScan",
        back_populates="scan_request",
        uselist=False,
        cascade="all, delete-orphan",
    )
    reviews: Mapped[List["UserReview"]] = relationship(
        "UserReview",
        back_populates="scan_request",
    )
    recruiter_reports: Mapped[List["RecruiterReport"]] = relationship(
        "RecruiterReport",
        back_populates="scan_request",
    )
    training_labels: Mapped[List["TrainingLabel"]] = relationship(
        "TrainingLabel",
        back_populates="scan_request",
    )
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="scans",
        primaryjoin="foreign(ScanRequest.user_id) == User.id",
    )
