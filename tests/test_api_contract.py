"""API Contract Acceptance Tests for POST /api/v1/analyze/job-text.

Verifies conformance to Section 4 of PROJECT_SPECIFICATION.md:
- Full schema structure, field types, and nested contract keys.
- Distinct separation of ML outputs, rule signals, and composite score.
- Provisional thresholds disclosure formatting.
- Insufficient evidence response structure.
- HTTP methods, content-types, and status code guarantees.
"""

import os
import sys
import uuid
from datetime import datetime
import pytest

# Ensure backend directory is in sys.path
backend_path = os.path.abspath("backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.config import settings


def test_api_contract_all_section_4_fields_present(test_client):
    """Verify that a successful job text analysis returns all Section 4 fields with exact types."""
    valid_job = """
    Senior Cloud Architect - Enterprise Infrastructure
    Location: New York, NY (Hybrid)
    
    About the Role:
    Designing fault-tolerant cloud solutions on AWS and Kubernetes.
    Collaborating with platform engineering to automate infrastructure provisioning.
    
    Requirements:
    - 7+ years of software architecture and cloud infrastructure experience.
    - Deep expertise in Terraform, Docker, Python, and PostgreSQL.
    - Bachelor's degree in Computer Science or equivalent.
    
    Compensation:
    - Base salary: $160,000 - $190,000 per year + 401(k) match.
    - Full health, vision, and dental insurance.
    
    Apply at https://careers.cloudenterprise.example.com.
    """
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": valid_job})
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    data = resp.json()

    # 1. Top-level identifiers & timestamps
    assert "report_id" in data
    uuid_obj = uuid.UUID(data["report_id"])
    assert str(uuid_obj) == data["report_id"]

    assert "timestamp" in data
    dt = datetime.fromisoformat(data["timestamp"])
    assert dt is not None

    # 2. Composite Risk Assessment
    assert "risk_score" in data
    assert isinstance(data["risk_score"], (int, float))
    assert 0.0 <= data["risk_score"] <= 100.0

    assert "risk_category" in data
    assert data["risk_category"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")

    # 3. Provisional Thresholds Schedule
    assert "provisional_thresholds" in data
    th = data["provisional_thresholds"]
    assert th["version"] == settings.RISK_THRESHOLD_VERSION
    assert th["status"] == "provisional"
    assert "ranges" in th
    assert len(th["ranges"]) == 4
    for r in th["ranges"]:
        assert "min_score" in r
        assert "max_score" in r
        assert "category" in r
        assert "description" in r
    assert "not statistically calibrated" in th["disclaimer"]

    # 4. Evidence Signals
    assert "evidence" in data
    assert isinstance(data["evidence"], list)
    assert len(data["evidence"]) > 0
    for ev in data["evidence"]:
        assert "evidence_type" in ev
        assert ev["evidence_type"] in ("rule_signal", "ml_prediction", "data_quality")
        assert "source_name" in ev
        assert "status" in ev
        assert ev["status"] in ("DETECTED", "NOT_DETECTED", "UNVERIFIED", "INSUFFICIENT_EVIDENCE")
        assert "summary" in ev
        assert len(ev["summary"]) > 0

    # 5. ML Analysis (Separated from composite score)
    assert "ml_analysis" in data
    ml = data["ml_analysis"]
    assert ml is not None
    assert ml["model_version"] == "v1.1.0"
    assert ml["primary_prediction"] in ("LEGITIMATE", "FRAUDULENT")
    assert ml["calibrated_prediction"] in ("LEGITIMATE", "FRAUDULENT")
    assert 0.0 <= ml["calibrated_probability"] <= 1.0
    assert 0.0 <= ml["uncalibrated_probability"] <= 1.0
    assert ml["primary_threshold"] == 0.62
    assert ml["calibrated_threshold"] == 0.40
    assert ml["decision_threshold"] == 0.40
    assert "Platt Scaling" in ml["calibration_method"]
    assert isinstance(ml["top_features"], list)
    for feat in ml["top_features"]:
        assert "feature" in feat
        assert "weight" in feat
        assert "direction" in feat
        assert feat["direction"] in ("fraud_indicative", "legitimate_indicative")

    # 6. Entity & Recruiter Check Summaries
    assert "company_verification" in data
    assert "status" in data["company_verification"]
    assert "summary" in data["company_verification"]

    assert "recruiter_checks" in data
    assert "status" in data["recruiter_checks"]
    assert "detected_emails" in data["recruiter_checks"]
    assert isinstance(data["recruiter_checks"]["detected_emails"], list)
    assert "free_email_detected" in data["recruiter_checks"]

    assert "community_summary" in data
    assert "status" in data["community_summary"]
    assert "review_count" in data["community_summary"]

    # 7. Safe Actions, Limitations, Disclaimers
    assert "recommended_safe_actions" in data
    assert isinstance(data["recommended_safe_actions"], list)
    assert len(data["recommended_safe_actions"]) > 0

    assert "limitations" in data
    assert isinstance(data["limitations"], list)
    assert len(data["limitations"]) > 0

    assert "disclaimer" in data
    assert len(data["disclaimer"]) > 0
    assert "informational" in data["disclaimer"].lower()


def test_api_contract_insufficient_evidence_structure(test_client):
    """Verify that insufficient evidence returns the documented null score and specific status."""
    scant_text = "Hiring now for office work. Good pay. Apply today."
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": scant_text})
    assert resp.status_code == 200
    data = resp.json()

    # Score must be None
    assert data["risk_score"] is None
    assert data["risk_category"] == "INSUFFICIENT_EVIDENCE"
    assert data["ml_analysis"] is None
    assert data["warning"] is not None
    assert "insufficient" in data["warning"].lower()

    # Data quality evidence item
    dq_evidence = [e for e in data["evidence"] if e["evidence_type"] == "data_quality"]
    assert len(dq_evidence) == 1
    assert dq_evidence[0]["status"] == "INSUFFICIENT_EVIDENCE"

    # Status in placeholders
    assert data["company_verification"]["status"] in ("INSUFFICIENT_TEXT", "UNKNOWN")
    assert data["recruiter_checks"]["status"] == "INSUFFICIENT_TEXT"


@pytest.mark.parametrize("disallowed_method", ["get", "put", "delete", "patch"])
def test_disallowed_http_methods_rejected(test_client, disallowed_method):
    """Verify endpoint rejects disallowed HTTP methods with 405 Method Not Allowed."""
    method_fn = getattr(test_client, disallowed_method)
    resp = method_fn("/api/v1/analyze/job-text")
    assert resp.status_code == 405
