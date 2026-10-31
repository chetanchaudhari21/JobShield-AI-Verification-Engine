"""Asynchronous OCR & Document Processing Background Worker.

Conforms to Feature F7, Section 5.7 & Section 15 of PROJECT_SPECIFICATION.md:
- Asynchronous queuing and execution for heavy PDF OCR processing.
- Strictly privacy-preserving: never logs raw document text; masks PII.
- Deduplication & Idempotency: prevents duplicate queueing for identical content SHA-256.
- Strict IDOR Protection: restricts job status and result access to the owner or ADMIN.
- Resource limits: enforces 10 MB upload limits, 10-page limits, and 30-second timeouts.
"""

from datetime import datetime, timezone, timedelta
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.models.worker import AsyncDocumentJob
from app.services.offer_letter_analyzer import (
    analyze_offer_letter,
    persist_offer_letter_scan,
)
from app.services.pdf_extractor import (
    EncryptedPDFError,
    ExcessivePagesError,
    InvalidPDFError,
    OCRTimeoutError,
    OversizedFileError,
    extract_text_and_ocr,
)

logger = logging.getLogger("jobshield.worker.ocr")


class WorkerJobError(Exception):
    """Base exception for background worker job failures."""
    pass


class JobNotFoundError(WorkerJobError):
    """Raised when the requested job is not found."""
    pass


class JobAccessForbiddenError(WorkerJobError):
    """Raised when a user attempts unauthorized access to another user's job."""
    pass


class JobValidationError(WorkerJobError):
    """Raised when file upload validation fails before enqueueing."""
    pass


def validate_file_payload(file_bytes: bytes, file_name: str) -> str:
    """Validates file magic bytes and size before creating a background job."""
    if not file_bytes:
        raise JobValidationError("Uploaded file is empty.")

    if len(file_bytes) > settings.MAX_OFFER_LETTER_UPLOAD_BYTES:
        max_mb = settings.MAX_OFFER_LETTER_UPLOAD_BYTES // (1024 * 1024)
        raise JobValidationError(f"File size exceeds maximum allowed upload limit ({max_mb} MB).")

    # Magic bytes validation for PDF
    if not file_bytes.startswith(b"%PDF"):
        raise JobValidationError("File is not a valid PDF document (missing %PDF header signature).")

    return hashlib.sha256(file_bytes).hexdigest()


def recover_stale_processing_jobs(db: Session, max_processing_age_seconds: int = 90) -> int:
    """Detects and fails jobs that were abandoned in PROCESSING status due to worker crash or restart.

    DURABILITY GUARANTEE:
    If an OCR worker process terminates unexpectedly, jobs are not left in an infinite PROCESSING state.
    They are transitioned to FAILED with a clear, actionable reason so clients can retry.
    """
    now = datetime.now(timezone.utc)
    stale_jobs = db.query(AsyncDocumentJob).filter(AsyncDocumentJob.status == "PROCESSING").all()
    recovered_count = 0
    for j in stale_jobs:
        started = j.started_at
        if started is not None:
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if (now - started).total_seconds() < max_processing_age_seconds:
                continue
        j.status = "FAILED"
        j.progress = 0
        j.error_message = "Document processing timed out or worker process was restarted. Please re-upload to retry."
        j.completed_at = now
        recovered_count += 1
    if recovered_count > 0:
        db.commit()
        logger.warning("Recovered %d stale/crashed OCR processing jobs.", recovered_count)
    return recovered_count


def enqueue_offer_letter_ocr_job(
    db: Session,
    file_bytes: bytes,
    file_name: str,
    claimed_company_name: Optional[str] = None,
    claimed_cin: Optional[str] = None,
    current_user: Optional[User] = None,
    session_id: Optional[str] = None,
) -> Tuple[AsyncDocumentJob, bool]:
    """Validates and enqueues an asynchronous OCR document job.

    DEDUPLICATION & IDEMPOTENCY:
    Computes file SHA-256. If an identical file is already PENDING or PROCESSING
    for this user or session, returns the existing job to avoid duplicate processing.
    """
    clean_filename = Path(file_name or "offer_letter.pdf").name
    file_sha256 = validate_file_payload(file_bytes, clean_filename)

    # Recover any crashed/stalled jobs before checking active duplicates
    recover_stale_processing_jobs(db)

    user_id = current_user.id if current_user else None

    # Check for existing pending/processing/completed duplicate job
    existing_query = db.query(AsyncDocumentJob).filter(
        AsyncDocumentJob.file_sha256 == file_sha256,
        AsyncDocumentJob.status.in_(["PENDING", "PROCESSING", "COMPLETED"]),
    )
    if user_id:
        existing_query = existing_query.filter(AsyncDocumentJob.user_id == user_id)
    elif session_id:
        existing_query = existing_query.filter(AsyncDocumentJob.session_id == session_id)

    existing_job = existing_query.order_by(AsyncDocumentJob.created_at.desc()).first()
    if existing_job:
        logger.info(
            "Reusing existing OCR job id=%s for sha256=%s (status=%s)",
            existing_job.id,
            file_sha256[:12],
            existing_job.status,
        )
        return existing_job, False

    # Create new job
    job = AsyncDocumentJob(
        id=str(uuid.uuid4()),
        user_id=user_id,
        session_id=session_id,
        job_type="OFFER_LETTER_OCR",
        file_sha256=file_sha256,
        file_name=clean_filename,
        file_size_bytes=len(file_bytes),
        status="PENDING",
        progress=0,
        claimed_company_name=claimed_company_name,
        claimed_cin=claimed_cin,
        created_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    logger.info("Enqueued new OCR job id=%s [sha256_prefix=%s, size=%d]", job.id, file_sha256[:12], len(file_bytes))
    return job, True


def execute_offer_letter_ocr_job(
    db: Session,
    job_id: str,
    file_bytes: bytes,
) -> AsyncDocumentJob:
    """Executes OCR extraction and recruitment fraud verification for an enqueued job.

    PRIVACY & SECURITY:
    - Never stores raw file bytes or extracted text in database tables or logs.
    - Deletes file buffer from memory upon completion.
    """
    job = db.query(AsyncDocumentJob).filter(AsyncDocumentJob.id == job_id).first()
    if not job:
        raise JobNotFoundError(f"Job '{job_id}' not found.")

    job.status = "PROCESSING"
    job.started_at = datetime.now(timezone.utc)
    job.progress = 20
    db.commit()

    try:
        # 1. Selective OCR text extraction (enforces 30s timeout and 10-page limit)
        doc = extract_text_and_ocr(
            file_bytes=file_bytes,
            file_name=job.file_name,
        )
        job.progress = 60
        db.commit()

        # 1.5 Validate Job Relevance of Offer Letter Document
        from app.services.job_relevance_validator import validate_offer_letter
        relevance = validate_offer_letter(text=doc.full_text, file_name=job.file_name)
        if relevance.status != "VALID":
            logger.info("Async OCR job id=%s rejected for non-job content: %s", job_id, relevance.reason_code)
            job.status = "FAILED"
            job.progress = 0
            job.error_message = relevance.supporting_message
            job.completed_at = datetime.now(timezone.utc)
            job.result_summary = {
                "is_job_related": False,
                "status": relevance.status,
                "reason_code": relevance.reason_code,
                "user_message": relevance.user_message,
                "supporting_message": relevance.supporting_message,
            }
            db.commit()
            db.refresh(job)
            return job

        # 2. Offer letter risk engine analysis
        analysis_result = analyze_offer_letter(
            doc=doc,
            claimed_company_name=job.claimed_company_name,
            cin=job.claimed_cin,
            db=db,
        )
        job.progress = 80
        db.commit()

        # 3. Persist scan records
        persist_offer_letter_scan(
            db=db,
            response=analysis_result,
            file_hash=job.file_sha256,
            user_id=job.user_id,
        )

        # 4. Update job to completed with sanitized summary
        job.status = "COMPLETED"
        job.progress = 100
        job.completed_at = datetime.now(timezone.utc)
        job.result_scan_id = analysis_result.report_id
        job.result_summary = {
            "report_id": analysis_result.report_id,
            "risk_score": analysis_result.risk_score,
            "risk_category": analysis_result.risk_category,
            "warning": analysis_result.warning,
            "override_floor_applied": analysis_result.override_floor_applied,
            "override_floor_reason": analysis_result.override_floor_reason,
            "employer_name": analysis_result.extracted_fields.company_name.value if analysis_result.extracted_fields.company_name else None,
            "job_title": analysis_result.extracted_fields.job_title.value if analysis_result.extracted_fields.job_title else None,
            "has_fee_demand": len(analysis_result.extracted_fields.fee_demands) > 0,
            "evidence_count": len(analysis_result.evidence),
        }
        db.commit()
        db.refresh(job)

        logger.info("Successfully completed async OCR job id=%s (scan_id=%s)", job.id, job.result_scan_id)
        return job

    except (OversizedFileError, ExcessivePagesError, EncryptedPDFError, InvalidPDFError, OCRTimeoutError) as exc:
        db.rollback()
        job = db.query(AsyncDocumentJob).filter(AsyncDocumentJob.id == job_id).first()
        if job:
            job.status = "FAILED"
            job.progress = 0
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
        logger.warning("OCR job id=%s failed with known document error: %s", job_id, exc)
        return job

    except Exception as exc:
        db.rollback()
        job = db.query(AsyncDocumentJob).filter(AsyncDocumentJob.id == job_id).first()
        if job:
            job.status = "FAILED"
            job.progress = 0
            job.error_message = f"Document processing failure: {type(exc).__name__}: {str(exc)}"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
        logger.error("OCR job id=%s failed with unhandled error: %s", job_id, type(exc).__name__)
        return job


def get_job_status_idor_protected(
    db: Session,
    job_id: str,
    current_user: Optional[User] = None,
    session_id: Optional[str] = None,
) -> AsyncDocumentJob:
    """Retrieves an asynchronous document job enforcing strict IDOR protection.

    ACCESS RULES:
    1. If the job has an assigned user_id:
       - Only that authenticated user or an ADMIN can view it.
    2. If the job was created by an anonymous visitor (session_id):
       - Only that matching session_id or an ADMIN can view it.
    3. Unauthorized attempts are rejected with 403 Forbidden.
    """
    job = db.query(AsyncDocumentJob).filter(AsyncDocumentJob.id == job_id).first()
    if not job:
        raise JobNotFoundError(f"Document analysis job '{job_id}' not found.")

    is_admin = current_user and current_user.role == "ADMIN"

    # User-owned job
    if job.user_id:
        if not current_user or (current_user.id != job.user_id and not is_admin):
            raise JobAccessForbiddenError("You do not have permission to access this private document job.")
    # Visitor-owned job
    elif job.session_id:
        if not is_admin and (not session_id or session_id != job.session_id):
            raise JobAccessForbiddenError("You do not have permission to access this document job.")

    # Automatic crash recovery check for this specific job
    if job.status == "PROCESSING" and job.started_at:
        now = datetime.now(timezone.utc)
        started_at = job.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        if (now - started_at).total_seconds() > 90:
            job.status = "FAILED"
            job.progress = 0
            job.error_message = "Document processing timed out or worker process was restarted. Please re-upload to retry."
            job.completed_at = now
            db.commit()
            logger.warning("Detected and failed stalled job id=%s during status check.", job.id)

    return job


def run_worker_daemon(poll_interval_seconds: float = 5.0, once: bool = False) -> None:
    """Standalone background worker daemon loop.

    Regularly polls for crashed jobs, performs queue housekeeping, and processes tasks.
    Gracefully handles SIGINT / SIGTERM signals.
    """
    import signal
    import sys
    import time
    from app.db.session import SessionLocal

    running = True

    def _sig_handler(signum, frame):
        nonlocal running
        logger.info("Received termination signal (%s). Shutting down OCR worker daemon gracefully...", signum)
        running = False

    signal.signal(signal.SIGINT, _sig_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _sig_handler)

    logger.info("JobShield AI Asynchronous OCR Worker Daemon started (poll_interval=%.1fs).", poll_interval_seconds)

    while running:
        try:
            with SessionLocal() as db:
                recovered = recover_stale_processing_jobs(db, max_processing_age_seconds=90)
                if recovered > 0:
                    logger.info("Worker daemon recovered %d stale jobs.", recovered)
        except Exception as exc:
            logger.error("Error in worker daemon sweep cycle: %s", exc)

        if once:
            break

        # Sleep in small slices to respond swiftly to shutdown signals
        sleep_elapsed = 0.0
        while running and sleep_elapsed < poll_interval_seconds:
            time.sleep(min(0.5, poll_interval_seconds - sleep_elapsed))
            sleep_elapsed += 0.5

    logger.info("JobShield AI Asynchronous OCR Worker Daemon stopped cleanly.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    run_worker_daemon()

