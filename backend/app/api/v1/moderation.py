"""Moderation Queue, Decisions, Appeals Resolution, and Audit Trail API.

Conforms to Section 4 & 5 of Specifications:
- Persistent moderation queue for community reviews and fraud reports
- Atomic database transactions committing decisions and append-only audit records together
- Authenticated appeals review and resolution
- Append-only audit trail with zero application-level edit/delete operations
- MANDATORY TRAINING DATA ISOLATION: Community decisions NEVER touch training_labels.
"""

from datetime import datetime, timezone
import logging
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import (
    require_admin,
    require_admin_training_curator,
    require_moderator,
)
from app.db.session import get_db
from app.models.community import (
    RecruiterReport,
    ReviewModeration,
    TrainingLabel,
    UserReview,
)
from app.models.user import ModerationAppeal, SecurityAuditLog, User
from app.schemas.community import (
    ModerationDecisionRequest,
    ModerationDecisionResponse,
    TrainingLabelCreateRequest,
    TrainingLabelResponse,
)
from app.schemas.moderation import (
    AppealResolveRequest,
    AppealResponse,
    ModerationAuditItem,
    ModerationAuditListResponse,
    ModerationQueueItem,
    ModerationQueueResponse,
)
from app.services.moderation_service import (
    ModerationError,
    create_curated_training_label,
    process_moderation_decision,
)
from app.services.recruiter_checker import mask_email

logger = logging.getLogger("jobshield.api.moderation")

router = APIRouter(prefix="/moderation", tags=["Moderation & Appeals"])


@router.get(
    "/queue",
    response_model=ModerationQueueResponse,
    summary="List Pending Moderation Queue Items",
    description="Lists pending or flagged reviews and fraud reports for moderator review with privacy masking.",
)
def get_moderation_queue(
    target_type: Optional[str] = Query(None, description="Filter: 'review' or 'report'"),
    status_filter: Optional[str] = Query("PENDING", alias="status", description="Status filter"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db),
) -> ModerationQueueResponse:
    items: List[ModerationQueueItem] = []
    norm_status = status_filter.upper() if status_filter else "PENDING"

    # 1. Fetch reviews if target_type is None or 'review'
    if not target_type or target_type.lower() in ("review", "user_review"):
        rev_q = db.query(UserReview).filter(func.upper(UserReview.moderation_status) == norm_status)
        reviews = rev_q.order_by(UserReview.created_at.asc()).offset(offset).limit(limit).all()

        for r in reviews:
            c_name = r.company.legal_name if r.company else None
            items.append(
                ModerationQueueItem(
                    id=r.id,
                    target_type="review",
                    status=r.moderation_status,
                    created_at=r.created_at,
                    company_id=r.company_id,
                    company_name=c_name,
                    rating=r.rating,
                    category=r.experience_category,
                    text_snippet=r.review_text[:200] if r.review_text else None,
                    submitter_user_id=r.user_id,
                )
            )

    # 2. Fetch reports if target_type is None or 'report'
    if not target_type or target_type.lower() in ("report", "recruiter_report"):
        rep_q = db.query(RecruiterReport).filter(func.upper(RecruiterReport.moderation_status) == norm_status)
        reports = rep_q.order_by(RecruiterReport.created_at.asc()).offset(offset).limit(limit).all()

        for rep in reports:
            c_name = rep.company.legal_name if rep.company else rep.claimed_company_name
            items.append(
                ModerationQueueItem(
                    id=rep.id,
                    target_type="report",
                    status=rep.moderation_status,
                    created_at=rep.created_at,
                    company_id=rep.company_id,
                    company_name=c_name,
                    report_type=rep.report_type,
                    text_snippet=rep.description[:200] if rep.description else None,
                    evidence_summary=rep.evidence_summary,
                    recruiter_email_masked=mask_email(rep.recruiter_email) if rep.recruiter_email else None,
                    submitter_user_id=rep.user_id,
                )
            )

    total_count = len(items)
    return ModerationQueueResponse(
        items=items[:limit],
        total=total_count,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/items/{target_type}/{item_id}",
    response_model=ModerationQueueItem,
    summary="Get Specific Moderation Item Details",
)
def get_moderation_item_details(
    target_type: str,
    item_id: str,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db),
) -> ModerationQueueItem:
    clean_target = target_type.strip().lower()

    if clean_target in ("review", "user_review"):
        rev = db.query(UserReview).filter(UserReview.id == item_id).first()
        if not rev:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found.")
        c_name = rev.company.legal_name if rev.company else None
        return ModerationQueueItem(
            id=rev.id,
            target_type="review",
            status=rev.moderation_status,
            created_at=rev.created_at,
            company_id=rev.company_id,
            company_name=c_name,
            rating=rev.rating,
            category=rev.experience_category,
            text_snippet=rev.review_text,
            submitter_user_id=rev.user_id,
        )

    elif clean_target in ("report", "recruiter_report"):
        rep = db.query(RecruiterReport).filter(RecruiterReport.id == item_id).first()
        if not rep:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
        c_name = rep.company.legal_name if rep.company else rep.claimed_company_name
        return ModerationQueueItem(
            id=rep.id,
            target_type="report",
            status=rep.moderation_status,
            created_at=rep.created_at,
            company_id=rep.company_id,
            company_name=c_name,
            report_type=rep.report_type,
            text_snippet=rep.description,
            evidence_summary=rep.evidence_summary,
            recruiter_email_masked=mask_email(rep.recruiter_email) if rep.recruiter_email else None,
            submitter_user_id=rep.user_id,
        )

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target type must be 'review' or 'report'.")


@router.post(
    "/decisions",
    response_model=ModerationDecisionResponse,
    summary="Apply Moderation Decision (Atomic Audit)",
    description="Applies a moderation decision in an atomic transaction and records an immutable audit record.",
)
def apply_decision(
    decision_in: ModerationDecisionRequest,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db),
) -> ModerationDecisionResponse:
    # Use authenticated user ID as moderator_id for accountability
    decision_in.moderator_id = current_user.id
    try:
        entry, new_status = process_moderation_decision(db, decision_in)

        # Log to security audit log
        audit = SecurityAuditLog(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            action=f"MODERATION_{decision_in.action.upper()}",
            target_type=entry.target_type,
            target_id=entry.review_id or entry.report_id or decision_in.target_id,
            details={"reason": decision_in.reason, "new_status": new_status},
            created_at=datetime.now(timezone.utc),
        )
        db.add(audit)
        db.commit()

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
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.get(
    "/audit-trail",
    response_model=ModerationAuditListResponse,
    summary="View Moderation Audit Trail",
    description="Retrieves the append-only audit trail of moderation actions.",
)
def get_audit_trail(
    target_type: Optional[str] = Query(None, description="Filter by target type"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db),
) -> ModerationAuditListResponse:
    query = db.query(ReviewModeration)
    if target_type:
        query = query.filter(ReviewModeration.target_type == target_type.lower())

    total = query.count()
    records = query.order_by(ReviewModeration.created_at.desc()).offset(offset).limit(limit).all()

    items = [
        ModerationAuditItem(
            id=r.id,
            target_type=r.target_type,
            review_id=r.review_id,
            report_id=r.report_id,
            moderator_id=r.moderator_id,
            action=r.action,
            reason=r.reason,
            appeal_status=r.appeal_status,
            created_at=r.created_at,
            audit_metadata=r.audit_metadata,
        )
        for r in records
    ]

    return ModerationAuditListResponse(items=items, total=total, limit=limit, offset=offset)


# ==============================================================================
# Appeals Resolution Workflow (Moderator / Admin)
# ==============================================================================
@router.get(
    "/appeals",
    response_model=List[AppealResponse],
    summary="List Moderation Appeals (Moderators & Admins)",
)
def list_appeals(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status ('PENDING', 'UPHELD', 'DISMISSED')"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db),
) -> List[AppealResponse]:
    query = db.query(ModerationAppeal)
    if status_filter:
        query = query.filter(ModerationAppeal.status == status_filter.upper())

    appeals = query.order_by(ModerationAppeal.created_at.asc()).offset(offset).limit(limit).all()
    return appeals


@router.post(
    "/appeals/{appeal_id}/resolve",
    response_model=AppealResponse,
    summary="Resolve Moderation Appeal",
    description="Resolves an appeal in an atomic transaction: UPHELD restores approval; DISMISSED affirms rejection.",
)
def resolve_appeal(
    appeal_id: str,
    resolve_in: AppealResolveRequest,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db),
) -> AppealResponse:
    appeal = db.query(ModerationAppeal).filter(ModerationAppeal.id == appeal_id).first()
    if not appeal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appeal record not found.")

    if appeal.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Appeal has already been resolved with status '{appeal.status}'.",
        )

    action = resolve_in.action.strip().upper()
    if action not in ("UPHELD", "DISMISSED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resolution action must be 'UPHELD' or 'DISMISSED'.",
        )

    now = datetime.now(timezone.utc)
    appeal.status = action
    appeal.reviewer_id = current_user.id
    appeal.resolution_notes = resolve_in.resolution_notes.strip()
    appeal.resolved_at = now

    # Update corresponding moderation record and target item
    mod_record = appeal.moderation_record
    if mod_record:
        mod_record.appeal_status = f"APPEAL_{action}"

        # If UPHELD, reverse rejection to APPROVED
        if action == "UPHELD":
            if mod_record.review_id:
                review = db.query(UserReview).filter(UserReview.id == mod_record.review_id).first()
                if review:
                    review.moderation_status = "APPROVED"
                    review.updated_at = now
            elif mod_record.report_id:
                report = db.query(RecruiterReport).filter(RecruiterReport.id == mod_record.report_id).first()
                if report:
                    report.moderation_status = "APPROVED"
                    report.updated_at = now

    audit = SecurityAuditLog(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        action=f"APPEAL_RESOLVE_{action}",
        target_type="moderation_appeal",
        target_id=appeal.id,
        details={"resolution_notes": resolve_in.resolution_notes},
        created_at=now,
    )
    db.add(audit)
    db.commit()
    db.refresh(appeal)

    logger.info("Appeal ID=%s resolved with status=%s by user=%s", appeal.id, action, current_user.id)
    return appeal


# ==============================================================================
# Isolated Training Label Curation (ADMIN ONLY)
# ==============================================================================
@router.post(
    "/training-labels",
    response_model=TrainingLabelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Curate Ground-Truth Training Label (Admins Only)",
    description="Explicitly authorizes a ground-truth training label. MANDATORY ISOLATION: Community feedback NEVER touches training labels.",
)
def curate_training_label(
    label_in: TrainingLabelCreateRequest,
    current_user: User = Depends(require_admin_training_curator),
    db: Session = Depends(get_db),
) -> TrainingLabelResponse:
    # Attribution to authenticated Admin curator
    label_in.reviewed_by = current_user.email or current_user.id
    try:
        label = create_curated_training_label(db, label_in)

        audit = SecurityAuditLog(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            action="CURATE_TRAINING_LABEL",
            target_type="training_label",
            target_id=label.id,
            details={"label": label.label, "source": label.label_source},
            created_at=datetime.now(timezone.utc),
        )
        db.add(audit)
        db.commit()

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
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
