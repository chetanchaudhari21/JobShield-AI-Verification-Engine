"""Integration and Unit Tests for POST /api/v1/analyze/job-text.

Verifies:
- Rejection of empty, whitespace-only, and oversized input payloads.
- Insufficient evidence response when text lacks minimum informative context.
- Legitimate job posting analysis (low risk, valid schema, proper field disclosure).
- Scam job posting detection (rule signals labeled distinctly, safe actions, high risk).
- No single keyword decides the outcome (counter-examples with 'bank' and 'fee').
- Database persistence of scan requests, verification evidence, and prediction records.
- Strict privacy: submitted raw text is NEVER logged or persisted in database records.
- Configurable provisional thresholds labeled as provisional and not calibrated.
"""

import os
import sys
import pytest
from starlette.testclient import TestClient

# Ensure backend directory is in sys.path
backend_path = os.path.abspath("backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models import PredictionHistory, ScanRequest, VerificationEvidence


@pytest.fixture
def test_client(db_session):
    """Provides a TestClient with get_db overridden to use the isolated test db_session."""
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_db, None)


def test_empty_and_whitespace_input_rejected(test_client):
    """Verify empty or whitespace-only inputs are rejected with 422 Unprocessable Entity."""
    # 1. Empty string
    resp1 = test_client.post("/api/v1/analyze/job-text", json={"text": ""})
    assert resp1.status_code == 422
    assert "Job text cannot be empty" in resp1.text or "at least 20" in resp1.text

    # 2. Whitespace-only string
    resp2 = test_client.post("/api/v1/analyze/job-text", json={"text": "      \n\n\t   "})
    assert resp2.status_code == 422

    # 3. String shorter than 20 characters
    resp3 = test_client.post("/api/v1/analyze/job-text", json={"text": "Short job"})
    assert resp3.status_code == 422
    assert "too short" in resp3.text or "at least 20" in resp3.text


def test_oversized_input_rejected(test_client):
    """Verify input exceeding 50,000 characters is rejected with 422."""
    huge_text = "Senior Python Engineer " * 2500  # ~57,500 chars
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": huge_text})
    assert resp.status_code == 422
    assert "exceeds maximum allowed size" in resp.text or "at most 50000" in resp.text


def test_insufficient_evidence_for_scant_text(test_client):
    """Verify text with insufficient informative context returns INSUFFICIENT_EVIDENCE."""
    scant_text = "Hiring job. Looking for someone with good work to apply now."
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": scant_text})
    assert resp.status_code == 200
    data = resp.json()

    assert data["risk_category"] == "INSUFFICIENT_EVIDENCE"
    assert data["risk_score"] is None
    assert "insufficient" in data["warning"].lower()
    assert data["provisional_thresholds"]["status"] == "provisional"
    assert data["provisional_thresholds"]["version"] == settings.RISK_THRESHOLD_VERSION

    # Evidence item must indicate insufficient evidence
    evidence_types = [e["evidence_type"] for e in data["evidence"]]
    assert "data_quality" in evidence_types


def test_legitimate_job_text_analysis(test_client):
    """Verify standard legitimate software engineering vacancy returns LOW risk with all Section 4 fields."""
    legit_job = """
    Senior Software Engineer - Backend (Python / FastAPI)
    Acme Tech Solutions Ltd. - London, UK (Hybrid)
    
    About the Role:
    We are seeking an experienced Backend Engineer to scale our distributed cloud architecture.
    You will collaborate with cross-functional teams to design high-throughput RESTful APIs,
    maintain PostgreSQL database schemas, and deploy containerized services on Kubernetes.
    
    Requirements:
    - 5+ years of software development experience with Python.
    - Deep familiarity with FastAPI, SQLAlchemy, and automated test frameworks.
    - Solid understanding of asynchronous programming and database indexing.
    - Bachelor's degree in Computer Science or equivalent practical experience.
    
    Benefits & Compensation:
    - Competitive salary: £85,000 - £100,000 per annum depending on experience.
    - Comprehensive private medical insurance and pension plan.
    - 28 days paid annual leave and flexible hybrid working arrangements.
    
    How to Apply:
    Submit your CV through our careers portal at https://careers.acmetech.example.com.
    """

    resp = test_client.post("/api/v1/analyze/job-text", json={"text": legit_job})
    assert resp.status_code == 200
    data = resp.json()

    # All required Section 4 fields must be present
    assert "report_id" in data
    assert "timestamp" in data
    assert "risk_score" in data
    assert "risk_category" in data
    assert "provisional_thresholds" in data
    assert "evidence" in data
    assert "ml_analysis" in data
    assert "company_verification" in data
    assert "recruiter_checks" in data
    assert "community_summary" in data
    assert "recommended_safe_actions" in data
    assert "limitations" in data
    assert "disclaimer" in data

    # Score expectations
    assert data["risk_score"] is not None
    assert 0.0 <= data["risk_score"] <= 30.0
    assert data["risk_category"] == "LOW"

    # ML Analysis expectations
    ml = data["ml_analysis"]
    assert ml["model_version"] == "v1.1.0"
    assert ml["primary_prediction"] == "LEGITIMATE"
    assert 0.0 <= ml["calibrated_probability"] <= 0.40
    assert ml["decision_threshold"] == 0.40
    assert "FrozenEstimator" in ml["calibration_method"]

    # Provisional thresholds must be explicit
    th = data["provisional_thresholds"]
    assert th["status"] == "provisional"
    assert "not statistically calibrated" in th["disclaimer"]


def test_scam_job_text_triggers_rules_and_high_risk(test_client):
    """Verify scam job asking for upfront fee and WhatsApp chat is flagged as HIGH/CRITICAL risk."""
    scam_job = """
    URGENT HIRING: Data Entry Assistant / Online Typist
    Immediate joining today! Only 2 spots left! Apply immediately!
    
    Work from home and earn 5000 daily with no prior experience needed.
    Guaranteed daily payout directly to your account.
    
    To secure your laptop equipment and complete background verification,
    candidates must pay an upfront registration fee of 1500 refundable security deposit.
    
    Contact HR manager immediately on WhatsApp: +91 9876543210.
    Send your resume to hr.hiring.fast@gmail.com for instant onboarding.
    """

    resp = test_client.post("/api/v1/analyze/job-text", json={"text": scam_job})
    assert resp.status_code == 200
    data = resp.json()

    assert data["risk_score"] >= 65.0
    assert data["risk_category"] in ("HIGH", "CRITICAL")
    assert data["warning"] is not None
    assert "POTENTIAL FRAUD" in data["warning"]

    # Rule signals must be disclosed as rules, not ML discoveries
    rule_evidence = [e for e in data["evidence"] if e["evidence_type"] == "rule_signal"]
    rule_names = [e["source_name"] for e in rule_evidence]

    assert any("Upfront Fees" in name for name in rule_names)
    assert any("Suspicious Contact" in name for name in rule_names)
    assert any("Free Webmail" in name for name in rule_names)

    # ML Analysis must be distinct
    assert data["ml_analysis"] is not None
    assert data["ml_analysis"]["primary_prediction"] in ("FRAUDULENT", "LEGITIMATE")

    # Safe actions must warn against paying fees
    actions_text = " ".join(data["recommended_safe_actions"])
    assert "NEVER PAY" in actions_text


def test_no_single_keyword_decides_outcome(test_client):
    """Verify that isolated words like 'fee' or 'bank' in legitimate contexts do NOT trigger fraud."""
    legit_bank_job = """
    Risk Management Associate - State Bank of Commerce
    Mumbai, India (Full-Time)
    
    About Us:
    State Bank of Commerce is a licensed commercial bank operating across 12 countries.
    We are seeking a Risk Analyst to evaluate credit portfolios and regulatory compliance.
    
    Benefits & Compensation:
    - We provide comprehensive tuition fee reimbursement for professional CFA certifications.
    - Annual banking performance bonus and provident fund contributions.
    - Annual salary: INR 12,00,000 - 15,00,000 per annum.
    
    Application:
    Apply via our official corporate portal at https://careers.statebankofcommerce.example.com.
    """

    resp = test_client.post("/api/v1/analyze/job-text", json={"text": legit_bank_job})
    assert resp.status_code == 200
    data = resp.json()

    # Neither upfront fee rule nor sensitive info rule should be DETECTED
    rule_evidence = [e for e in data["evidence"] if e["evidence_type"] == "rule_signal"]
    detected_rule_names = [e["source_name"] for e in rule_evidence]

    assert not any("Upfront Fees" in name for name in detected_rule_names)
    assert not any("Sensitive Information" in name for name in detected_rule_names)
    assert data["risk_category"] in ("LOW", "MODERATE")


def test_database_persistence_of_scans_evidence_predictions(test_client, db_session):
    """Verify that every scan correctly persists ScanRequest, VerificationEvidence, and PredictionHistory rows."""
    test_text = """
    Senior Data Engineer needed for building ETL pipelines.
    Python, SQL, Apache Spark, Snowflake.
    Competitive salary 120,000 USD per year. Apply at careers@example.com.
    """

    resp = test_client.post("/api/v1/analyze/job-text", json={"text": test_text})
    assert resp.status_code == 200
    data = resp.json()
    report_id = data["report_id"]

    # 1. Query ScanRequest
    scan = db_session.query(ScanRequest).filter(ScanRequest.id == report_id).first()
    assert scan is not None
    assert scan.input_type == "job_text"
    assert scan.status == "completed"
    assert scan.input_reference.startswith("sha256:")

    # 2. Query VerificationEvidence
    evidence_rows = db_session.query(VerificationEvidence).filter(VerificationEvidence.scan_id == report_id).all()
    assert len(evidence_rows) > 0
    for ev in evidence_rows:
        assert ev.evidence_type in ("rule_signal", "ml_prediction", "data_quality")
        assert ev.status in ("DETECTED", "NOT_DETECTED", "UNVERIFIED")

    # 3. Query PredictionHistory
    pred = db_session.query(PredictionHistory).filter(PredictionHistory.scan_id == report_id).first()
    assert pred is not None
    assert pred.model_version == "v1.1.0"
    assert pred.risk_score == data["risk_score"]
    assert pred.risk_category == data["risk_category"]
    assert pred.threshold_version == settings.RISK_THRESHOLD_VERSION
    assert pred.explanation is not None


def test_no_raw_submitted_text_in_logs_or_db(test_client, db_session, caplog):
    """Verify strict privacy enforcement: the raw submitted text is NEVER stored in DB or logged."""
    canary_token = "CANARY_TOKEN_TOP_SECRET_USER_TEXT_123456789"
    job_with_canary = f"""
    Senior Backend Architect. Developing microservices.
    This job description includes a confidential internal reference: {canary_token}.
    Full-time role with 401k, health dental vision, 140,000 USD base salary.
    """

    resp = test_client.post("/api/v1/analyze/job-text", json={"text": job_with_canary})
    assert resp.status_code == 200
    report_id = resp.json()["report_id"]

    # 1. Check ScanRequest table in DB
    scan = db_session.query(ScanRequest).filter(ScanRequest.id == report_id).first()
    assert scan is not None
    assert canary_token not in scan.input_reference
    assert canary_token not in str(scan.id)

    # 2. Check VerificationEvidence table in DB
    evidences = db_session.query(VerificationEvidence).filter(VerificationEvidence.scan_id == report_id).all()
    for ev in evidences:
        assert canary_token not in ev.summary
        assert canary_token not in str(ev.raw_metadata)

    # 3. Check PredictionHistory table in DB
    pred = db_session.query(PredictionHistory).filter(PredictionHistory.scan_id == report_id).first()
    assert pred is not None
    assert canary_token not in str(pred.explanation)

    # 4. Check application logs (caplog)
    for log_record in caplog.records:
        assert canary_token not in log_record.message


def test_validation_error_redacts_submitted_text(test_client):
    """Verify that validation errors (422) never echo or leak raw submitted text in client responses."""
    canary = "SENSITIVE_LEAK_CANARY_STRING_99999"
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": canary[:10]})
    assert resp.status_code == 422
    # The response text must NEVER contain the raw canary string
    assert canary[:10] not in resp.text
    assert "[REDACTED" in resp.text


def test_missing_model_artifact_raises_503(test_client, monkeypatch):
    """Verify that missing ML model artifact results in HTTP 503 and never returns partial analysis or falls back to v1.0.0."""
    from app.services.ml_inference import MLInferenceService

    broken_service = MLInferenceService(artifact_path="ml/artifacts/non_existent_model.joblib")
    monkeypatch.setattr("app.services.risk_engine.get_ml_service", lambda: broken_service)

    resp = test_client.post(
        "/api/v1/analyze/job-text",
        json={"text": "Senior Python Backend Developer with 5 years experience in building APIs. Apply now."},
    )
    assert resp.status_code == 503
    assert "ML inference service is currently unavailable" in resp.json()["detail"]
    assert broken_service.version != "v1.0.0"


def test_corrupt_model_artifact_raises_503(test_client, monkeypatch, tmp_path):
    """Verify that a corrupted model artifact results in HTTP 503 without returning partial rule-only analysis."""
    import joblib
    from app.services.ml_inference import MLInferenceService

    corrupt_file = tmp_path / "corrupt_artifact.joblib"
    joblib.dump({"version": "v1.1.0", "corrupted": True}, corrupt_file)

    broken_service = MLInferenceService(artifact_path=str(corrupt_file))
    monkeypatch.setattr("app.services.risk_engine.get_ml_service", lambda: broken_service)

    resp = test_client.post(
        "/api/v1/analyze/job-text",
        json={"text": "Senior Python Backend Developer with 5 years experience in building APIs. Apply now."},
    )
    assert resp.status_code == 503
    assert "ML inference service is currently unavailable" in resp.json()["detail"]


def test_ml_inference_exception_raises_503(test_client, monkeypatch):
    """Verify that unexpected ML inference exceptions fail cleanly with HTTP 503 instead of masking the error."""
    from app.services.ml_inference import get_ml_service

    ml_svc = get_ml_service()

    def _raising_transform(*args, **kwargs):
        raise RuntimeError("Simulated vectorizer internal memory fault")

    monkeypatch.setattr(ml_svc.vectorizer, "transform", _raising_transform)

    resp = test_client.post(
        "/api/v1/analyze/job-text",
        json={"text": "Senior Python Backend Developer with 5 years experience in building APIs. Apply now."},
    )
    assert resp.status_code == 503
    assert "ML inference service is currently unavailable" in resp.json()["detail"]


def test_database_persistence_failure_raises_503(test_client, db_session, monkeypatch):
    """Verify that database persistence failure returns HTTP 503 and does NOT return an unpersisted report_id."""
    from sqlalchemy.exc import OperationalError

    def _failing_commit():
        raise OperationalError("Simulated DB connection lost during commit", None, None)

    monkeypatch.setattr(db_session, "commit", _failing_commit)

    resp = test_client.post(
        "/api/v1/analyze/job-text",
        json={"text": "Senior Python Backend Developer with 5 years experience in building APIs. Apply now."},
    )
    assert resp.status_code == 503
    assert "Database persistence failed" in resp.json()["detail"]


def test_insufficient_evidence_never_categorized_as_low_risk(test_client):
    """Explicitly verify that insufficient evidence is never categorized as LOW or LEGITIMATE."""
    test_cases = [
        "Quick job for you. Apply here today please.",
        "Hiring now for office work. Good pay.",
        "Work from home. Flexible hours available.",
    ]
    for text in test_cases:
        resp = test_client.post("/api/v1/analyze/job-text", json={"text": text})
        assert resp.status_code == 200
        data = resp.json()
        assert data["risk_category"] == "INSUFFICIENT_EVIDENCE"
        assert data["risk_category"] != "LOW"
        assert data["risk_category"] != "LEGITIMATE"
        assert data["risk_score"] is None
        assert data["ml_analysis"] is None


def test_model_thresholds_and_separation_verified(test_client):
    """Verify that primary threshold (0.62) and calibrated threshold (0.40) are distinct and documented."""
    legit_job = """
    Principal Site Reliability Engineer
    Datacenter infrastructure, Terraform, AWS, Prometheus monitoring.
    Competitive package 150,000 USD. Apply at https://careers.example.com.
    """
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": legit_job})
    assert resp.status_code == 200
    data = resp.json()

    ml = data["ml_analysis"]
    assert ml["model_version"] == "v1.1.0"
    assert ml["primary_threshold"] == 0.62
    assert ml["calibrated_threshold"] == 0.40
    assert ml["decision_threshold"] == 0.40
    assert ml["primary_prediction"] in ("LEGITIMATE", "FRAUDULENT")
    assert ml["calibrated_prediction"] in ("LEGITIMATE", "FRAUDULENT")

    # Verify ML probability is bounded in [0, 1] while risk score is bounded in [0, 100]
    assert 0.0 <= ml["calibrated_probability"] <= 1.0
    assert 0.0 <= data["risk_score"] <= 100.0
    assert data["risk_score"] != ml["calibrated_probability"]
