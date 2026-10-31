"""Pydantic schemas for Administrative Controls and Security Audit Logs."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class AdminUserListItem(BaseModel):
    """User summary for administrator oversight."""
    id: str
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    scans_count: int = 0

    class Config:
        from_attributes = True


class AdminUserListResponse(BaseModel):
    users: List[AdminUserListItem]
    total: int
    limit: int
    offset: int


class RoleUpdateRequest(BaseModel):
    """Admin role update schema."""
    role: str = Field(..., description="'USER', 'MODERATOR', or 'ADMIN'")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in ("USER", "MODERATOR", "ADMIN"):
            raise ValueError(f"Invalid role '{v}'. Allowed roles: 'USER', 'MODERATOR', 'ADMIN'.")
        return clean


class StatusUpdateRequest(BaseModel):
    """Admin user activation/deactivation schema."""
    is_active: bool


class SecurityAuditLogResponse(BaseModel):
    """Security audit trail entry."""
    id: str
    user_id: Optional[str] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SecurityAuditLogListResponse(BaseModel):
    logs: List[SecurityAuditLogResponse]
    total: int
    limit: int
    offset: int
