"""User Appeals API Router.

Conforms to Section 5 of Specifications:
- Authenticated user appeal submission against eligible moderation decisions
- Ownership validation: users can only appeal decisions on their own submitted feedback
- Duplicate active appeal prevention
- Status tracking: PENDING, UPHELD, DISMISSED
"""

from datetime import datetime, timezone
import logging
from typing import List
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_user
from app.db.session import get_db
from app.models.community import RecruiterReport, ReviewModeration, UserReview
from app.models.user import ModerationAppeal, SecurityAuditLog, User
from app.schemas.moderation import AppealCreateRequest, AppealResponse

logger = logging.getLogger("jobshield.api.appeals")

router = APIRouter(prefix="/appeals", tags=["User Appeals"])


@router.post(
    "",
    response_model=AppealResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit Appeal Against Moderation Decision",
    description="Allows authenticated users to appeal a moderation decision on their own submitted review or report.",
)
def create_appeal(
    appeal_in: AppealCreateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AppealResponse:
    # 1. Verify moderation record exists
    mod_record = db.query(ReviewModeration).filter(ReviewModeration.id == appeal_in.moderation_id).first()
    if not mod_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Moderation decision with ID '{appeal_in.moderation_id}' was not found.",
        )

    # 2. Verify ownership: user must own the targeted review or report (unless Admin)
    if current_user.role != "ADMIN":
        owns_item = False
        if mod_record.review_id:
            rev = db.query(UserReview).filter(UserReview.id == mod_record.review_id).first()
            if rev and rev.user_id == current_user.id:
                owns_item = True
        elif mod_record.report_id:
            rep = db.query(RecruiterReport).filter(RecruiterReport.id == mod_record.report_id).first()
            if rep and rep.user_id == current_user.id:
                owns_item = True

        if not owns_item:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only appeal moderation decisions on items submitted by your own account.",
            )

    # 3. Check for existing active appeal
    existing_appeal = db.query(ModerationAppeal).filter(
        ModerationAppeal.moderation_id == appeal_in.moderation_id,
        ModerationAppeal.status == "PENDING",
    ).first()
    if existing_appeal:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active appeal for this moderation decision is already under review.",
        )

    now = datetime.now(timezone.utc)
    new_appeal = ModerationAppeal(
        id=str(uuid.uuid4()),
        moderation_id=mod_record.id,
        user_id=current_user.id,
        appeal_reason=appeal_in.appeal_reason.strip(),
        status="PENDING",
        created_at=now,
    )
    db.add(new_appeal)

    # Update moderation record appeal status
    mod_record.appeal_status = "PENDING_APPEAL"

    # Security Audit Log
    audit = SecurityAuditLog(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        action="USER_APPEAL_SUBMITTED",
        target_type="moderation_appeal",
        target_id=new_appeal.id,
        details={"moderation_id": mod_record.id},
        created_at=now,
    )
    db.add(audit)
    db.commit()
    db.refresh(new_appeal)

    logger.info("New appeal submitted: id=%s by user=%s", new_appeal.id, current_user.id)
    return new_appeal


@router.get(
    "/my-appeals",
    response_model=List[AppealResponse],
    summary="List Current User's Appeals",
)
def get_my_appeals(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> List[AppealResponse]:
    appeals = (
        db.query(ModerationAppeal)
        .filter(ModerationAppeal.user_id == current_user.id)
        .order_by(ModerationAppeal.created_at.desc())
        .all()
    )
    return appeals


@router.get(
    "/{appeal_id}",
    response_model=AppealResponse,
    summary="Get Appeal Details",
)
def get_appeal_details(
    appeal_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AppealResponse:
    appeal = db.query(ModerationAppeal).filter(ModerationAppeal.id == appeal_id).first()
    if not appeal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appeal not found.")

    # Only owner or Moderator/Admin can view
    if appeal.user_id != current_user.id and current_user.role not in ("MODERATOR", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this appeal.",
        )

    return appeal
