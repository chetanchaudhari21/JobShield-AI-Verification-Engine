"""Scans & Reports API Router.

Implements Feature F10 & Production Scan History:
- GET /api/v1/scans/my-scans (Authenticated user scan history)
- GET /api/v1/scans/{scan_id} (Scan details with IDOR protection)
- DELETE /api/v1/scans/{scan_id} (User scan deletion)
- GET /api/v1/scans/{scan_id}/report.pdf (Evidence-based PDF report with access control)
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user_optional, require_user
from app.db.session import get_db
from app.models.company import Company
from app.models.offer import OfferLetterScan
from app.models.prediction import PredictionHistory
from app.models.recruiter import RecruiterEmailScan
from app.models.scan import ScanRequest
from app.models.user import SecurityAuditLog, User
from app.models.verification import VerificationEvidence
from app.reports.pdf_generator import generate_verification_report_pdf
from app.schemas.scan import UserScanListResponse, UserScanSummaryItem

logger = logging.getLogger("jobshield.api.scans")

router = APIRouter(prefix="/scans", tags=["Scans & Reports"])


@router.get(
    "/my-scans",
    response_model=UserScanListResponse,
    summary="List Authenticated User's Scan History",
    description="Returns a paginated list of scans performed by the authenticated user.",
)
def get_my_scans(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> UserScanListResponse:
    query = db.query(ScanRequest).filter(ScanRequest.user_id == current_user.id)
    total = query.count()
    scans = query.order_by(ScanRequest.created_at.desc()).offset(offset).limit(limit).all()

    items = []
    for s in scans:
        latest_pred = (
            db.query(PredictionHistory)
            .filter(PredictionHistory.scan_id == s.id)
            .order_by(PredictionHistory.created_at.desc())
            .first()
        )
        company_name = None
        if s.offer_scan and s.offer_scan.claimed_company_name:
            company_name = s.offer_scan.claimed_company_name
        else:
            evs = (
                db.query(VerificationEvidence)
                .filter(VerificationEvidence.scan_id == s.id)
                .all()
            )
            for e in evs:
                meta = e.raw_metadata or {}
                if isinstance(meta, dict):
                    candidate = meta.get("legal_name") or meta.get("claimed_company_name") or meta.get("company_name")
                    if candidate:
                        company_name = candidate
                        break

        items.append(
            UserScanSummaryItem(
                id=s.id,
                input_type=s.input_type,
                input_reference=s.input_reference,
                status=s.status,
                created_at=s.created_at,
                risk_score=latest_pred.risk_score if latest_pred else None,
                risk_category=latest_pred.risk_category if latest_pred else None,
                claimed_company_name=company_name,
            )
        )

    return UserScanListResponse(scans=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{scan_id}",
    summary="Get Scan Details (with IDOR Protection)",
    description="Returns scan details. Private scans with an owner require authorization.",
)
def get_scan_details(
    scan_id: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict:
    scan = db.query(ScanRequest).filter(ScanRequest.id == scan_id).first()
    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan record '{scan_id}' was not found.",
        )

    # IDOR Protection: If scan has a user_id, only the owner or an Admin can access it
    if scan.user_id:
        if not current_user or (current_user.id != scan.user_id and current_user.role != "ADMIN"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this private scan record.",
            )

    latest_pred = (
        db.query(PredictionHistory)
        .filter(PredictionHistory.scan_id == scan.id)
        .order_by(PredictionHistory.created_at.desc())
        .first()
    )

    evidence_records = (
        db.query(VerificationEvidence)
        .filter(VerificationEvidence.scan_id == scan.id)
        .order_by(VerificationEvidence.id.asc())
        .all()
    )

    evidence_items = []
    for ev in evidence_records:
        evidence_items.append({
            "evidence_type": ev.evidence_type,
            "source_name": ev.source_name,
            "status": ev.status,
            "confidence": ev.confidence,
            "summary": ev.summary,
            "limitations": ev.limitations,
            "details": ev.raw_metadata or {},
            "source_url": ev.source_url,
        })

    explanation = (latest_pred.explanation or {}) if latest_pred else {}

    ml_analysis = None
    if latest_pred:
        ml_analysis = {
            "model_version": latest_pred.model_version,
            "primary_prediction": latest_pred.predicted_class,
            "calibrated_probability": latest_pred.model_probability,
            "calibration_method": explanation.get("calibration_method", "sigmoid"),
            "primary_threshold": explanation.get("primary_threshold", 0.5),
            "calibrated_threshold": explanation.get("calibrated_threshold", 0.5),
            "decision_threshold": explanation.get("decision_threshold", 0.5),
            "calibrated_prediction": explanation.get("calibrated_prediction", latest_pred.predicted_class),
            "explanation_method": explanation.get("explanation_method", "auto"),
            "score_type": explanation.get("score_type", "log_odds"),
            "target_class": explanation.get("target_class", 1),
            "intercept": explanation.get("intercept", 0.0),
            "decision_score": explanation.get("decision_score", 0.0),
            "reconciled_score": explanation.get("reconciled_score", 0.0),
            "is_reconciled": explanation.get("is_reconciled", True),
            "active_feature_count": explanation.get("active_feature_count", 0),
            "total_feature_contribution": explanation.get("total_feature_contribution", 0.0),
            "explanation_available": explanation.get("explanation_available", True),
            "explanation_unavailable_reason": explanation.get("explanation_unavailable_reason"),
            "explanation_disclaimer": explanation.get("explanation_disclaimer"),
            "top_features": explanation.get("top_features", []),
            "top_positive_features": explanation.get("top_positive_features", []),
            "top_negative_features": explanation.get("top_negative_features", []),
        }

    return {
        "id": scan.id,
        "report_id": scan.id,
        "input_type": scan.input_type,
        "input_reference": scan.input_reference,
        "status": scan.status,
        "created_at": scan.created_at,
        "timestamp": scan.completed_at or scan.created_at,
        "risk_score": latest_pred.risk_score if (latest_pred and latest_pred.risk_score >= 0) else None,
        "risk_category": latest_pred.risk_category if latest_pred else None,
        "warning": explanation.get("warning"),
        "override_floor_applied": explanation.get("override_floor_applied"),
        "override_floor_reason": explanation.get("override_floor_reason"),
        "recommended_safe_actions": explanation.get("recommended_safe_actions", []),
        "limitations": explanation.get("limitations", []),
        "disclaimer": explanation.get("disclaimer"),
        "community_summary": explanation.get("community_summary"),
        "company_verification": explanation.get("company_verification"),
        "duplicate_analysis": explanation.get("duplicate_analysis"),
        "domain_check": explanation.get("domain_check"),
        "recruiter_checks": explanation.get("recruiter_checks"),
        "evidence": evidence_items,
        "ml_analysis": ml_analysis,
    }


@router.delete(
    "/{scan_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Stored Scan Record",
    description="Allows authenticated users to delete their own stored scan data.",
)
def delete_scan(
    scan_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    scan = db.query(ScanRequest).filter(ScanRequest.id == scan_id).first()
    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan record '{scan_id}' was not found.",
        )

    # Permission check: must be owner or Admin
    if scan.user_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this scan record.",
        )

    db.delete(scan)
    db.commit()
    logger.info("Scan record ID=%s deleted by user=%s", scan_id, current_user.id)
    return {"message": "Scan record and associated data deleted successfully."}


@router.get(
    "/{scan_id}/report.pdf",
    summary="Download Evidence-Based Verification PDF Report",
    description=(
        "Generates and returns an authoritative, evidence-based verification PDF report for a completed scan. "
        "Strictly derived from persisted scan results. Enforces IDOR protection on private user scans."
    ),
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Generated verification report in PDF format",
        },
        404: {
            "description": "Scan record not found",
        },
    },
)
def get_scan_report_pdf(
    scan_id: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> Response:
    """Retrieves persisted scan and returns the official PDF verification report."""
    scan = db.query(ScanRequest).filter(ScanRequest.id == scan_id).first()
    if not scan:
        logger.info("PDF report requested for nonexistent scan_id=%s", scan_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan record '{scan_id}' was not found.",
        )

    if scan.status in ("INVALID", "UNCERTAIN"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verification report is not available for non-job input scans.",
        )

    # IDOR Protection: If scan has a user_id, only the owner or an Admin can download
    if scan.user_id:
        if not current_user or (current_user.id != scan.user_id and current_user.role != "ADMIN"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to download this private verification report.",
            )

    # Retrieve associated records
    evidence_records = (
        db.query(VerificationEvidence)
        .filter(VerificationEvidence.scan_id == scan_id)
        .order_by(VerificationEvidence.id.asc())
        .all()
    )

    prediction_records = (
        db.query(PredictionHistory)
        .filter(PredictionHistory.scan_id == scan_id)
        .order_by(PredictionHistory.id.desc())
        .all()
    )

    offer_scan = (
        db.query(OfferLetterScan)
        .filter(OfferLetterScan.scan_id == scan_id)
        .first()
    )

    recruiter_scan = (
        db.query(RecruiterEmailScan)
        .filter(RecruiterEmailScan.scan_id == scan_id)
        .first()
    )

    company: Optional[Company] = None
    company_id: Optional[int] = None
    if offer_scan and offer_scan.company_id:
        company_id = offer_scan.company_id
    elif recruiter_scan and recruiter_scan.claimed_company_id:
        company_id = recruiter_scan.claimed_company_id

    if company_id:
        company = db.query(Company).filter(Company.id == company_id).first()

    try:
        pdf_bytes = generate_verification_report_pdf(
            scan=scan,
            evidence_records=evidence_records,
            prediction_records=prediction_records,
            offer_scan=offer_scan,
            recruiter_scan=recruiter_scan,
            company=company,
        )
    except Exception as exc:
        logger.error(
            "Failed to generate verification report PDF for scan_id=%s: %s",
            scan_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while rendering the verification report PDF.",
        ) from exc

    short_id = scan_id[:8] if scan_id else "report"
    filename = f"JobShield_Report_{short_id}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )
