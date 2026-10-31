"""Tests for F8 & F9: Community Feedback, Moderation & Company Reputation.

Verifies:
1. Migration schema: user_reviews, recruiter_reports, review_moderation, training_labels.
2. Bayesian reputation formula:
   - R = (n / (n + m)) * r_bar + (m / (n + m)) * C
   - Zero ratings: R = C, raw_mean = None, confidence = 0.0
   - Small n: damped towards C
   - Large n: approaches empirical mean r_bar
   - Excludes pending, rejected, and duplicate reviews
3. Fraud allegations separation:
   - Recruiter reports are kept strictly separate from star ratings
   - Never converted into stars or fraud probability
4. Abuse prevention:
   - Rate limiting per submitter hash
   - Burst limit protection
   - Deduplication via content hash
   - Submitter IP privacy hashing (raw IP never stored)
5. Sensitive data rejection:
   - Blocks submissions containing passwords, OTPs, financial details
6. Training data isolation (Critical Mandate):
   - Reviews and reports NEVER create or modify training_labels
   - Training labels only created through explicit authorized curator endpoints
   - Unauthorized attempts return 403 Forbidden
7. Full API workflow:
   - Reviews submission and listing
   - Fraud report submission and listing
   - Sourced Bayesian reputation retrieval
   - Moderation decision and appeals
"""

import hashlib
import uuid
import pytest
from sqlalchemy import inspect
from starlette.testclient import TestClient

from app.core.config import settings
from app.models.community import (
    RecruiterReport,
    ReviewModeration,
    TrainingLabel,
    UserReview,
)
from app.models.company import Company
from app.services.rate_limiter import (
    SlidingWindowRateLimiter,
    community_rate_limiter,
    compute_report_content_hash,
    compute_review_content_hash,
    hash_submitter,
)
from app.services.reputation_service import calculate_bayesian_reputation, get_company_reputation


# ==============================================================================
# 1. Database Schema & Migration Verification
# ==============================================================================
def test_community_database_schema(test_engine):
    """Verifies that all F8/F9 tables and columns exist in the database schema."""
    inspector = inspect(test_engine)
    table_names = inspector.get_table_names()

    assert "user_reviews" in table_names
    assert "recruiter_reports" in table_names
    assert "review_moderation" in table_names
    assert "training_labels" in table_names

    # Check user_reviews columns
    review_cols = {col["name"] for col in inspector.get_columns("user_reviews")}
    assert {"id", "company_id", "rating", "experience_category", "review_text", "moderation_status", "submitter_hash", "content_hash"}.issubset(review_cols)

    # Check recruiter_reports columns
    report_cols = {col["name"] for col in inspector.get_columns("recruiter_reports")}
    assert {"id", "company_id", "report_type", "description", "evidence_summary", "moderation_status", "submitter_hash", "content_hash"}.issubset(report_cols)

    # Check training_labels columns
    label_cols = {col["name"] for col in inspector.get_columns("training_labels")}
    assert {"id", "label", "label_source", "validation_status", "reviewed_by", "evidence_reference"}.issubset(label_cols)


# ==============================================================================
# 2. Bayesian Reputation Mathematics Verification
# ==============================================================================
def test_bayesian_reputation_math_zero_reviews():
    """When n = 0, reputation equals prior C (3.5) and confidence is 0.0."""
    result = calculate_bayesian_reputation([], prior_m=5.0, prior_c=3.5)
    assert result["total_approved_reviews"] == 0
    assert result["raw_mean_rating"] is None
    assert result["bayesian_rating"] == 3.5
    assert result["confidence_score"] == 0.0


def test_bayesian_reputation_math_damping_effect():
    """Tests the dampening effect on small review counts vs large review counts."""
    m = 5.0
    c = 3.5

    # Case 1: Single 5-star review (n=1, r_bar=5.0)
    # R = (1/(1+5))*5.0 + (5/(1+5))*3.5 = (5.0 + 17.5)/6 = 22.5/6 = 3.75
    res1 = calculate_bayesian_reputation([5], prior_m=m, prior_c=c)
    assert res1["total_approved_reviews"] == 1
    assert res1["raw_mean_rating"] == 5.0
    assert res1["bayesian_rating"] == 3.75
    assert res1["confidence_score"] == round(1.0 / 6.0, 4)

    # Case 2: 100 5-star reviews (n=100, r_bar=5.0)
    # R = (100/105)*5.0 + (5/105)*3.5 = (500 + 17.5)/105 = 517.5/105 = 4.93
    res100 = calculate_bayesian_reputation([5] * 100, prior_m=m, prior_c=c)
    assert res100["total_approved_reviews"] == 100
    assert res100["bayesian_rating"] == 4.93
    assert res100["confidence_score"] == round(100.0 / 105.0, 4)

    # Case 3: Single 1-star review (n=1, r_bar=1.0)
    # R = (1/6)*1.0 + (5/6)*3.5 = (1.0 + 17.5)/6 = 18.5/6 = 3.08
    res_low = calculate_bayesian_reputation([1], prior_m=m, prior_c=c)
    assert res_low["bayesian_rating"] == 3.08


def test_bayesian_reputation_invalid_parameters():
    """Validates boundary conditions on prior parameters."""
    with pytest.raises(ValueError, match="Prior strength m must be positive"):
        calculate_bayesian_reputation([5], prior_m=0.0)

    with pytest.raises(ValueError, match="Prior mean C must be between 1.0 and 5.0"):
        calculate_bayesian_reputation([5], prior_c=6.0)


# ==============================================================================
# 3. Abuse Prevention, Rate Limiting & Hashing
# ==============================================================================
def test_sliding_window_rate_limiter():
    """Verifies that sliding window limiter enforces request limits and burst limits."""
    limiter = SlidingWindowRateLimiter(max_requests=4, window_seconds=60, burst_limit=2, burst_seconds=5)
    key = "test_user_key"

    # Request 1: allowed
    allowed, err = limiter.check_and_record(key)
    assert allowed is True
    assert err is None

    # Request 2: allowed
    allowed, err = limiter.check_and_record(key)
    assert allowed is True

    # Request 3 within burst window (5s): burst blocked!
    allowed, err = limiter.check_and_record(key)
    assert allowed is False
    assert "Burst rate limit exceeded" in err


def test_submitter_privacy_hashing():
    """Verifies that submitter IP is hashed deterministically with salt, never stored raw."""
    ip = "192.168.1.100"
    salt = "test-salt-secret"
    h1 = hash_submitter(ip, salt=salt)
    h2 = hash_submitter(ip, salt=salt)

    assert h1 == h2
    assert len(h1) == 64
    assert ip not in h1


def test_content_hashing_deduplication():
    """Verifies that content hash changes with target, rating, category, and text."""
    h1 = compute_review_content_hash("Company A", 5, "interview_process", "Great experience!")
    h2 = compute_review_content_hash("company a", 5, "interview_process", "Great experience!")
    # Normalized whitespace and casing produces identical hash
    assert h1 == h2

    # Different rating produces different hash
    h3 = compute_review_content_hash("Company A", 4, "interview_process", "Great experience!")
    assert h1 != h3


# ==============================================================================
# 4. Training Data Isolation (Critical Mandate)
# ==============================================================================
def test_community_submissions_never_create_training_labels(test_client, db_session):
    """CRITICAL SAFETY TEST: Community reviews and fraud reports must NEVER create or alter training_labels."""
    # Count existing training labels
    initial_labels_count = db_session.query(TrainingLabel).count()

    # Reset rate limiter
    community_rate_limiter.reset_for_test()

    # 1. Submit a user review
    review_res = test_client.post(
        "/api/v1/reviews",
        json={
            "company_name": "Acme Innovations Ltd",
            "rating": 5,
            "category": "interview_process",
            "review_text": "A smooth interview process with technical interviewers.",
        },
    )
    assert review_res.status_code == 201

    # 2. Submit a fraud report
    report_res = test_client.post(
        "/api/v1/reports",
        json={
            "company_name": "Acme Innovations Ltd",
            "report_type": "fee_demand",
            "details": "They asked for 5000 rupees security deposit before releasing the offer letter.",
            "evidence_summary": "Email from hr-fake@acme-careers.net with UPI payment QR.",
        },
    )
    assert report_res.status_code == 201

    # Check training_labels table: MUST REMAIN UNCHANGED
    post_count = db_session.query(TrainingLabel).count()
    assert post_count == initial_labels_count, "Community feedback must NEVER automatically create training labels!"


def test_training_label_requires_authorized_credentials(test_client, db_session):
    """Verifies that training labels can only be created via authorized curator endpoint."""
    # Attempt without moderator key -> 403 Forbidden
    res_unauth = test_client.post(
        "/api/v1/moderation/training-labels",
        json={
            "label": "FRAUDULENT",
            "label_source": "EXPERT_CURATION",
            "reviewed_by": "curator_alice",
            "evidence_reference": "Explicit advance-fee fraud scheme detected in clause 4.",
            "validation_notes": "Curated manually from sample corpus.",
        },
    )
    assert res_unauth.status_code == 403

    # Authorized submission -> 201 Created
    res_auth = test_client.post(
        "/api/v1/moderation/training-labels",
        headers={"X-Moderator-Key": settings.MODERATOR_SECRET_KEY},
        json={
            "label": "FRAUDULENT",
            "label_source": "EXPERT_CURATION",
            "reviewed_by": "curator_alice",
            "evidence_reference": "Explicit advance-fee fraud scheme detected in clause 4.",
            "validation_notes": "Curated manually from sample corpus.",
        },
    )
    assert res_auth.status_code == 201
    label_data = res_auth.json()
    assert label_data["label"] == "FRAUDULENT"
    assert label_data["validation_status"] == "APPROVED"
    assert label_data["is_active_for_training"] is True


# ==============================================================================
# 5. Sensitive Data Rejection
# ==============================================================================
def test_sensitive_data_check_rejects_credentials(test_client):
    """Submissions containing passwords, OTPs, or bank details are strictly rejected."""
    community_rate_limiter.reset_for_test()

    res = test_client.post(
        "/api/v1/reviews",
        json={
            "company_name": "Tech Corp",
            "rating": 3,
            "category": "communication",
            "review_text": "They told me my one-time password OTP is 493021.",
        },
    )
    assert res.status_code == 422  # Pydantic validation error


# ==============================================================================
# 6. Full Reputation & Query API Workflow
# ==============================================================================
def test_company_reputation_api_flow(test_client, db_session):
    """End-to-end test of company creation, multiple reviews, fraud report, and reputation calculation."""
    community_rate_limiter.reset_for_test()

    # 1. Create a test company in DB
    test_company = Company(
        legal_name="Apex Global Technologies Limited",
        normalized_name="apex global technologies limited",
        cin="U72200MH2020PTC123456",
        registry_status="Active",
    )
    db_session.add(test_company)
    db_session.commit()
    db_session.refresh(test_company)
    comp_id = test_company.id

    # 2. Add approved reviews directly or via API
    r1 = UserReview(
        id=str(uuid.uuid4()),
        company_id=comp_id,
        rating=5,
        experience_category="interview_process",
        review_text="Very professional interviewers.",
        moderation_status="APPROVED",
        submitter_hash=hash_submitter("1.1.1.1"),
        content_hash="test-content-hash-1",
    )
    r2 = UserReview(
        id=str(uuid.uuid4()),
        company_id=comp_id,
        rating=4,
        experience_category="offer_clarity",
        review_text="Clear salary breakdown and benefits.",
        moderation_status="APPROVED",
        submitter_hash=hash_submitter("2.2.2.2"),
        content_hash="test-content-hash-2",
    )
    # Add a pending review (must be EXCLUDED from n and reputation)
    r3 = UserReview(
        id=str(uuid.uuid4()),
        company_id=comp_id,
        rating=1,
        experience_category="communication",
        review_text="Pending review text.",
        moderation_status="PENDING",
        submitter_hash=hash_submitter("3.3.3.3"),
        content_hash="test-content-hash-3",
    )
    # Add a rejected review (must be EXCLUDED)
    r4 = UserReview(
        id=str(uuid.uuid4()),
        company_id=comp_id,
        rating=1,
        experience_category="communication",
        review_text="Rejected review text.",
        moderation_status="REJECTED",
        submitter_hash=hash_submitter("4.4.4.4"),
        content_hash="test-content-hash-4",
    )
    db_session.add_all([r1, r2, r3, r4])

    # 3. Add a fraud report (MUST NOT affect star ratings)
    rep1 = RecruiterReport(
        id=str(uuid.uuid4()),
        company_id=comp_id,
        report_type="fake_offer",
        description="Received an offer letter with fake salary promise from spoofed email.",
        evidence_summary="Attached PDF offer scan.",
        moderation_status="PENDING",
        submitter_hash=hash_submitter("5.5.5.5"),
        content_hash="test-content-hash-report",
    )
    db_session.add(rep1)
    db_session.commit()

    # 4. Fetch Company Reputation
    rep_res = test_client.get(f"/api/v1/companies/{comp_id}/reputation")
    assert rep_res.status_code == 200
    data = rep_res.json()

    # Verify counts: only r1 and r2 are approved
    assert data["company_id"] == comp_id
    assert data["total_approved_reviews"] == 2
    assert data["raw_mean_rating"] == 4.5  # (5 + 4) / 2 = 4.5

    # Bayesian rating: (2 * 4.5 + 5.0 * 3.5) / (2 + 5.0) = (9.0 + 17.5) / 7 = 26.5 / 7 = 3.79
    assert data["bayesian_rating"] == 3.79
    assert data["confidence_score"] == round(2.0 / 7.0, 4)
    assert data["rating_distribution"]["5"] == 1
    assert data["rating_distribution"]["4"] == 1
    assert data["rating_distribution"]["1"] == 0  # 1-star reviews were pending or rejected

    # Verify fraud reports are kept completely distinct
    assert data["fraud_reports_count"] == 1
    assert data["fraud_reports_by_type"] == {"fake_offer": 1}

    # 5. Test Moderation Decision Endpoint
    mod_res = test_client.post(
        "/api/v1/moderation/decisions",
        headers={"X-Moderator-Key": settings.MODERATOR_SECRET_KEY},
        json={
            "target_type": "review",
            "target_id": r3.id,
            "action": "APPROVE",
            "moderator_id": "mod_sarah",
            "reason": "Verified legitimate applicant feedback.",
        },
    )
    assert mod_res.status_code == 200
    assert mod_res.json()["new_status"] == "APPROVED"

    # Now r3 is approved! Re-fetch reputation: n should become 3
    rep_res2 = test_client.get(f"/api/v1/companies/{comp_id}/reputation")
    assert rep_res2.status_code == 200
    data2 = rep_res2.json()
    assert data2["total_approved_reviews"] == 3
    # ratings: 5, 4, 1 -> mean = 10 / 3 = 3.33
    # bayesian = (3 * 3.333 + 5 * 3.5) / 8 = (10 + 17.5) / 8 = 27.5 / 8 = 3.44
    assert data2["raw_mean_rating"] == 3.33
    assert data2["bayesian_rating"] == 3.44
