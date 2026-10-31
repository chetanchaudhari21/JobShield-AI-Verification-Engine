"""0006_offer_letter_scans

Revision ID: 0006_offer_letter
Revises: 0005_job_similarity
Create Date: 2026-10-16 01:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0006_offer_letter"
down_revision: Union[str, None] = "0005_job_similarity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(JSONB, "postgresql")

    op.create_table(
        "offer_letter_scans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scan_id", sa.String(length=36), sa.ForeignKey("scan_requests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("is_scanned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ocr_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ocr_engine", sa.String(length=50), nullable=True),
        sa.Column("claimed_company_name", sa.String(length=255), nullable=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("extracted_summary", json_type, nullable=True),
        sa.Column("risk_category", sa.String(length=20), nullable=False, server_default="LOW"),
        sa.Column("risk_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("has_fee_demand", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("has_sensitive_request", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_offer_letter_scans_id"), "offer_letter_scans", ["id"], unique=False)
    op.create_index(op.f("ix_offer_letter_scans_scan_id"), "offer_letter_scans", ["scan_id"], unique=False)
    op.create_index(op.f("ix_offer_letter_scans_file_hash"), "offer_letter_scans", ["file_hash"], unique=False)
    op.create_index(op.f("ix_offer_letter_scans_claimed_company_name"), "offer_letter_scans", ["claimed_company_name"], unique=False)
    op.create_index(op.f("ix_offer_letter_scans_company_id"), "offer_letter_scans", ["company_id"], unique=False)
    op.create_index(op.f("ix_offer_letter_scans_risk_category"), "offer_letter_scans", ["risk_category"], unique=False)
    op.create_index(op.f("ix_offer_letter_scans_has_fee_demand"), "offer_letter_scans", ["has_fee_demand"], unique=False)
    op.create_index(op.f("ix_offer_letter_scans_has_sensitive_request"), "offer_letter_scans", ["has_sensitive_request"], unique=False)
    op.create_index(op.f("ix_offer_letter_scans_created_at"), "offer_letter_scans", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_offer_letter_scans_created_at"), table_name="offer_letter_scans")
    op.drop_index(op.f("ix_offer_letter_scans_has_sensitive_request"), table_name="offer_letter_scans")
    op.drop_index(op.f("ix_offer_letter_scans_has_fee_demand"), table_name="offer_letter_scans")
    op.drop_index(op.f("ix_offer_letter_scans_risk_category"), table_name="offer_letter_scans")
    op.drop_index(op.f("ix_offer_letter_scans_company_id"), table_name="offer_letter_scans")
    op.drop_index(op.f("ix_offer_letter_scans_claimed_company_name"), table_name="offer_letter_scans")
    op.drop_index(op.f("ix_offer_letter_scans_file_hash"), table_name="offer_letter_scans")
    op.drop_index(op.f("ix_offer_letter_scans_scan_id"), table_name="offer_letter_scans")
    op.drop_index(op.f("ix_offer_letter_scans_id"), table_name="offer_letter_scans")
    op.drop_table("offer_letter_scans")
