"""Tests for Recruiter Email & Communication Verification (Feature F3/F4).

Verifies:
- Email syntax validation without external SMTP probing
- Privacy-preserving masking and SHA-256 hashing (raw email never stored)
- Free webmail detection against enterprise company claims
- Corporate domain matching with mandatory identity caveats
- Domain mismatch and lookalike detection
- Contextual recruitment message analysis (rules + ML)
- Database persistence in recruiter_email_scans and scan_requests
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
from starlette.testclient import TestClient

from app.models.company import Company, CompanyDomain
from app.models.recruiter import RecruiterEmailScan
from app.models.scan import ScanRequest
from app.services.domain_checker import DomainCheckResult
from app.services.recruiter_checker import (
    hash_email,
    is_free_webmail_domain,
    mask_email,
    validate_email_syntax,
    verify_recruiter_email,
)


def make_mock_domain_result(
    domain: str,
    lookalike_flags: dict = None,
    resolved_ips: list = None,
    dns_status: str = "PASS",
) -> DomainCheckResult:
    return DomainCheckResult(
        domain=domain,
        dns_status=dns_status,
        mx_status="PASS",
        spf_status="PASS",
        dkim_status="PASS",
        dmarc_status="PASS",
        lookalike_flags=lookalike_flags or {"is_lookalike": False},
        source_details={"resolved_ips": resolved_ips or ["93.184.216.34"]},
        checked_at=datetime.now(timezone.utc),
    )


class TestRecruiterEmailPrivacyAndSyntax:
    """Verifies privacy masking, SHA-256 hashing, and syntax checks."""

    def test_mask_email(self):
        assert mask_email("careers@infosys.com") == "c***s@infosys.com"
        assert mask_email("hr@tcs.com") == "h*@tcs.com"
        assert mask_email("bob@amazon.com") == "b*b@amazon.com"
        assert mask_email("recruiter.lead.global@acme.corp") == "r***l@acme.corp"
        assert mask_email("a@test.com") == "*@test.com"

    def test_hash_email_deterministic(self):
        h1 = hash_email("Careers@Infosys.com ")
        h2 = hash_email("careers@infosys.com")
        assert h1 == h2
        assert len(h1) == 64

    def test_validate_email_syntax(self):
        valid, local, domain = validate_email_syntax("recruiter@example.com")
        assert valid is True
        assert local == "recruiter"
        assert domain == "example.com"

        invalid_cases = [
            "",
            "not-an-email",
            "@missing-local.com",
            "missing-domain@",
            "missing-tld@domain",
            "spaces in@domain.com",
            "a" * 255 + "@domain.com",
        ]
        for case in invalid_cases:
            valid, _, _ = validate_email_syntax(case)
            assert valid is False


class TestRecruiterEmailAnalysisEndpoint:
    """Tests POST /api/v1/analyze/recruiter-email route."""

    def test_free_webmail_recruiter_triggers_high_warning_for_claimed_enterprise(
        self, test_client: TestClient
    ):
        """Free webmail address claimed to represent an enterprise is flagged with FREE_EMAIL_PROVIDER."""
        with patch("app.services.recruiter_checker.check_domain_security") as mock_dc:
            mock_dc.return_value = make_mock_domain_result(
                domain="gmail.com",
                resolved_ips=["142.250.190.46"],
            )

            response = test_client.post(
                "/api/v1/analyze/recruiter-email",
                json={
                    "email": "infosys.hr.recruitment@gmail.com",
                    "company_name": "Infosys Limited",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["email_status"] == "FREE_EMAIL_PROVIDER"
            assert data["is_free_email"] is True
            assert data["email_masked"] == "i***t@gmail.com"
            assert data["risk_category"] in ("HIGH", "CRITICAL")
            evidence_types = [e["evidence_type"] for e in data["evidence"]]
            assert "recruiter_email_signal" in evidence_types
            assert any("free webmail" in action.lower() or "corporate" in action.lower()
                       for action in data["recommended_safe_actions"])

    def test_corporate_domain_match_with_sender_identity_caveat(
        self, test_client: TestClient, db_session
    ):
        """Official corporate domain match returns DOMAIN_MATCH and explicit identity disclaimer."""
        with patch("app.services.recruiter_checker.check_domain_security") as mock_dc:
            mock_dc.return_value = make_mock_domain_result(domain="infosys.com")

            response = test_client.post(
                "/api/v1/analyze/recruiter-email",
                json={
                    "email": "careers@infosys.com",
                    "company_name": "Infosys Limited",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["email_status"] == "DOMAIN_MATCH"
            assert data["email_masked"] == "c***s@infosys.com"
            assert data["is_free_email"] is False
            assert data["risk_category"] == "LOW"

            # Mandatory requirement: Never claim domain match proves individual sender identity
            limitations_text = " ".join(data["limitations"]).lower()
            assert "not prove" in limitations_text or "does not definitively prove" in limitations_text

    def test_domain_mismatch_detected(self, test_client: TestClient):
        """Recruiter emailing from unrelated third-party domain triggers MISMATCH_DETECTED."""
        with patch("app.services.recruiter_checker.check_domain_security") as mock_dc:
            mock_dc.return_value = make_mock_domain_result(domain="unrelated-staffing.org")

            response = test_client.post(
                "/api/v1/analyze/recruiter-email",
                json={
                    "email": "hr@unrelated-staffing.org",
                    "company_name": "Infosys Limited",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["email_status"] == "MISMATCH_DETECTED"
            assert data["email_masked"] == "h*@unrelated-staffing.org"

    def test_lookalike_domain_triggers_critical_alert(self, test_client: TestClient):
        """Lookalike / typosquatting domain returns LOOKALIKE_WARNING and high risk score."""
        with patch("app.services.recruiter_checker.check_domain_security") as mock_dc:
            mock_dc.return_value = make_mock_domain_result(
                domain="inf0sys-careers.com",
                lookalike_flags={
                    "is_lookalike": True,
                    "matched_legitimate_domain": "infosys.com",
                    "similarity_type": "homoglyph_replacement",
                },
            )

            response = test_client.post(
                "/api/v1/analyze/recruiter-email",
                json={
                    "email": "careers@inf0sys-careers.com",
                    "company_name": "Infosys Limited",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["email_status"] == "LOOKALIKE_WARNING"
            assert data["risk_category"] == "CRITICAL"
            assert data["risk_score"] >= 80.0

    def test_recruiter_email_with_message_text_evaluates_heuristics_and_ml(
        self, test_client: TestClient
    ):
        """User-pasted message text is evaluated for upfront fees, WhatsApp contacts, and ML probability."""
        suspicious_message = (
            "Congratulations! You are shortlisted for the Data Entry Analyst position at Infosys Limited. "
            "To secure your joining kit and company laptop, please pay a refundable registration deposit of $150. "
            "Contact HR manager immediately on WhatsApp: +1 555-019-2834."
        )

        with patch("app.services.recruiter_checker.check_domain_security") as mock_dc:
            mock_dc.return_value = make_mock_domain_result(
                domain="gmail.com",
                resolved_ips=["142.250.190.46"],
            )

            response = test_client.post(
                "/api/v1/analyze/recruiter-email",
                json={
                    "email": "infosys.hiring.fast@gmail.com",
                    "company_name": "Infosys Limited",
                    "message_text": suspicious_message,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["risk_category"] == "CRITICAL"
            assert data["risk_score"] >= 85.0
            assert data["ml_analysis"] is not None
            rule_types = [e["source_name"] for e in data["evidence"]]
            assert any("Upfront Fees" in r for r in rule_types)

    def test_database_persistence_masks_email_and_preserves_privacy(
        self, test_client: TestClient, db_session
    ):
        """Verifies scan is persisted in scan_requests and recruiter_email_scans with masked email."""
        with patch("app.services.recruiter_checker.check_domain_security") as mock_dc:
            mock_dc.return_value = make_mock_domain_result(domain="infosys.com")

            raw_email = "executive.recruiter@infosys.com"
            response = test_client.post(
                "/api/v1/analyze/recruiter-email",
                json={
                    "email": raw_email,
                    "company_name": "Infosys Limited",
                },
            )
            assert response.status_code == 200
            report_id = response.json()["report_id"]

            # Query database directly
            scan_req = db_session.query(ScanRequest).filter(ScanRequest.id == report_id).first()
            assert scan_req is not None
            assert scan_req.input_type == "recruiter_email"
            assert raw_email not in scan_req.input_reference  # Raw email must never be stored

            # Check recruiter_email_scans record
            recruiter_scan = (
                db_session.query(RecruiterEmailScan)
                .filter(RecruiterEmailScan.scan_id == report_id)
                .first()
            )
            assert recruiter_scan is not None
            assert recruiter_scan.email_masked == "e***r@infosys.com"
            assert recruiter_scan.email_hash == hash_email(raw_email)
            assert recruiter_scan.domain == "infosys.com"
            assert recruiter_scan.status == "DOMAIN_MATCH"
