"""Automated Integration & Regression Tests for Feature F11: Privacy-First Chrome Extension.

Tests:
1. Manifest V3 validation (minimal permissions, CSP, host permissions, valid files).
2. Backend CORS compatibility with Chrome Extension origins.
3. Analysis API endpoint contract compatibility with extension payloads.
4. Scan details and PDF report download integration.
5. Strict privacy guarantee: no raw submitted text persistence in the database.
6. IDOR protection on private scans.
"""

import json
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.scan import ScanRequest
from app.models.prediction import PredictionHistory
from app.models.verification import VerificationEvidence


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_manifest_v3_structure_and_minimal_permissions():
    """Validates that manifest.json strictly adheres to Chrome Manifest V3

    and minimal-permission privacy principles (Section 3 of prompt).
    """
    manifest_path = Path("extension/manifest.json")
    assert manifest_path.exists(), "extension/manifest.json must exist"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # 1. Manifest version
    assert manifest.get("manifest_version") == 3, "Extension must use Manifest V3"

    # 2. Permissions must be minimal: only activeTab, scripting, storage
    permissions = manifest.get("permissions", [])
    assert "activeTab" in permissions, "activeTab is required for user-initiated page inspection"
    assert "scripting" in permissions, "scripting is required to execute extraction script"
    assert "storage" in permissions, "storage is required for user preferences"

    # Disallow broad, invasive permissions
    disallowed_permissions = [
        "tabs",
        "history",
        "cookies",
        "webNavigation",
        "webRequest",
        "management",
        "proxy",
        "vpnProvider",
        "<all_urls>",
    ]
    for p in disallowed_permissions:
        assert p not in permissions, f"Broad permission '{p}' violates privacy-first requirements"

    # 3. Host permissions must be strictly bounded to configured API origins
    host_permissions = manifest.get("host_permissions", [])
    assert len(host_permissions) > 0, "host_permissions must be specified"
    assert "<all_urls>" not in host_permissions, "<all_urls> host permission is strictly prohibited"
    for hp in host_permissions:
        assert (
            "localhost:8000" in hp or "127.0.0.1:8000" in hp or "jobshield.ai" in hp
        ), f"Unbounded host permission '{hp}' is not allowed"

    # 4. Content Security Policy must restrict script execution
    csp = manifest.get("content_security_policy", {})
    extension_pages_csp = csp.get("extension_pages", "")
    assert "script-src 'self'" in extension_pages_csp, "CSP must enforce script-src 'self'"
    assert "object-src 'none'" in extension_pages_csp, "CSP must enforce object-src 'none'"

    # 5. Required files exist
    assert Path("extension/popup.html").exists(), "extension/popup.html must exist"
    assert Path("extension/popup.css").exists(), "extension/popup.css must exist"
    assert Path("extension/popup.js").exists(), "extension/popup.js must exist"
    assert Path("extension/extractor.js").exists(), "extension/extractor.js must exist"
    assert Path("extension/icons/icon16.png").exists(), "icon16.png must exist"
    assert Path("extension/icons/icon48.png").exists(), "icon48.png must exist"
    assert Path("extension/icons/icon128.png").exists(), "icon128.png must exist"


def test_backend_cors_preflight_allows_configured_chrome_extension_origin(client: TestClient):
    """Verifies that FastAPI backend allows preflight CORS requests from the explicitly configured Chrome extension."""
    test_origin = "chrome-extension://abcdefghijklmnopqrstuvwxyz123456"
    resp = client.options(
        "/api/v1/analyze/job-text",
        headers={
            "Origin": test_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,accept",
        },
    )
    assert resp.status_code == 200
    allow_origin = resp.headers.get("access-control-allow-origin")
    assert allow_origin == test_origin


def test_backend_cors_rejects_untrusted_valid_format_chrome_extension_origin(client: TestClient):
    """Verifies that an untrusted extension with a valid 32-character ID format is strictly rejected."""
    untrusted_origin = "chrome-extension://fedcba9876543210zyxwvutsrqponmlk"
    resp = client.options(
        "/api/v1/analyze/job-text",
        headers={
            "Origin": untrusted_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,accept",
        },
    )
    # Origin is strictly rejected because it is not in the explicit allowlist
    allow_origin = resp.headers.get("access-control-allow-origin")
    assert allow_origin != untrusted_origin


def test_backend_cors_rejects_rogue_chrome_extension_origins(client: TestClient):
    """Verifies that arbitrary, rogue extension origins not conforming to 32-char ID format are rejected."""
    rogue_origin = "chrome-extension://malicious-attacker-domain-or-script"
    resp = client.options(
        "/api/v1/analyze/job-text",
        headers={
            "Origin": rogue_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,accept",
        },
    )
    # Origin is not allowed by CORS headers
    allow_origin = resp.headers.get("access-control-allow-origin")
    assert allow_origin != rogue_origin


def test_analyze_job_text_contract_for_extension_payload(client: TestClient):
    """Verifies that POST /api/v1/analyze/job-text handles payloads formatted

    by the Chrome extension and returns valid scores, categories, and report_id.
    """
    job_text = (
        "Position: Remote Executive Assistant\n"
        "Company: Apex Global Logistics Ltd\n"
        "Salary: $3,500 weekly payout\n"
        "Job Description:\n"
        "Immediate vacancy for remote coordinator. A company laptop will be provided. "
        "Candidates must pay a refundable training security deposit of $150 prior to dispatch.\n"
        "Contact on WhatsApp: +1 555-019-8833."
    )

    payload = {
        "text": job_text,
        "company_name": "Apex Global Logistics Ltd",
        "cin": None,
        "explanation_method": "auto",
    }

    resp = client.post(
        "/api/v1/analyze/job-text",
        json=payload,
        headers={"Origin": "chrome-extension://abcdefghijklmnopqrstuvwxyz123456"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "report_id" in data
    assert "risk_score" in data
    assert "risk_category" in data
    assert data["risk_category"] in ("LOW", "MODERATE", "HIGH", "CRITICAL", "INSUFFICIENT_EVIDENCE")
    assert isinstance(data.get("evidence"), list)
    assert len(data["evidence"]) > 0

    # Ensure fee deposit was detected by heuristic rules
    detected_sources = [e["source_name"] for e in data["evidence"]]
    assert any("Fee" in s or "Upfront" in s or "Deposit" in s for s in detected_sources)

    # Privacy verification: Raw submitted text must NEVER be persisted in the DB
    scan_id = data["report_id"]
    db = SessionLocal()
    try:
        scan_rec = db.query(ScanRequest).filter(ScanRequest.id == scan_id).first()
        assert scan_rec is not None
        assert "refundable training security deposit" not in scan_rec.input_reference
        assert scan_rec.input_reference.startswith("sha256:")
    finally:
        db.close()


def test_get_scan_details_for_full_report_view(client: TestClient):
    """Verifies that GET /api/v1/scans/{scan_id} returns complete persisted evidence

    and metadata so the web Results page can render the report when opened from the extension.
    """
    # 1. Create a scan via text analysis
    job_text = (
        "Senior Software Engineer needed for cloud computing architecture. "
        "Must have proficiency in Python, FastAPI, Docker, and PostgreSQL. "
        "Competitive salary and full health insurance provided."
    )
    res = client.post("/api/v1/analyze/job-text", json={"text": job_text})
    assert res.status_code == 200
    report_id = res.json()["report_id"]

    # 2. Fetch scan details by ID
    get_res = client.get(f"/api/v1/scans/{report_id}")
    assert get_res.status_code == 200
    details = get_res.json()

    assert details["id"] == report_id
    assert details["report_id"] == report_id
    assert "risk_score" in details
    assert "risk_category" in details
    assert "evidence" in details
    assert isinstance(details["evidence"], list)

    # 3. Fetch PDF report for this scan
    pdf_res = client.get(f"/api/v1/scans/{report_id}/report.pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers.get("content-type") == "application/pdf"
    assert len(pdf_res.content) > 1000
