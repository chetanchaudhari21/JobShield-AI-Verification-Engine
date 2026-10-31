"""0002_companies_and_sources

Revision ID: 0002_companies_and_sources
Revises: 0001_initial_mvp
Create Date: 2026-10-13 23:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_companies_and_sources"
down_revision: Union[str, None] = "0001_initial_mvp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. companies
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("cin", sa.String(length=50), nullable=True),
        sa.Column("entity_type", sa.String(length=100), nullable=True),
        sa.Column("registry_status", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_companies_id"), "companies", ["id"], unique=False)
    op.create_index(op.f("ix_companies_normalized_name"), "companies", ["normalized_name"], unique=False)
    op.create_index(op.f("ix_companies_cin"), "companies", ["cin"], unique=False)
    op.create_index(op.f("ix_companies_registry_status"), "companies", ["registry_status"], unique=False)

    # 2. company_source_records
    op.create_table(
        "company_source_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=100), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_record_id", sa.String(length=100), nullable=True),
        sa.Column("source_status", sa.String(length=50), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("match_method", sa.String(length=50), nullable=False),
        sa.Column("match_confidence", sa.Float(), server_default=sa.text("1.0"), nullable=False),
        sa.Column("raw_metadata", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_company_source_records_id"), "company_source_records", ["id"], unique=False)
    op.create_index(op.f("ix_company_source_records_company_id"), "company_source_records", ["company_id"], unique=False)
    op.create_index(op.f("ix_company_source_records_source_name"), "company_source_records", ["source_name"], unique=False)
    op.create_index(op.f("ix_company_source_records_source_record_id"), "company_source_records", ["source_record_id"], unique=False)

    # 3. startup_recognition
    op.create_table(
        "startup_recognition",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("recognition_status", sa.String(length=50), nullable=False),
        sa.Column("recognition_id", sa.String(length=100), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("status_details", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_startup_recognition_id"), "startup_recognition", ["id"], unique=False)
    op.create_index(op.f("ix_startup_recognition_company_id"), "startup_recognition", ["company_id"], unique=False)
    op.create_index(op.f("ix_startup_recognition_recognition_status"), "startup_recognition", ["recognition_status"], unique=False)
    op.create_index(op.f("ix_startup_recognition_recognition_id"), "startup_recognition", ["recognition_id"], unique=False)

    # 4. company_domains
    op.create_table(
        "company_domains",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("verification_status", sa.String(length=50), server_default="UNVERIFIED", nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_company_domains_id"), "company_domains", ["id"], unique=False)
    op.create_index(op.f("ix_company_domains_company_id"), "company_domains", ["company_id"], unique=False)
    op.create_index(op.f("ix_company_domains_domain"), "company_domains", ["domain"], unique=False)
    op.create_index(op.f("ix_company_domains_verification_status"), "company_domains", ["verification_status"], unique=False)


def downgrade() -> None:
    # 4. company_domains
    op.drop_index(op.f("ix_company_domains_verification_status"), table_name="company_domains")
    op.drop_index(op.f("ix_company_domains_domain"), table_name="company_domains")
    op.drop_index(op.f("ix_company_domains_company_id"), table_name="company_domains")
    op.drop_index(op.f("ix_company_domains_id"), table_name="company_domains")
    op.drop_table("company_domains")

    # 3. startup_recognition
    op.drop_index(op.f("ix_startup_recognition_recognition_id"), table_name="startup_recognition")
    op.drop_index(op.f("ix_startup_recognition_recognition_status"), table_name="startup_recognition")
    op.drop_index(op.f("ix_startup_recognition_company_id"), table_name="startup_recognition")
    op.drop_index(op.f("ix_startup_recognition_id"), table_name="startup_recognition")
    op.drop_table("startup_recognition")

    # 2. company_source_records
    op.drop_index(op.f("ix_company_source_records_source_record_id"), table_name="company_source_records")
    op.drop_index(op.f("ix_company_source_records_source_name"), table_name="company_source_records")
    op.drop_index(op.f("ix_company_source_records_company_id"), table_name="company_source_records")
    op.drop_index(op.f("ix_company_source_records_id"), table_name="company_source_records")
    op.drop_table("company_source_records")

    # 1. companies
    op.drop_index(op.f("ix_companies_registry_status"), table_name="companies")
    op.drop_index(op.f("ix_companies_cin"), table_name="companies")
    op.drop_index(op.f("ix_companies_normalized_name"), table_name="companies")
    op.drop_index(op.f("ix_companies_id"), table_name="companies")
    op.drop_table("companies")
