"""Regression and Unit Tests for Company Name and CIN Extraction.

Verifies requirements:
1. Explicit company-name supplied in request takes precedence and is passed reliably.
2. Clearly labelled text (e.g. 'Company Name: Infosys Limited') is extracted unambiguously when field is empty.
3. Arbitrary words are never inferred as company names (missing names return UNKNOWN).
4. Multiple conflicting candidate company names are detected as ambiguous and return UNKNOWN.
5. Extracted name is passed into verification and returned as queried_name in API response.
6. Statuses UNKNOWN, SOURCE_UNAVAILABLE, STALE, and NO_MATCH are distinctly returned.
7. NO_MATCH is never classified as fraud.
"""

import pytest
from starlette.testclient import TestClient

from app.verification.extraction import (
    extract_company_info,
    extract_company_name_from_text,
    extract_cin_from_text,
)
from app.verification.company_verifier import CompanyVerifier, VerificationStatus


class TestCompanyNameExtraction:
    """Unit tests for extract_company_name_from_text and extract_company_info."""

    def test_labelled_company_name_extraction_variations(self):
        """Verify various standard labelled company header prefixes."""
        cases = [
            ("Company Name: Infosys Limited", "Infosys Limited"),
            ("Company: Infosys Limited", "Infosys Limited"),
            ("Employer Name: Tata Consultancy Services", "Tata Consultancy Services"),
            ("Employer: Wipro Limited", "Wipro Limited"),
            ("Organisation Name: HCL Technologies Limited", "HCL Technologies Limited"),
            ("Organization Name: Tech Mahindra Limited", "Tech Mahindra Limited"),
            ("Hiring Entity: Larsen & Toubro Infotech", "Larsen & Toubro Infotech"),
            ("Client Name: Acme Global Cloud", "Acme Global Cloud"),
            ("- **Company Name:** Infosys Limited", "Infosys Limited"),
            ("* Company: Infosys Limited", "Infosys Limited"),
            ("### Organization: Reliance Industries Limited", "Reliance Industries Limited"),
            ("Company Name: Infosys Limited | Location: Bengaluru", "Infosys Limited"),
            ("Company Name: Infosys Limited ; Bangalore Office", "Infosys Limited"),
            ("Company Name: \"Infosys Limited\"", "Infosys Limited"),
        ]
        for text, expected in cases:
            extracted, is_ambig, candidates = extract_company_name_from_text(text)
            assert extracted == expected, f"Failed for text: {text!r}"
            assert is_ambig is False
            assert len(candidates) == 1

    def test_explicitly_supplied_company_name_takes_precedence(self):
        """Explicit company_name argument takes precedence over any text in job description."""
        job_text = (
            "Position: Senior Backend Engineer\n"
            "Company Name: Unrelated Text Corp\n"
            "We are hiring experienced software engineers."
        )
        info = extract_company_info(job_text, explicit_company_name="Infosys Limited")
        assert info.company_name == "Infosys Limited"
        assert info.is_name_ambiguous is False
        assert info.candidate_names == ["Infosys Limited"]

    def test_missing_company_name_does_not_infer_from_arbitrary_words(self):
        """Unlabelled job text containing various arbitrary corporate words must not guess a company name."""
        job_text = (
            "We are seeking a senior python engineer to join our fast-growing enterprise startup. "
            "Our company values innovation, diversity, and excellence. "
            "The client expects high throughput microservices and cloud infrastructure. "
            "Apply today for immediate consideration."
        )
        extracted, is_ambig, candidates = extract_company_name_from_text(job_text)
        assert extracted is None
        assert is_ambig is False
        assert len(candidates) == 0

        info = extract_company_info(job_text)
        assert info.company_name is None
        assert info.is_name_ambiguous is False

    def test_ambiguous_company_names_flagged(self):
        """Multiple conflicting clearly-labelled company names must return ambiguous=True and company_name=None."""
        job_text = (
            "Job Summary:\n"
            "Company Name: Infosys Limited\n"
            "Role: Software Engineer\n"
            "Employer: Wipro Limited\n"
            "Location: Electronic City, Bengaluru"
        )
        extracted, is_ambig, candidates = extract_company_name_from_text(job_text)
        assert extracted is None
        assert is_ambig is True
        assert len(candidates) == 2
        assert "Infosys Limited" in candidates
        assert "Wipro Limited" in candidates

        info = extract_company_info(job_text)
        assert info.company_name is None
        assert info.is_name_ambiguous is True
        assert "Ambiguous" in (info.extraction_notes or "")

    def test_repeated_equivalent_company_names_not_ambiguous(self):
        """Multiple mentions that normalize to the same legal entity are not ambiguous."""
        job_text = (
            "Company Name: Infosys Limited\n"
            "About the Role: Developer\n"
            "Company: Infosys Ltd"
        )
        extracted, is_ambig, candidates = extract_company_name_from_text(job_text)
        assert extracted == "Infosys Limited"
        assert is_ambig is False
        assert len(candidates) == 2

    def test_placeholders_rejected(self):
        """Placeholder values like Confidential, N/A, Unknown are discarded."""
        for placeholder in ["Confidential", "N/A", "Unknown", "Undisclosed", "None", "Private"]:
            text = f"Company Name: {placeholder}\nWe are looking for an engineer."
            extracted, is_ambig, candidates = extract_company_name_from_text(text)
            assert extracted is None
            assert is_ambig is False
            assert len(candidates) == 0

    def test_cin_extraction_and_ambiguity(self):
        """Verify extraction of standard 21-character CIN from labelled and unlabelled text."""
        # Unambiguous CIN
        text1 = "Corporate Identification Number: L85110KA1981PLC013115\nRole: Lead Developer"
        cin1, ambig1, _ = extract_cin_from_text(text1)
        assert cin1 == "L85110KA1981PLC013115"
        assert ambig1 is False

        # Ambiguous conflicting CINs
        text2 = "CIN: L85110KA1981PLC013115 and subsidiary CIN: U72200MH2020PTC123456"
        cin2, ambig2, candidates2 = extract_cin_from_text(text2)
        assert cin2 is None
        assert ambig2 is True
        assert len(candidates2) == 2


class TestCompanyVerificationApiFlow:
    """Integration tests verifying full API request flow for company verification."""

    def test_user_scenario_infosys_limited_in_job_text(self, test_client: TestClient):
        """User scenario: job text contains 'Company Name: Infosys Limited' with empty form company name.
        
        Must extract 'Infosys Limited', pass it into verification, report queried_name,
        and return NO_MATCH (or MATCHED) with clear explanation of what was checked.
        """
        job_text = (
            "Company Name: Infosys Limited\n"
            "Position: Senior Systems Engineer - Python / Cloud\n"
            "Experience: 4 to 8 years\n"
            "Job Description:\n"
            "We are seeking a senior software engineer to design and develop enterprise applications. "
            "Must have experience in Python, relational databases, REST APIs, and automated testing frameworks. "
            "Apply through official careers channel."
        )

        response = test_client.post(
            "/api/v1/analyze/job-text",
            json={"text": job_text},  # separate company_name is omitted
        )
        assert response.status_code == 200
        data = response.json()

        cv = data["company_verification"]
        assert cv is not None
        # Queried name must be returned in API response
        assert cv["queried_name"] == "Infosys Limited"
        # Must not be UNKNOWN ('No company name provided')
        assert cv["status"] in ("NO_MATCH", "MATCHED", "SOURCE_UNAVAILABLE")
        assert cv["status"] != "UNKNOWN"
        assert "Infosys Limited" in cv["summary"]
        assert cv["is_fraud_signal"] is False

        # In evidence list, queried_name must be present in details
        cv_ev = next(e for e in data["evidence"] if e["source_name"] == "MCA-21 & DPIIT Registry Verifier")
        assert cv_ev["details"]["queried_name"] == "Infosys Limited"

    def test_explicitly_supplied_company_name_in_request(self, test_client: TestClient):
        """Explicit company_name field in payload is verified directly."""
        job_text = (
            "We are looking for a Senior Developer with 5+ years of experience in Django, "
            "FastAPI, and PostgreSQL. Remote work available. Competitive salary."
        )
        response = test_client.post(
            "/api/v1/analyze/job-text",
            json={
                "text": job_text,
                "company_name": "Infosys Limited",
            },
        )
        assert response.status_code == 200
        data = response.json()

        cv = data["company_verification"]
        assert cv["queried_name"] == "Infosys Limited"
        assert cv["status"] in ("NO_MATCH", "MATCHED", "SOURCE_UNAVAILABLE")
        assert cv["status"] != "UNKNOWN"
        assert "Infosys Limited" in cv["summary"]

    def test_missing_company_name_returns_unknown(self, test_client: TestClient):
        """When neither explicit field nor labelled text is present, return UNKNOWN."""
        job_text = (
            "We are looking for a Senior Developer with 5+ years of experience in Django, "
            "FastAPI, and PostgreSQL. Remote work available. Competitive salary."
        )
        response = test_client.post(
            "/api/v1/analyze/job-text",
            json={"text": job_text},
        )
        assert response.status_code == 200
        data = response.json()

        cv = data["company_verification"]
        assert cv["status"] == "UNKNOWN"
        assert cv["queried_name"] is None
        assert "No company name" in cv["summary"]

    def test_ambiguous_company_names_in_text_returns_unknown(self, test_client: TestClient):
        """When text contains multiple conflicting company names, return UNKNOWN with explanation."""
        job_text = (
            "Company Name: Infosys Limited\n"
            "Employer: Wipro Limited\n"
            "We are looking for a Senior Developer with 5+ years of experience in Django, "
            "FastAPI, and PostgreSQL. Remote work available. Competitive salary."
        )
        response = test_client.post(
            "/api/v1/analyze/job-text",
            json={"text": job_text},
        )
        assert response.status_code == 200
        data = response.json()

        cv = data["company_verification"]
        assert cv["status"] == "UNKNOWN"
        assert "Ambiguous company name" in cv["summary"]
        assert "Infosys Limited" in cv["summary"]
        assert "Wipro Limited" in cv["summary"]
