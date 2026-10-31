"""0008_auth_rbac_audit_and_appeals

Revision ID: 0008_auth_rbac_audit
Revises: 0007_community_feedback
Create Date: 2026-10-17 01:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0008_auth_rbac_audit"
down_revision: Union[str, None] = "0007_community_feedback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(JSONB, "postgresql")

    # 1. users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=30), nullable=False, server_default="USER"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)
    op.create_index(op.f("ix_users_is_active"), "users", ["is_active"], unique=False)
    op.create_index(op.f("ix_users_created_at"), "users", ["created_at"], unique=False)

    # 2. refresh_tokens table (revocable refresh sessions)
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_refresh_tokens_id"), "refresh_tokens", ["id"], unique=False)
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)
    op.create_index(op.f("ix_refresh_tokens_token_hash"), "refresh_tokens", ["token_hash"], unique=True)
    op.create_index(op.f("ix_refresh_tokens_expires_at"), "refresh_tokens", ["expires_at"], unique=False)
    op.create_index(op.f("ix_refresh_tokens_revoked_at"), "refresh_tokens", ["revoked_at"], unique=False)

    # 3. security_audit_logs table (append-only)
    op.create_table(
        "security_audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=True),
        sa.Column("target_id", sa.String(length=100), nullable=True),
        sa.Column("details", json_type, nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_security_audit_logs_id"), "security_audit_logs", ["id"], unique=False)
    op.create_index(op.f("ix_security_audit_logs_user_id"), "security_audit_logs", ["user_id"], unique=False)
    op.create_index(op.f("ix_security_audit_logs_action"), "security_audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_security_audit_logs_target_type"), "security_audit_logs", ["target_type"], unique=False)
    op.create_index(op.f("ix_security_audit_logs_created_at"), "security_audit_logs", ["created_at"], unique=False)

    # 4. moderation_appeals table
    op.create_table(
        "moderation_appeals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("moderation_id", sa.String(length=36), sa.ForeignKey("review_moderation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("appeal_reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING"),
        sa.Column("reviewer_id", sa.String(length=36), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_moderation_appeals_id"), "moderation_appeals", ["id"], unique=False)
    op.create_index(op.f("ix_moderation_appeals_moderation_id"), "moderation_appeals", ["moderation_id"], unique=False)
    op.create_index(op.f("ix_moderation_appeals_user_id"), "moderation_appeals", ["user_id"], unique=False)
    op.create_index(op.f("ix_moderation_appeals_status"), "moderation_appeals", ["status"], unique=False)
    op.create_index(op.f("ix_moderation_appeals_created_at"), "moderation_appeals", ["created_at"], unique=False)

    # 5. Add user_id column to user_reviews and recruiter_reports
    with op.batch_alter_table("user_reviews") as batch_op:
        batch_op.add_column(
            sa.Column("user_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_user_reviews_user_id", "users", ["user_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_index("ix_user_reviews_user_id", ["user_id"], unique=False)

    with op.batch_alter_table("recruiter_reports") as batch_op:
        batch_op.add_column(
            sa.Column("user_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_recruiter_reports_user_id", "users", ["user_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_index("ix_recruiter_reports_user_id", ["user_id"], unique=False)


def downgrade() -> None:
    # 5. Drop user_id columns and constraints
    with op.batch_alter_table("recruiter_reports") as batch_op:
        batch_op.drop_constraint("fk_recruiter_reports_user_id", type_="foreignkey")
        batch_op.drop_index("ix_recruiter_reports_user_id")
        batch_op.drop_column("user_id")

    with op.batch_alter_table("user_reviews") as batch_op:
        batch_op.drop_constraint("fk_user_reviews_user_id", type_="foreignkey")
        batch_op.drop_index("ix_user_reviews_user_id")
        batch_op.drop_column("user_id")

    # 4. Drop moderation_appeals
    op.drop_index(op.f("ix_moderation_appeals_created_at"), table_name="moderation_appeals")
    op.drop_index(op.f("ix_moderation_appeals_status"), table_name="moderation_appeals")
    op.drop_index(op.f("ix_moderation_appeals_user_id"), table_name="moderation_appeals")
    op.drop_index(op.f("ix_moderation_appeals_moderation_id"), table_name="moderation_appeals")
    op.drop_index(op.f("ix_moderation_appeals_id"), table_name="moderation_appeals")
    op.drop_table("moderation_appeals")

    # 3. Drop security_audit_logs
    op.drop_index(op.f("ix_security_audit_logs_created_at"), table_name="security_audit_logs")
    op.drop_index(op.f("ix_security_audit_logs_target_type"), table_name="security_audit_logs")
    op.drop_index(op.f("ix_security_audit_logs_action"), table_name="security_audit_logs")
    op.drop_index(op.f("ix_security_audit_logs_user_id"), table_name="security_audit_logs")
    op.drop_index(op.f("ix_security_audit_logs_id"), table_name="security_audit_logs")
    op.drop_table("security_audit_logs")

    # 2. Drop refresh_tokens
    op.drop_index(op.f("ix_refresh_tokens_revoked_at"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_expires_at"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_token_hash"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    # 1. Drop users
    op.drop_index(op.f("ix_users_created_at"), table_name="users")
    op.drop_index(op.f("ix_users_is_active"), table_name="users")
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
