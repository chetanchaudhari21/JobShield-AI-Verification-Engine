"""Recruiter email scans ORM model.

Conforms to Section 8 (Table 7) & Feature F3 of PROJECT_SPECIFICATION.md:
- Privacy-first: only stores masked email identifiers and SHA-256 hashes
- Tracks claimed company association and verification status
- Never tests mailbox existence via SMTP
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
import uuid
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.scan import ScanRequest


class RecruiterEmailScan(Base):
    """
    Audit log of recruiter email and communication verification scans.
    Table 7 of PROJECT_SPECIFICATION.md.
    """
    __tablename__ = "recruiter_email_scans"

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
    claimed_company_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    email_masked: Mapped[str] = mapped_column(String(255), nullable=False)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="IDENTITY_UNVERIFIED",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    retention_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    scan_request: Mapped[Optional["ScanRequest"]] = relationship(
        "ScanRequest",
        back_populates="recruiter_scan",
    )
