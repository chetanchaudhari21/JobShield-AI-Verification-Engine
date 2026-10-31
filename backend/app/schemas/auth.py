"""Pydantic schemas for User Authentication and Account Management."""

from datetime import datetime
import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator

from app.core.security import validate_password_strength

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class UserRegisterRequest(BaseModel):
    """Registration schema.

    CRITICAL SECURITY MANDATE:
    Role cannot be specified by the user to prevent privilege escalation / mass assignment.
    """
    email: str = Field(..., max_length=255, description="Valid user email address")
    password: str = Field(..., min_length=8, max_length=128, description="Strong password (min 8 chars, 1 upper, 1 lower, 1 digit)")
    full_name: Optional[str] = Field(None, max_length=255, description="User full name")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email format.")
        return clean

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        err = validate_password_strength(v)
        if err:
            raise ValueError(err)
        return v


class UserLoginRequest(BaseModel):
    """User login request schema."""
    email: str = Field(..., max_length=255)
    password: str = Field(..., max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    """Access token and session metadata."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    role: str
    user_id: str


class RefreshTokenRequest(BaseModel):
    """Optional payload for clients unable to use HttpOnly cookies."""
    refresh_token: Optional[str] = None


class UserResponse(BaseModel):
    """Public user profile response."""
    id: str
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChangePasswordRequest(BaseModel):
    """Password modification schema."""
    current_password: str = Field(..., max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_pwd(cls, v: str) -> str:
        err = validate_password_strength(v)
        if err:
            raise ValueError(err)
        return v
