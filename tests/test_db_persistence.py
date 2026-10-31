"""Database Persistence Acceptance Tests for JobShield AI.

Verifies:
- Relational mapping between ScanRequest, VerificationEvidence, and PredictionHistory.
- SHA-256 cryptographic digest calculation and reference formatting.
- Clean isolation between multiple sequential scans.
- Cascade deletion behavior (all children cleaned on scan deletion).
- Partial persistence omission for insufficient evidence (omitting ML prediction record).
"""

import hashlib
import os
import sys
import pytest

# Ensure backend directory is in sys.path
backend_path = os.path.abspath("backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.models import PredictionHistory, ScanRequest, VerificationEvidence


def test_scan_and_all_relations_persisted(test_client, db_session):
    """Verify that a successful scan persists ScanRequest, VerificationEvidence, and PredictionHistory with foreign keys."""
    job_text = """
    Lead React Native Developer - Mobile Engineering Team
    London, UK (Full-time)
    
    We are seeking a senior mobile engineer with 4+ years of React Native and TypeScript experience.
    Competitive compensation £75,000 - £90,000 per year with equity stock options.
    Apply via our official corporate careers portal at https://careers.mobiletech.example.com.
    """
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": job_text})
    assert resp.status_code == 200
    report_id = resp.json()["report_id"]

    # 1. Verify ScanRequest record
    scan = db_session.query(ScanRequest).filter(ScanRequest.id == report_id).first()
    assert scan is not None
    assert scan.input_type == "job_text"
    assert scan.status == "completed"
    assert scan.completed_at is not None

    # Verify SHA-256 reference
    expected_hash = hashlib.sha256(job_text.strip().encode("utf-8")).hexdigest()
    assert scan.input_reference == f"sha256:{expected_hash}"

    # 2. Verify VerificationEvidence relationship
    assert len(scan.evidence_records) > 0
    for ev in scan.evidence_records:
        assert ev.scan_id == report_id
        assert ev.evidence_type in ("rule_signal", "ml_prediction", "data_quality")
        assert ev.source_name is not None
        assert ev.summary is not None

    # 3. Verify PredictionHistory relationship
    assert len(scan.prediction_records) == 1
    pred = scan.prediction_records[0]
    assert pred.scan_id == report_id
    assert pred.model_version == "v1.1.0"
    assert pred.predicted_class in ("LEGITIMATE", "FRAUDULENT")
    assert pred.model_probability is not None
    assert 0.0 <= pred.model_probability <= 1.0
    assert pred.risk_score == resp.json()["risk_score"]
    assert pred.risk_category == resp.json()["risk_category"]
    assert isinstance(pred.explanation, dict)
    assert "decision_threshold" in pred.explanation


def test_insufficient_evidence_persists_scan_and_evidence_without_prediction(test_client, db_session):
    """Verify that an insufficient evidence scan creates ScanRequest and data_quality evidence, but no PredictionHistory."""
    scant_text = "Hiring immediately for work. Apply now."
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": scant_text})
    assert resp.status_code == 200
    report_id = resp.json()["report_id"]

    scan = db_session.query(ScanRequest).filter(ScanRequest.id == report_id).first()
    assert scan is not None
    assert scan.status == "completed"

    # Must have data_quality evidence item
    assert len(scan.evidence_records) == 1
    assert scan.evidence_records[0].evidence_type == "data_quality"
    assert scan.evidence_records[0].status == "INSUFFICIENT_EVIDENCE"

    # ML was not evaluated, so no PredictionHistory row should exist
    assert len(scan.prediction_records) == 0


def test_multiple_scans_isolated_and_independent(test_client, db_session):
    """Verify that scanning identical text multiple times creates distinct scans with separate report IDs."""
    job_text = """
    Full Stack Developer needed. Python and React.
    Competitive salary 90,000 USD. Apply at careers@example.com.
    """
    resp1 = test_client.post("/api/v1/analyze/job-text", json={"text": job_text})
    resp2 = test_client.post("/api/v1/analyze/job-text", json={"text": job_text})

    assert resp1.status_code == 200
    assert resp2.status_code == 200

    id1 = resp1.json()["report_id"]
    id2 = resp2.json()["report_id"]
    assert id1 != id2

    scan1 = db_session.query(ScanRequest).filter(ScanRequest.id == id1).first()
    scan2 = db_session.query(ScanRequest).filter(ScanRequest.id == id2).first()
    assert scan1 is not None
    assert scan2 is not None
    assert scan1.id != scan2.id
    # Both have the same content hash in input_reference
    assert scan1.input_reference == scan2.input_reference


def test_persistence_cascade_delete(test_client, db_session):
    """Verify that deleting a ScanRequest cascades and removes associated evidence and predictions."""
    job_text = """
    DevOps Engineer with AWS, Terraform, and CI/CD experience.
    Salary 110,000 USD. Apply at https://careers.example.com.
    """
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": job_text})
    report_id = resp.json()["report_id"]

    scan = db_session.query(ScanRequest).filter(ScanRequest.id == report_id).first()
    assert scan is not None
    assert len(scan.evidence_records) > 0
    assert len(scan.prediction_records) > 0

    # Delete scan request
    db_session.delete(scan)
    db_session.commit()

    # Verify children are deleted via CASCADE
    remaining_evidence = db_session.query(VerificationEvidence).filter(VerificationEvidence.scan_id == report_id).all()
    remaining_preds = db_session.query(PredictionHistory).filter(PredictionHistory.scan_id == report_id).all()
    assert len(remaining_evidence) == 0
    assert len(remaining_preds) == 0


def test_persistence_succeeds_even_when_company_verification_encounters_db_error(test_client, db_session):
    """Regression test for UI error: 'Database persistence failed. Scan record could not be saved.'

    Verifies that when company registry verification encounters an internal DB query failure,
    the session transaction is rolled back cleanly so that scan records (ScanRequest,
    VerificationEvidence, PredictionHistory) are still persisted and committed without
    PendingRollbackError or DatabasePersistenceError (HTTP 503).
    """
    from unittest.mock import patch

    sample_text = (
        "We are looking for a Senior Python Developer with 5+ years of experience in Django, "
        "FastAPI, and PostgreSQL. Remote work available. Competitive salary."
    )

    orig_execute = db_session.execute
    called = False

    def failing_execute(*args, **kwargs):
        nonlocal called
        if not called:
            called = True
            raise Exception("Simulated DB query error during company lookup")
        return orig_execute(*args, **kwargs)

    with patch.object(db_session, "execute", side_effect=failing_execute):
        resp = test_client.post(
            "/api/v1/analyze/job-text",
            json={
                "text": sample_text,
                "company_name": "Tech Corp Pvt Ltd",
            },
        )

    # Must NOT fail with 503 "Database persistence failed"
    assert resp.status_code == 200
    data = resp.json()
    assert data["company_verification"]["status"] == "SOURCE_UNAVAILABLE"

    # Scan records must be persisted
    report_id = data["report_id"]
    scan = db_session.query(ScanRequest).filter(ScanRequest.id == report_id).first()
    assert scan is not None
    assert scan.status == "completed"
    assert len(scan.evidence_records) > 0
    assert len(scan.prediction_records) == 1
