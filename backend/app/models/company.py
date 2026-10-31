"""Company and Verification Source ORM Models for JobShield AI.

Conforms to Section 8 & Feature F2 of PROJECT_SPECIFICATION.md:
- Core company entity registry with canonical normalized names
- Independent source provenance records (MCA, DPIIT, etc.)
- Startup recognition status (DPIIT / Startup India)
- Verified and observed company domains
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.community import RecruiterReport, UserReview


class Company(Base):
    """
    Core company entity storing canonical legal name, normalized matching name,
    CIN (Corporate Identification Number) if available, and current registry status.
    """
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cin: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    registry_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    source_records: Mapped[List["CompanySourceRecord"]] = relationship(
        "CompanySourceRecord",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    startup_recognitions: Mapped[List["StartupRecognition"]] = relationship(
        "StartupRecognition",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    domains: Mapped[List["CompanyDomain"]] = relationship(
        "CompanyDomain",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    reviews: Mapped[List["UserReview"]] = relationship(
        "UserReview",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    recruiter_reports: Mapped[List["RecruiterReport"]] = relationship(
        "RecruiterReport",
        back_populates="company",
        cascade="all, delete-orphan",
    )


class CompanySourceRecord(Base):
    """
    Independent source record tracking dataset provenance, raw metadata,
    retrieval timestamps, match methodology, and confidence.
    """
    __tablename__ = "company_source_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_record_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    source_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    match_method: Mapped[str] = mapped_column(String(50), nullable=False)
    match_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    raw_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "raw_metadata",
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    company: Mapped["Company"] = relationship("Company", back_populates="source_records")


class StartupRecognition(Base):
    """
    Tracks DPIIT / Startup India recognition status, certificate number,
    checked timestamp, and status details.
    """
    __tablename__ = "startup_recognition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recognition_status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    recognition_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    status_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "status_details",
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    company: Mapped["Company"] = relationship("Company", back_populates="startup_recognitions")


class CompanyDomain(Base):
    """
    Tracks official and verified company web domains, MX routing domains,
    and verification evidence summaries.
    """
    __tablename__ = "company_domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="UNVERIFIED",
        index=True,
    )
    evidence_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    company: Mapped["Company"] = relationship("Company", back_populates="domains")
