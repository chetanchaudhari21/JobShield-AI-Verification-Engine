"""Job Listings and Similarity Matches ORM models.

Conforms to Section 8 (Tables 5 & 6) and Feature F4/F5 of PROJECT_SPECIFICATION.md:
- Ingested and registered job listings with normalized text, content hashes, and metadata
- Exact-hash and TF-IDF cosine similarity matches between listings
- Deduplication and impersonation tracking with strictly ordered unique pairs
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base


class JobListing(Base):
    """
    Stored job listing repository record.
    Table 5 of PROJECT_SPECIFICATION.md.
    """
    __tablename__ = "job_listings"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    normalized_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)
    claimed_company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    job_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    job_location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    employment_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="DIRECT_INPUT")
    extraction_status: Mapped[str] = mapped_column(String(50), nullable=False, default="COMPLETED")
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
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
    company: Mapped[Optional["Company"]] = relationship("Company", foreign_keys=[company_id])
    matches_as_a: Mapped[List["JobSimilarityMatch"]] = relationship(
        "JobSimilarityMatch",
        foreign_keys="JobSimilarityMatch.listing_id_a",
        back_populates="listing_a",
        cascade="all, delete-orphan",
    )
    matches_as_b: Mapped[List["JobSimilarityMatch"]] = relationship(
        "JobSimilarityMatch",
        foreign_keys="JobSimilarityMatch.listing_id_b",
        back_populates="listing_b",
        cascade="all, delete-orphan",
    )


class JobSimilarityMatch(Base):
    """
    Exact and near-duplicate similarity match record between two listings.
    Table 6 of PROJECT_SPECIFICATION.md.
    Enforces listing_id_a < listing_id_b to guarantee single directional uniqueness.
    """
    __tablename__ = "job_similarity_matches"
    __table_args__ = (
        UniqueConstraint("listing_id_a", "listing_id_b", name="uq_job_similarity_pair"),
        CheckConstraint("listing_id_a < listing_id_b", name="ck_job_similarity_order"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    listing_id_a: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("job_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    listing_id_b: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("job_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_exact_match: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    match_classification: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    supporting_evidence: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    contradictory_evidence: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    reasons: Mapped[Optional[List[str]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    algorithm_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="tfidf_cosine_v1.0.0",
    )

    # Relationships
    listing_a: Mapped["JobListing"] = relationship("JobListing", foreign_keys=[listing_id_a], back_populates="matches_as_a")
    listing_b: Mapped["JobListing"] = relationship("JobListing", foreign_keys=[listing_id_b], back_populates="matches_as_b")
