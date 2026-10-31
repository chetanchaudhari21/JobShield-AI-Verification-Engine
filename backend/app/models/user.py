"""User Authentication, RBAC, Refresh Sessions, Security Audit & Appeals Models.

Conforms to Section 8, 9, 10 of PROJECT_SPECIFICATION.md:
- User identity with Argon2id hashed credentials and centralized RBAC roles
- Revocable refresh token session tracking with hash storage and reuse detection
- Security audit trail for admin actions, privilege changes, and authentication events
- Formal moderation appeals workflow with complete audit lifecycle
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.community import RecruiterReport, ReviewModeration, UserReview
    from app.models.scan import ScanRequest

json_type = JSON().with_variant(JSONB, "postgresql")


class User(Base):
    """Registered application user with assigned RBAC role."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Roles: 'VISITOR', 'USER', 'MODERATOR', 'ADMIN'
    role: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="USER",
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    scans: Mapped[List["ScanRequest"]] = relationship(
        "ScanRequest",
        back_populates="user",
        primaryjoin="foreign(ScanRequest.user_id) == User.id",
    )
    reviews: Mapped[List["UserReview"]] = relationship(
        "UserReview",
        back_populates="user",
    )
    reports: Mapped[List["RecruiterReport"]] = relationship(
        "RecruiterReport",
        back_populates="user",
    )
    appeals: Mapped[List["ModerationAppeal"]] = relationship(
        "ModerationAppeal",
        back_populates="user",
        foreign_keys="ModerationAppeal.user_id",
    )
    security_audit_logs: Mapped[List["SecurityAuditLog"]] = relationship(
        "SecurityAuditLog",
        back_populates="user",
    )


class RefreshToken(Base):
    """
    Revocable refresh token session with cryptographic SHA-256 hash storage.
    Raw tokens are NEVER stored in the database.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None


class SecurityAuditLog(Base):
    """
    Append-only security audit log recording administrative, moderation, and authentication actions.
    No application-level update or delete operations are exposed.
    """

    __tablename__ = "security_audit_logs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(json_type, nullable=True)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="security_audit_logs")


class ModerationAppeal(Base):
    """
    Formal appeals submitted by authenticated users challenging moderation decisions.
    """

    __tablename__ = "moderation_appeals"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    moderation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("review_moderation.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    appeal_reason: Mapped[str] = mapped_column(Text, nullable=False)

    # Lifecycle: 'PENDING', 'UPHELD', 'DISMISSED'
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PENDING",
        index=True,
    )
    reviewer_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    moderation_record: Mapped["ReviewModeration"] = relationship("ReviewModeration")
    user: Mapped[Optional["User"]] = relationship("User", back_populates="appeals", foreign_keys=[user_id])
