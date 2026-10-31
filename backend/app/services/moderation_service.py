"""Moderation and Training-Data Isolation Service (F8 & F9).

Conforms to Section 8 (Tables 11-14) & Section 9 of PROJECT_SPECIFICATION.md:
- Moderation lifecycle for community reviews and fraud reports (approve, reject, flag, appeal_upheld, appeal_dismissed)
- Submitter appeal handling with audit trail in review_moderation
- TRAINING DATA ISOLATION (MANDATORY):
  Community reviews and recruiter reports NEVER automatically populate or alter training_labels.
  Training labels can ONLY be created through an explicit, authorized curator workflow.
"""

from datetime import datetime, timezone
import logging
from typing import Optional, Tuple
import uuid
from sqlalchemy.orm import Session

from app.models.community import (
    RecruiterReport,
    ReviewModeration,
    TrainingLabel,
    UserReview,
)
from app.schemas.community import (
    ModerationAppealRequest,
    ModerationDecisionRequest,
    TrainingLabelCreateRequest,
)

logger = logging.getLogger("jobshield.community.moderation")


class ModerationError(Exception):
    """Base exception for moderation workflow errors."""
    pass


def process_moderation_decision(
    db: Session,
    request: ModerationDecisionRequest,
) -> Tuple[ReviewModeration, str]:
    """Applies a moderator decision to a review or fraud report and logs an audit record."""
    target_type = request.target_type.strip().lower()
    action = request.action.strip().upper()
    new_status = ""
    review_id = None
    report_id = None

    if target_type in ("user_review", "review"):
        target_type_clean = "review"
        review = db.query(UserReview).filter(UserReview.id == request.target_id).first()
        if not review:
            raise ModerationError(f"UserReview with ID {request.target_id} not found.")

        review_id = review.id
        if action in ("APPROVE", "APPROVED"):
            new_status = "APPROVED"
        elif action in ("REJECT", "REJECTED"):
            new_status = "REJECTED"
        elif action == "FLAG":
            new_status = "FLAGGED"
        elif action == "APPEAL_UPHELD":
            new_status = "APPROVED"
        elif action == "APPEAL_DISMISSED":
            new_status = "REJECTED"
        else:
            raise ModerationError(f"Invalid action '{action}' for UserReview. Allowed: APPROVE, REJECT, FLAG, APPEAL_UPHELD, APPEAL_DISMISSED.")

        review.moderation_status = new_status
        review.moderation_reason = request.reason.strip()
        review.updated_at = datetime.now(timezone.utc)

    elif target_type in ("recruiter_report", "report"):
        target_type_clean = "report"
        report = db.query(RecruiterReport).filter(RecruiterReport.id == request.target_id).first()
        if not report:
            raise ModerationError(f"RecruiterReport with ID {request.target_id} not found.")

        report_id = report.id
        if action in ("APPROVE", "APPROVED", "VERIFY"):
            new_status = "APPROVED"
        elif action in ("REJECT", "REJECTED", "DISMISS"):
            new_status = "REJECTED"
        elif action == "FLAG":
            new_status = "FLAGGED"
        elif action == "APPEAL_UPHELD":
            new_status = "APPROVED"
        elif action == "APPEAL_DISMISSED":
            new_status = "REJECTED"
        else:
            raise ModerationError(f"Invalid action '{action}' for RecruiterReport. Allowed: APPROVE, REJECT, FLAG, APPEAL_UPHELD, APPEAL_DISMISSED.")

        report.moderation_status = new_status
        report.moderation_reason = request.reason.strip()
        report.updated_at = datetime.now(timezone.utc)

    else:
        raise ModerationError(f"Unsupported target_type '{request.target_type}'. Must be 'review' or 'report'.")

    # Record the moderation audit trail
    audit_entry = ReviewModeration(
        id=str(uuid.uuid4()),
        target_type=target_type_clean,
        review_id=review_id,
        report_id=report_id,
        moderator_id=request.moderator_id.strip(),
        action=action,
        reason=request.reason.strip(),
        appeal_status="NONE",
        audit_metadata=request.audit_metadata,
        created_at=datetime.now(timezone.utc),
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)

    logger.info(
        "Moderation applied: target_type=%s, target_id=%s, action=%s, new_status=%s, moderator=%s",
        target_type, request.target_id, action, new_status, request.moderator_id
    )

    return audit_entry, new_status


def submit_moderation_appeal(
    db: Session,
    request: ModerationAppealRequest,
) -> ReviewModeration:
    """Records an appeal from a submitter against a moderation decision."""
    mod_record = db.query(ReviewModeration).filter(ReviewModeration.id == request.moderation_id).first()
    if not mod_record:
        raise ModerationError(f"Moderation record ID {request.moderation_id} not found.")

    if mod_record.appeal_status in ("APPEAL_UPHELD", "PENDING_APPEAL"):
        raise ModerationError(f"Moderation record is already in '{mod_record.appeal_status}' status.")

    mod_record.appeal_status = "PENDING_APPEAL"
    meta = mod_record.audit_metadata or {}
    meta["appeal_reason"] = request.appeal_reason.strip()
    meta["appealed_at"] = datetime.now(timezone.utc).isoformat()
    mod_record.audit_metadata = meta

    db.commit()
    db.refresh(mod_record)

    logger.info("Moderation appeal submitted for record ID=%s", mod_record.id)
    return mod_record


def create_curated_training_label(
    db: Session,
    request: TrainingLabelCreateRequest,
) -> TrainingLabel:
    """Explicitly curates and authorizes a ground-truth training label.

    MANDATORY SYSTEM ISOLATION:
    - This function requires explicit curator credentials.
    - Community submissions NEVER automatically call or trigger this function.
    - An explicit human curator decision is strictly required before any data is admitted to training sets.
    """
    valid_labels = {"FRAUDULENT", "LEGITIMATE"}
    norm_label = request.label.strip().upper()
    if norm_label not in valid_labels:
        raise ModerationError(f"Invalid label '{request.label}'. Must be one of {valid_labels}")

    now = datetime.now(timezone.utc)
    new_label = TrainingLabel(
        id=str(uuid.uuid4()),
        scan_id=request.scan_id,
        job_id=request.job_id,
        label=norm_label,
        label_source=request.label_source.strip(),
        validation_status="APPROVED",
        reviewed_by=request.reviewed_by.strip(),
        evidence_reference=request.evidence_reference.strip(),
        dataset_version=request.dataset_version or "v1.0.0",
        validation_notes=request.validation_notes.strip() if request.validation_notes else None,
        created_at=now,
        approved_for_training_at=now,
    )
    db.add(new_label)
    db.commit()
    db.refresh(new_label)

    logger.info("Created authorized training label ID=%s, label=%s", new_label.id, new_label.label)
    return new_label
