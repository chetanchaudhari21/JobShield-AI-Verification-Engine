"""Community Feedback, Reviews, Reports, and Moderation API Endpoints (F8 & F9).

Conforms to Sections 8, 9, 11 of PROJECT_SPECIFICATION.md:
- POST /api/v1/reviews - Submit 1-5 star service-experience review
- GET /api/v1/reviews - Query community reviews
- POST /api/v1/reports - Submit recruiter fraud/impersonation report
- GET /api/v1/reports - Query fraud reports
- POST /api/v1/reports/{report_id}/appeal - Appeal a report decision
- POST /api/v1/moderation/decisions - Apply moderation action (auth required)
- POST /api/v1/moderation/appeals - Appeal a moderation action
- POST /api/v1/moderation/training-labels - Explicit curator training-label authorization (auth required)
"""

from datetime import datetime, timezone
import logging
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.community import (
    RecruiterReport,
    ReviewModeration,
    TrainingLabel,
    UserReview,
)
from app.models.company import Company
from app.schemas.community import (
    CompanyReputationResponse,
    ModerationAppealRequest,
    ModerationAppealResponse,
    ModerationDecisionRequest,
    ModerationDecisionResponse,
    RecruiterReportCreate,
    RecruiterReportResponse,
    TrainingLabelCreateRequest,
    TrainingLabelResponse,
    UserReviewCreate,
    UserReviewResponse,
)
from app.services.moderation_service import (
    ModerationError,
    create_curated_training_label,
    process_moderation_decision,
    submit_moderation_appeal,
)
from app.services.rate_limiter import (
    community_rate_limiter,
    compute_report_content_hash,
    compute_review_content_hash,
    hash_submitter,
)
from app.services.recruiter_checker import mask_email
from app.services.reputation_service import get_company_reputation

logger = logging.getLogger("jobshield.api.community")

router = APIRouter(tags=["Community & Moderation"])


def get_client_ip(request: Request) -> str:
    """Extracts client IP address safely, checking proxy headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def verify_moderator_auth(
    x_moderator_key: Optional[str] = Header(None, alias="X-Moderator-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> None:
    """Verifies that the request provides valid moderator/curator credentials."""
    expected = settings.MODERATOR_SECRET_KEY
    token = x_moderator_key
    if not token and authorization:
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        else:
            token = authorization.strip()

    if not token or token != expected:
        logger.warning("Unauthorized moderation access attempt.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid or missing moderator authorization credentials.",
        )


# ==============================================================================
# Reviews API (1-5 Star Service Ratings)
# ==============================================================================
@router.post(
    "/reviews",
    response_model=UserReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit Community Service Review",
    description=(
        "Submits a 1-5 star recruitment service experience review. "
        "Enforces sliding-window rate limiting, duplicate detection, and sensitive data checks. "
        "Raw client IPs are never stored."
    ),
)
def create_review(
    review_in: UserReviewCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> UserReviewResponse:
    # 1. Minimum identifier requirement
    if not review_in.company_id and not review_in.company_name and not review_in.recruiter_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Review must specify at least one of company_id, company_name, or recruiter_email.",
        )

    # 2. Rate limiting check
    client_ip = get_client_ip(request)
    submitter_hash = hash_submitter(client_ip)
    allowed, err_msg = community_rate_limiter.check_and_record(submitter_hash)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=err_msg,
        )

    # 3. Deduplicate content
    target_key = str(review_in.company_id or review_in.company_name or review_in.recruiter_email)
    content_hash = compute_review_content_hash(
        target=target_key,
        rating=review_in.rating,
        category=review_in.category,
        text=review_in.review_text,
    )

    existing = db.query(UserReview).filter(UserReview.content_hash == content_hash).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A duplicate review with identical content has already been submitted.",
        )

    # 4. Resolve company if company_name provided
    company_id = review_in.company_id
    company_name = review_in.company_name
    if company_id:
        comp = db.get(Company, company_id)
        if not comp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Company ID {company_id} not found in verified database.",
            )
        company_name = comp.legal_name
    elif company_name:
        normalized = company_name.strip().lower()
        comp = db.query(Company).filter(Company.normalized_name == normalized).first()
        if comp:
            company_id = comp.id
            company_name = comp.legal_name

    # 5. Create Review
    new_review = UserReview(
        id=str(uuid.uuid4()),
        company_id=company_id,
        scan_id=review_in.scan_id,
        job_id=review_in.job_id,
        rating=review_in.rating,
        experience_category=review_in.category,
        review_text=review_in.review_text,
        submitter_hash=submitter_hash,
        content_hash=content_hash,
        moderation_status="APPROVED",  # Standard approved on submission
        is_verified_experience=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(new_review)
    db.commit()
    db.refresh(new_review)

    return UserReviewResponse(
        id=new_review.id,
        company_id=new_review.company_id,
        company_name=company_name,
        recruiter_email_masked=None,
        scan_id=new_review.scan_id,
        rating=new_review.rating,
        category=new_review.experience_category,
        review_text=new_review.review_text,
        status=new_review.moderation_status,
        created_at=new_review.created_at,
    )


@router.get(
    "/reviews",
    response_model=List[UserReviewResponse],
    summary="List Community Reviews",
)
def list_reviews(
    company_id: Optional[int] = Query(None, description="Filter by company ID"),
    status_filter: Optional[str] = Query("APPROVED", alias="status", description="Filter by moderation status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> List[UserReviewResponse]:
    query = db.query(UserReview)
    if company_id:
        query = query.filter(UserReview.company_id == company_id)
    if status_filter:
        query = query.filter(UserReview.moderation_status == status_filter.upper())

    query = query.order_by(UserReview.created_at.desc()).offset(offset).limit(limit)
    reviews = query.all()

    results: List[UserReviewResponse] = []
    for r in reviews:
        c_name = r.company.legal_name if r.company else None
        results.append(
            UserReviewResponse(
                id=r.id,
                company_id=r.company_id,
                company_name=c_name,
                recruiter_email_masked=None,
                scan_id=r.scan_id,
                rating=r.rating,
                category=r.experience_category,
                review_text=r.review_text,
                status=r.moderation_status,
                created_at=r.created_at,
            )
        )
    return results


# ==============================================================================
# Fraud Reports API (Separate Allegation Channel)
# ==============================================================================
@router.post(
    "/reports",
    response_model=RecruiterReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit Recruiter Fraud Report",
    description=(
        "Submits an allegation of recruiter fraud, impersonation, phishing, or fee demand. "
        "Strictly separated from 1-5 star service ratings. Never converts into fraud probabilities."
    ),
)
def create_report(
    report_in: RecruiterReportCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> RecruiterReportResponse:
    if not report_in.company_id and not report_in.company_name and not report_in.recruiter_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Report must specify at least one of company_id, company_name, or recruiter_email.",
        )

    # Rate limiting
    client_ip = get_client_ip(request)
    submitter_hash = hash_submitter(client_ip)
    allowed, err_msg = community_rate_limiter.check_and_record(submitter_hash)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=err_msg,
        )

    # Deduplicate content
    target_key = str(report_in.company_id or report_in.company_name or report_in.recruiter_email)
    content_hash = compute_report_content_hash(
        target=target_key,
        report_type=report_in.report_type,
        details=report_in.details,
    )

    existing = db.query(RecruiterReport).filter(RecruiterReport.content_hash == content_hash).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A duplicate report with identical content has already been submitted.",
        )

    company_id = report_in.company_id
    company_name = report_in.company_name
    if company_id:
        comp = db.get(Company, company_id)
        if not comp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Company ID {company_id} not found in verified database.",
            )
        company_name = comp.legal_name
    elif company_name:
        normalized = company_name.strip().lower()
        comp = db.query(Company).filter(Company.normalized_name == normalized).first()
        if comp:
            company_id = comp.id
            company_name = comp.legal_name

    new_report = RecruiterReport(
        id=str(uuid.uuid4()),
        company_id=company_id,
        claimed_company_name=company_name,
        recruiter_email=report_in.recruiter_email,
        scan_id=report_in.scan_id,
        job_id=report_in.job_id,
        report_type=report_in.report_type,
        description=report_in.details,
        evidence_summary=report_in.evidence_summary,
        submitter_hash=submitter_hash,
        content_hash=content_hash,
        moderation_status="PENDING",
        created_at=datetime.now(timezone.utc),
    )
    db.add(new_report)
    db.commit()
    db.refresh(new_report)

    return RecruiterReportResponse(
        id=new_report.id,
        company_id=new_report.company_id,
        company_name=company_name,
        recruiter_email_masked=mask_email(new_report.recruiter_email) if new_report.recruiter_email else None,
        scan_id=new_report.scan_id,
        report_type=new_report.report_type,
        details=new_report.description,
        evidence_summary=new_report.evidence_summary,
        status=new_report.moderation_status,
        created_at=new_report.created_at,
    )


@router.get(
    "/reports",
    response_model=List[RecruiterReportResponse],
    summary="List Fraud Reports",
)
def list_reports(
    company_id: Optional[int] = Query(None, description="Filter by company ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> List[RecruiterReportResponse]:
    query = db.query(RecruiterReport)
    if company_id:
        query = query.filter(RecruiterReport.company_id == company_id)
    if status_filter:
        query = query.filter(RecruiterReport.moderation_status == status_filter.upper())

    query = query.order_by(RecruiterReport.created_at.desc()).offset(offset).limit(limit)
    reports = query.all()

    results: List[RecruiterReportResponse] = []
    for rep in reports:
        c_name = rep.company.legal_name if rep.company else rep.claimed_company_name
        results.append(
            RecruiterReportResponse(
                id=rep.id,
                company_id=rep.company_id,
                company_name=c_name,
                recruiter_email_masked=mask_email(rep.recruiter_email) if rep.recruiter_email else None,
                scan_id=rep.scan_id,
                report_type=rep.report_type,
                details=rep.description,
                evidence_summary=rep.evidence_summary,
                status=rep.moderation_status,
                created_at=rep.created_at,
            )
        )
    return results


# ==============================================================================
# Moderation & Appeals Endpoints
# ==============================================================================
@router.post(
    "/reports/{report_id}/appeal",
    response_model=ModerationAppealResponse,
    summary="Appeal a Report Decision",
)
def appeal_report(
    report_id: str,
    appeal_in: ModerationAppealRequest,
    db: Session = Depends(get_db),
) -> ModerationAppealResponse:
    report = db.get(RecruiterReport, report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Report ID {report_id} not found.")

    report.moderation_status = "PENDING_APPEAL"
    report.updated_at = datetime.now(timezone.utc)
    db.commit()

    return ModerationAppealResponse(
        moderation_id=report_id,
        appeal_status="PENDING_APPEAL",
        message="Appeal has been registered and queued for moderator re-evaluation.",
        appealed_at=datetime.now(timezone.utc),
    )


@router.post(
    "/moderation/decisions",
    response_model=ModerationDecisionResponse,
    summary="Apply Moderation Action (Authorized Staff Only)",
    dependencies=[Depends(verify_moderator_auth)],
)
def apply_moderation_decision(
    decision_in: ModerationDecisionRequest,
    db: Session = Depends(get_db),
) -> ModerationDecisionResponse:
    try:
        entry, new_status = process_moderation_decision(db, decision_in)
        target_entity_id = entry.review_id or entry.report_id or decision_in.target_id
        return ModerationDecisionResponse(
            id=entry.id,
            target_type=entry.target_type,
            target_id=target_entity_id,
            action=entry.action,
            moderator_id=entry.moderator_id,
            reason=entry.reason,
            new_status=new_status,
            created_at=entry.created_at,
        )
    except ModerationError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.post(
    "/moderation/appeals",
    response_model=ModerationAppealResponse,
    summary="Submit Moderation Appeal",
)
def appeal_moderation(
    appeal_in: ModerationAppealRequest,
    db: Session = Depends(get_db),
) -> ModerationAppealResponse:
    try:
        mod = submit_moderation_appeal(db, appeal_in)
        return ModerationAppealResponse(
            moderation_id=mod.id,
            appeal_status=mod.appeal_status or "PENDING_APPEAL",
            message="Appeal submitted successfully.",
            appealed_at=datetime.now(timezone.utc),
        )
    except ModerationError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


# ==============================================================================
# Isolated Training Label Curation (Authorized Curators Only)
# ==============================================================================
@router.post(
    "/moderation/training-labels",
    response_model=TrainingLabelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Explicitly Curate Training Label (Authorized Curators Only)",
    description=(
        "Explicitly creates or updates an authorized training label. "
        "MANDATORY ISOLATION: Community reviews/reports NEVER automatically create training labels. "
        "Requires explicit curator credentials and human verification rationale."
    ),
    dependencies=[Depends(verify_moderator_auth)],
)
def create_training_label(
    label_in: TrainingLabelCreateRequest,
    db: Session = Depends(get_db),
) -> TrainingLabelResponse:
    try:
        label = create_curated_training_label(db, label_in)
        return TrainingLabelResponse(
            id=label.id,
            scan_id=label.scan_id,
            job_id=label.job_id,
            label=label.label,
            label_source=label.label_source,
            validation_status=label.validation_status,
            reviewed_by=label.reviewed_by,
            evidence_reference=label.evidence_reference,
            dataset_version=label.dataset_version,
            validation_notes=label.validation_notes,
            is_active_for_training=True,
            created_at=label.created_at,
            approved_for_training_at=label.approved_for_training_at,
        )
    except ModerationError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
