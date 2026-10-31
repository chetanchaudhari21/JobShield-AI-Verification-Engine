"""0005_job_listings_and_similarity_matches

Revision ID: 0005_job_listings_and_similarity_matches
Revises: 0004_recruiter_email_scans
Create Date: 2026-10-16 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "0005_job_similarity"
down_revision: Union[str, None] = "0004_recruiter_email_scans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create job_listings table (Table 5 of PROJECT_SPECIFICATION.md)
    op.create_table(
        "job_listings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("normalized_url", sa.Text(), nullable=True),
        sa.Column("claimed_company_name", sa.String(length=255), nullable=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("job_title", sa.String(length=255), nullable=True),
        sa.Column("job_description", sa.Text(), nullable=True),
        sa.Column("job_location", sa.String(length=255), nullable=True),
        sa.Column("employment_type", sa.String(length=100), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_domain", sa.String(length=255), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False, server_default="DIRECT_INPUT"),
        sa.Column("extraction_status", sa.String(length=50), nullable=False, server_default="COMPLETED"),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_job_listings_id"), "job_listings", ["id"], unique=False)
    op.create_index(op.f("ix_job_listings_normalized_url"), "job_listings", ["normalized_url"], unique=False)
    op.create_index(op.f("ix_job_listings_claimed_company_name"), "job_listings", ["claimed_company_name"], unique=False)
    op.create_index(op.f("ix_job_listings_company_id"), "job_listings", ["company_id"], unique=False)
    op.create_index(op.f("ix_job_listings_job_title"), "job_listings", ["job_title"], unique=False)
    op.create_index(op.f("ix_job_listings_content_hash"), "job_listings", ["content_hash"], unique=False)
    op.create_index(op.f("ix_job_listings_source_domain"), "job_listings", ["source_domain"], unique=False)
    op.create_index(op.f("ix_job_listings_collected_at"), "job_listings", ["collected_at"], unique=False)

    # 2. Create job_similarity_matches table (Table 6 of PROJECT_SPECIFICATION.md)
    # Uses JSON with JSONB variant for PostgreSQL compatibility and SQLite test support
    json_type = sa.JSON().with_variant(JSONB, "postgresql")
    op.create_table(
        "job_similarity_matches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("listing_id_a", sa.String(length=36), sa.ForeignKey("job_listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("listing_id_b", sa.String(length=36), sa.ForeignKey("job_listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_exact_match", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("similarity_score", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("match_classification", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("supporting_evidence", json_type, nullable=True),
        sa.Column("contradictory_evidence", json_type, nullable=True),
        sa.Column("reasons", json_type, nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("algorithm_version", sa.String(length=50), nullable=False, server_default="tfidf_cosine_v1.0.0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("listing_id_a", "listing_id_b", name="uq_job_similarity_pair"),
        sa.CheckConstraint("listing_id_a < listing_id_b", name="ck_job_similarity_order"),
    )
    op.create_index(op.f("ix_job_similarity_matches_id"), "job_similarity_matches", ["id"], unique=False)
    op.create_index(op.f("ix_job_similarity_matches_listing_id_a"), "job_similarity_matches", ["listing_id_a"], unique=False)
    op.create_index(op.f("ix_job_similarity_matches_listing_id_b"), "job_similarity_matches", ["listing_id_b"], unique=False)
    op.create_index(op.f("ix_job_similarity_matches_match_classification"), "job_similarity_matches", ["match_classification"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_job_similarity_matches_match_classification"), table_name="job_similarity_matches")
    op.drop_index(op.f("ix_job_similarity_matches_listing_id_b"), table_name="job_similarity_matches")
    op.drop_index(op.f("ix_job_similarity_matches_listing_id_a"), table_name="job_similarity_matches")
    op.drop_index(op.f("ix_job_similarity_matches_id"), table_name="job_similarity_matches")
    op.drop_table("job_similarity_matches")

    op.drop_index(op.f("ix_job_listings_collected_at"), table_name="job_listings")
    op.drop_index(op.f("ix_job_listings_source_domain"), table_name="job_listings")
    op.drop_index(op.f("ix_job_listings_content_hash"), table_name="job_listings")
    op.drop_index(op.f("ix_job_listings_job_title"), table_name="job_listings")
    op.drop_index(op.f("ix_job_listings_company_id"), table_name="job_listings")
    op.drop_index(op.f("ix_job_listings_claimed_company_name"), table_name="job_listings")
    op.drop_index(op.f("ix_job_listings_normalized_url"), table_name="job_listings")
    op.drop_index(op.f("ix_job_listings_id"), table_name="job_listings")
    op.drop_table("job_listings")
