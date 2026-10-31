"""0009_async_document_jobs

Revision ID: 0009_async_document_jobs
Revises: 0008_auth_rbac_audit
Create Date: 2026-10-18 00:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0009_async_document_jobs"
down_revision: Union[str, None] = "0008_auth_rbac_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(JSONB, "postgresql")

    op.create_table(
        "async_document_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("job_type", sa.String(length=50), nullable=False, server_default="OFFER_LETTER_OCR"),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed_company_name", sa.String(length=255), nullable=True),
        sa.Column("claimed_cin", sa.String(length=21), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_scan_id", sa.String(length=36), nullable=True),
        sa.Column("result_summary", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["result_scan_id"], ["scan_requests.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(op.f("ix_async_document_jobs_id"), "async_document_jobs", ["id"], unique=False)
    op.create_index(op.f("ix_async_document_jobs_user_id"), "async_document_jobs", ["user_id"], unique=False)
    op.create_index(op.f("ix_async_document_jobs_session_id"), "async_document_jobs", ["session_id"], unique=False)
    op.create_index(op.f("ix_async_document_jobs_job_type"), "async_document_jobs", ["job_type"], unique=False)
    op.create_index(op.f("ix_async_document_jobs_file_sha256"), "async_document_jobs", ["file_sha256"], unique=False)
    op.create_index(op.f("ix_async_document_jobs_status"), "async_document_jobs", ["status"], unique=False)
    op.create_index(op.f("ix_async_document_jobs_created_at"), "async_document_jobs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_async_document_jobs_created_at"), table_name="async_document_jobs")
    op.drop_index(op.f("ix_async_document_jobs_status"), table_name="async_document_jobs")
    op.drop_index(op.f("ix_async_document_jobs_file_sha256"), table_name="async_document_jobs")
    op.drop_index(op.f("ix_async_document_jobs_job_type"), table_name="async_document_jobs")
    op.drop_index(op.f("ix_async_document_jobs_session_id"), table_name="async_document_jobs")
    op.drop_index(op.f("ix_async_document_jobs_user_id"), table_name="async_document_jobs")
    op.drop_index(op.f("ix_async_document_jobs_id"), table_name="async_document_jobs")
    op.drop_table("async_document_jobs")
