"""0004_recruiter_email_scans

Revision ID: 0004_recruiter_email_scans
Revises: 0003_domain_checks
Create Date: 2026-10-15 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_recruiter_email_scans"
down_revision: Union[str, None] = "0003_domain_checks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recruiter_email_scans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scan_id", sa.String(length=36), sa.ForeignKey("scan_requests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("claimed_company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email_masked", sa.String(length=255), nullable=False),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="IDENTITY_UNVERIFIED"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_recruiter_email_scans_id"), "recruiter_email_scans", ["id"], unique=False)
    op.create_index(op.f("ix_recruiter_email_scans_scan_id"), "recruiter_email_scans", ["scan_id"], unique=False)
    op.create_index(op.f("ix_recruiter_email_scans_email_hash"), "recruiter_email_scans", ["email_hash"], unique=False)
    op.create_index(op.f("ix_recruiter_email_scans_domain"), "recruiter_email_scans", ["domain"], unique=False)
    op.create_index(op.f("ix_recruiter_email_scans_status"), "recruiter_email_scans", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_recruiter_email_scans_status"), table_name="recruiter_email_scans")
    op.drop_index(op.f("ix_recruiter_email_scans_domain"), table_name="recruiter_email_scans")
    op.drop_index(op.f("ix_recruiter_email_scans_email_hash"), table_name="recruiter_email_scans")
    op.drop_index(op.f("ix_recruiter_email_scans_scan_id"), table_name="recruiter_email_scans")
    op.drop_index(op.f("ix_recruiter_email_scans_id"), table_name="recruiter_email_scans")
    op.drop_table("recruiter_email_scans")
