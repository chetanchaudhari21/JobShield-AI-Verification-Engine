"""Core Cryptographic Security, Password Hashing, and JWT Token Services.

Conforms to Section 2 (Authentication) & Section 3 (RBAC) of Mandatory Requirements:
- Argon2id password hashing via argon2-cffi. Never store plaintext or weak hashes.
- Short-lived signed JWT access tokens with audience, issuer, and expiration validation.
- Revocable refresh token hashing (SHA-256) and generation with secrets.token_urlsafe.
- Privacy-preserving client IP hashing.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import re
import secrets
from typing import Any, Dict, Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
import jwt

from app.core.config import settings

logger = logging.getLogger("jobshield.core.security")

# Argon2id password hasher with RFC 9106 recommended parameters
# Memory: 64 MiB, Time iterations: 3, Parallelism: 4 threads, Hash length: 32 bytes
pwd_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Hashes a plaintext password using Argon2id with random salt."""
    if not password:
        raise ValueError("Password cannot be empty.")
    return pwd_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against an Argon2id hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return pwd_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def validate_password_strength(password: str) -> Optional[str]:
    """Validates that a password satisfies security requirements.

    Requirements:
    - Minimum 8 characters, maximum 128 characters.
    - At least one uppercase letter, one lowercase letter, and one digit.
    """
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if len(password) > 128:
        return "Password must not exceed 128 characters."
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return "Password must contain at least one lowercase letter."
    if not re.search(r"\d", password):
        return "Password must contain at least one digit."
    return None


def create_access_token(
    user_id: Optional[str] = None,
    role: str = "USER",
    email: str = "",
    expires_delta: Optional[timedelta] = None,
    subject: Optional[str] = None,
) -> str:
    """Creates a short-lived signed JWT access token.

    Claims:
    - sub: user_id
    - role: assigned RBAC role
    - email: user's normalized email
    - iss: configured issuer
    - aud: configured audience
    - exp: expiration timestamp
    - iat: issued-at timestamp
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    sub_val = str(user_id or subject or "")
    payload = {
        "sub": sub_val,
        "role": str(role).upper(),
        "email": str(email).lower(),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "exp": expire,
        "iat": now,
    }

    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decodes and validates a JWT access token.

    Validates signature, expiration, issuer, and audience.
    Raises jwt.PyJWTError on failure.
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        issuer=settings.JWT_ISSUER,
        audience=settings.JWT_AUDIENCE,
    )


def generate_refresh_token() -> str:
    """Generates a cryptographically strong URL-safe random string for refresh token."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """Computes SHA-256 digest of refresh token for database storage.

    CRITICAL SECURITY MANDATE: Raw refresh tokens are never stored in the database.
    """
    clean = token.strip().encode("utf-8")
    return hashlib.sha256(clean).hexdigest()


def hash_client_ip(ip: str, salt: Optional[str] = None) -> str:
    """Computes privacy-preserving salted cryptographic hash of client IP."""
    clean_ip = (ip or "127.0.0.1").strip()
    active_salt = salt or settings.COMMUNITY_SALT
    salted = f"{active_salt}:{clean_ip}".encode("utf-8")
    return hashlib.sha256(salted).hexdigest()
