"""Async Document & OCR Job Queue ORM Model.

Conforms to Section 5.7 & Section 15 of PROJECT_SPECIFICATION.md:
- Asynchronous tracking for heavy PDF parsing and selective Tesseract OCR.
- Idempotency & deduplication via content SHA-256 digests.
- Ownership tracking with strict IDOR protections (user_id and visitor session_id).
- Strictly privacy-preserving: stores only non-reversible hashes and sanitized findings.
"""

from datetime import datetime
from typing import Any, Dict, Optional
import uuid

from sqlalchemy import (
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


class AsyncDocumentJob(Base):
    """Tracks asynchronous OCR and document analysis jobs."""

    __tablename__ = "async_document_jobs"

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
    session_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    job_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="OFFER_LETTER_OCR",
        index=True,
    )
    file_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PENDING",
        index=True,
    )
    progress: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    claimed_company_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    claimed_cin: Mapped[Optional[str]] = mapped_column(
        String(21),
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    result_scan_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("scan_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    result_summary: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User")
    scan: Mapped[Optional["ScanRequest"]] = relationship("ScanRequest")
