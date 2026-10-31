import json
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables and .env file.
    """
    APP_NAME: str = "JobShield AI"
    APP_ENV: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Database URL using psycopg (PostgreSQL 18)
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/jobshield_db"

    # CORS Allowed Origins
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    # Explicit Chrome Extension IDs whitelisted for credentialed cross-origin requests
    CHROME_EXTENSION_IDS: Union[List[str], str] = [
        "abcdefghijklmnopqrstuvwxyz123456",
    ]

    # Machine Learning Settings
    ML_MODEL_ARTIFACT_PATH: str = "ml/artifacts/jobshield_fraud_detector_v1.1.0.joblib"

    # Configurable Provisional Risk Engine Settings
    RISK_THRESHOLD_VERSION: str = "provisional_v1.0.0"
    RISK_SCORE_WEIGHT_ML: float = 0.55
    RISK_SCORE_WEIGHT_RULES: float = 0.45
    RISK_THRESHOLD_LOW: float = 30.0
    RISK_THRESHOLD_MODERATE: float = 60.0
    RISK_THRESHOLD_HIGH: float = 80.0
    MIN_JOB_TEXT_LENGTH: int = 20
    MAX_JOB_TEXT_LENGTH: int = 50000
    MIN_INFORMATIVE_WORDS: int = 10

    # Offer Letter Analyzer (F7) Settings
    MAX_OFFER_LETTER_UPLOAD_BYTES: int = 10 * 1024 * 1024  # 10 MB
    MAX_OFFER_LETTER_PAGES: int = 10
    OFFER_LETTER_TIMEOUT_SECONDS: int = 30
    TESSERACT_CMD: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    OCR_MAX_IMAGE_DIMENSION: int = 4096
    OCR_DPI: int = 150

    # Community Feedback & Reputation (F8 & F9) Settings
    REPUTATION_PRIOR_STRENGTH_M: float = 5.0
    REPUTATION_PRIOR_MEAN_C: float = 3.5
    COMMUNITY_RATE_LIMIT_PER_MINUTE: int = 5
    COMMUNITY_SALT: str = "jobshield-community-salt-2026"
    MODERATOR_SECRET_KEY: str = "jobshield-moderator-secret-key-2026"

    # Authentication, Session & RBAC Settings
    JWT_SECRET_KEY: str = "jobshield-jwt-dev-secret-key-change-in-production-2026-secure-32-bytes"
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "jobshield-ai"
    JWT_AUDIENCE: str = "jobshield-api"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    AUTH_COOKIE_NAME: str = "jobshield_access"
    REFRESH_COOKIE_NAME: str = "jobshield_refresh"
    AUTH_COOKIE_SECURE: bool = False
    AUTH_COOKIE_SAMESITE: str = "lax"
    AUTH_COOKIE_HTTPONLY: bool = True
    LOGIN_RATE_LIMIT_PER_MINUTE: int = 5

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            val = v.strip()
            if not val:
                return []
            if val.startswith("[") and val.endswith("]"):
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [origin.strip() for origin in val.split(",") if origin.strip()]
        elif isinstance(v, list):
            return [str(origin).strip() for origin in v if str(origin).strip()]
        return []

    @field_validator("CHROME_EXTENSION_IDS", mode="before")
    @classmethod
    def assemble_chrome_extension_ids(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            val = v.strip()
            if not val:
                return []
            if val.startswith("[") and val.endswith("]"):
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [ext_id.strip() for ext_id in val.split(",") if ext_id.strip()]
        elif isinstance(v, list):
            return [str(ext_id).strip() for ext_id in v if str(ext_id).strip()]
        return []


settings = Settings()
