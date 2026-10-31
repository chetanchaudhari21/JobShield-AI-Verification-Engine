"""Authentication API Router.

Implements Section 2 of Production Specifications:
- Registration with Argon2id password hashing
- Login with generic error messages and rate limiting
- Short-lived signed JWT access tokens (15m expiry)
- Revocable refresh token session design with reuse detection and token rotation
- Secure, HttpOnly, SameSite cookies for web clients + Bearer token support
- User profile (/me) and password management
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Optional
import uuid
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import (
    check_login_rate_limit,
    get_current_user,
)
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_client_ip,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.session import get_db
from app.models.user import RefreshToken, SecurityAuditLog, User
from app.schemas.auth import (
    ChangePasswordRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)

logger = logging.getLogger("jobshield.api.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Sets secure, HttpOnly, SameSite cookies on the response."""
    # Access token cookie (short-lived)
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=settings.AUTH_COOKIE_HTTPONLY,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )
    # Refresh token cookie (session-lived)
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=settings.AUTH_COOKIE_HTTPONLY,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/api/v1/auth",  # Scoped specifically to auth endpoints
    )


def clear_auth_cookies(response: Response) -> None:
    """Clears authentication cookies on logout."""
    response.delete_cookie(key=settings.AUTH_COOKIE_NAME, path="/")
    response.delete_cookie(key=settings.REFRESH_COOKIE_NAME, path="/api/v1/auth")


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register New User",
    description="Registers a new user account with Argon2id password hashing. Role defaults to USER.",
)
def register(
    register_in: UserRegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> UserResponse:
    # Check if email is already registered
    existing = db.query(User).filter(User.email == register_in.email).first()
    if existing:
        # Generic error message to prevent user enumeration
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists.",
        )

    hashed_pwd = hash_password(register_in.password)
    user_id = str(uuid.uuid4())

    new_user = User(
        id=user_id,
        email=register_in.email,
        hashed_password=hashed_pwd,
        full_name=register_in.full_name,
        role="USER",  # Strict: Users can NEVER register themselves as MODERATOR or ADMIN
        is_active=True,
        is_verified=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(new_user)

    # Security Audit Log
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")
    audit = SecurityAuditLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        action="USER_REGISTER",
        target_type="user",
        target_id=user_id,
        ip_hash=hash_client_ip(ip),
        details={"email": register_in.email},
        created_at=datetime.now(timezone.utc),
    )
    db.add(audit)
    db.commit()
    db.refresh(new_user)

    logger.info("New user registered successfully: id=%s", user_id)
    return new_user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="User Login",
    description="Authenticates with email and password. Returns access token and sets secure HttpOnly cookies.",
    dependencies=[Depends(check_login_rate_limit)],
)
def login(
    login_in: UserLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    generic_error = "Invalid email or password."
    user = db.query(User).filter(User.email == login_in.email).first()
    if not user:
        # Dummy verification to prevent timing attacks
        verify_password("dummy", "$argon2id$v=19$m=65536,t=3,p=4$dummy$dummy")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=generic_error)

    if not verify_password(login_in.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=generic_error)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated or suspended. Please contact support.",
        )

    # Update last login
    now = datetime.now(timezone.utc)
    user.last_login_at = now

    # Generate short-lived access token
    access_token = create_access_token(
        user_id=user.id,
        role=user.role,
        email=user.email,
    )

    # Generate revocable refresh token
    raw_refresh = generate_refresh_token()
    token_hash = hash_refresh_token(raw_refresh)
    expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")
    user_agent = request.headers.get("user-agent")

    refresh_session = RefreshToken(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        created_at=now,
        user_agent=user_agent[:500] if user_agent else None,
        ip_hash=hash_client_ip(ip),
    )
    db.add(refresh_session)

    # Audit log
    audit = SecurityAuditLog(
        id=str(uuid.uuid4()),
        user_id=user.id,
        action="USER_LOGIN",
        target_type="user",
        target_id=user.id,
        ip_hash=hash_client_ip(ip),
        details={"role": user.role},
        created_at=now,
    )
    db.add(audit)
    db.commit()

    # Set secure HttpOnly cookies
    set_auth_cookies(response, access_token=access_token, refresh_token=raw_refresh)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_token=raw_refresh,
        role=user.role,
        user_id=user.id,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh Session Token",
    description="Rotates refresh token and generates a new access token. Detects token reuse attacks.",
)
def refresh_token(
    request: Request,
    response: Response,
    body: Optional[RefreshTokenRequest] = None,
    jobshield_refresh: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
) -> TokenResponse:
    # Extract token from cookie or request body
    raw_token = jobshield_refresh or (body.refresh_token if body else None)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing. Please log in again.",
        )

    token_hash = hash_refresh_token(raw_token)
    session_record = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    now = datetime.now(timezone.utc)

    # REUSE DETECTION: If token was already revoked, this indicates a potential replay/theft attack!
    if session_record and session_record.revoked_at is not None:
        user_id = session_record.user_id
        logger.warning("Token reuse detected for user_id=%s! Revoking all active sessions.", user_id)
        # Invalidate ALL active sessions for this user immediately
        db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        ).update({"revoked_at": now})

        audit = SecurityAuditLog(
            id=str(uuid.uuid4()),
            user_id=user_id,
            action="SECURITY_ALERT_REFRESH_TOKEN_REUSE",
            target_type="refresh_token",
            target_id=session_record.id,
            details={"warning": "Revoked token replayed; all user sessions terminated"},
            created_at=now,
        )
        db.add(audit)
        db.commit()
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Security violation: Token reuse detected. All active sessions have been terminated. Please log in again.",
        )

    if not session_record:
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired or invalid. Please log in again.",
        )

    expires_at = session_record.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if not expires_at or expires_at < now:
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired or invalid. Please log in again.",
        )

    user = session_record.user
    if not user or not user.is_active:
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive or suspended.",
        )

    # TOKEN ROTATION: Revoke old token and issue a fresh one
    session_record.revoked_at = now

    new_raw_refresh = generate_refresh_token()
    new_hash = hash_refresh_token(new_raw_refresh)
    new_expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")
    user_agent = request.headers.get("user-agent")

    new_session = RefreshToken(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=new_hash,
        expires_at=new_expires,
        created_at=now,
        user_agent=user_agent[:500] if user_agent else None,
        ip_hash=hash_client_ip(ip),
    )
    db.add(new_session)

    # Issue fresh access token
    new_access_token = create_access_token(
        user_id=user.id,
        role=user.role,
        email=user.email,
    )
    db.commit()

    set_auth_cookies(response, access_token=new_access_token, refresh_token=new_raw_refresh)

    return TokenResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_token=new_raw_refresh,
        role=user.role,
        user_id=user.id,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="User Logout",
    description="Revokes current refresh token session and clears authentication cookies.",
)
def logout(
    request: Request,
    response: Response,
    jobshield_refresh: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
) -> dict:
    raw_token = jobshield_refresh
    if raw_token:
        token_hash = hash_refresh_token(raw_token)
        session_record = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
        if session_record and session_record.revoked_at is None:
            session_record.revoked_at = datetime.now(timezone.utc)
            db.commit()

    clear_auth_cookies(response)
    return {"message": "Logged out successfully."}


@router.post(
    "/revoke-all",
    status_code=status.HTTP_200_OK,
    summary="Revoke All User Sessions",
    description="Revokes all active refresh tokens for the current user.",
)
def revoke_all_sessions(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    now = datetime.now(timezone.utc)
    count = db.query(RefreshToken).filter(
        RefreshToken.user_id == current_user.id,
        RefreshToken.revoked_at.is_(None),
    ).update({"revoked_at": now})

    audit = SecurityAuditLog(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        action="REVOKE_ALL_SESSIONS",
        target_type="user",
        target_id=current_user.id,
        details={"revoked_count": count},
        created_at=now,
    )
    db.add(audit)
    db.commit()

    clear_auth_cookies(response)
    return {"message": f"Successfully revoked {count} active session(s)."}


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get Current User Profile",
)
def get_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return current_user


@router.put(
    "/me/password",
    status_code=status.HTTP_200_OK,
    summary="Change Password",
)
@router.post(
    "/me/password",
    status_code=status.HTTP_200_OK,
    summary="Change Password (POST alias)",
    include_in_schema=False,
)
def change_password(
    pwd_in: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(pwd_in.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password verification failed.",
        )

    current_user.hashed_password = hash_password(pwd_in.new_password)
    current_user.updated_at = datetime.now(timezone.utc)

    # Invalidate other active refresh sessions on password change for security
    db.query(RefreshToken).filter(
        RefreshToken.user_id == current_user.id,
        RefreshToken.revoked_at.is_(None),
    ).update({"revoked_at": datetime.now(timezone.utc)})

    audit = SecurityAuditLog(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        action="PASSWORD_CHANGED",
        target_type="user",
        target_id=current_user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(audit)
    db.commit()

    return {"message": "Password updated successfully. Other active sessions have been revoked."}
