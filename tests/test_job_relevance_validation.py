"""Comprehensive Automated Tests for Job-Relevance Validation & Invalid Input Guard Layer.

Verifies:
1. Legitimate job postings (with and without salary/company) pass relevance validation.
2. Recruitment scam postings pass relevance validation (ensuring they reach fraud analyzers).
3. Recipes, source code, weather, academic essays, casual chat, and product sales are rejected as INVALID.
4. Ambiguous short snippets are classified as UNCERTAIN rather than scams.
5. Invalid/uncertain inputs do NOT invoke ML inference, do NOT compute risk scores, and do NOT persist ScanRequest in DB.
6. Attempting to download a verification PDF for an invalid/uncertain scan returns HTTP 404.
7. Job URL analysis rejects non-job URLs and handles anti-bot (403/429) as UNCERTAIN without misclassification.
8. Offer letter analysis rejects non-offer documents (e.g. invoices) and unreadable scans.
9. Async OCR worker enforces relevance check and marks non-offer jobs as FAILED.
10. Recruiter email with non-job message text is rejected as INVALID; email without body returns UNCERTAIN message risk.
"""

from datetime import datetime, timezone
import os
import sys
from unittest.mock import patch
import pytest
from starlette.testclient import TestClient

backend_path = os.path.abspath("backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.models.scan import ScanRequest
from app.models.worker import AsyncDocumentJob
from app.services.job_relevance_validator import (
    validate_job_text,
    validate_job_url,
    validate_offer_letter,
    validate_recruiter_email,
)
from app.services.safe_fetch import SafeFetchResult
from tests.test_offer_letter_analyzer import make_text_pdf


# -----------------------------------------------------------------------------
# Unit Tests for validate_job_text
# -----------------------------------------------------------------------------

class TestValidateJobTextUnit:
    """Verifies standalone deterministic classification of text inputs."""

    def test_legitimate_job_with_full_details_passes(self):
        text = """
        Senior Python Backend Engineer - Cloud Infrastructure Team
        Company: TechNova Solutions
        Location: Remote / Bangalore
        Compensation: INR 24,00,000 - 32,00,000 per annum + Benefits
        
        Responsibilities:
        - Design and maintain scalable microservices using FastAPI and PostgreSQL.
        - Collaborate with cross-functional product and DevOps teams.
        - Write robust unit and integration tests with pytest.
        
        Requirements:
        - 4+ years of backend software engineering experience.
        - Bachelor's or Master's degree in Computer Science.
        - Proficiency in Docker, Kubernetes, and AWS cloud services.
        
        To apply, submit your resume and GitHub profile to careers@technova.example.com.
        """
        res = validate_job_text(text)
        assert res.is_job_related is True
        assert res.status == "VALID"
        assert res.reason_code == "JOB_CONTENT_CONFIRMED"

    def test_legitimate_job_without_salary_or_company_passes(self):
        """Legitimate vacancies without salary or company name must STILL pass validation."""
        text = """
        Looking for a passionate React Native Developer to build our next-generation mobile apps.
        Must have hands-on experience with Redux Toolkit, TypeScript, and offline-first SQLite synchronization.
        Key duties include building fluid animations and optimizing performance across iOS and Android.
        Requirements: Minimum 3 years building consumer mobile apps.
        Interested candidates please send your resume and portfolio to apply.
        """
        res = validate_job_text(text)
        assert res.is_job_related is True
        assert res.status == "VALID"
        assert res.reason_code == "JOB_CONTENT_CONFIRMED"

    def test_scam_recruitment_posting_passes_relevance_validation(self):
        """Fraudulent recruitment postings must pass relevance so they reach the fraud risk engine."""
        scam_text = """
        URGENT HIRING: Data Entry Operator & Back Office Assistant!
        Work from home part-time and earn $500 to $1,000 weekly payout!
        No experience or educational degree required. Freshers welcome.
        Must pay refundable security deposit of $100 for registration and training software.
        Contact our HR Manager immediately on WhatsApp: +1 555-019-2834. Apply now!
        """
        res = validate_job_text(scam_text)
        assert res.is_job_related is True
        assert res.status == "VALID"

    def test_cooking_recipe_rejected_as_invalid(self):
        recipe = """
        Preheat oven to 375 degrees F. In a large bowl, whisk together 2 cups of flour,
        1 tsp baking soda, and 1/2 tsp salt. In another bowl, beat 1 cup softened butter,
        3/4 cup granulated sugar, and 2 eggs until creamy. Stir in chocolate chips.
        Drop rounded tablespoons onto ungreased baking sheets. Bake for 9 to 11 minutes until golden brown.
        """
        res = validate_job_text(recipe)
        assert res.is_job_related is False
        assert res.status == "INVALID"
        assert res.reason_code == "RECIPE_DETECTED"
        assert "recipe" in res.supporting_message.lower()

    def test_source_code_rejected_as_invalid(self):
        code_snippet = """
        import os
        import sys
        
        def calculate_factorial(n: int) -> int:
            if n <= 1:
                return 1
            return n * calculate_factorial(n - 1)
        
        class MathEngine:
            def __init__(self, precision: int = 4):
                self.precision = precision
        """
        res = validate_job_text(code_snippet)
        assert res.is_job_related is False
        assert res.status == "INVALID"
        assert res.reason_code == "SOURCE_CODE_DETECTED"
        assert "source code" in res.supporting_message.lower()

    def test_weather_forecast_rejected_as_invalid(self):
        weather = """
        Today's weather forecast for London:
        Expect overcast skies with a maximum temperature of 17 degrees Celsius and 82% humidity.
        Scattered precipitation and wind speeds reaching 20 mph are expected throughout the afternoon.
        Overnight lows will drop to 11 degrees with foggy patches.
        """
        res = validate_job_text(weather)
        assert res.is_job_related is False
        assert res.status == "INVALID"
        assert res.reason_code == "WEATHER_FORECAST"

    def test_academic_essay_rejected_as_invalid(self):
        essay = """
        In this essay, we examine the historiographical debates surrounding the fall of the Western Roman Empire.
        Our literature review investigates primary archaeological sources and empirical economic findings.
        In conclusion, this study demonstrates that political fragmentation preceded catastrophic fiscal collapse.
        """
        res = validate_job_text(essay)
        assert res.is_job_related is False
        assert res.status == "INVALID"
        assert res.reason_code == "ACADEMIC_ESSAY"

    def test_personal_chat_rejected_as_invalid(self):
        chat = """
        Hey what's up bro! Are you free tonight? Let's hang out and watch the football match.
        Talk to you later, haha so funny! See you tomorrow at the cafe.
        """
        res = validate_job_text(chat)
        assert res.is_job_related is False
        assert res.status == "INVALID"
        assert res.reason_code == "PERSONAL_CHAT"

    def test_product_sales_rejected_as_invalid(self):
        product = """
        Premium Wireless Noise-Cancelling Headphones.
        Product specifications: 40mm drivers, Bluetooth 5.2, 30-hour battery life.
        In stock with free shipping! Add to cart now and use discount code SAVE20 at checkout.
        """
        res = validate_job_text(product)
        assert res.is_job_related is False
        assert res.status == "INVALID"
        assert res.reason_code == "PRODUCT_SALES"

    def test_repetitive_gibberish_rejected_as_invalid(self):
        gibberish = "asdfasdfasdfasdfasdfasdfasdfasdfasdfasdfasdfasdf"
        res = validate_job_text(gibberish)
        assert res.is_job_related is False
        assert res.status == "INVALID"
        assert res.reason_code == "REPETITIVE_GIBBERISH"

    def test_ambiguous_short_snippet_returns_uncertain(self):
        """Ambiguous weak inputs must be UNCERTAIN rather than labeled as scam or valid."""
        ambiguous = "Urgent need call me on 9876543210 for work details."
        res = validate_job_text(ambiguous)
        assert res.is_job_related is False
        assert res.status == "UNCERTAIN"
        assert res.reason_code == "AMBIGUOUS_SHORT_TEXT"


# -----------------------------------------------------------------------------
# End-to-End API Integration Tests: POST /api/v1/analyze/job-text
# -----------------------------------------------------------------------------

class TestJobTextEndpointGuard:
    """Verifies that the /job-text endpoint enforces the validation guard and blocks persistence."""

    def test_unrelated_text_returns_invalid_input_and_skips_persistence(self, test_client: TestClient, db_session):
        recipe_payload = {
            "text": "Preheat oven to 350 degrees F. Whisk 2 cups of flour, sugar, and baking powder. Bake for 25 minutes."
        }
        resp = test_client.post("/api/v1/analyze/job-text", json=recipe_payload)
        assert resp.status_code == 200
        data = resp.json()

        # Guard outputs
        assert data["is_job_related"] is False
        assert data["risk_category"] == "INVALID_INPUT"
        assert data["risk_score"] is None
        assert data["warning"] == "Please provide job-related input to continue."
        assert data["relevance"]["status"] == "INVALID"
        assert data["relevance"]["reason_code"] == "RECIPE_DETECTED"
        assert data["ml_analysis"] is None
        assert len(data["evidence"]) == 0

        # CRITICAL PRIVACY & DB REQUIREMENT: ScanRequest must NOT be persisted in DB
        report_id = data["report_id"]
        scan = db_session.query(ScanRequest).filter(ScanRequest.id == report_id).first()
        assert scan is None, "Non-job input must NOT persist a ScanRequest record in the database"

        # CRITICAL REPORT REQUIREMENT: Downloading a PDF report must return 404
        pdf_resp = test_client.get(f"/api/v1/scans/{report_id}/report.pdf")
        assert pdf_resp.status_code == 404

    def test_valid_job_text_executes_pipeline_and_persists_scan(self, test_client: TestClient, db_session):
        valid_job = {
            "text": """
            Lead Full Stack Engineer - FinTech Platform
            London, UK (Hybrid)
            We are hiring an experienced engineer with 5+ years of React, Node.js, and PostgreSQL experience.
            Responsibilities include developing payment gateway integrations and mentoring junior developers.
            Competitive compensation £80,000 - £95,000 + equity. Apply with CV to jobs@fintech.example.com.
            """
        }
        resp = test_client.post("/api/v1/analyze/job-text", json=valid_job)
        assert resp.status_code == 200
        data = resp.json()

        assert data["is_job_related"] is True
        assert data["relevance"]["status"] == "VALID"
        assert data["risk_score"] is not None
        assert data["ml_analysis"] is not None

        # Confirms scan is persisted for valid jobs
        report_id = data["report_id"]
        scan = db_session.query(ScanRequest).filter(ScanRequest.id == report_id).first()
        assert scan is not None


# -----------------------------------------------------------------------------
# End-to-End API Integration Tests: POST /api/v1/analyze/job-url
# -----------------------------------------------------------------------------

class TestJobUrlEndpointGuard:
    """Verifies that the /job-url endpoint validates relevance and handles anti-bot pages."""

    def test_unrelated_url_content_returns_invalid_input(self, test_client: TestClient, db_session):
        recipe_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Classic Chocolate Cake Recipe</title></head>
        <body>
          <h1>Chocolate Fudge Cake</h1>
          <p>Ingredients: 2 cups flour, 1 cup sugar, 2 eggs, 1 tsp baking powder. Preheat oven to 350F and bake for 30 minutes.</p>
        </body>
        </html>
        """
        with patch("app.api.v1.analyze.safe_fetch_url") as mock_fetch:
            mock_fetch.return_value = SafeFetchResult(
                final_url="https://recipes.example.com/cake",
                status_code=200,
                content=recipe_html,
                content_type="text/html",
                redirect_history=[],
                resolved_ips=["93.184.216.34"],
            )

            resp = test_client.post("/api/v1/analyze/job-url", json={"url": "https://recipes.example.com/cake"})
            assert resp.status_code == 200
            data = resp.json()

            assert data["is_job_related"] is False
            assert data["risk_category"] == "INVALID_INPUT"
            assert data["risk_score"] is None
            assert data["relevance"]["status"] == "INVALID"
            assert data["relevance"]["reason_code"] == "RECIPE_DETECTED"

            # DB check: must not persist scan
            report_id = data["report_id"]
            scan = db_session.query(ScanRequest).filter(ScanRequest.id == report_id).first()
            assert scan is None

    def test_anti_bot_403_returns_uncertain_with_paste_guidance(self, test_client: TestClient):
        with patch("app.api.v1.analyze.safe_fetch_url") as mock_fetch:
            mock_fetch.return_value = SafeFetchResult(
                final_url="https://careers.company.com/job/123",
                status_code=403,
                content="<html><body>Access Denied - Cloudflare Bot Management</body></html>",
                content_type="text/html",
                redirect_history=[],
                resolved_ips=["104.16.132.229"],
            )

            resp = test_client.post("/api/v1/analyze/job-url", json={"url": "https://careers.company.com/job/123"})
            assert resp.status_code == 200
            data = resp.json()

            assert data["is_job_related"] is False
            assert data["relevance"]["status"] == "UNCERTAIN"
            assert data["relevance"]["reason_code"] == "BOT_PROTECTION_OR_SPARSE"
            assert "paste" in data["relevance"]["supporting_message"].lower()


# -----------------------------------------------------------------------------
# End-to-End API Integration Tests: POST /api/v1/analyze/offer-letter
# -----------------------------------------------------------------------------

class TestOfferLetterEndpointGuard:
    """Verifies that the /offer-letter endpoint rejects non-offer documents and unreadable PDFs."""

    def test_unrelated_invoice_pdf_rejected_as_invalid(self, test_client: TestClient, db_session):
        invoice_text = """
        TAX INVOICE
        Bill To: Acme Corporation
        Invoice No: INV-2026-9812
        Invoice Date: 12-Oct-2026
        Payment Due: 26-Oct-2026
        
        Item Description: Cloud Hosting Server Tier 3
        Quantity: 2
        Unit Price: $500.00
        Subtotal: $1,000.00
        Total Amount Due: $1,180.00 (inclusive of GST)
        Please wire payment to Chase Bank Account #987654321.
        """
        pdf_bytes = make_text_pdf(invoice_text)

        files = {"file": ("invoice_2026.pdf", pdf_bytes, "application/pdf")}
        resp = test_client.post("/api/v1/analyze/offer-letter", files=files)
        assert resp.status_code == 200
        data = resp.json()

        assert data["is_job_related"] is False
        assert data["risk_category"] == "INVALID_INPUT"
        assert data["risk_score"] is None
        assert data["relevance"]["status"] == "INVALID"
        assert data["relevance"]["reason_code"] == "NON_OFFER_DOCUMENT"
        assert "not appear to be an employment offer letter" in data["relevance"]["supporting_message"]

        # Confirm not persisted
        report_id = data["report_id"]
        scan = db_session.query(ScanRequest).filter(ScanRequest.id == report_id).first()
        assert scan is None

        # Confirm PDF report download returns 404
        pdf_resp = test_client.get(f"/api/v1/scans/{report_id}/report.pdf")
        assert pdf_resp.status_code == 404

    def test_unreadable_sparse_pdf_returns_uncertain(self, test_client: TestClient):
        sparse_text = "Hi"  # < 30 chars
        pdf_bytes = make_text_pdf(sparse_text)

        files = {"file": ("blank_scan.pdf", pdf_bytes, "application/pdf")}
        resp = test_client.post("/api/v1/analyze/offer-letter", files=files)
        assert resp.status_code == 200
        data = resp.json()

        assert data["is_job_related"] is False
        assert data["relevance"]["status"] == "UNCERTAIN"
        assert data["relevance"]["reason_code"] == "UNREADABLE_DOCUMENT"


# -----------------------------------------------------------------------------
# Async OCR Worker Guard Tests
# -----------------------------------------------------------------------------

class TestAsyncOCRWorkerGuard:
    """Verifies that the background OCR worker rejects non-offer documents and sets job to FAILED."""

    def test_worker_fails_non_offer_job_without_persisting_scan(self, db_session):
        from app.workers.ocr_worker import execute_offer_letter_ocr_job, enqueue_offer_letter_ocr_job

        invoice_text = """
        COMMERCIAL INVOICE / PURCHASE ORDER
        Vendor: Global Hardware Supplies
        Bill To: Logistics Corp
        Item: 50x Office Chairs
        Total Amount Due: $4,500
        Payment Due Date: Net 30 days
        """
        pdf_bytes = make_text_pdf(invoice_text)

        job, _ = enqueue_offer_letter_ocr_job(
            db=db_session,
            file_bytes=pdf_bytes,
            file_name="commercial_invoice.pdf",
            session_id="test-session-worker-guard",
        )

        completed_job = execute_offer_letter_ocr_job(
            db=db_session,
            job_id=job.id,
            file_bytes=pdf_bytes,
        )

        assert completed_job.status == "FAILED"
        assert completed_job.result_scan_id is None
        assert "not appear to be an employment offer letter" in completed_job.error_message
        assert completed_job.result_summary["is_job_related"] is False
        assert completed_job.result_summary["status"] == "INVALID"
        assert completed_job.result_summary["reason_code"] == "NON_OFFER_DOCUMENT"


# -----------------------------------------------------------------------------
# Recruiter Email Guard Tests
# -----------------------------------------------------------------------------

class TestRecruiterEmailGuard:
    """Verifies recruiter email validation with and without recruitment message body."""

    def test_recruiter_email_with_recipe_message_rejected_as_invalid(self, test_client: TestClient, db_session):
        recipe_msg = "Preheat oven to 375F. Mix 2 cups flour with sugar and eggs. Bake for 20 minutes."
        resp = test_client.post(
            "/api/v1/analyze/recruiter-email",
            json={
                "email": "hr@legitcorp.com",
                "message_text": recipe_msg,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["is_job_related"] is False
        assert data["risk_category"] == "INVALID_INPUT"
        assert data["risk_score"] is None
        assert data["relevance"]["status"] == "INVALID"
        assert data["relevance"]["reason_code"] == "RECIPE_DETECTED"

        # Scan should not be persisted
        report_id = data["report_id"]
        scan = db_session.query(ScanRequest).filter(ScanRequest.id == report_id).first()
        assert scan is None

    def test_recruiter_email_without_body_returns_uncertain_message_risk(self, test_client: TestClient):
        with patch("app.services.recruiter_checker.check_domain_security") as mock_dc:
            from tests.test_recruiter_email_analysis import make_mock_domain_result
            mock_dc.return_value = make_mock_domain_result(domain="infosys.com")

            resp = test_client.post(
                "/api/v1/analyze/recruiter-email",
                json={"email": "recruiter@infosys.com"},
            )
            assert resp.status_code == 200
            data = resp.json()

            assert data["is_job_related"] is True
            assert data["relevance"]["status"] == "UNCERTAIN"
            assert data["relevance"]["reason_code"] == "EMAIL_ONLY_NO_CONTEXT"
            assert "Without the email message body" in data["relevance"]["supporting_message"]


# -----------------------------------------------------------------------------
# Regression Tests for Dynamic Portals (e.g. Naukri) & Incidental Employment Terms
# -----------------------------------------------------------------------------

class TestDynamicPortalAndRegressionGuard:
    """Verifies robustness against dynamic portal layouts, collapsed descriptions,
    unrelated portal pages, and incidental employment terms.
    """

    def test_naukri_style_job_listing_with_title_company_responsibilities_qualifications_passes(self):
        """Simulates the Naukri.com American Express 'Analyst - Data Science' posting."""
        text = """
        Job Title: Analyst - Data Science
        Company: American Express
        Experience: 1 - 4 years
        Location: Gurgaon/Gurugram, Bengaluru
        
        Job Description:
        As an Analyst in Data Science at American Express, you will be part of the Risk and Information Management team.
        
        Key Responsibilities:
        - Build, optimize, and deploy machine learning and AI models for risk management and fraud prevention.
        - Analyze complex financial data and transaction patterns to drive predictive strategies.
        - Collaborate with engineering and cross-functional teams to implement analytical solutions.
        
        Qualifications:
        - Bachelor's or Master's degree in Computer Science, Statistics, Mathematics, or related field.
        - 1 to 4 years of experience with Python, SQL, and data science frameworks.
        - Strong problem solving skills and expertise in predictive modeling.
        """
        result = validate_job_text(text)
        assert result.is_job_related is True
        assert result.status == "VALID"
        assert result.reason_code == "JOB_CONTENT_CONFIRMED"
        assert result.details["dimensions_matched"] >= 3

    def test_job_listing_with_partial_or_collapsed_text_returns_uncertain(self):
        """Collapsed job snippet with weak/partial cues returns UNCERTAIN rather than false fraud score."""
        text = "Analyst - Data Science\nAmerican Express\n... Read more"
        result = validate_job_text(text)
        assert result.is_job_related is False
        assert result.status == "UNCERTAIN"
        assert result.reason_code == "AMBIGUOUS_SHORT_TEXT"
        assert "incomplete or ambiguous" in result.user_message.lower() or "insufficient recruitment" in result.supporting_message.lower()

    def test_valid_listing_without_salary_information_passes(self):
        """Legitimate job posting without compensation details passes validation."""
        text = """
        Job Title: Cloud Software Engineer
        Company: Capgemini
        Location: Pune, Maharashtra
        Employment Type: Full Time, Permanent
        
        Responsibilities:
        - Design and develop cloud-native backend applications using Java and Spring Boot.
        - Collaborate with architecture team on microservices migration.
        - Maintain CI/CD deployment pipelines on AWS.
        
        Required Skills:
        - Degree in Engineering or Computer Applications.
        - 3 - 6 years of experience in Java development and cloud infrastructure.
        """
        result = validate_job_text(text)
        assert result.is_job_related is True
        assert result.status == "VALID"
        assert result.reason_code == "JOB_CONTENT_CONFIRMED"

    def test_unrelated_naukri_page_rejected_as_invalid(self):
        """Unrelated portal services or resume builder page on Naukri is rejected as INVALID."""
        text = """
        Naukri FastForward Resume Writing Services
        Get your resume crafted by industry experts.
        Highlight your achievements with professional resume templates.
        Free resume critique report and recruiter spotlight features.
        Download Word and PDF resume samples today.
        """
        result = validate_job_text(text)
        assert result.is_job_related is False
        assert result.status == "INVALID"
        assert result.reason_code == "UNRELATED_CONTENT"
        assert result.user_message == "Please provide job-related input to continue."

    def test_non_job_page_with_employment_words_appearing_incidentally_rejected(self):
        """Academic or philosophical essay mentioning 'developers' or 'scientists' incidentally is rejected."""
        text = """
        In this essay, we examine the philosophical underpinnings of artificial intelligence and machine cognition.
        Many developers and scientists have observed that historical breakthroughs in computing mirror early
        epistemological inquiries into human thought. In conclusion, this study demonstrates that cognitive
        methodology remains central to contemporary philosophy of mind.
        """
        result = validate_job_text(text)
        assert result.is_job_related is False
        assert result.status == "INVALID"
        assert result.reason_code == "ACADEMIC_ESSAY"

    def test_endpoint_guarantees_no_risk_assessment_for_unrelated_input(self, test_client: TestClient, db_session):
        """Verifies API returns is_job_related=False, risk_score=None, and does not persist scans."""
        resp = test_client.post(
            "/api/v1/analyze/job-text",
            json={"text": "Today's weather report: partly cloudy with humidity of 75% and wind speeds of 15 km/h."},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_job_related"] is False
        assert data["risk_score"] is None
        assert data["risk_category"] == "INVALID_INPUT"
        assert data["warning"] == "Please provide job-related input to continue."
        assert len(data["evidence"]) <= 1  # only InputGuard diagnostic item, no fraud evidence
        
        # Confirmation that scan record is not persisted in DB
        scan = db_session.query(ScanRequest).filter(ScanRequest.id == data["report_id"]).first()
        assert scan is None
