"""0007_community_feedback_and_moderation

Revision ID: 0007_community_feedback
Revises: 0006_offer_letter
Create Date: 2026-10-17 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0007_community_feedback"
down_revision: Union[str, None] = "0006_offer_letter"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(JSONB, "postgresql")

    # 1. user_reviews (Table 11 of PROJECT_SPECIFICATION.md)
    op.create_table(
        "user_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("job_id", sa.String(length=36), sa.ForeignKey("job_listings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scan_id", sa.String(length=36), sa.ForeignKey("scan_requests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitter_hash", sa.String(length=64), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("experience_category", sa.String(length=50), nullable=False, server_default="GENERAL_EXPERIENCE"),
        sa.Column("review_text", sa.Text(), nullable=True),
        sa.Column("moderation_status", sa.String(length=30), nullable=False, server_default="PENDING"),
        sa.Column("moderation_reason", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("is_verified_experience", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="check_user_review_rating_range"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_reviews_id"), "user_reviews", ["id"], unique=False)
    op.create_index(op.f("ix_user_reviews_company_id"), "user_reviews", ["company_id"], unique=False)
    op.create_index(op.f("ix_user_reviews_job_id"), "user_reviews", ["job_id"], unique=False)
    op.create_index(op.f("ix_user_reviews_scan_id"), "user_reviews", ["scan_id"], unique=False)
    op.create_index(op.f("ix_user_reviews_submitter_hash"), "user_reviews", ["submitter_hash"], unique=False)
    op.create_index(op.f("ix_user_reviews_rating"), "user_reviews", ["rating"], unique=False)
    op.create_index(op.f("ix_user_reviews_experience_category"), "user_reviews", ["experience_category"], unique=False)
    op.create_index(op.f("ix_user_reviews_moderation_status"), "user_reviews", ["moderation_status"], unique=False)
    op.create_index(op.f("ix_user_reviews_content_hash"), "user_reviews", ["content_hash"], unique=False)
    op.create_index(op.f("ix_user_reviews_created_at"), "user_reviews", ["created_at"], unique=False)

    # 2. recruiter_reports (Table 12 of PROJECT_SPECIFICATION.md)
    op.create_table(
        "recruiter_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("claimed_company_name", sa.String(length=255), nullable=True),
        sa.Column("recruiter_email", sa.String(length=255), nullable=True),
        sa.Column("recruiter_domain", sa.String(length=255), nullable=True),
        sa.Column("job_id", sa.String(length=36), sa.ForeignKey("job_listings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scan_id", sa.String(length=36), sa.ForeignKey("scan_requests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitter_hash", sa.String(length=64), nullable=False),
        sa.Column("report_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("evidence_metadata", json_type, nullable=True),
        sa.Column("moderation_status", sa.String(length=30), nullable=False, server_default="PENDING"),
        sa.Column("moderation_reason", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_recruiter_reports_id"), "recruiter_reports", ["id"], unique=False)
    op.create_index(op.f("ix_recruiter_reports_company_id"), "recruiter_reports", ["company_id"], unique=False)
    op.create_index(op.f("ix_recruiter_reports_claimed_company_name"), "recruiter_reports", ["claimed_company_name"], unique=False)
    op.create_index(op.f("ix_recruiter_reports_recruiter_domain"), "recruiter_reports", ["recruiter_domain"], unique=False)
    op.create_index(op.f("ix_recruiter_reports_job_id"), "recruiter_reports", ["job_id"], unique=False)
    op.create_index(op.f("ix_recruiter_reports_scan_id"), "recruiter_reports", ["scan_id"], unique=False)
    op.create_index(op.f("ix_recruiter_reports_submitter_hash"), "recruiter_reports", ["submitter_hash"], unique=False)
    op.create_index(op.f("ix_recruiter_reports_report_type"), "recruiter_reports", ["report_type"], unique=False)
    op.create_index(op.f("ix_recruiter_reports_moderation_status"), "recruiter_reports", ["moderation_status"], unique=False)
    op.create_index(op.f("ix_recruiter_reports_content_hash"), "recruiter_reports", ["content_hash"], unique=False)
    op.create_index(op.f("ix_recruiter_reports_created_at"), "recruiter_reports", ["created_at"], unique=False)

    # 3. review_moderation (Table 13 of PROJECT_SPECIFICATION.md)
    op.create_table(
        "review_moderation",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("review_id", sa.String(length=36), sa.ForeignKey("user_reviews.id", ondelete="CASCADE"), nullable=True),
        sa.Column("report_id", sa.String(length=36), sa.ForeignKey("recruiter_reports.id", ondelete="CASCADE"), nullable=True),
        sa.Column("moderator_id", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("appeal_status", sa.String(length=30), nullable=False, server_default="NONE"),
        sa.Column("audit_metadata", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_review_moderation_id"), "review_moderation", ["id"], unique=False)
    op.create_index(op.f("ix_review_moderation_target_type"), "review_moderation", ["target_type"], unique=False)
    op.create_index(op.f("ix_review_moderation_review_id"), "review_moderation", ["review_id"], unique=False)
    op.create_index(op.f("ix_review_moderation_report_id"), "review_moderation", ["report_id"], unique=False)
    op.create_index(op.f("ix_review_moderation_moderator_id"), "review_moderation", ["moderator_id"], unique=False)
    op.create_index(op.f("ix_review_moderation_appeal_status"), "review_moderation", ["appeal_status"], unique=False)
    op.create_index(op.f("ix_review_moderation_created_at"), "review_moderation", ["created_at"], unique=False)

    # 4. training_labels (Table 14 of PROJECT_SPECIFICATION.md)
    op.create_table(
        "training_labels",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scan_id", sa.String(length=36), sa.ForeignKey("scan_requests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("job_id", sa.String(length=36), sa.ForeignKey("job_listings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("label", sa.String(length=50), nullable=False),
        sa.Column("label_source", sa.String(length=100), nullable=False),
        sa.Column("validation_status", sa.String(length=30), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("reviewed_by", sa.String(length=100), nullable=False),
        sa.Column("evidence_reference", sa.Text(), nullable=False),
        sa.Column("dataset_version", sa.String(length=50), nullable=True),
        sa.Column("validation_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("approved_for_training_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_training_labels_id"), "training_labels", ["id"], unique=False)
    op.create_index(op.f("ix_training_labels_scan_id"), "training_labels", ["scan_id"], unique=False)
    op.create_index(op.f("ix_training_labels_job_id"), "training_labels", ["job_id"], unique=False)
    op.create_index(op.f("ix_training_labels_label"), "training_labels", ["label"], unique=False)
    op.create_index(op.f("ix_training_labels_label_source"), "training_labels", ["label_source"], unique=False)
    op.create_index(op.f("ix_training_labels_validation_status"), "training_labels", ["validation_status"], unique=False)
    op.create_index(op.f("ix_training_labels_reviewed_by"), "training_labels", ["reviewed_by"], unique=False)
    op.create_index(op.f("ix_training_labels_created_at"), "training_labels", ["created_at"], unique=False)
    op.create_index(op.f("ix_training_labels_approved_for_training_at"), "training_labels", ["approved_for_training_at"], unique=False)


def downgrade() -> None:
    # Drop tables in reverse dependency order
    # 4. training_labels
    op.drop_index(op.f("ix_training_labels_approved_for_training_at"), table_name="training_labels")
    op.drop_index(op.f("ix_training_labels_created_at"), table_name="training_labels")
    op.drop_index(op.f("ix_training_labels_reviewed_by"), table_name="training_labels")
    op.drop_index(op.f("ix_training_labels_validation_status"), table_name="training_labels")
    op.drop_index(op.f("ix_training_labels_label_source"), table_name="training_labels")
    op.drop_index(op.f("ix_training_labels_label"), table_name="training_labels")
    op.drop_index(op.f("ix_training_labels_job_id"), table_name="training_labels")
    op.drop_index(op.f("ix_training_labels_scan_id"), table_name="training_labels")
    op.drop_index(op.f("ix_training_labels_id"), table_name="training_labels")
    op.drop_table("training_labels")

    # 3. review_moderation
    op.drop_index(op.f("ix_review_moderation_created_at"), table_name="review_moderation")
    op.drop_index(op.f("ix_review_moderation_appeal_status"), table_name="review_moderation")
    op.drop_index(op.f("ix_review_moderation_moderator_id"), table_name="review_moderation")
    op.drop_index(op.f("ix_review_moderation_report_id"), table_name="review_moderation")
    op.drop_index(op.f("ix_review_moderation_review_id"), table_name="review_moderation")
    op.drop_index(op.f("ix_review_moderation_target_type"), table_name="review_moderation")
    op.drop_index(op.f("ix_review_moderation_id"), table_name="review_moderation")
    op.drop_table("review_moderation")

    # 2. recruiter_reports
    op.drop_index(op.f("ix_recruiter_reports_created_at"), table_name="recruiter_reports")
    op.drop_index(op.f("ix_recruiter_reports_content_hash"), table_name="recruiter_reports")
    op.drop_index(op.f("ix_recruiter_reports_moderation_status"), table_name="recruiter_reports")
    op.drop_index(op.f("ix_recruiter_reports_report_type"), table_name="recruiter_reports")
    op.drop_index(op.f("ix_recruiter_reports_submitter_hash"), table_name="recruiter_reports")
    op.drop_index(op.f("ix_recruiter_reports_scan_id"), table_name="recruiter_reports")
    op.drop_index(op.f("ix_recruiter_reports_job_id"), table_name="recruiter_reports")
    op.drop_index(op.f("ix_recruiter_reports_recruiter_domain"), table_name="recruiter_reports")
    op.drop_index(op.f("ix_recruiter_reports_claimed_company_name"), table_name="recruiter_reports")
    op.drop_index(op.f("ix_recruiter_reports_company_id"), table_name="recruiter_reports")
    op.drop_index(op.f("ix_recruiter_reports_id"), table_name="recruiter_reports")
    op.drop_table("recruiter_reports")

    # 1. user_reviews
    op.drop_index(op.f("ix_user_reviews_created_at"), table_name="user_reviews")
    op.drop_index(op.f("ix_user_reviews_content_hash"), table_name="user_reviews")
    op.drop_index(op.f("ix_user_reviews_moderation_status"), table_name="user_reviews")
    op.drop_index(op.f("ix_user_reviews_experience_category"), table_name="user_reviews")
    op.drop_index(op.f("ix_user_reviews_rating"), table_name="user_reviews")
    op.drop_index(op.f("ix_user_reviews_submitter_hash"), table_name="user_reviews")
    op.drop_index(op.f("ix_user_reviews_scan_id"), table_name="user_reviews")
    op.drop_index(op.f("ix_user_reviews_job_id"), table_name="user_reviews")
    op.drop_index(op.f("ix_user_reviews_company_id"), table_name="user_reviews")
    op.drop_index(op.f("ix_user_reviews_id"), table_name="user_reviews")
    op.drop_table("user_reviews")
