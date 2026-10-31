"""Input Validation Acceptance Tests for JobShield AI Analysis API.

Verifies:
- Missing, null, and non-string payload structures are rejected with 422.
- Exact boundary validation: 19 chars (rejected), 20 chars (accepted), 50,000 chars (accepted), 50,001 chars (rejected).
- Whitespace stripping and trimmed boundary validation.
- Multi-byte unicode, emoji, and control character safety.
- Zero-leakage guarantee: raw invalid inputs are redacted from 422 response bodies.
"""

import os
import sys
import pytest

# Ensure backend directory is in sys.path
backend_path = os.path.abspath("backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)


def test_missing_text_key_rejected(test_client):
    """Verify payload missing the required 'text' field is rejected with 422."""
    resp = test_client.post("/api/v1/analyze/job-text", json={})
    assert resp.status_code == 422
    assert "Field required" in resp.text or "field_required" in resp.text


def test_null_and_none_text_rejected(test_client):
    """Verify payload with null 'text' value is rejected with 422."""
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": None})
    assert resp.status_code == 422
    assert "Input should be a valid string" in resp.text or "string_type" in resp.text


@pytest.mark.parametrize("invalid_value", [
    12345,
    3.14159,
    True,
    False,
    ["Software Engineer", "Remote"],
    {"job_description": "We are hiring"},
])
def test_non_string_types_rejected(test_client, invalid_value):
    """Verify non-string types for 'text' are strictly rejected with 422."""
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": invalid_value})
    assert resp.status_code == 422
    assert "string" in resp.text.lower()


def test_exact_lower_boundary_19_chars_rejected(test_client):
    """Verify string of length exactly 19 characters is rejected with 422."""
    raw_19 = "A" * 19
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": raw_19})
    assert resp.status_code == 422
    assert "too short" in resp.text or "minimum 20 characters" in resp.text


def test_exact_lower_boundary_20_chars_accepted(test_client):
    """Verify string of length exactly 20 characters is accepted (returns 200)."""
    raw_20 = "A" * 20
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": raw_20})
    assert resp.status_code == 200
    data = resp.json()
    assert "report_id" in data


def test_exact_upper_boundary_50000_chars_accepted(test_client):
    """Verify string of length exactly 50,000 characters is accepted (returns 200)."""
    raw_50000 = "Senior Python Developer role with extensive cloud requirements. " * 781 + ("A" * 16)
    assert len(raw_50000) == 50000
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": raw_50000})
    assert resp.status_code == 200
    data = resp.json()
    assert "report_id" in data


def test_exact_upper_boundary_50001_chars_rejected(test_client):
    """Verify string of length exactly 50,001 characters is rejected with 422."""
    raw_50001 = "A" * 50001
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": raw_50001})
    assert resp.status_code == 422
    assert "exceeds maximum allowed size" in resp.text or "50,000" in resp.text


@pytest.mark.parametrize("whitespace_payload", [
    "   ",
    "\t\t\t\t",
    "\n\n\n\n\n",
    "   \n  \t  \r\n   ",
    " " * 100,
])
def test_whitespace_only_payloads_rejected(test_client, whitespace_payload):
    """Verify various whitespace configurations are rejected with 422."""
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": whitespace_payload})
    assert resp.status_code == 422
    assert "cannot be empty or contain only whitespace" in resp.text


def test_trimmed_length_boundary_validation(test_client):
    """Verify boundary checks are performed on trimmed content, not raw padded spaces."""
    # 25 leading/trailing spaces + 19 actual characters = 69 raw chars, but trimmed is 19
    padded_short = " " * 25 + ("B" * 19) + " " * 25
    resp1 = test_client.post("/api/v1/analyze/job-text", json={"text": padded_short})
    assert resp1.status_code == 422
    assert "too short" in resp1.text

    # 10 leading/trailing spaces + 20 actual characters = trimmed is 20
    padded_valid = " " * 10 + ("C" * 20) + " " * 10
    resp2 = test_client.post("/api/v1/analyze/job-text", json={"text": padded_valid})
    assert resp2.status_code == 200


def test_unicode_multibyte_and_special_characters_accepted(test_client):
    """Verify multi-byte UTF-8 (emojis, Devnagari, CJK, accents) is handled safely."""
    unicode_job = """
    नमस्ते! 🚀 Senior AI Engineer (कृत्रिम बुद्धिमत्ता) needed in Tokyo / 東京.
    Requirements: Python, PyTorch, LLMs, Transformer architectures.
    Competitive salary ¥12,000,000 - ¥15,000,000 per annum with health insurance.
    Apply via our official careers portal at https://careers.tokyo-ai.example.com.
    """
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": unicode_job})
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_id"] is not None
    assert data["risk_category"] in ("LOW", "MODERATE")


def test_validation_errors_redact_raw_input(test_client):
    """Verify strict privacy: invalid input string is NEVER echoed back in 422 responses."""
    secret_canary = "SUPER_SECRET_PAYLOAD_TOKEN_DO_NOT_LEAK_98765"
    resp = test_client.post("/api/v1/analyze/job-text", json={"text": secret_canary[:15]})
    assert resp.status_code == 422
    assert secret_canary[:15] not in resp.text
    assert "[REDACTED" in resp.text
