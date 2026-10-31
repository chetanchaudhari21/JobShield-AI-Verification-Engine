"""0001_initial_mvp_tables

Revision ID: 0001_initial_mvp
Revises: 
Create Date: 2026-10-12 23:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_mvp"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. scan_requests
    op.create_table(
        "scan_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("input_type", sa.String(length=50), nullable=False),
        sa.Column("input_reference", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scan_requests_id"), "scan_requests", ["id"], unique=False)
    op.create_index(op.f("ix_scan_requests_user_id"), "scan_requests", ["user_id"], unique=False)
    op.create_index(op.f("ix_scan_requests_status"), "scan_requests", ["status"], unique=False)
    op.create_index(op.f("ix_scan_requests_created_at"), "scan_requests", ["created_at"], unique=False)

    # 2. verification_evidence
    op.create_table(
        "verification_evidence",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_id", sa.String(length=36), nullable=False),
        sa.Column("evidence_type", sa.String(length=50), nullable=False),
        sa.Column("source_name", sa.String(length=100), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("limitations", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True),
        sa.ForeignKeyConstraint(["scan_id"], ["scan_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_verification_evidence_scan_id"), "verification_evidence", ["scan_id"], unique=False)
    op.create_index(op.f("ix_verification_evidence_evidence_type"), "verification_evidence", ["evidence_type"], unique=False)

    # 3. prediction_history
    op.create_table(
        "prediction_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_id", sa.String(length=36), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column("predicted_class", sa.String(length=50), nullable=False),
        sa.Column("model_probability", sa.Float(), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("risk_category", sa.String(length=30), nullable=False),
        sa.Column("threshold_version", sa.String(length=50), nullable=False),
        sa.Column("explanation", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["scan_id"], ["scan_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_prediction_history_scan_id"), "prediction_history", ["scan_id"], unique=False)
    op.create_index(op.f("ix_prediction_history_model_version"), "prediction_history", ["model_version"], unique=False)

    # 4. model_versions
    op.create_table(
        "model_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("artifact_path", sa.String(length=255), nullable=False),
        sa.Column("dataset_snapshot", sa.String(length=100), nullable=False),
        sa.Column("metrics", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True),
        sa.Column("calibration_summary", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True),
        sa.Column("evaluation_status", sa.String(length=50), nullable=False, server_default="candidate"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_model_versions_version"), "model_versions", ["version"], unique=True)

    # 5. dataset_imports
    op.create_table(
        "dataset_imports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_name", sa.String(length=100), nullable=False),
        sa.Column("version_or_snapshot", sa.String(length=100), nullable=False),
        sa.Column("license", sa.String(length=100), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("validation_summary", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dataset_imports_dataset_name"), "dataset_imports", ["dataset_name"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_dataset_imports_dataset_name"), table_name="dataset_imports")
    op.drop_table("dataset_imports")

    op.drop_index(op.f("ix_model_versions_version"), table_name="model_versions")
    op.drop_table("model_versions")

    op.drop_index(op.f("ix_prediction_history_model_version"), table_name="prediction_history")
    op.drop_index(op.f("ix_prediction_history_scan_id"), table_name="prediction_history")
    op.drop_table("prediction_history")

    op.drop_index(op.f("ix_verification_evidence_evidence_type"), table_name="verification_evidence")
    op.drop_index(op.f("ix_verification_evidence_scan_id"), table_name="verification_evidence")
    op.drop_table("verification_evidence")

    op.drop_index(op.f("ix_scan_requests_created_at"), table_name="scan_requests")
    op.drop_index(op.f("ix_scan_requests_status"), table_name="scan_requests")
    op.drop_index(op.f("ix_scan_requests_user_id"), table_name="scan_requests")
    op.drop_index(op.f("ix_scan_requests_id"), table_name="scan_requests")
    op.drop_table("scan_requests")
