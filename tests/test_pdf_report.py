"""Automated Test Suite for Feature F10: Evidence-Based PDF Verification Report.

Conforms to Feature F10 & Sections 2, 4, 5, 11 of PROJECT_SPECIFICATION.md:
- Validates GET /api/v1/scans/{scan_id}/report.pdf endpoint.
- Validates 404 response for nonexistent scans.
- Validates strictly evidence-based PDF generation across all scan types:
  (job_text, job_url, recruiter_email, offer_letter).
- Inspects text content of generated PDFs using PyMuPDF (fitz) text extraction.
- Verifies honest representation of missing optional fields (no fabricated data).
- Verifies that report generation does NOT rerun ML models, rules, or external checks.
- Verifies privacy guarantees (no raw text body, email masked, no sensitive secrets).
- Verifies multi-page rendering, two-pass page numbering, and special character safety.
"""

from datetime import datetime, timezone
import io
from typing import Any, Dict
from unittest.mock import patch
import uuid

import pymupdf
import pytest
from starlette.testclient import TestClient

from app.models.company import Company
from app.models.offer import OfferLetterScan
from app.models.prediction import PredictionHistory
from app.models.recruiter import RecruiterEmailScan
from app.models.scan import ScanRequest
from app.models.verification import VerificationEvidence
from app.reports.pdf_generator import generate_verification_report_pdf


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extracts all text content across all pages of a PDF byte stream with whitespace normalization."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pages_text = [page.get_text() for page in doc]
    # Join and collapse whitespace so table-cell line breaks don't split tokens
    return " ".join("\n".join(pages_text).split())


def extract_pdf_page_count(pdf_bytes: bytes) -> int:
    """Returns the total number of pages in a PDF byte stream."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    return len(doc)


def test_pdf_report_nonexistent_scan_returns_404(test_client: TestClient):
    """Verify that requesting a report for a nonexistent scan returns standard 404."""
    nonexistent_id = str(uuid.uuid4())
    res = test_client.get(f"/api/v1/scans/{nonexistent_id}/report.pdf")
    assert res.status_code == 404
    data = res.json()
    assert "not found" in data["detail"].lower()
    assert nonexistent_id in data["detail"]


def test_pdf_report_job_text_scan_success(test_client: TestClient, db_session):
    """Verify successful PDF report generation for a job text analysis scan."""
    # 1. Create and persist a job text scan
    job_payload = {
        "text": (
            "Senior Frontend Engineer wanted at high-growth software company. 5+ years experience in React, "
            "TypeScript, Next.js, and automated testing. Competitive salary, equity, and healthcare benefits."
        ),
        "company_name": "Acme Software Corp",
    }
    post_res = test_client.post("/api/v1/analyze/job-text", json=job_payload)
    assert post_res.status_code == 200
    analysis = post_res.json()
    scan_id = analysis["report_id"]

    # 2. Request PDF Report
    pdf_res = test_client.get(f"/api/v1/scans/{scan_id}/report.pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert "attachment;" in pdf_res.headers["content-disposition"]
    assert f"JobShield_Report_{scan_id[:8]}.pdf" in pdf_res.headers["content-disposition"]

    # 3. Extract and verify text
    pdf_text = extract_pdf_text(pdf_res.content)
    assert "JobShield AI - Evidence-Based Verification Report" in pdf_text
    assert scan_id[:8] in pdf_text
    assert "Pasted Job Description Text" in pdf_text
    assert "1. Executive Summary & Composite Risk Score" in pdf_text
    assert "2. Machine Learning Model Analysis" in pdf_text
    assert "3. Explainable AI (XAI) - Linguistic Feature Contributions" in pdf_text
    assert "Recommended Safe Actions" in pdf_text
    assert "Data Sources & Provenance Metadata" in pdf_text
    assert "Legal Disclaimer & Regulatory Notice" in pdf_text

    # Privacy guarantee: raw job text body should not be dumped in the report
    assert "5+ years experience in React, TypeScript, Next.js" not in pdf_text
    # But cryptographic reference is present
    assert "sha256:" in pdf_text


def test_pdf_report_high_risk_rule_floor_and_warning(test_client: TestClient, db_session):
    """Verify that critical risk findings, warnings, and safety override floors appear in the PDF."""
    fee_scam_text = (
        "Urgent hiring for Home Data Entry typist. You must pay a $150 registration fee and "
        "equipment deposit prior to interview. Immediate placement guaranteed."
    )
    post_res = test_client.post("/api/v1/analyze/job-text", json={"text": fee_scam_text})
    assert post_res.status_code == 200
    analysis = post_res.json()
    scan_id = analysis["report_id"]

    pdf_res = test_client.get(f"/api/v1/scans/{scan_id}/report.pdf")
    assert pdf_res.status_code == 200

    pdf_text = extract_pdf_text(pdf_res.content)
    # Check score and category
    assert analysis["risk_category"] in pdf_text
    assert f"{analysis['risk_score']:.1f}" in pdf_text

    # Check alert / warning
    assert "POTENTIAL FRAUD ADVISORY" in pdf_text
    if analysis.get("override_floor_applied"):
        assert "RULE SAFETY OVERRIDE FLOOR ACTIVE" in pdf_text

    # Check rule findings
    assert "Detected Rule-Based Findings" in pdf_text
    assert "Rule: Upfront Fees Request" in pdf_text or "Upfront" in pdf_text


def test_pdf_report_job_url_scan(test_client: TestClient, db_session):
    """Verify PDF report formatting for a Job URL scan with domain security checks."""
    scan_id = str(uuid.uuid4())
    now_ts = datetime.now(timezone.utc)

    # Directly persist a job_url scan in the database
    scan_req = ScanRequest(
        id=scan_id,
        input_type="job_url",
        input_reference="https://careers.example-corp.com/jobs/12345",
        status="completed",
        created_at=now_ts,
        completed_at=now_ts,
    )
    db_session.add(scan_req)

    # Domain evidence
    ev_domain = VerificationEvidence(
        scan_id=scan_id,
        evidence_type="domain_intelligence",
        source_name="Cloudflare 1.1.1.1 DNS over HTTPS",
        source_url="https://careers.example-corp.com/jobs/12345",
        observed_at=now_ts,
        status="PASS",
        confidence=1.0,
        summary="Domain 'example-corp.com' has valid DNS, MX, SPF, and DMARC enforcement.",
        limitations="Technical check only.",
        raw_metadata={"dns": "PASS", "mx": "PASS", "spf": "PASS", "dmarc": "PASS"},
    )
    db_session.add(ev_domain)

    # Prediction history
    pred = PredictionHistory(
        scan_id=scan_id,
        model_version="baseline_v1.1.0",
        predicted_class="LEGITIMATE",
        model_probability=0.082,
        risk_score=15.0,
        risk_category="LOW",
        threshold_version="provisional_v1.0.0",
        explanation={
            "page_type": "job_posting",
            "fetch_status_code": 200,
            "extracted_title": "Senior Distributed Systems Engineer",
            "extracted_company": "Example Corporation",
            "domain_check": {
                "domain": "example-corp.com",
                "dns_status": "PASS",
                "mx_status": "PASS",
                "spf_status": "PASS",
                "dmarc_status": "PASS",
                "lookalike_warning": None,
            },
            "duplicate_analysis": {
                "status": "UNIQUE_LISTING",
                "highest_similarity_score": 0.12,
                "total_matches_found": 0,
                "impersonation_warning": None,
            },
            "company_verification": {
                "claimed_company": "Example Corporation",
                "cin": "U72200MH2018PTC123456",
                "mca_status": "MATCHED",
                "is_startup": False,
            },
            "recommended_safe_actions": [
                "Verify vacancy on official career portal.",
            ],
            "limitations": [
                "Static HTML analysis only.",
            ],
        },
    )
    db_session.add(pred)
    db_session.commit()

    pdf_res = test_client.get(f"/api/v1/scans/{scan_id}/report.pdf")
    assert pdf_res.status_code == 200
    pdf_text = extract_pdf_text(pdf_res.content)

    assert "Public Job URL Ingestion" in pdf_text
    assert "careers.example-corp" in pdf_text
    assert "LOW RISK" in pdf_text
    assert "15.0" in pdf_text
    assert "Domain Security & Technical Email Authentication" in pdf_text
    assert "example-corp.com" in pdf_text
    assert "Job Duplication & Content Impersonation Signals" in pdf_text
    assert "UNIQUE_LISTING" in pdf_text


def test_pdf_report_offer_letter_scan(test_client: TestClient, db_session):
    """Verify PDF report formatting for an Offer Letter document scan."""
    scan_id = str(uuid.uuid4())
    now_ts = datetime.now(timezone.utc)

    scan_req = ScanRequest(
        id=scan_id,
        input_type="offer_letter",
        input_reference="offer:a1b2c3d4e5f67890",
        status="completed",
        created_at=now_ts,
        completed_at=now_ts,
    )
    db_session.add(scan_req)

    offer_scan = OfferLetterScan(
        id=str(uuid.uuid4()),
        scan_id=scan_id,
        file_hash="a1b2c3d4e5f67890" * 4,
        file_name="executive_offer_letter.pdf",
        file_size_bytes=145200,
        page_count=2,
        is_scanned=True,
        ocr_applied=True,
        ocr_engine="Tesseract OCR Engine (v5.3.0)",
        claimed_company_name="Apex Global Technologies",
        company_id=None,
        extracted_summary={
            "job_title": "Regional Operations Director",
            "salary": "$180,000 per annum + performance bonus",
            "fee_demands_count": 1,
            "domains": ["apex-global-tech.com"],
            "suspicious_indicators": ["Advance security deposit for executive laptop requested."],
        },
        risk_category="CRITICAL",
        risk_score=88.5,
        has_fee_demand=True,
        has_sensitive_request=False,
    )
    db_session.add(offer_scan)

    pred = PredictionHistory(
        scan_id=scan_id,
        model_version="offer_v1.0.0",
        predicted_class="FRAUDULENT",
        model_probability=0.885,
        risk_score=88.5,
        risk_category="CRITICAL",
        threshold_version="offer_v1.0.0",
        explanation={
            "warning": "CRITICAL RISK: Advance fee demand detected in offer document.",
            "recommended_safe_actions": ["Never transfer security deposits for company equipment."],
            "limitations": ["OCR text extraction may be subject to character recognition errors."],
        },
    )
    db_session.add(pred)
    db_session.commit()

    pdf_res = test_client.get(f"/api/v1/scans/{scan_id}/report.pdf")
    assert pdf_res.status_code == 200
    pdf_text = extract_pdf_text(pdf_res.content)

    assert "Offer Letter Document Analysis" in pdf_text
    assert "88.5" in pdf_text
    assert "CRITICAL RISK" in pdf_text
    assert "Offer Letter Document & Clause Analysis" in pdf_text
    assert "executive_offer_letter.pdf" in pdf_text
    assert "Tesseract OCR Engine" in pdf_text
    assert "Regional Operations Director" in pdf_text
    assert "$180,000 per annum" in pdf_text
    assert "YES (Advance Fee Detected)" in pdf_text


def test_pdf_report_recruiter_email_scan_masks_email(test_client: TestClient, db_session):
    """Verify that recruiter email scans preserve privacy and mask the email address."""
    scan_id = str(uuid.uuid4())
    now_ts = datetime.now(timezone.utc)

    scan_req = ScanRequest(
        id=scan_id,
        input_type="recruiter_email",
        input_reference="email_hash:fedcba9876543210",
        status="completed",
        created_at=now_ts,
        completed_at=now_ts,
    )
    db_session.add(scan_req)

    recruiter_scan = RecruiterEmailScan(
        id=str(uuid.uuid4()),
        scan_id=scan_id,
        claimed_company_id=None,
        email_masked="j***e@freemail-careers.com",
        email_hash="fedcba9876543210" * 4,
        domain="freemail-careers.com",
        status="FREE_WEBMAIL_DOMAIN",
    )
    db_session.add(recruiter_scan)

    pred = PredictionHistory(
        scan_id=scan_id,
        model_version="recruiter_v1.0.0",
        predicted_class="SUSPICIOUS",
        model_probability=0.65,
        risk_score=65.0,
        risk_category="HIGH",
        threshold_version="provisional_v1.0.0",
        explanation={
            "domain_check": {
                "domain": "freemail-careers.com",
                "dns_status": "PASS",
                "mx_status": "PASS",
                "spf_status": "NOT_APPLICABLE",
                "dmarc_status": "NOT_FOUND",
            },
            "recruiter_checks": {
                "status": "FREE_WEBMAIL",
                "detected_emails": ["j***e@freemail-careers.com"],
                "free_email_detected": True,
            },
        },
    )
    db_session.add(pred)
    db_session.commit()

    pdf_res = test_client.get(f"/api/v1/scans/{scan_id}/report.pdf")
    assert pdf_res.status_code == 200
    pdf_text = extract_pdf_text(pdf_res.content)

    assert "Recruiter Email Verification" in pdf_text
    assert "HIGH RISK" in pdf_text
    # Masked email is present
    assert "freemail-careers.com" in pdf_text
    # Raw email is NOT present anywhere
    assert "john.doe@freemail-careers.com" not in pdf_text


def test_pdf_generator_does_not_rerun_inference_or_checks(test_client: TestClient, db_session):
    """Verify that report generation strictly reads database records and never invokes ML or network."""
    # 1. Create a scan
    job_payload = {
        "text": "Software engineer job description with python, fastAPI, and react skills required. Standard corporate benefits.",
    }
    post_res = test_client.post("/api/v1/analyze/job-text", json=job_payload)
    scan_id = post_res.json()["report_id"]

    # 2. Mock out the ML service inference method, risk engine, and safe fetch
    with patch("app.services.ml_inference.MLInferenceService.analyze_text") as mock_ml, \
         patch("app.services.risk_engine.RiskEngine.analyze_job_text") as mock_risk, \
         patch("app.services.safe_fetch.safe_fetch_url") as mock_fetch:

        pdf_res = test_client.get(f"/api/v1/scans/{scan_id}/report.pdf")
        assert pdf_res.status_code == 200

        # Verify that NONE of the heavy analytical or network functions were called
        mock_ml.assert_not_called()
        mock_risk.assert_not_called()
        mock_fetch.assert_not_called()


def test_pdf_report_handles_missing_fields_gracefully():
    """Verify that scans with missing optional fields render honestly without errors or hallucinations."""
    scan_id = str(uuid.uuid4())
    now_ts = datetime.now(timezone.utc)

    # Bare-bones scan request with minimal data
    scan_req = ScanRequest(
        id=scan_id,
        input_type="job_text",
        input_reference=None,
        status="completed",
        created_at=now_ts,
        completed_at=None,
    )

    pdf_bytes = generate_verification_report_pdf(
        scan=scan_req,
        evidence_records=[],
        prediction_records=[],
        offer_scan=None,
        recruiter_scan=None,
        company=None,
    )
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000

    pdf_text = extract_pdf_text(pdf_bytes)
    assert scan_id[:8] in pdf_text
    assert "Pasted Job Description Text" in pdf_text
    assert "Not Recorded" in pdf_text or "Not Specified" in pdf_text
    # Does not fabricate an unverified company or domain
    assert "Not Specified" in pdf_text or "UNVERIFIED" in pdf_text


def test_pdf_report_special_characters_and_multipage():
    """Verify that special characters (&, <, >, quotes, symbols) and multi-page layouts render safely."""
    scan_id = str(uuid.uuid4())
    now_ts = datetime.now(timezone.utc)

    scan_req = ScanRequest(
        id=scan_id,
        input_type="job_text",
        input_reference="sha256:abc123xyz <test>",
        status="completed",
        created_at=now_ts,
        completed_at=now_ts,
    )

    # Add multiple evidence records with special characters to ensure multi-page flow
    ev_records = []
    for i in range(12):
        ev = VerificationEvidence(
            scan_id=scan_id,
            evidence_type="rule_signal",
            source_name=f"Detector & Rule #{i+1} <XML>",
            source_url="https://example.com/check?param=1&foo=bar",
            observed_at=now_ts,
            status="FLAGGED",
            confidence=0.85,
            summary=f"Special symbols: 100% $250 > & < 'quoted phrase' in rule finding #{i+1}.",
            limitations="Rule limitation & constraints <disclosed>.",
            raw_metadata={"index": i},
        )
        ev_records.append(ev)

    pred = PredictionHistory(
        scan_id=scan_id,
        model_version="v1.1.0 & scikit-learn",
        predicted_class="FRAUDULENT",
        model_probability=0.91,
        risk_score=91.0,
        risk_category="CRITICAL",
        threshold_version="provisional_v1.0.0",
        explanation={
            "warning": "Alert: Symbols <script> & ampersand & quotes 'tested' safely.",
            "top_positive_features": [
                {"feature_name": "urgent & cash", "contribution": 1.45},
                {"feature_name": "fee <deposit>", "contribution": 1.20},
            ],
            "top_negative_features": [
                {"feature_name": "engineering & science", "contribution": -1.10},
            ],
            "recommended_safe_actions": [f"Safe step #{j+1} & verify carefully." for j in range(6)],
            "limitations": [f"Limitation #{k+1} regarding models & rules." for k in range(5)],
        },
    )

    pdf_bytes = generate_verification_report_pdf(
        scan=scan_req,
        evidence_records=ev_records,
        prediction_records=[pred],
    )

    assert isinstance(pdf_bytes, bytes)
    pages = extract_pdf_page_count(pdf_bytes)
    assert pages >= 2

    pdf_text = extract_pdf_text(pdf_bytes)
    # Check that XML-escaped content was decoded cleanly into text by PyMuPDF
    assert "Detector & Rule #1 <XML>" in pdf_text or "Detector & Rule" in pdf_text
    assert "Special symbols: 100% $250 > & < 'quoted phrase'" in pdf_text or "$250" in pdf_text
    # Check page numbers
    assert f"Page 1 of {pages}" in pdf_text
    assert f"Page 2 of {pages}" in pdf_text


def test_pdf_report_end_to_end_from_offer_letter_upload(test_client: TestClient, db_session):
    """Verify that uploading an offer letter via POST /api/v1/analyze/offer-letter
    reliably persists ScanRequest, OfferLetterScan, Evidence, and PredictionHistory,
    and allows immediate downloading of the PDF report via GET /api/v1/scans/{scan_id}/report.pdf."""
    from tests.test_offer_letter_analyzer import make_text_pdf, SCAM_FEE_OFFER_TEXT

    pdf_bytes = make_text_pdf(SCAM_FEE_OFFER_TEXT)
    files = {"file": ("acme_offer_letter.pdf", pdf_bytes, "application/pdf")}
    post_res = test_client.post(
        "/api/v1/analyze/offer-letter",
        files=files,
        data={"company_name": "Acme Dynamic Tech Solutions Pvt Ltd"},
    )
    assert post_res.status_code == 200
    data = post_res.json()
    scan_id = data["report_id"]
    assert scan_id is not None

    # 1. Verify ScanRequest persisted in database
    scan_req = db_session.query(ScanRequest).filter(ScanRequest.id == scan_id).first()
    assert scan_req is not None
    assert scan_req.input_type == "offer_letter"
    assert scan_req.status == "completed"

    # 2. Verify OfferLetterScan persisted and linked
    offer_scan = db_session.query(OfferLetterScan).filter(OfferLetterScan.scan_id == scan_id).first()
    assert offer_scan is not None
    assert offer_scan.file_name == "acme_offer_letter.pdf"
    assert offer_scan.has_fee_demand is True
    assert offer_scan.risk_category == "HIGH"

    # 3. Verify PredictionHistory persisted and linked
    pred = db_session.query(PredictionHistory).filter(PredictionHistory.scan_id == scan_id).first()
    assert pred is not None
    assert pred.risk_category == "HIGH"

    # 4. Verify VerificationEvidence persisted and linked
    evidence = db_session.query(VerificationEvidence).filter(VerificationEvidence.scan_id == scan_id).all()
    assert len(evidence) > 0

    # 5. Download the PDF verification report
    pdf_res = test_client.get(f"/api/v1/scans/{scan_id}/report.pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert "attachment;" in pdf_res.headers["content-disposition"]
    assert f"JobShield_Report_{scan_id[:8]}.pdf" in pdf_res.headers["content-disposition"]

    # 6. Extract text and verify contents
    pdf_text = extract_pdf_text(pdf_res.content)
    assert "JobShield AI - Evidence-Based Verification Report" in pdf_text
    assert scan_id[:8] in pdf_text
    assert "Offer Letter Document & Clause Analysis" in pdf_text
    assert "acme_offer_letter.pdf" in pdf_text
    assert "Advance Fee Detected" in pdf_text or "YES" in pdf_text
    assert "Corporate Registry Verification" in pdf_text

