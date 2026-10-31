"""Tests for Feature F5: Duplicate Job Detection and Impersonation Signals.

Validates all 12 required test conditions:
1. Identical normalized job descriptions
2. Known near-duplicate descriptions
3. Different jobs with similar boilerplate
4. Legitimate reposts from the same employer
5. Legitimate syndicated listings across job boards
6. Similar descriptions published under conflicting company identities
7. Lookalike domains and recruiter-domain mismatches
8. Missing descriptions and incomplete source data
9. Duplicate-pair uniqueness and database persistence (listing_id_a < listing_id_b)
10. Migration upgrade and rollback for 0005
11. Evidence provenance and confidence semantics
12. Confirmation that duplicate detection alone never classifies a listing as fraud
"""

from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app.main import app
from app.models.company import Company
from app.models.job import JobListing, JobSimilarityMatch
from app.services.duplicate_detector import (
    classify_duplicate_pair,
    compute_content_hash,
    compute_tfidf_similarity,
    find_and_record_similarity_matches,
    normalize_job_text,
    normalize_job_url,
)

client = TestClient(app)


# Sample vacancy texts
BASE_ENGINEER_TEXT = """
Position: Senior Backend Engineer (Python / FastAPI)
Company: Infosys Limited
Location: Bangalore, India
Employment Type: Full-time

Job Description:
We are looking for a Senior Backend Engineer to join our cloud architecture team.
You will be responsible for building high-throughput microservices using FastAPI,
optimizing PostgreSQL queries, and deploying containerized applications on Kubernetes.
You will collaborate with cross-functional teams to design scalable distributed systems.

Requirements:
- 5+ years of software development experience with Python.
- Strong knowledge of FastAPI, SQLAlchemy, and asynchronous programming.
- Experience with PostgreSQL database tuning and indexing.
- Familiarity with Docker, Kubernetes, and CI/CD pipelines.

Benefits:
- Competitive salary and health insurance coverage.
- Annual performance bonus and retirement benefits.
"""

# Identical text with altered whitespace, smart quotes, and dashes
IDENTICAL_FORMATTED_TEXT = """
Position: Senior Backend Engineer (Python / FastAPI)
Company: Infosys Limited
Location: Bangalore, India
Employment Type: Full-time

Job Description:
We  are   looking  for  a  Senior Backend  Engineer  to join our cloud architecture team.
You will be responsible for building high-throughput microservices using FastAPI,
optimizing PostgreSQL queries, and deploying containerized applications on Kubernetes.
You will collaborate with cross-functional teams to design scalable distributed systems.

Requirements:
• 5+ years of software development experience with Python.
• Strong knowledge of “FastAPI”, ‘SQLAlchemy’, and asynchronous programming.
• Experience with PostgreSQL database tuning and indexing.
• Familiarity with Docker, Kubernetes, and CI/CD pipelines.

Benefits:
- Competitive salary and health insurance coverage.
— Annual performance bonus and retirement benefits.
"""

# Near duplicate with minor location and salary adjustments
NEAR_DUPLICATE_TEXT = """
Position: Senior Backend Engineer (Python / FastAPI)
Company: Infosys Limited
Location: Hyderabad, India (Hybrid)
Employment Type: Full-time

Job Description:
We are looking for a Senior Backend Engineer to join our growing engineering team in Hyderabad.
You will be responsible for building high-throughput microservices using FastAPI,
optimizing PostgreSQL queries, and deploying containerized services on Kubernetes.
You will collaborate with global teams to design scalable distributed systems.

Requirements:
- 5+ years of software development experience with Python.
- Strong knowledge of FastAPI, SQLAlchemy, and asynchronous programming.
- Experience with PostgreSQL database tuning, replication, and indexing.
- Familiarity with Docker, Kubernetes, and AWS cloud deployment.

Benefits:
- Competitive compensation package and comprehensive health benefits.
- Annual performance bonus and hybrid work flexibility.
"""

# Completely different role sharing standard corporate boilerplate
DIFFERENT_JOB_SAME_BOILERPLATE = """
Position: Senior Graphic Designer & UI Illustrator
Company: Infosys Limited
Location: Pune, India
Employment Type: Full-time

Job Description:
We are seeking a talented Senior Graphic Designer to create captivating visual designs,
marketing assets, brand identities, and digital illustrations for our enterprise software suite.
You will collaborate with product managers and marketing teams to establish design systems.

Requirements:
- 5+ years of digital graphic design and brand illustration experience.
- Mastery of Figma, Adobe Illustrator, Photoshop, and After Effects.
- Proven portfolio demonstrating creative typography, color theory, and vector arts.

Benefits:
- Competitive salary and health insurance coverage.
- Annual performance bonus and retirement benefits.
"""


# -----------------------------------------------------------------------------
# 1. Identical normalized job descriptions
# -----------------------------------------------------------------------------
def test_1_identical_normalized_job_descriptions():
    norm_base = normalize_job_text(BASE_ENGINEER_TEXT)
    norm_formatted = normalize_job_text(IDENTICAL_FORMATTED_TEXT)

    assert norm_base == norm_formatted
    hash_base = compute_content_hash(BASE_ENGINEER_TEXT)
    hash_formatted = compute_content_hash(IDENTICAL_FORMATTED_TEXT)
    assert hash_base == hash_formatted

    sim = compute_tfidf_similarity(BASE_ENGINEER_TEXT, IDENTICAL_FORMATTED_TEXT)
    assert sim == 1.0


# -----------------------------------------------------------------------------
# 2. Known near-duplicate descriptions
# -----------------------------------------------------------------------------
def test_2_known_near_duplicate_descriptions():
    sim = compute_tfidf_similarity(BASE_ENGINEER_TEXT, NEAR_DUPLICATE_TEXT)
    assert sim >= 0.80
    assert sim < 1.0

    listing_a = JobListing(
        id="listing-001",
        job_description=BASE_ENGINEER_TEXT,
        claimed_company_name="Infosys Limited",
        content_hash=compute_content_hash(BASE_ENGINEER_TEXT),
        source_domain="infosys.com",
        collected_at=datetime.now(timezone.utc),
    )
    listing_b = JobListing(
        id="listing-002",
        job_description=NEAR_DUPLICATE_TEXT,
        claimed_company_name="Infosys Limited",
        content_hash=compute_content_hash(NEAR_DUPLICATE_TEXT),
        source_domain="infosys.com",
        collected_at=datetime.now(timezone.utc),
    )

    eval_res = classify_duplicate_pair(listing_a, listing_b)
    assert eval_res["match_classification"] == "NEAR_DUPLICATE"
    assert eval_res["similarity_score"] >= 0.80
    assert eval_res["confidence"] >= 0.80


# -----------------------------------------------------------------------------
# 3. Different jobs with similar boilerplate
# -----------------------------------------------------------------------------
def test_3_different_jobs_with_similar_boilerplate():
    sim = compute_tfidf_similarity(BASE_ENGINEER_TEXT, DIFFERENT_JOB_SAME_BOILERPLATE)
    # Cosine similarity must remain low despite boilerplate sharing
    assert sim < 0.65

    listing_a = JobListing(
        id="listing-001",
        job_description=BASE_ENGINEER_TEXT,
        claimed_company_name="Infosys Limited",
        content_hash=compute_content_hash(BASE_ENGINEER_TEXT),
        collected_at=datetime.now(timezone.utc),
    )
    listing_diff = JobListing(
        id="listing-003",
        job_description=DIFFERENT_JOB_SAME_BOILERPLATE,
        claimed_company_name="Infosys Limited",
        content_hash=compute_content_hash(DIFFERENT_JOB_SAME_BOILERPLATE),
        collected_at=datetime.now(timezone.utc),
    )

    eval_res = classify_duplicate_pair(listing_a, listing_diff)
    assert eval_res["match_classification"] == "INSUFFICIENT_EVIDENCE"
    assert eval_res["similarity_score"] < 0.70


# -----------------------------------------------------------------------------
# 4. Legitimate reposts from the same employer
# -----------------------------------------------------------------------------
def test_4_legitimate_reposts_from_same_employer():
    past_date = datetime.now(timezone.utc) - timedelta(days=30)
    current_date = datetime.now(timezone.utc)

    listing_orig = JobListing(
        id="listing-repost-orig",
        job_description=BASE_ENGINEER_TEXT,
        claimed_company_name="Infosys Limited",
        content_hash=compute_content_hash(BASE_ENGINEER_TEXT),
        source_domain="careers.infosys.com",
        collected_at=past_date,
    )
    listing_repost = JobListing(
        id="listing-repost-new",
        job_description=BASE_ENGINEER_TEXT,
        claimed_company_name="Infosys Limited",
        content_hash=compute_content_hash(BASE_ENGINEER_TEXT),
        source_domain="careers.infosys.com",
        collected_at=current_date,
    )

    eval_res = classify_duplicate_pair(listing_orig, listing_repost)
    assert eval_res["match_classification"] == "LIKELY_REPOST"
    assert eval_res["confidence"] >= 0.85
    assert any("repost" in r.lower() for r in eval_res["reasons"])


# -----------------------------------------------------------------------------
# 5. Legitimate syndicated listings across job boards
# -----------------------------------------------------------------------------
def test_5_legitimate_syndicated_listings_across_job_boards():
    now = datetime.now(timezone.utc)
    listing_corporate = JobListing(
        id="listing-corp",
        job_description=BASE_ENGINEER_TEXT,
        claimed_company_name="Infosys Limited",
        content_hash=compute_content_hash(BASE_ENGINEER_TEXT),
        source_domain="infosys.com",
        collected_at=now,
    )
    listing_naukri = JobListing(
        id="listing-naukri",
        job_description=BASE_ENGINEER_TEXT,
        claimed_company_name="Infosys Limited",
        content_hash=compute_content_hash(BASE_ENGINEER_TEXT),
        source_domain="naukri.com",
        collected_at=now,
    )

    eval_res = classify_duplicate_pair(listing_corporate, listing_naukri)
    assert eval_res["match_classification"] == "EXACT_DUPLICATE"
    # Must NOT flag impersonation
    assert "LOOKALIKE_DOMAIN_DETECTED" not in eval_res["impersonation_signals"]
    assert "COMPANY_IDENTITY_CONFLICT" not in eval_res["impersonation_signals"]
    assert any("syndication" in c["summary"].lower() for c in eval_res["contradictory_evidence"])


# -----------------------------------------------------------------------------
# 6. Similar descriptions published under conflicting company identities
# -----------------------------------------------------------------------------
def test_6_similar_descriptions_under_conflicting_company_identities():
    listing_infosys = JobListing(
        id="listing-infy",
        job_description=BASE_ENGINEER_TEXT,
        claimed_company_name="Infosys Limited",
        content_hash=compute_content_hash(BASE_ENGINEER_TEXT),
        source_domain="infosys.com",
        collected_at=datetime.now(timezone.utc),
    )
    listing_imposter = JobListing(
        id="listing-imposter",
        job_description=BASE_ENGINEER_TEXT,
        claimed_company_name="Acme Cloud Dynamics Inc",  # Conflicting entity
        content_hash=compute_content_hash(BASE_ENGINEER_TEXT),
        source_domain="acmeclouddynamics.com",
        collected_at=datetime.now(timezone.utc),
    )

    eval_res = classify_duplicate_pair(listing_infosys, listing_imposter)
    assert eval_res["match_classification"] == "POTENTIAL_SUSPICIOUS_COPY"
    assert "COMPANY_IDENTITY_CONFLICT" in eval_res["impersonation_signals"]
    assert eval_res["confidence"] >= 0.85


# -----------------------------------------------------------------------------
# 7. Lookalike domains and recruiter-domain mismatches
# -----------------------------------------------------------------------------
def test_7_lookalike_domains_and_recruiter_domain_mismatches():
    listing_genuine = JobListing(
        id="listing-gen",
        job_description=BASE_ENGINEER_TEXT,
        claimed_company_name="Infosys Limited",
        content_hash=compute_content_hash(BASE_ENGINEER_TEXT),
        source_domain="infosys.com",
        collected_at=datetime.now(timezone.utc),
    )
    listing_lookalike = JobListing(
        id="listing-spoof",
        job_description=BASE_ENGINEER_TEXT,
        claimed_company_name="Infosys Limited",
        content_hash=compute_content_hash(BASE_ENGINEER_TEXT),
        source_domain="inf0sys-careers.com",  # Lookalike typo domain
        collected_at=datetime.now(timezone.utc),
    )

    eval_res = classify_duplicate_pair(listing_genuine, listing_lookalike)
    assert eval_res["match_classification"] == "POTENTIAL_SUSPICIOUS_COPY"
    assert "LOOKALIKE_DOMAIN_DETECTED" in eval_res["impersonation_signals"]
    assert eval_res["confidence"] >= 0.90


# -----------------------------------------------------------------------------
# 8. Missing descriptions and incomplete source data
# -----------------------------------------------------------------------------
def test_8_missing_descriptions_and_incomplete_source_data():
    empty_listing = JobListing(
        id="listing-empty",
        job_description="",
        content_hash=compute_content_hash(""),
    )
    short_snippet_listing = JobListing(
        id="listing-short",
        job_description="Hiring now! Immediate opening for developer. Apply fast.",
        content_hash=compute_content_hash("Hiring now! Immediate opening for developer. Apply fast."),
    )

    eval_res = classify_duplicate_pair(empty_listing, short_snippet_listing)
    assert eval_res["match_classification"] == "INSUFFICIENT_EVIDENCE"
    assert eval_res["confidence"] == 0.0


# -----------------------------------------------------------------------------
# 9. Duplicate-pair uniqueness and database persistence
# -----------------------------------------------------------------------------
def test_9_duplicate_pair_uniqueness_and_database_persistence(db_session: Session):
    # Register two listings
    listing_a = JobListing(
        id="dup-test-uuid-a",
        job_title="Software Architect",
        job_description=BASE_ENGINEER_TEXT,
        claimed_company_name="Infosys Limited",
        content_hash=compute_content_hash(BASE_ENGINEER_TEXT),
        source_domain="infosys.com",
    )
    listing_b = JobListing(
        id="dup-test-uuid-b",
        job_title="Lead Backend Engineer",
        job_description=NEAR_DUPLICATE_TEXT,
        claimed_company_name="Infosys Limited",
        content_hash=compute_content_hash(NEAR_DUPLICATE_TEXT),
        source_domain="infosys.com",
    )
    db_session.add_all([listing_a, listing_b])
    db_session.commit()

    # Find matches for listing A
    matches_a = find_and_record_similarity_matches(listing_a, db_session)
    assert len(matches_a) == 1

    # In database, ensure listing_id_a < listing_id_b constraint was satisfied
    db_match = db_session.query(JobSimilarityMatch).first()
    assert db_match is not None
    assert db_match.listing_id_a < db_match.listing_id_b
    assert db_match.listing_id_a == "dup-test-uuid-a"
    assert db_match.listing_id_b == "dup-test-uuid-b"

    # Now run matching for listing B: must update existing record without inserting duplicate reversed pair
    matches_b = find_and_record_similarity_matches(listing_b, db_session)
    total_db_matches = db_session.query(JobSimilarityMatch).count()
    assert total_db_matches == 1

    # Clean up
    db_session.delete(listing_a)
    db_session.delete(listing_b)
    db_session.commit()


# -----------------------------------------------------------------------------
# 10. Migration upgrade and rollback for 0005
# -----------------------------------------------------------------------------
def test_10_migration_upgrade_and_rollback_0005(test_db_url: str, test_engine):
    import argparse
    from alembic import command
    from alembic.config import Config

    inspector = inspect(test_engine)
    tables = set(inspector.get_table_names())
    assert "job_listings" in tables
    assert "job_similarity_matches" in tables

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.cmd_opts = argparse.Namespace(x=["url=" + test_db_url])

    # Downgrade to 0004_recruiter_email_scans
    command.downgrade(alembic_cfg, "0004_recruiter_email_scans")

    # Verify tables dropped
    inspector_down = inspect(test_engine)
    tables_down = set(inspector_down.get_table_names())
    assert "job_listings" not in tables_down
    assert "job_similarity_matches" not in tables_down
    assert "recruiter_email_scans" in tables_down

    # Re-upgrade to head
    command.upgrade(alembic_cfg, "head")

    inspector_up = inspect(test_engine)
    tables_up = set(inspector_up.get_table_names())
    assert "job_listings" in tables_up
    assert "job_similarity_matches" in tables_up


# -----------------------------------------------------------------------------
# 11. Evidence provenance and confidence semantics
# -----------------------------------------------------------------------------
def test_11_evidence_provenance_and_confidence_semantics():
    norm_url, domain = normalize_job_url(
        "https://www.linkedin.com/jobs/view/123456789/?ref=search&utm_source=email&utm_campaign=daily_job_alert"
    )
    # Tracking parameters removed, job ID preserved
    assert "utm_source" not in norm_url
    assert "utm_campaign" not in norm_url
    assert "ref" not in norm_url
    assert "linkedin.com/jobs/view/123456789" in norm_url
    assert domain == "linkedin.com"

    listing_a = JobListing(
        id="listing-prov-a",
        job_description=BASE_ENGINEER_TEXT,
        content_hash=compute_content_hash(BASE_ENGINEER_TEXT),
        source_domain="infosys.com",
        collected_at=datetime.now(timezone.utc),
    )
    listing_b = JobListing(
        id="listing-prov-b",
        job_description=IDENTICAL_FORMATTED_TEXT,
        content_hash=compute_content_hash(IDENTICAL_FORMATTED_TEXT),
        source_domain="infosys.com",
        collected_at=datetime.now(timezone.utc),
    )

    eval_res = classify_duplicate_pair(listing_a, listing_b)
    # Confidence is documented rule level, distinct from statistical probability
    assert 0.0 <= eval_res["confidence"] <= 1.0
    assert len(eval_res["supporting_evidence"]) > 0
    assert len(eval_res["reasons"]) > 0
    assert len(eval_res["recommended_next_steps"]) > 0


# -----------------------------------------------------------------------------
# 12. Confirmation that duplicate detection alone never classifies a listing as fraud
# -----------------------------------------------------------------------------
def test_12_duplicate_detection_alone_never_classifies_as_fraud(db_session: Session, test_client):
    # Create legitimate corporate listing
    listing_legit = JobListing(
        id="listing-fraud-test-1",
        job_title="Senior Python Backend Developer",
        job_description=BASE_ENGINEER_TEXT,
        claimed_company_name="Infosys Limited",
        content_hash=compute_content_hash(BASE_ENGINEER_TEXT),
        source_domain="infosys.com",
    )
    db_session.add(listing_legit)
    db_session.commit()

    # Analyze via API endpoint
    response = test_client.post(
        "/api/v1/analyze/job-text",
        json={
            "text": BASE_ENGINEER_TEXT,
            "company_name": "Infosys Limited",
        },
    )
    assert response.status_code == 200
    data = response.json()

    # Exact duplicate was identified in repository
    assert data["duplicate_analysis"] is not None
    assert data["duplicate_analysis"]["status"] == "EXACT_DUPLICATE"
    assert data["duplicate_analysis"]["total_matches_found"] >= 1

    # Verify duplicate did NOT force fraud category
    # Legitimate job posting must remain LOW risk
    assert data["risk_category"] == "LOW"
    assert data["risk_score"] < 30.0

    # Clean up
    db_session.delete(listing_legit)
    db_session.commit()
