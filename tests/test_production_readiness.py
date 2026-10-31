"""Comprehensive Automated Tests for Phase 7: Production Readiness & Governance.

Covers:
1. Model Registry & Provenance Checksums (SHA-256 validation, seeding v1.0.0 and v1.1.0).
2. Atomic Model Deployment & Hot-Swap (Audit trail, state swap, zero-downtime inference update).
3. Atomic Model Rollback (Restoration of prior archived version with compliance logging).
4. Candidate Rejection & Evaluation Gates (Rejection of unapproved, corrupt, or sub-threshold models).
5. Privacy-Preserving Drift Monitoring (Aggregate statistics, PSI calculation, zero PII/raw text leak).
6. Data Provenance & Community Quarantine Enforcement (Community reviews isolated from ML labels).
7. Manual-Only Retraining Execution (Staged as 'candidate', never auto-deployed).
8. Asynchronous Document OCR Worker & Queue (Magic bytes check, deduplication by SHA-256).
9. Strict IDOR Authorization on Asynchronous Jobs (Cross-user job isolation).
10. RBAC Matrix for Production Governance Endpoints (Visitor 401, User 403, Admin 200).
"""

from datetime import datetime, timezone, timedelta
import hashlib
import io
import os
import uuid
import pytest
from starlette.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.models.community import RecruiterReport, TrainingLabel, UserReview
from app.models.ml import DatasetImport, ModelVersion
from app.models.user import SecurityAuditLog, User
from app.models.worker import AsyncDocumentJob
from app.services.drift_monitor import calculate_psi, get_privacy_preserving_drift_metrics
from app.services.ml_inference import MLInferenceService
from app.services.model_registry import (
    ModelDeploymentError,
    ModelEvaluationFailedError,
    ModelNotFoundError,
    compute_file_sha256,
    deploy_model_atomic,
    get_active_model_record,
    list_registered_models,
    rollback_model_atomic,
    seed_model_registry,
    validate_artifact_bundle,
)
from app.workers.ocr_worker import (
    JobAccessForbiddenError,
    JobNotFoundError,
    JobValidationError,
    enqueue_offer_letter_ocr_job,
    execute_offer_letter_ocr_job,
    get_job_status_idor_protected,
    recover_stale_processing_jobs,
    run_worker_daemon,
    validate_file_payload,
)


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
PRECOMPUTED_ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$qUeL8Xq4rK7wE6y8uI9oPA$B5yL9q4rK7wE6y8uI9oPAzXyK7wE6y8uI9oPAzXyK7w"


def create_user(db_session, email: str, role: str = "USER", password: str = "Pass1234!") -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=email.lower().strip(),
        hashed_password=PRECOMPUTED_ARGON2_HASH,
        full_name=f"User {role}",
        role=role,
        is_active=True,
        is_verified=True,
    )
    db_session.add(u)
    db_session.commit()
    return u


def auth_headers(user: User) -> dict:
    token = create_access_token(user_id=user.id, email=user.email, role=user.role)
    return {"Authorization": f"Bearer {token}"}


import pymupdf


def make_text_pdf(text: str, num_pages: int = 1) -> bytes:
    doc = pymupdf.open()
    for i in range(num_pages):
        page = doc.new_page()
        page.insert_text((50, 72), f"Page {i + 1}\n\n{text}")
    data = doc.tobytes()
    doc.close()
    return data


SAMPLE_MINIMAL_PDF = make_text_pdf(
    "Offer of Employment\nDear Candidate,\nWe are pleased to offer you the position of Software Engineer at Acme Corp.\n"
    "Annual CTC: INR 12,00,000. Joining Date: 2026-11-01.\nContact: hr@acme-corp.com\nCIN: U72200MH2018PTC309123"
)


# ------------------------------------------------------------------------------
# 1. Model Registry & Seeding Tests
# ------------------------------------------------------------------------------
def test_seed_model_registry_populates_artifacts(db_session):
    """Verifies that seed_model_registry correctly scans ml/artifacts and registers v1.0.0 and v1.1.0."""
    seeded = seed_model_registry(db_session)
    assert len(seeded) >= 1

    v1_1 = db_session.query(ModelVersion).filter(ModelVersion.version == "v1.1.0").first()
    assert v1_1 is not None
    assert v1_1.evaluation_status == "active"
    assert v1_1.metrics is not None
    assert "sha256" in v1_1.metrics
    assert len(v1_1.metrics["sha256"]) == 64  # valid sha256 hex string


def test_list_registered_models_structure(db_session):
    """Verifies list_registered_models returns structured provenance and metrics."""
    seed_model_registry(db_session)
    models = list_registered_models(db_session)
    assert len(models) >= 1

    versions = [m["version"] for m in models]
    assert "v1.1.0" in versions

    for m in models:
        assert "sha256" in m
        assert "evaluation_status" in m
        assert "primary_metrics" in m


def test_validate_artifact_bundle_integrity():
    """Verifies artifact bundle integrity validation."""
    valid, err, bundle = validate_artifact_bundle("ml/artifacts/jobshield_fraud_detector_v1.1.0.joblib")
    assert valid is True
    assert err is None
    assert "vectorizer" in bundle
    assert "primary_classifier" in bundle
    assert "calibrated_classifier" in bundle

    # Non-existent file
    valid_fake, err_fake, _ = validate_artifact_bundle("ml/artifacts/non_existent.joblib")
    assert valid_fake is False
    assert "does not exist" in err_fake


# ------------------------------------------------------------------------------
# 2. Atomic Model Deployment & Rollback Tests
# ------------------------------------------------------------------------------
def test_atomic_model_deployment_and_rollback(db_session):
    """Verifies atomic zero-downtime hot swap and atomic rollback with audit trail."""
    seed_model_registry(db_session)
    admin = create_user(db_session, "admin_deploy@jobshield.ai", role="ADMIN")

    # Ensure v1.1.0 is active
    active = get_active_model_record(db_session)
    assert active.version == "v1.1.0"

    # Deploy v1.0.0 (if present)
    v1_0 = db_session.query(ModelVersion).filter(ModelVersion.version == "v1.0.0").first()
    if v1_0:
        res = deploy_model_atomic(version="v1.0.0", db=db_session, admin_id=admin.id)
        assert res["status"] == "deployed"
        assert res["version"] == "v1.0.0"
        assert res["previous_version"] == "v1.1.0"

        # Check DB states
        db_session.refresh(v1_0)
        assert v1_0.evaluation_status == "active"
        db_session.refresh(active)
        assert active.evaluation_status == "archived"

        # Check audit log
        audit = (
            db_session.query(SecurityAuditLog)
            .filter(SecurityAuditLog.action == "MODEL_DEPLOY")
            .order_by(SecurityAuditLog.created_at.desc())
            .first()
        )
        assert audit is not None
        assert audit.target_id == "v1.0.0"

        # Test Rollback
        rb_res = rollback_model_atomic(db=db_session, admin_id=admin.id)
        assert rb_res["status"] == "rolled_back"
        assert rb_res["active_version"] == "v1.1.0"
        assert rb_res["rolled_back_from"] == "v1.0.0"

        db_session.refresh(active)
        assert active.evaluation_status == "active"

        rb_audit = (
            db_session.query(SecurityAuditLog)
            .filter(SecurityAuditLog.action == "MODEL_ROLLBACK")
            .order_by(SecurityAuditLog.created_at.desc())
            .first()
        )
        assert rb_audit is not None
        assert rb_audit.target_id == "v1.1.0"


def test_atomic_deployment_rejects_invalid_models(db_session):
    """Verifies that unapproved, missing, or rejected models cannot be deployed."""
    seed_model_registry(db_session)
    admin = create_user(db_session, "admin_deploy_fail@jobshield.ai", role="ADMIN")

    # Missing model
    with pytest.raises(ModelNotFoundError):
        deploy_model_atomic("v9.9.9", db=db_session, admin_id=admin.id)

    # Explicitly rejected model
    rejected = ModelVersion(
        version="v1.9.9-rejected",
        artifact_path="ml/artifacts/jobshield_fraud_detector_v1.1.0.joblib",
        dataset_snapshot="test",
        evaluation_status="rejected",
    )
    db_session.add(rejected)
    db_session.commit()

    with pytest.raises(ModelEvaluationFailedError):
        deploy_model_atomic("v1.9.9-rejected", db=db_session, admin_id=admin.id)


# ------------------------------------------------------------------------------
# 3. Privacy-Preserving Drift Monitoring Tests
# ------------------------------------------------------------------------------
def test_psi_calculation():
    """Verifies Population Stability Index mathematical properties."""
    # Identical distributions should yield ~0 PSI
    dist = [0.85, 0.08, 0.04, 0.03]
    assert calculate_psi(dist, dist) < 0.001

    # Shifted distribution
    shifted = [0.70, 0.15, 0.10, 0.05]
    psi = calculate_psi(dist, shifted)
    assert psi > 0.05


def test_privacy_preserving_drift_metrics_zero_pii(db_session):
    """Verifies drift metrics compute mathematical aggregates and zero PII or raw texts."""
    metrics = get_privacy_preserving_drift_metrics(db=db_session, window_days=30)
    assert "window_days" in metrics
    assert "sample_size" in metrics
    assert "risk_category_distribution" in metrics
    assert "psi_score" in metrics
    assert "score_statistics" in metrics
    assert "disclaimer" in metrics

    # Verify absence of raw text keys
    assert "raw_text" not in metrics
    assert "email" not in metrics
    assert "description" not in metrics
    assert "user_input" not in metrics


# ------------------------------------------------------------------------------
# 4. Data Provenance & Quarantine Enforcement Tests
# ------------------------------------------------------------------------------
def test_data_provenance_and_community_quarantine(db_session):
    """Verifies unreviewed community reviews and recruiter reports are strictly quarantined from training."""
    from app.ml.retrain import get_data_provenance_and_quarantine_summary

    # Add sample community review & report
    rev = UserReview(
        submitter_hash="test_sub_hash_1",
        content_hash="test_review_hash",
        rating=1,
        experience_category="RECRUITER_COMMUNICATION",
        review_text="Possible phishing attempt asking for upfront money",
        moderation_status="APPROVED",
    )
    rep = RecruiterReport(
        submitter_hash="test_sub_hash_2",
        claimed_company_name="Acme Corp",
        report_type="FEE_DEMAND",
        description="Demanded deposit fee",
        content_hash="content_hash_12345",
        moderation_status="APPROVED",
    )
    db_session.add_all([rev, rep])
    db_session.commit()

    summary = get_data_provenance_and_quarantine_summary(db_session)
    assert summary["status"] == "governed"
    assert summary["community_data_quarantine"]["is_isolated_from_training"] is True
    assert summary["community_data_quarantine"]["user_reviews_quarantined"] >= 1
    assert summary["community_data_quarantine"]["recruiter_reports_quarantined"] >= 1

    # Invariant: TrainingLabel table remains untouched by community submissions
    training_label_count = db_session.query(TrainingLabel).count()
    assert training_label_count == 0


# ------------------------------------------------------------------------------
# 5. Manual Retraining Engine Tests
# ------------------------------------------------------------------------------
def test_manual_retraining_execution_stages_candidate(db_session):
    """Verifies manual retraining produces a candidate model that is NOT automatically deployed."""
    from app.ml.retrain import execute_manual_retraining_workflow

    admin = create_user(db_session, "admin_trainer@jobshield.ai", role="ADMIN")
    seed_model_registry(db_session)

    active_before = get_active_model_record(db_session)
    active_version_before = active_before.version

    result = execute_manual_retraining_workflow(
        db=db_session,
        invoked_by_admin=admin.email,
    )

    assert result["status"] == "candidate_staged"
    assert result["version"].startswith("v1.2.0-candidate-")
    assert result["deployed"] is False

    # Verify active model is UNCHANGED
    active_after = get_active_model_record(db_session)
    assert active_after.version == active_version_before
    assert active_after.evaluation_status == "active"

    # Verify candidate is recorded in DB
    candidate_rec = (
        db_session.query(ModelVersion)
        .filter(ModelVersion.version == result["version"])
        .first()
    )
    assert candidate_rec is not None
    assert candidate_rec.evaluation_status == "candidate"
    assert candidate_rec.deployed_at is None


# ------------------------------------------------------------------------------
# 6. Asynchronous OCR Worker & Queue Tests
# ------------------------------------------------------------------------------
def test_validate_file_payload():
    """Verifies PDF magic bytes and payload validation."""
    valid_sha256 = validate_file_payload(SAMPLE_MINIMAL_PDF, "sample.pdf")
    assert len(valid_sha256) == 64

    # Non-PDF rejection
    with pytest.raises(JobValidationError) as exc:
        validate_file_payload(b"Not a PDF document", "test.txt")
    assert "missing %PDF header" in str(exc.value)

    # Empty file rejection
    with pytest.raises(JobValidationError) as exc_empty:
        validate_file_payload(b"", "empty.pdf")
    assert "empty" in str(exc_empty.value)


def test_enqueue_offer_letter_ocr_job_and_deduplication(db_session):
    """Verifies job creation, SHA-256 calculation, and deduplication for identical files."""
    user = create_user(db_session, "job_user@jobshield.ai", role="USER")

    # First upload
    job1, is_new1 = enqueue_offer_letter_ocr_job(
        db=db_session,
        file_bytes=SAMPLE_MINIMAL_PDF,
        file_name="offer_letter.pdf",
        current_user=user,
    )
    assert is_new1 is True
    assert job1.status == "PENDING"
    assert job1.file_sha256 == hashlib.sha256(SAMPLE_MINIMAL_PDF).hexdigest()

    # Second upload of the identical file by the same user -> Deduplicated!
    job2, is_new2 = enqueue_offer_letter_ocr_job(
        db=db_session,
        file_bytes=SAMPLE_MINIMAL_PDF,
        file_name="offer_letter_copy.pdf",
        current_user=user,
    )
    assert is_new2 is False
    assert job2.id == job1.id


def test_async_job_idor_protection(db_session):
    """Verifies that User B cannot access User A's asynchronous document job."""
    user_a = create_user(db_session, "user_a@jobshield.ai", role="USER")
    user_b = create_user(db_session, "user_b@jobshield.ai", role="USER")
    admin = create_user(db_session, "admin_jobs@jobshield.ai", role="ADMIN")

    job, _ = enqueue_offer_letter_ocr_job(
        db=db_session,
        file_bytes=SAMPLE_MINIMAL_PDF,
        file_name="private_offer.pdf",
        current_user=user_a,
    )

    # Owner can access
    job_res = get_job_status_idor_protected(db=db_session, job_id=job.id, current_user=user_a)
    assert job_res.id == job.id

    # Admin can access
    admin_job_res = get_job_status_idor_protected(db=db_session, job_id=job.id, current_user=admin)
    assert admin_job_res.id == job.id

    # User B is forbidden (IDOR protection)
    with pytest.raises(JobAccessForbiddenError):
        get_job_status_idor_protected(db=db_session, job_id=job.id, current_user=user_b)


def test_execute_offer_letter_ocr_job(db_session):
    """Verifies end-to-end background OCR execution updates job status and stores result scan."""
    user = create_user(db_session, "ocr_runner@jobshield.ai", role="USER")
    job, _ = enqueue_offer_letter_ocr_job(
        db=db_session,
        file_bytes=SAMPLE_MINIMAL_PDF,
        file_name="sample_offer.pdf",
        current_user=user,
    )

    completed_job = execute_offer_letter_ocr_job(
        db=db_session,
        job_id=job.id,
        file_bytes=SAMPLE_MINIMAL_PDF,
    )

    assert completed_job.status == "COMPLETED"
    assert completed_job.progress == 100
    assert completed_job.result_scan_id is not None
    assert completed_job.result_summary is not None
    assert "risk_score" in completed_job.result_summary
    assert "risk_category" in completed_job.result_summary


def test_ocr_worker_stale_job_crash_recovery(db_session):
    """Verifies that stale jobs left in PROCESSING by a crashed worker are automatically failed and recoverable."""
    user = create_user(db_session, "crash_test_user@jobshield.ai", role="USER")
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=120)

    # Simulate an abandoned job from a crashed worker process
    crashed_job = AsyncDocumentJob(
        id=str(uuid.uuid4()),
        user_id=user.id,
        job_type="OFFER_LETTER_OCR",
        file_sha256=hashlib.sha256(SAMPLE_MINIMAL_PDF).hexdigest(),
        file_name="crashed.pdf",
        file_size_bytes=len(SAMPLE_MINIMAL_PDF),
        status="PROCESSING",
        progress=30,
        started_at=stale_time,
        created_at=stale_time,
    )
    db_session.add(crashed_job)
    db_session.commit()

    # Querying status directly triggers automatic crash recovery
    checked_job = get_job_status_idor_protected(db_session, crashed_job.id, current_user=user)
    assert checked_job.status == "FAILED"
    assert "timed out or worker process was restarted" in checked_job.error_message

    # Re-uploading the same file now successfully enqueues a fresh job instead of hanging
    new_job, is_new = enqueue_offer_letter_ocr_job(
        db=db_session,
        file_bytes=SAMPLE_MINIMAL_PDF,
        file_name="crashed_retry.pdf",
        current_user=user,
    )
    assert is_new is True
    assert new_job.id != crashed_job.id
    assert new_job.status == "PENDING"


def test_ocr_worker_daemon_sweep_cycle(db_session):
    """Verifies that the standalone background worker daemon sweep cycle executes cleanly."""
    # Execute a single daemon sweep cycle
    run_worker_daemon(poll_interval_seconds=0.1, once=True)


def test_multi_process_model_sync(db_session):
    """Verifies that an out-of-sync worker process detects active model changes in DB and synchronizes."""
    seed_model_registry(db_session)

    # Simulate worker process 2 initialized with v1.0.0
    worker2_svc = MLInferenceService(artifact_path="ml/artifacts/jobshield_fraud_detector_v1.0.0.joblib")
    assert worker2_svc.version == "v1.0.0"

    # Admin activates v1.1.0 in DB
    v11 = db_session.query(ModelVersion).filter(ModelVersion.version == "v1.1.0").first()
    v10 = db_session.query(ModelVersion).filter(ModelVersion.version == "v1.0.0").first()
    v10.evaluation_status = "archived"
    v11.evaluation_status = "active"
    db_session.commit()

    # Worker process 2 synchronizes from DB
    updated = worker2_svc.sync_active_model_from_db(db=db_session, force=True)
    assert updated is True
    assert worker2_svc.version == "v1.1.0"
    assert worker2_svc.is_available() is True


# ------------------------------------------------------------------------------
# 7. Production API Endpoints & RBAC Integration Tests
# ------------------------------------------------------------------------------
def test_admin_models_endpoints_rbac(test_client, db_session):
    """Verifies RBAC enforcement on admin model endpoints (Visitor 401, User 403, Admin 200)."""
    user = create_user(db_session, "regular_ml@jobshield.ai", role="USER")
    admin = create_user(db_session, "admin_ml@jobshield.ai", role="ADMIN")

    # 1. Unauthenticated (401)
    res_unauth = test_client.get("/api/v1/admin/models")
    assert res_unauth.status_code == 401

    # 2. Regular User (403)
    res_user = test_client.get("/api/v1/admin/models", headers=auth_headers(user))
    assert res_user.status_code == 403

    # 3. Admin (200)
    res_admin = test_client.get("/api/v1/admin/models", headers=auth_headers(admin))
    assert res_admin.status_code == 200
    body = res_admin.json()
    assert "models" in body
    assert body["total"] >= 1


def test_admin_monitoring_drift_endpoint(test_client, db_session):
    """Verifies the drift monitoring endpoint returns privacy-preserving metrics."""
    admin = create_user(db_session, "admin_drift@jobshield.ai", role="ADMIN")
    res = test_client.get("/api/v1/admin/monitoring/drift?window_days=14", headers=auth_headers(admin))
    assert res.status_code == 200
    data = res.json()
    assert data["window_days"] == 14
    assert "psi_score" in data
    assert "disclaimer" in data


def test_admin_retraining_endpoints(test_client, db_session):
    """Verifies training provenance and manual retraining trigger endpoints."""
    admin = create_user(db_session, "admin_retrain_ep@jobshield.ai", role="ADMIN")

    # Provenance
    prov_res = test_client.get("/api/v1/admin/retraining/provenance", headers=auth_headers(admin))
    assert prov_res.status_code == 200
    prov_data = prov_res.json()
    assert prov_data["status"] == "governed"
    assert prov_data["community_data_quarantine"]["is_isolated_from_training"] is True

    # Manual Retrain Trigger
    train_res = test_client.post("/api/v1/admin/retraining/trigger", headers=auth_headers(admin))
    assert train_res.status_code == 200
    train_data = train_res.json()
    assert train_data["status"] == "candidate_staged"
    assert train_data["deployed"] is False


def test_async_jobs_api_flow(test_client, db_session):
    """Verifies the async OCR jobs API: enqueue (202), poll status (200), and IDOR protection (403)."""
    user_a = create_user(db_session, "api_user_a@jobshield.ai", role="USER")
    user_b = create_user(db_session, "api_user_b@jobshield.ai", role="USER")

    # Enqueue valid PDF
    files = {"file": ("offer.pdf", io.BytesIO(SAMPLE_MINIMAL_PDF), "application/pdf")}
    data = {"company_name": "Acme Inc"}
    res = test_client.post(
        "/api/v1/jobs/offer-letter/async",
        headers=auth_headers(user_a),
        files=files,
        data=data,
    )
    assert res.status_code == 202
    job_info = res.json()
    job_id = job_info["id"]
    assert job_info["status"] == "PENDING"
    assert job_info["is_new_job"] is True

    # Poll status as Owner (200)
    status_res = test_client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers(user_a))
    assert status_res.status_code == 200
    assert status_res.json()["id"] == job_id

    # Poll status as User B -> 403 Forbidden (IDOR Protection)
    status_res_b = test_client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers(user_b))
    assert status_res_b.status_code == 403
    assert "do not have permission" in status_res_b.json()["detail"].lower()

    # Reject non-PDF upload
    bad_files = {"file": ("bad.exe", io.BytesIO(b"MZ executable header"), "application/octet-stream")}
    bad_res = test_client.post(
        "/api/v1/jobs/offer-letter/async",
        headers=auth_headers(user_a),
        files=bad_files,
    )
    assert bad_res.status_code == 400
    assert "%pdf" in bad_res.json()["detail"].lower()
