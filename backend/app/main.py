import logging
import re
from typing import Any, Dict
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings

logger = logging.getLogger("jobshield")
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Explainable AI-Powered Job & Internship Verification Platform",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Custom validation exception handler: strips raw submitted user text from validation error responses
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    sanitized_errors = []
    for err in exc.errors():
        err_copy = dict(err)
        # Redact raw input value to prevent user text from appearing in validation logs or client responses
        if "input" in err_copy:
            val = err_copy["input"]
            if isinstance(val, str) and len(val) > 0:
                err_copy["input"] = f"[REDACTED: len={len(val)}]"
            else:
                err_copy["input"] = "[REDACTED]"
        if "ctx" in err_copy:
            ctx = dict(err_copy["ctx"])
            if "error" in ctx:
                ctx["error"] = str(ctx["error"])
            err_copy["ctx"] = ctx
        sanitized_errors.append(err_copy)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": sanitized_errors},
    )

# Configure CORS from environment / settings
allowed_origins = list(settings.CORS_ORIGINS) if settings.CORS_ORIGINS else []
if settings.CHROME_EXTENSION_IDS:
    for ext_id in settings.CHROME_EXTENSION_IDS:
        allowed_origins.append(f"chrome-extension://{ext_id}")

# Strictly permit ONLY explicitly configured extension IDs — NO broad fallback
extension_origin_regex = (
    r"^chrome-extension://(" + "|".join(re.escape(i) for i in settings.CHROME_EXTENSION_IDS) + r")$"
    if settings.CHROME_EXTENSION_IDS
    else None
)

if allowed_origins:
    cors_kwargs = {
        "allow_origins": allowed_origins,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }
    if extension_origin_regex:
        cors_kwargs["allow_origin_regex"] = extension_origin_regex
    app.add_middleware(CORSMiddleware, **cors_kwargs)

# Register API v1 routes
from app.api.v1 import api_v1_router
app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)


def check_database_readiness() -> str:
    """
    Safely probe database connectivity using the central SQLAlchemy engine.
    Returns: 'ready', 'unavailable', or 'unconfigured'.
    Ensures connection strings and credentials are never exposed in responses or logs.
    """
    if not settings.DATABASE_URL:
        return "unconfigured"
    try:
        from sqlalchemy import text
        from app.db.session import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ready"
    except Exception as exc:
        # Log generic exception name only — NEVER log connection strings with credentials
        logger.warning("Database readiness probe failed: %s", type(exc).__name__)
        return "unavailable"


def check_ml_readiness() -> str:
    """
    Safely probe whether the required ML model artifact bundle is loaded and available.
    Returns: 'ready' or 'unavailable'.
    """
    try:
        from app.services.ml_inference import get_ml_service
        ml_svc = get_ml_service()
        return "ready" if ml_svc.is_available() else "unavailable"
    except Exception as exc:
        logger.warning("ML readiness probe failed: %s", type(exc).__name__)
        return "unavailable"


@app.get(
    "/health",
    tags=["Health"],
    summary="Liveness Probe",
    description="Returns 200 OK if the backend server process is running.",
)
async def health_liveness() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
    }


@app.get(
    "/api/v1/health/ready",
    tags=["Health"],
    summary="Readiness Probe",
    description="Evaluates dependency readiness without exposing secrets or connection strings.",
)
async def health_readiness(response: Response) -> Dict[str, Any]:
    db_status = check_database_readiness()
    ml_status = check_ml_readiness()
    is_ready = (db_status == "ready") and (ml_status == "ready")

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "environment": settings.APP_ENV,
            "dependencies": {
                "database": db_status,
                "ml_inference": ml_status,
            },
        }

    return {
        "status": "ready",
        "environment": settings.APP_ENV,
        "dependencies": {
            "database": db_status,
            "ml_inference": ml_status,
        },
    }


@app.get("/", tags=["Root"], include_in_schema=False)
async def root() -> Dict[str, Any]:
    return {
        "message": f"Welcome to {settings.APP_NAME} API. Visit /docs for OpenAPI documentation.",
        "status": "online",
    }
