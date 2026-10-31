"""Offer Letter Scans ORM model.

Conforms to Feature F7 & Sections 5 and 11 of PROJECT_SPECIFICATION.md:
- Privacy-first: only stores safe extracted metadata, page references, and risk outcomes.
- Never stores PDF binaries or sensitive candidate PII (passwords, OTPs, bank accounts).
- Tracks OCR execution provenance, page count, and fee demands.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.scan import ScanRequest

json_type = JSON().with_variant(JSONB, "postgresql")


class OfferLetterScan(Base):
    """Audit log of offer letter scans and text/OCR extraction results."""

    __tablename__ = "offer_letter_scans"

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
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_scanned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ocr_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ocr_engine: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    claimed_company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    extracted_summary: Mapped[Optional[Dict[str, Any]]] = mapped_column(json_type, nullable=True)
    risk_category: Mapped[str] = mapped_column(String(20), nullable=False, default="LOW", index=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    has_fee_demand: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    has_sensitive_request: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

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
        back_populates="offer_scan",
    )
