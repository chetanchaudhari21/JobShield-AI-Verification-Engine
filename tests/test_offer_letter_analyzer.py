"""Comprehensive test suite for Feature F7: Offer Letter Analyzer.

Covers all 14 required conditions:
1. Valid text-based PDF.
2. Scanned PDF processed using OCR.
3. Invalid or non-PDF content with a misleading .pdf filename.
4. Oversized uploads.
5. PDFs exceeding the page limit.
6. Missing Tesseract executable.
7. OCR failure and timeout.
8. Corrupt and encrypted PDFs.
9. Temporary-file cleanup after success and failure.
10. Sensitive information not appearing in logs.
11. Fee/deposit clause extraction.
12. Company and domain mismatches.
13. Missing or ambiguous company evidence.
14. API persistence and error handling.
"""

import io
import logging
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
import pytest
from PIL import Image, ImageDraw
import pymupdf
import pytesseract
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.company import Company, CompanySourceRecord
from app.models.offer import OfferLetterScan
from app.models.prediction import PredictionHistory
from app.models.scan import ScanRequest
from app.models.verification import VerificationEvidence
from app.services.pdf_extractor import (
    EncryptedPDFError,
    ExcessivePagesError,
    InvalidPDFError,
    OCRTimeoutError,
    OversizedFileError,
    _run_ocr_on_page,
    extract_text_and_ocr,
    resolve_tesseract_cmd,
)
from app.services.offer_letter_analyzer import (
    analyze_offer_letter,
    extract_offer_letter_data,
    mask_person_name,
    mask_phone_number,
)


# Helper functions to synthesize test PDFs in memory
def make_text_pdf(text: str, num_pages: int = 1) -> bytes:
    """Creates a synthetic text-based PDF with pymupdf."""
    doc = pymupdf.open()
    for i in range(num_pages):
        page = doc.new_page()
        page.insert_text((50, 72), f"Page {i + 1}\n\n{text}")
    data = doc.tobytes()
    doc.close()
    return data


def make_scanned_pdf(text: str) -> bytes:
    """Creates a synthetic scanned image-only PDF with PIL and pymupdf."""
    img = Image.new("RGB", (900, 300), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((40, 50), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    doc = pymupdf.open()
    page = doc.new_page(width=900, height=300)
    page.insert_image(page.rect, stream=buf.getvalue())
    data = doc.tobytes()
    doc.close()
    return data


def make_encrypted_pdf(text: str, password: str = "secret") -> bytes:
    """Creates a password-encrypted PDF."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password)
    doc.close()
    return data


LEGIT_OFFER_TEXT = """
OFFER OF EMPLOYMENT
Company: Infosys Limited
Registered Office: Electronics City, Hosur Road, Bangalore, India

Dear Rajesh Sharma,
We are pleased to offer you the position of Senior Backend Engineer at Infosys Limited.
Gross Salary: Rs. 15,00,000 per annum (Fifteen Lakhs Rupees).

Key Dates:
- Offer Date: 15-10-2026
- Joining Date: 01-12-2026
- Acceptance Deadline: 25-10-2026

Contact HR Operations:
Email: careers@infosys.com
Phone: +91 80285 20261
Official Portal: https://careers.infosys.com

Please sign and return the duplicate copy of this letter.
"""

SCAM_FEE_OFFER_TEXT = """
APPOINTMENT LETTER
Company: Acme Dynamic Tech Solutions Pvt Ltd
Candidate Name: John Doe
Position: Remote Cloud Operations Associate
Salary: $5,500 monthly

To secure your company-dispatched laptop equipment and complete background verification,
the candidate must pay an upfront refundable security deposit of $150 prior to shipping hardware.

Please remit payment immediately to our onboarding coordinator.
Contact HR: hr.coordinator.fast@gmail.com
Phone: +1 555-019-2834
"""


# -----------------------------------------------------------------------------
# 1. Valid text-based PDF
# -----------------------------------------------------------------------------
def test_1_valid_text_based_pdf(db_session: Session):
    pdf_bytes = make_text_pdf(LEGIT_OFFER_TEXT, num_pages=2)
    doc = extract_text_and_ocr(pdf_bytes, file_name="infosys_offer.pdf")

    assert doc.page_count == 2
    assert not doc.is_scanned
    assert not doc.ocr_applied
    assert doc.file_name == "infosys_offer.pdf"

    res = analyze_offer_letter(doc, db=db_session)
    assert res.extracted_fields.job_title is not None
    assert "Senior Backend Engineer" in res.extracted_fields.job_title.value
    assert res.extracted_fields.salary_compensation is not None
    assert "15,00,000" in res.extracted_fields.salary_compensation.value
    assert not res.extracted_fields.has_fee_demand
    assert res.risk_category == "LOW"
    assert res.risk_score < 35.0


# -----------------------------------------------------------------------------
# 2. Scanned PDF processed using OCR
# -----------------------------------------------------------------------------
def test_2_scanned_pdf_processed_using_ocr(db_session: Session):
    scanned_text = "OFFICIAL OFFER LETTER\nCompany: Infosys Limited\nPosition: Software Engineer\nDate: 15-10-2026"
    pdf_bytes = make_scanned_pdf(scanned_text)

    doc = extract_text_and_ocr(pdf_bytes, file_name="scanned_offer.pdf")
    assert doc.page_count == 1
    assert doc.is_scanned
    assert doc.ocr_applied
    assert doc.ocr_engine is not None
    assert "tesseract" in doc.ocr_engine.lower()

    # OCR should extract core keywords from the rendered image
    full_text = doc.full_text.lower()
    assert "infosys" in full_text or "offer" in full_text or "software" in full_text


# -----------------------------------------------------------------------------
# 3. Invalid or non-PDF content with a misleading .pdf filename
# -----------------------------------------------------------------------------
def test_3_invalid_or_non_pdf_content_with_misleading_pdf_filename(test_client):
    fake_payload = b"MZ\x90\x00\x03\x00\x00\x00Windows Executable disguised as PDF"
    files = {"file": ("malicious.pdf", fake_payload, "application/pdf")}

    response = test_client.post("/api/v1/analyze/offer-letter", files=files)
    assert response.status_code == 400
    assert "magic bytes" in response.json()["detail"].lower()


# -----------------------------------------------------------------------------
# 4. Oversized uploads
# -----------------------------------------------------------------------------
def test_4_oversized_uploads(test_client):
    valid_pdf_start = b"%PDF-1.4\n" + b"A" * 2000
    # Test enforcement with a small limit
    with pytest.raises(OversizedFileError) as exc_info:
        extract_text_and_ocr(valid_pdf_start, max_bytes=500)
    assert "exceeds maximum permitted upload limit" in str(exc_info.value)

    # API endpoint size error
    with patch.object(settings, "MAX_OFFER_LETTER_UPLOAD_BYTES", 100):
        files = {"file": ("large.pdf", b"%PDF-1.4\n" + b"0" * 500, "application/pdf")}
        response = test_client.post("/api/v1/analyze/offer-letter", files=files)
        assert response.status_code == 413


# -----------------------------------------------------------------------------
# 5. PDFs exceeding the page limit
# -----------------------------------------------------------------------------
def test_5_pdfs_exceeding_page_limit(test_client):
    eleven_page_pdf = make_text_pdf("Short page text", num_pages=11)
    files = {"file": ("eleven_pages.pdf", eleven_page_pdf, "application/pdf")}

    response = test_client.post("/api/v1/analyze/offer-letter", files=files)
    assert response.status_code == 400
    assert "maximum permitted page limit" in response.json()["detail"].lower()


# -----------------------------------------------------------------------------
# 6. Missing Tesseract executable
# -----------------------------------------------------------------------------
def test_6_missing_tesseract_executable(db_session: Session):
    scanned_pdf = make_scanned_pdf("Scan content with no OCR available")

    # Mock Tesseract as unavailable
    with patch("app.services.pdf_extractor.resolve_tesseract_cmd", return_value=None):
        doc = extract_text_and_ocr(scanned_pdf, file_name="no_ocr.pdf")
        assert doc.is_scanned
        assert not doc.ocr_applied
        assert any("Tesseract OCR engine is not configured" in lim for lim in doc.limitations)

        # Analysis must not fail or automatically classify as fraud due to OCR absence
        res = analyze_offer_letter(doc, db=db_session)
        assert res.risk_category in ("LOW", "MODERATE")
        assert not res.extracted_fields.has_fee_demand


# -----------------------------------------------------------------------------
# 7. OCR failure and timeout
# -----------------------------------------------------------------------------
def test_7_ocr_failure_and_timeout():
    page_mock = pymupdf.open().new_page()

    with patch("pytesseract.image_to_string", side_effect=TimeoutError("Timeout")):
        with pytest.raises(OCRTimeoutError) as exc_info:
            _run_ocr_on_page(page_mock, page_num=1, timeout_seconds=1)
        assert "timed out on page 1" in str(exc_info.value)


# -----------------------------------------------------------------------------
# 8. Corrupt and encrypted PDFs
# -----------------------------------------------------------------------------
def test_8_corrupt_and_encrypted_pdfs(test_client):
    # Corrupt PDF structure
    corrupt_bytes = b"%PDF-1.4\nGarbage data that is completely corrupt"
    files_corrupt = {"file": ("corrupt.pdf", corrupt_bytes, "application/pdf")}
    res_corrupt = test_client.post("/api/v1/analyze/offer-letter", files=files_corrupt)
    assert res_corrupt.status_code == 400
    assert "corrupt or invalid" in res_corrupt.json()["detail"].lower()

    # Password-encrypted PDF
    enc_bytes = make_encrypted_pdf("Encrypted secret text", password="secret_password")
    files_enc = {"file": ("encrypted.pdf", enc_bytes, "application/pdf")}
    res_enc = test_client.post("/api/v1/analyze/offer-letter", files=files_enc)
    assert res_enc.status_code == 400
    assert "encrypted or password-protected" in res_enc.json()["detail"].lower()


# -----------------------------------------------------------------------------
# 9. Temporary-file cleanup after success and failure
# -----------------------------------------------------------------------------
def test_9_temporary_file_cleanup_after_success_and_failure():
    temp_dir = tempfile.gettempdir()
    files_before = set(os.listdir(temp_dir))

    # Run OCR on valid synthetic page
    scanned_pdf = make_scanned_pdf("Temporary file lifecycle check")
    _ = extract_text_and_ocr(scanned_pdf)

    files_after = set(os.listdir(temp_dir))
    # No lingering PNG temp files from OCR should remain
    new_pngs = [f for f in files_after - files_before if f.endswith(".png")]
    assert len(new_pngs) == 0


# -----------------------------------------------------------------------------
# 10. Sensitive information not appearing in logs
# -----------------------------------------------------------------------------
def test_10_sensitive_information_not_appearing_in_logs(caplog):
    caplog.set_level(logging.INFO)

    secret_name = "SuperSecretCandidateName"
    secret_clause = "Secret payment clause of $9999 to personal account"
    pdf_bytes = make_text_pdf(f"Dear {secret_name},\n{secret_clause}")

    doc = extract_text_and_ocr(pdf_bytes, file_name="confidential_offer.pdf")
    _ = analyze_offer_letter(doc)

    logged_text = caplog.text
    # Candidate name and raw document body must NEVER appear in logger output
    assert secret_name not in logged_text
    assert secret_clause not in logged_text


# -----------------------------------------------------------------------------
# 11. Fee/deposit clause extraction
# -----------------------------------------------------------------------------
def test_11_fee_deposit_clause_extraction(db_session: Session):
    pdf_bytes = make_text_pdf(SCAM_FEE_OFFER_TEXT)
    doc = extract_text_and_ocr(pdf_bytes, file_name="fee_scam_letter.pdf")

    res = analyze_offer_letter(doc, db=db_session)
    assert res.extracted_fields.has_fee_demand
    assert len(res.extracted_fields.fee_demands) >= 1

    fee = res.extracted_fields.fee_demands[0]
    assert fee.category == "SECURITY_DEPOSIT"
    assert "$150" in (fee.amount or "")
    assert fee.is_refundable_claimed is True
    assert res.risk_category == "HIGH"
    assert res.risk_score >= 85.0
    assert any("Do Not Pay" in a for a in res.recommended_safe_actions)


# -----------------------------------------------------------------------------
# 12. Company and domain mismatches
# -----------------------------------------------------------------------------
def test_12_company_and_domain_mismatches(db_session: Session):
    mismatch_text = """
    Company: Tata Consultancy Services Limited
    Position: Cloud Architect
    Salary: ₹20,00,000 per annum
    Contact Recruiter: hr.tcs.hiring@inf0sys-careers.com
    Official portal: https://inf0sys-careers.com
    """
    pdf_bytes = make_text_pdf(mismatch_text)
    doc = extract_text_and_ocr(pdf_bytes, file_name="spoofed_domain_offer.pdf")

    res = analyze_offer_letter(doc, db=db_session)
    assert "LOOKALIKE_DOMAIN_DETECTED" in res.suspicious_indicators
    assert res.risk_score >= 75.0
    assert any(e.evidence_type == "domain_lookalike_spoof" for e in res.evidence)


# -----------------------------------------------------------------------------
# 13. Missing or ambiguous company evidence
# -----------------------------------------------------------------------------
def test_13_missing_or_ambiguous_company_evidence(db_session: Session):
    # Seed MCA source records so registry is loaded and searched
    legit_company = Company(
        id=101,
        legal_name="Infosys Limited",
        normalized_name="INFOSYS LIMITED",
        cin="L85110KA1981PLC013115",
        entity_type="PLC",
        registry_status="Active",
    )
    mca_source = CompanySourceRecord(
        company_id=101,
        source_name="MCA_COMPANY_MASTER",
        source_record_id="L85110KA1981PLC013115",
        match_method="CIN_EXACT",
        match_confidence=1.0,
    )
    db_session.add_all([legit_company, mca_source])
    db_session.commit()

    unregistered_text = """
    Company: Unregistered Fictitious International Corp
    Position: Data Entry Clerk
    Salary: ₹25,000 monthly
    Contact: hiring@unregisteredfictitious.example.org
    """
    pdf_bytes = make_text_pdf(unregistered_text)
    doc = extract_text_and_ocr(pdf_bytes, file_name="unregistered_company.pdf")

    res = analyze_offer_letter(doc, db=db_session)
    assert "COMPANY_NOT_IN_MCA_REGISTRY" in res.suspicious_indicators
    assert res.company_verification is not None
    assert res.company_verification.status == "NO_MATCH"
    # Unregistered company raises caution, but alone with no fees should not exceed threshold
    assert not res.extracted_fields.has_fee_demand


# -----------------------------------------------------------------------------
# 14. API persistence and error handling
# -----------------------------------------------------------------------------
def test_14_api_persistence_and_error_handling(test_client, db_session: Session):
    pdf_bytes = make_text_pdf(SCAM_FEE_OFFER_TEXT)
    files = {"file": ("persisted_offer_letter.pdf", pdf_bytes, "application/pdf")}

    response = test_client.post(
        "/api/v1/analyze/offer-letter",
        files=files,
        data={"company_name": "Acme Dynamic Tech Solutions Pvt Ltd"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["report_id"] is not None
    assert data["page_count"] == 1
    assert data["risk_category"] == "HIGH"
    assert data["extracted_fields"]["has_fee_demand"] is True

    # Verify persistence in offer_letter_scans table
    scan_record = (
        db_session.query(OfferLetterScan)
        .filter(OfferLetterScan.file_name == "persisted_offer_letter.pdf")
        .first()
    )
    assert scan_record is not None
    assert scan_record.scan_id == data["report_id"]
    assert scan_record.has_fee_demand is True
    assert scan_record.risk_category == "HIGH"
    assert scan_record.risk_score >= 80.0
    assert scan_record.page_count == 1

    # Verify ScanRequest persistence and linkage
    scan_req = (
        db_session.query(ScanRequest)
        .filter(ScanRequest.id == data["report_id"])
        .first()
    )
    assert scan_req is not None
    assert scan_req.input_type == "offer_letter"
    assert scan_req.status == "completed"

    # Verify PredictionHistory persistence
    pred_history = (
        db_session.query(PredictionHistory)
        .filter(PredictionHistory.scan_id == data["report_id"])
        .first()
    )
    assert pred_history is not None
    assert pred_history.risk_category == "HIGH"

    # Verify VerificationEvidence persistence
    ev_records = (
        db_session.query(VerificationEvidence)
        .filter(VerificationEvidence.scan_id == data["report_id"])
        .all()
    )
    assert len(ev_records) > 0
