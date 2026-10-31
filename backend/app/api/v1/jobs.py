"""Asynchronous Document Analysis & OCR Jobs API Router.

Conforms to Feature F7, Section 5.7 & Section 15 of PROJECT_SPECIFICATION.md:
- Enqueue heavy offer letter PDF parsing and selective OCR jobs asynchronously.
- Non-blocking execution with background task processing.
- Deduplication for identical uploaded file SHA-256 digests.
- Strict IDOR authorization: users can only monitor their own jobs.
- Privacy-preserving: zero raw text stored in job summaries.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user_optional
from app.db.session import SessionLocal, get_db
from app.models.user import User
from app.workers.ocr_worker import (
    JobAccessForbiddenError,
    JobNotFoundError,
    JobValidationError,
    enqueue_offer_letter_ocr_job,
    execute_offer_letter_ocr_job,
    get_job_status_idor_protected,
)

logger = logging.getLogger("jobshield.api.jobs")

router = APIRouter(prefix="/jobs", tags=["Async Document Jobs"])


class AsyncJobResponse(BaseModel):
    id: str = Field(..., description="Unique UUID job identifier")
    job_type: str = Field(..., description="Type of document job (e.g. OFFER_LETTER_OCR)")
    status: str = Field(..., description="'PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'")
    progress: int = Field(0, description="Job completion percentage (0 - 100)")
    file_name: str
    file_size_bytes: int
    is_new_job: bool = Field(True, description="False if this was a deduplicated reused job")
    error_message: Optional[str] = None
    result_scan_id: Optional[str] = None
    result_summary: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


def run_ocr_background_task(job_id: str, file_bytes: bytes) -> None:
    """Background task runner executing OCR processing asynchronously."""
    db = SessionLocal()
    try:
        execute_offer_letter_ocr_job(db=db, job_id=job_id, file_bytes=file_bytes)
    except Exception as exc:
        logger.error("Background OCR worker error for job_id=%s: %s", job_id, type(exc).__name__)
    finally:
        db.close()


@router.post(
    "/offer-letter/async",
    response_model=AsyncJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue Asynchronous Offer Letter OCR Job",
    description=(
        "Enqueues a heavy offer-letter PDF for asynchronous OCR extraction and recruitment fraud analysis. "
        "Returns 202 Accepted with a job ID for polling status. Enforces file limits and deduplication."
    ),
)
async def enqueue_offer_letter_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Offer letter PDF document"),
    company_name: Optional[str] = Form(None, description="Optional claimed employer name"),
    cin: Optional[str] = Form(None, description="Optional Corporate Identification Number (CIN)"),
    x_session_id: Optional[str] = Header(None, description="Optional visitor session identifier for IDOR tracking"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> AsyncJobResponse:
    clean_filename = Path(file.filename or "offer_letter.pdf").name

    try:
        file_bytes = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read uploaded file payload.",
        ) from exc

    try:
        job, is_new = enqueue_offer_letter_ocr_job(
            db=db,
            file_bytes=file_bytes,
            file_name=clean_filename,
            claimed_company_name=company_name.strip() if company_name else None,
            claimed_cin=cin.strip() if cin else None,
            current_user=current_user,
            session_id=x_session_id.strip() if x_session_id else None,
        )
    except JobValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # If new job, dispatch background processing
    if is_new and job.status == "PENDING":
        background_tasks.add_task(run_ocr_background_task, job_id=job.id, file_bytes=file_bytes)

    return AsyncJobResponse(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        file_name=job.file_name,
        file_size_bytes=job.file_size_bytes,
        is_new_job=is_new,
        error_message=job.error_message,
        result_scan_id=job.result_scan_id,
        result_summary=job.result_summary,
        created_at=job.created_at.isoformat() if job.created_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@router.get(
    "/{job_id}",
    response_model=AsyncJobResponse,
    summary="Get Asynchronous Job Status (IDOR Protected)",
    description="Retrieves the current processing status of an enqueued document job. Enforces IDOR security.",
)
def get_job_status(
    job_id: str,
    x_session_id: Optional[str] = Header(None, description="Optional visitor session identifier"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> AsyncJobResponse:
    try:
        job = get_job_status_idor_protected(
            db=db,
            job_id=job_id,
            current_user=current_user,
            session_id=x_session_id.strip() if x_session_id else None,
        )
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except JobAccessForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    return AsyncJobResponse(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        file_name=job.file_name,
        file_size_bytes=job.file_size_bytes,
        is_new_job=False,
        error_message=job.error_message,
        result_scan_id=job.result_scan_id,
        result_summary=job.result_summary,
        created_at=job.created_at.isoformat() if job.created_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@router.get(
    "/{job_id}/result",
    summary="Get Completed Job Result (IDOR Protected)",
    description="Returns the verified analysis summary once a document job is COMPLETED.",
)
def get_job_result(
    job_id: str,
    x_session_id: Optional[str] = Header(None, description="Optional visitor session identifier"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    try:
        job = get_job_status_idor_protected(
            db=db,
            job_id=job_id,
            current_user=current_user,
            session_id=x_session_id.strip() if x_session_id else None,
        )
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except JobAccessForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    if job.status == "FAILED":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=job.error_message or "Document processing failed.",
        )

    if job.status != "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is currently {job.status} (progress: {job.progress}%). Result is not yet available.",
        )

    return {
        "job_id": job.id,
        "status": job.status,
        "report_id": job.result_scan_id,
        "summary": job.result_summary,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
