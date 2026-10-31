"""0003_domain_checks

Revision ID: 0003_domain_checks
Revises: 0002_companies_and_sources
Create Date: 2026-10-15 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_domain_checks"
down_revision: Union[str, None] = "0002_companies_and_sources"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "domain_checks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("dns_status", sa.String(length=50), nullable=False, server_default="UNKNOWN"),
        sa.Column("mx_status", sa.String(length=50), nullable=False, server_default="UNKNOWN"),
        sa.Column("spf_status", sa.String(length=50), nullable=False, server_default="UNKNOWN"),
        sa.Column("dkim_status", sa.String(length=50), nullable=False, server_default="UNKNOWN"),
        sa.Column("dmarc_status", sa.String(length=50), nullable=False, server_default="UNKNOWN"),
        sa.Column("lookalike_flags", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True),
        sa.Column("source_details", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_domain_checks_id"), "domain_checks", ["id"], unique=False)
    op.create_index(op.f("ix_domain_checks_domain"), "domain_checks", ["domain"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_domain_checks_domain"), table_name="domain_checks")
    op.drop_index(op.f("ix_domain_checks_id"), table_name="domain_checks")
    op.drop_table("domain_checks")
