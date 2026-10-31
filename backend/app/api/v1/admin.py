"""Administrative Controls and System Audit API Router.

Conforms to Section 3 (RBAC) & Section 4 (Audit Trail) of Specifications:
- Authorized user and role management
- Account status management (activation / suspension with session termination)
- Append-only security audit log viewer
- All endpoints strictly restricted to ADMIN role
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.scan import ScanRequest
from app.models.user import RefreshToken, SecurityAuditLog, User
from app.schemas.admin import (
    AdminUserListItem,
    AdminUserListResponse,
    RoleUpdateRequest,
    SecurityAuditLogListResponse,
    SecurityAuditLogResponse,
    StatusUpdateRequest,
)

logger = logging.getLogger("jobshield.api.admin")

router = APIRouter(prefix="/admin", tags=["Administrative Controls"])


@router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="List Users (Admin Only)",
    description="Retrieves a paginated list of users with optional filtering by role, status, or search query.",
)
def list_users(
    search: Optional[str] = Query(None, description="Search by email or name"),
    role: Optional[str] = Query(None, description="Filter by role: 'USER', 'MODERATOR', 'ADMIN'"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserListResponse:
    query = db.query(User)

    if search:
        term = f"%{search.strip().lower()}%"
        query = query.filter((func.lower(User.email).like(term)) | (func.lower(User.full_name).like(term)))
    if role:
        query = query.filter(User.role == role.strip().upper())
    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    total = query.count()
    users = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()

    items = []
    for u in users:
        scans_count = db.query(ScanRequest).filter(ScanRequest.user_id == u.id).count()
        items.append(
            AdminUserListItem(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                role=u.role,
                is_active=u.is_active,
                is_verified=u.is_verified,
                created_at=u.created_at,
                last_login_at=u.last_login_at,
                scans_count=scans_count,
            )
        )

    return AdminUserListResponse(users=items, total=total, limit=limit, offset=offset)


@router.put(
    "/users/{user_id}/role",
    response_model=AdminUserListItem,
    summary="Update User Role (Admin Only)",
    description="Assigns a new role (USER, MODERATOR, ADMIN) to a user account. Records security audit entry.",
)
def update_user_role(
    user_id: str,
    role_in: RoleUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserListItem:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    old_role = user.role
    new_role = role_in.role.strip().upper()

    # Self-demotion safeguard: Prevent sole admin from demoting themselves
    if user.id == current_admin.id and new_role != "ADMIN":
        admin_count = db.query(User).filter(User.role == "ADMIN", User.is_active.is_(True)).count()
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the only active Administrator account.",
            )

    user.role = new_role
    user.updated_at = datetime.now(timezone.utc)

    # Invalidate existing access tokens by revoking active sessions so role takes effect
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked_at.is_(None),
    ).update({"revoked_at": datetime.now(timezone.utc)})

    audit = SecurityAuditLog(
        id=str(uuid.uuid4()),
        user_id=current_admin.id,
        action="ROLE_CHANGE",
        target_type="user",
        target_id=user.id,
        details={"old_role": old_role, "new_role": new_role},
        created_at=datetime.now(timezone.utc),
    )
    db.add(audit)
    db.commit()
    db.refresh(user)

    logger.info("User ID=%s role changed from %s to %s by admin=%s", user.id, old_role, new_role, current_admin.id)
    scans_count = db.query(ScanRequest).filter(ScanRequest.user_id == user.id).count()
    return AdminUserListItem(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        scans_count=scans_count,
    )


@router.put(
    "/users/{user_id}/status",
    response_model=AdminUserListItem,
    summary="Update Account Status (Admin Only)",
    description="Activates or deactivates a user account. Deactivation terminates all active sessions.",
)
def update_user_status(
    user_id: str,
    status_in: StatusUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserListItem:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if user.id == current_admin.id and not status_in.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot deactivate their own account.",
        )

    old_status = user.is_active
    user.is_active = status_in.is_active
    user.updated_at = datetime.now(timezone.utc)

    # If deactivating, terminate all active refresh sessions immediately
    if not status_in.is_active:
        db.query(RefreshToken).filter(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        ).update({"revoked_at": datetime.now(timezone.utc)})

    audit = SecurityAuditLog(
        id=str(uuid.uuid4()),
        user_id=current_admin.id,
        action="ACCOUNT_STATUS_CHANGE",
        target_type="user",
        target_id=user.id,
        details={"old_is_active": old_status, "new_is_active": status_in.is_active},
        created_at=datetime.now(timezone.utc),
    )
    db.add(audit)
    db.commit()
    db.refresh(user)

    scans_count = db.query(ScanRequest).filter(ScanRequest.user_id == user.id).count()
    return AdminUserListItem(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        scans_count=scans_count,
    )


@router.get(
    "/audit-logs",
    response_model=SecurityAuditLogListResponse,
    summary="View Security Audit Logs (Admin Only)",
    description="Lists the append-only security audit trail of authentication events and administrative changes.",
)
def list_security_audit_logs(
    action: Optional[str] = Query(None, description="Filter by action type"),
    target_type: Optional[str] = Query(None, description="Filter by target type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SecurityAuditLogListResponse:
    query = db.query(SecurityAuditLog)
    if action:
        query = query.filter(SecurityAuditLog.action == action.strip().upper())
    if target_type:
        query = query.filter(SecurityAuditLog.target_type == target_type.strip().lower())

    total = query.count()
    logs = query.order_by(SecurityAuditLog.created_at.desc()).offset(offset).limit(limit).all()

    items = [
        SecurityAuditLogResponse(
            id=l.id,
            user_id=l.user_id,
            action=l.action,
            target_type=l.target_type,
            target_id=l.target_id,
            details=l.details,
            created_at=l.created_at,
        )
        for l in logs
    ]

    return SecurityAuditLogListResponse(logs=items, total=total, limit=limit, offset=offset)


# ============================================================================
# FEATURE F12: MODEL REGISTRY, ATOMIC DEPLOYMENT, DRIFT & PROVENANCE
# ============================================================================

@router.get(
    "/models",
    summary="List Registered Models (Admin Only)",
    description="Lists all model versions in the registry with their evaluation metrics, status, and checksums.",
)
def list_models_endpoint(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    from app.services.model_registry import list_registered_models, seed_model_registry
    # Ensure registry is seeded with artifacts on disk
    seed_model_registry(db)
    models = list_registered_models(db)
    return {
        "total": len(models),
        "models": models,
    }


@router.get(
    "/models/active",
    summary="Get Active Model Information (Admin Only)",
    description="Retrieves the currently deployed active ML model version and its threshold configuration.",
)
def get_active_model_endpoint(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    from app.services.model_registry import get_active_model_record, seed_model_registry
    seed_model_registry(db)
    active = get_active_model_record(db)
    if not active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active model found in the registry.",
        )
    metrics = active.metrics or {}
    return {
        "version": active.version,
        "artifact_path": active.artifact_path,
        "sha256": metrics.get("sha256", "unavailable"),
        "deployed_at": active.deployed_at.isoformat() if active.deployed_at else None,
        "primary_metrics": metrics.get("primary_model_metrics", {}),
        "calibrated_metrics": metrics.get("calibrated_model_metrics", {}),
    }


@router.post(
    "/models/{version}/deploy",
    summary="Atomically Deploy Evaluated Model Version (Admin Only)",
    description="Atomically swaps the active model to the requested evaluated version. Rolls back cleanly if loading fails.",
)
def deploy_model_endpoint(
    version: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    from app.services.model_registry import (
        deploy_model_atomic,
        ModelDeploymentError,
        ModelEvaluationFailedError,
        ModelNotFoundError,
    )
    try:
        result = deploy_model_atomic(version=version, db=db, admin_id=current_admin.id)
        return result
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ModelEvaluationFailedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ModelDeploymentError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post(
    "/models/rollback",
    summary="Atomically Rollback to Previous Model (Admin Only)",
    description="Rolls back active model deployment to the most recently archived model version.",
)
def rollback_model_endpoint(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    from app.services.model_registry import (
        rollback_model_atomic,
        ModelDeploymentError,
        ModelNotFoundError,
    )
    try:
        result = rollback_model_atomic(db=db, admin_id=current_admin.id)
        return result
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ModelDeploymentError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get(
    "/monitoring/drift",
    summary="Privacy-Preserving Drift Monitoring (Admin Only)",
    description="Computes aggregate prediction distribution shifts (PSI) against baseline. Never exposes user text.",
)
def get_drift_endpoint(
    window_days: int = Query(30, ge=1, le=365),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    from app.services.drift_monitor import get_privacy_preserving_drift_metrics
    return get_privacy_preserving_drift_metrics(db=db, window_days=window_days)


@router.get(
    "/retraining/provenance",
    summary="Training Data Provenance & Quarantine Status (Admin Only)",
    description="Lists dataset provenance, approved label counts, and confirms quarantine of unreviewed community data.",
)
def get_provenance_endpoint(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    from app.ml.retrain import get_data_provenance_and_quarantine_summary
    return get_data_provenance_and_quarantine_summary(db=db)


@router.post(
    "/retraining/trigger",
    summary="Execute Manual Model Retraining (Admin Only)",
    description="Manually triggers training on approved labels. Evaluates against test benchmark. Never automatically deploys.",
)
def trigger_retrain_endpoint(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    from app.ml.retrain import execute_manual_retraining_workflow, RetrainingGovernanceError
    try:
        return execute_manual_retraining_workflow(
            db=db,
            invoked_by_admin=current_admin.email,
        )
    except RetrainingGovernanceError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

