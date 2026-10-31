"""API tests for /api/v1/listings endpoints."""

import pytest
from starlette.testclient import TestClient
from app.main import app

client = TestClient(app)

SAMPLE_JOB_TEXT = """
Position: Senior Cloud DevOps Engineer
Company: Tata Consultancy Services Limited
Location: Mumbai, India

Job Description:
We are hiring a Senior Cloud DevOps Engineer to scale enterprise cloud infrastructure.
You will manage Terraform templates, configure AWS / Azure VPCs, and automate deployments
using GitLab CI/CD pipelines. Experience with Kubernetes cluster operations is required.

Requirements:
- 5+ years of DevOps engineering experience.
- Strong proficiency with Terraform, Docker, and Kubernetes.
- In-depth experience with AWS or Azure cloud architectures.
- Experience with Prometheus and Grafana monitoring stacks.
"""

COPYCAT_JOB_TEXT = SAMPLE_JOB_TEXT  # Identical text under a suspicious unverified employer


def test_register_or_analyze_job_listing(test_client):
    res = test_client.post(
        "/api/v1/listings/register-or-analyze",
        json={
            "job_title": "Senior Cloud DevOps Engineer",
            "job_description": SAMPLE_JOB_TEXT,
            "claimed_company_name": "Tata Consultancy Services Limited",
            "source_url": "https://careers.tcs.com/jobs/devops-101?utm_source=linkedin&ref=search",
            "job_location": "Mumbai, India",
            "employment_type": "Full-time",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["id"] is not None
    assert data["content_hash"] is not None
    # Check tracking parameters were stripped from normalized URL
    assert "utm_source" not in data["normalized_url"]
    assert "ref" not in data["normalized_url"]
    assert data["source_domain"] in ("careers.tcs.com", "tcs.com")
    assert data["duplicate_analysis"] is not None

    listing_id = data["id"]

    # Test GET /api/v1/listings/{listing_id}
    get_res = test_client.get(f"/api/v1/listings/{listing_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == listing_id

    # Test GET /api/v1/listings/{listing_id}/similar
    sim_res = test_client.get(f"/api/v1/listings/{listing_id}/similar")
    assert sim_res.status_code == 200
    sim_data = sim_res.json()
    assert "status" in sim_data
    assert "total_matches_found" in sim_data

    # Now register a second listing with conflicting company identity (impersonation copy)
    imposter_res = test_client.post(
        "/api/v1/listings/register-or-analyze",
        json={
            "job_title": "Senior Cloud DevOps Engineer",
            "job_description": COPYCAT_JOB_TEXT,
            "claimed_company_name": "Acme Global Placements Ltd",
            "source_url": "https://acme-placements.example.org/apply/devops-job",
        },
    )
    assert imposter_res.status_code == 201
    imposter_data = imposter_res.json()
    assert imposter_data["duplicate_analysis"] is not None
    assert imposter_data["duplicate_analysis"]["status"] == "POTENTIAL_SUSPICIOUS_COPY"
    assert imposter_data["duplicate_analysis"]["total_matches_found"] >= 1
    assert imposter_data["duplicate_analysis"]["impersonation_warning"] is not None


def test_check_duplicate_ad_hoc(test_client):
    # Register the initial listing first
    test_client.post(
        "/api/v1/listings/register-or-analyze",
        json={
            "job_title": "Senior Cloud DevOps Engineer",
            "job_description": SAMPLE_JOB_TEXT,
            "claimed_company_name": "Tata Consultancy Services Limited",
            "source_url": "https://careers.tcs.com/jobs/devops-101",
        },
    )
    res = test_client.post(
        "/api/v1/listings/check-duplicate",
        json={
            "text": SAMPLE_JOB_TEXT,
            "company_name": "Tata Consultancy Services Limited",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "total_matches_found" in data
    assert data["highest_similarity_score"] >= 0.95


def test_get_nonexistent_listing_returns_404(test_client):
    res = test_client.get("/api/v1/listings/nonexistent-uuid-999")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()
