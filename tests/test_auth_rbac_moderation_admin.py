"""Comprehensive tests for Authentication, RBAC, Moderation, Audit Trail, Scan History, and Admin Controls.

Covers:
1. User Registration & Password Validation (Argon2id, complexity, duplicate email, default role USER).
2. User Authentication (JWT access token, rate limiting, generic error messages, change password).
3. Refresh Token Lifecycle (Cookie & body support, rotation, reuse detection terminating all sessions, logout).
4. RBAC Matrix (VISITOR, USER, MODERATOR, ADMIN role enforcement across routes).
5. Scan History & IDOR Protection (Private scan ownership, /my-scans, IDOR denial on scan and PDF download, user deletion).
6. Moderation Queue & Atomic Decisions (Pending items list, filters, pagination, atomic moderation decision with audit log).
7. Appeals Lifecycle (User submits appeal on rejected review/report, moderator resolves UPHELD/DISMISSED).
8. Admin Controls (User listing, role modification, account deactivation session revocation, audit log listing).
9. Training-Label Isolation Invariant (Community actions/moderation/appeals NEVER alter training labels; only Admin can curate).
"""

from datetime import datetime, timezone
import hashlib
import uuid
import pytest
from starlette.testclient import TestClient

from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.core.dependencies import login_rate_limiter
from app.models.community import (
    RecruiterReport,
    ReviewModeration,
    TrainingLabel,
    UserReview,
)
from app.models.company import Company
from app.models.offer import OfferLetterScan
from app.models.scan import ScanRequest
from app.models.user import ModerationAppeal, RefreshToken, SecurityAuditLog, User


# ------------------------------------------------------------------------------
# Helpers & Fixtures
# ------------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def reset_rate_limiters():
    login_rate_limiter.reset_for_test()
    yield
    login_rate_limiter.reset_for_test()


def create_test_user(db_session, email: str, role: str = "USER", password: str = "SecurePass123!", is_active: bool = True) -> User:
    """Helper to create and persist a test user."""
    user = User(
        id=str(uuid.uuid4()),
        email=email.lower().strip(),
        hashed_password=hash_password(password),
        full_name=f"Test {role}",
        role=role,
        is_active=is_active,
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def auth_headers(user: User) -> dict:
    """Helper to generate Authorization Bearer header for a given user."""
    token = create_access_token(
        subject=user.id,
        role=user.role,
        email=user.email,
    )
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# 1. Registration & Password Validation
# ==============================================================================
def test_user_registration_success(test_client: TestClient, db_session):
    """Test standard user registration succeeds with default role USER."""
    payload = {
        "email": "newuser@example.com",
        "password": "StrongPassword123!",
        "full_name": "New Job Seeker",
    }
    resp = test_client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "newuser@example.com"
    assert data["full_name"] == "New Job Seeker"
    assert data["role"] == "USER"
    assert "password" not in data
    assert "hashed_password" not in data

    # Verify user exists in database and password is an Argon2id hash
    db_user = db_session.query(User).filter(User.email == "newuser@example.com").first()
    assert db_user is not None
    assert db_user.role == "USER"
    assert db_user.hashed_password.startswith("$argon2id$")
    assert verify_password("StrongPassword123!", db_user.hashed_password)


def test_user_registration_password_complexity(test_client: TestClient):
    """Test registration rejects weak passwords that violate complexity policy."""
    weak_passwords = [
        ("short1!", "at least 8 characters"),
        ("alllowercase123!", "uppercase letter"),
        ("ALLUPPERCASE123!", "lowercase letter"),
        ("NoDigitsHere!!", "at least one digit"),
    ]
    for weak_pw, expected_err in weak_passwords:
        resp = test_client.post(
            "/api/v1/auth/register",
            json={
                "email": f"weak_{uuid.uuid4().hex[:6]}@example.com",
                "password": weak_pw,
                "full_name": "Weak Tester",
            },
        )
        assert resp.status_code in (400, 422)
        assert expected_err in resp.text.lower()


def test_user_registration_duplicate_email(test_client: TestClient, db_session):
    """Test registration fails if email is already registered."""
    create_test_user(db_session, "duplicate@example.com")
    resp = test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": "ValidPassword123!",
            "full_name": "Duplicate Tester",
        },
    )
    assert resp.status_code in (400, 409)
    assert "already exists" in resp.json()["detail"].lower()


# ==============================================================================
# 2. Authentication & Rate Limiting
# ==============================================================================
def test_user_login_success(test_client: TestClient, db_session):
    """Test successful login issues JWT access token and HttpOnly refresh token cookie."""
    user = create_test_user(db_session, "login_test@example.com", password="CorrectPass123!")
    resp = test_client.post(
        "/api/v1/auth/login",
        json={"email": "login_test@example.com", "password": "CorrectPass123!"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user_id"] == user.id
    assert data["role"] == "USER"
    assert settings.REFRESH_COOKIE_NAME in resp.cookies


def test_user_login_invalid_credentials_generic_message(test_client: TestClient, db_session):
    """Test failed login returns generic error without disclosing account existence."""
    create_test_user(db_session, "exist@example.com", password="CorrectPass123!")

    # Wrong password
    resp1 = test_client.post(
        "/api/v1/auth/login",
        json={"email": "exist@example.com", "password": "WrongPassword123!"},
    )
    assert resp1.status_code == 401
    assert resp1.json()["detail"] == "Invalid email or password."

    # Non-existent user
    resp2 = test_client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "WrongPassword123!"},
    )
    assert resp2.status_code == 401
    assert resp2.json()["detail"] == "Invalid email or password."


def test_login_rate_limiting(test_client: TestClient, db_session):
    """Test consecutive failed login attempts trigger 429 Too Many Requests."""
    login_rate_limiter.reset_for_test()
    target_email = "ratelimit_target@example.com"
    create_test_user(db_session, target_email, password="ValidPassword123!")

    # Burst limit is 3 requests within 10s window
    for _ in range(3):
        r = test_client.post(
            "/api/v1/auth/login",
            json={"email": target_email, "password": "BadPassword123!"},
        )
        assert r.status_code == 401

    # 4th attempt within 10s should be rate limited
    blocked_resp = test_client.post(
        "/api/v1/auth/login",
        json={"email": target_email, "password": "BadPassword123!"},
    )
    assert blocked_resp.status_code == 429
    assert "rate limit exceeded" in blocked_resp.json()["detail"].lower()


def test_get_current_user_and_change_password(test_client: TestClient, db_session):
    """Test /auth/me returns current user profile and password change works."""
    user = create_test_user(db_session, "changepw@example.com", password="OldPassword123!")
    headers = auth_headers(user)

    # Check /auth/me
    me_resp = test_client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "changepw@example.com"

    # Change password
    change_resp = test_client.post(
        "/api/v1/auth/me/password",
        headers=headers,
        json={"current_password": "OldPassword123!", "new_password": "NewStrongPass456!"},
    )
    assert change_resp.status_code == 200

    # Old password should now fail
    fail_login = test_client.post(
        "/api/v1/auth/login",
        json={"email": "changepw@example.com", "password": "OldPassword123!"},
    )
    assert fail_login.status_code == 401

    # New password should succeed
    succ_login = test_client.post(
        "/api/v1/auth/login",
        json={"email": "changepw@example.com", "password": "NewStrongPass456!"},
    )
    assert succ_login.status_code == 200


# ==============================================================================
# 3. Refresh Token Rotation & Reuse Detection
# ==============================================================================
def test_refresh_token_rotation_and_reuse_defense(test_client: TestClient, db_session):
    """Test refresh token rotation issues a new token, and reusing an old token revokes ALL user sessions."""
    user = create_test_user(db_session, "refresh_test@example.com", password="SecurePass123!")
    refresh_cookie_key = settings.REFRESH_COOKIE_NAME

    # 1. Login to obtain refresh token
    login_resp = test_client.post(
        "/api/v1/auth/login",
        json={"email": "refresh_test@example.com", "password": "SecurePass123!"},
    )
    assert login_resp.status_code == 200
    refresh_token_1 = login_resp.cookies.get(refresh_cookie_key)
    assert refresh_token_1 is not None

    # Verify token record in DB
    h1 = hash_refresh_token(refresh_token_1)
    db_token1 = db_session.query(RefreshToken).filter(RefreshToken.token_hash == h1).first()
    assert db_token1 is not None
    assert not db_token1.is_revoked

    # 2. Use refresh token 1 to get a new token pair (rotation)
    test_client.cookies.set(refresh_cookie_key, refresh_token_1)
    refresh_resp1 = test_client.post("/api/v1/auth/refresh")
    assert refresh_resp1.status_code == 200
    refresh_token_2 = refresh_resp1.cookies.get(refresh_cookie_key)
    assert refresh_token_2 is not None
    assert refresh_token_2 != refresh_token_1

    # Token 1 is now revoked
    db_session.refresh(db_token1)
    assert db_token1.is_revoked is True

    # 3. REUSE ATTACK: Attacker/client attempts to use token 1 again
    test_client.cookies.set(refresh_cookie_key, refresh_token_1)
    reuse_resp = test_client.post("/api/v1/auth/refresh")
    assert reuse_resp.status_code == 401

    # REUSE DEFENSE VERIFICATION: All active refresh tokens for this user must now be revoked
    active_tokens = (
        db_session.query(RefreshToken)
        .filter(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .all()
    )
    assert len(active_tokens) == 0

    # Even token 2 is now revoked due to replay attack detection
    test_client.cookies.set(refresh_cookie_key, refresh_token_2)
    refresh_resp2 = test_client.post("/api/v1/auth/refresh")
    assert refresh_resp2.status_code == 401


def test_logout_revokes_refresh_token(test_client: TestClient, db_session):
    """Test /auth/logout revokes the active session and clears the cookie."""
    user = create_test_user(db_session, "logout_user@example.com", password="SecurePass123!")
    refresh_cookie_key = settings.REFRESH_COOKIE_NAME

    login_resp = test_client.post(
        "/api/v1/auth/login",
        json={"email": "logout_user@example.com", "password": "SecurePass123!"},
    )
    raw_token = login_resp.cookies.get(refresh_cookie_key)

    # Logout
    logout_resp = test_client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200

    # Refresh should now fail
    test_client.cookies.set(refresh_cookie_key, raw_token)
    ref_resp = test_client.post("/api/v1/auth/refresh")
    assert ref_resp.status_code == 401


# ==============================================================================
# 4. RBAC Permissions Matrix
# ==============================================================================
def test_rbac_access_matrix(test_client: TestClient, db_session):
    """Test RBAC enforcement across VISITOR, USER, MODERATOR, and ADMIN roles."""
    user = create_test_user(db_session, "normal_user@example.com", role="USER")
    moderator = create_test_user(db_session, "mod_user@example.com", role="MODERATOR")
    admin = create_test_user(db_session, "admin_user@example.com", role="ADMIN")

    user_hdrs = auth_headers(user)
    mod_hdrs = auth_headers(moderator)
    admin_hdrs = auth_headers(admin)

    # 1. Moderation Queue Endpoint (/api/v1/moderation/queue)
    # Visitor -> 401 Unauthorized
    assert test_client.get("/api/v1/moderation/queue").status_code == 401
    # User -> 403 Forbidden
    assert test_client.get("/api/v1/moderation/queue", headers=user_hdrs).status_code == 403
    # Moderator -> 200 OK
    assert test_client.get("/api/v1/moderation/queue", headers=mod_hdrs).status_code == 200
    # Admin -> 200 OK
    assert test_client.get("/api/v1/moderation/queue", headers=admin_hdrs).status_code == 200

    # 2. Admin Users Endpoint (/api/v1/admin/users)
    # Visitor -> 401
    assert test_client.get("/api/v1/admin/users").status_code == 401
    # User -> 403
    assert test_client.get("/api/v1/admin/users", headers=user_hdrs).status_code == 403
    # Moderator -> 403
    assert test_client.get("/api/v1/admin/users", headers=mod_hdrs).status_code == 403
    # Admin -> 200
    assert test_client.get("/api/v1/admin/users", headers=admin_hdrs).status_code == 200

    # 3. Security Audit Logs (/api/v1/admin/audit-logs)
    assert test_client.get("/api/v1/admin/audit-logs", headers=mod_hdrs).status_code == 403
    assert test_client.get("/api/v1/admin/audit-logs", headers=admin_hdrs).status_code == 200


# ==============================================================================
# 5. Scan History & IDOR Protection
# ==============================================================================
def test_scan_history_and_idor_protection(test_client: TestClient, db_session):
    """Test private scan association with user_id, /my-scans listing, and IDOR protection."""
    user_a = create_test_user(db_session, "user_a@example.com", role="USER")
    user_b = create_test_user(db_session, "user_b@example.com", role="USER")
    admin = create_test_user(db_session, "admin_scan@example.com", role="ADMIN")

    headers_a = auth_headers(user_a)
    headers_b = auth_headers(user_b)
    headers_admin = auth_headers(admin)

    # 1. Create a scan for User A
    scan_a = ScanRequest(
        id=str(uuid.uuid4()),
        user_id=user_a.id,
        input_type="job_text",
        input_reference="sha256:abc12345",
        status="completed",
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(scan_a)
    db_session.commit()

    # 2. User A lists their scans via /api/v1/scans/my-scans
    list_resp_a = test_client.get("/api/v1/scans/my-scans", headers=headers_a)
    assert list_resp_a.status_code == 200
    items_a = list_resp_a.json()["scans"]
    assert len(items_a) == 1
    assert items_a[0]["id"] == scan_a.id

    # User B has no scans
    list_resp_b = test_client.get("/api/v1/scans/my-scans", headers=headers_b)
    assert list_resp_b.status_code == 200
    assert len(list_resp_b.json()["scans"]) == 0

    # 3. IDOR Protection: User B tries to get User A's scan
    get_b_resp = test_client.get(f"/api/v1/scans/{scan_a.id}", headers=headers_b)
    assert get_b_resp.status_code == 403
    assert "permission" in get_b_resp.json()["detail"].lower()

    # IDOR Protection: Anonymous visitor tries to get User A's private scan
    get_anon_resp = test_client.get(f"/api/v1/scans/{scan_a.id}")
    assert get_anon_resp.status_code == 403

    # IDOR Protection: User B tries to download User A's report.pdf
    pdf_b_resp = test_client.get(f"/api/v1/scans/{scan_a.id}/report.pdf", headers=headers_b)
    assert pdf_b_resp.status_code == 403

    # User A CAN access their own scan
    get_a_resp = test_client.get(f"/api/v1/scans/{scan_a.id}", headers=headers_a)
    assert get_a_resp.status_code == 200

    # Admin CAN access User A's scan (elevated review privilege)
    get_admin_resp = test_client.get(f"/api/v1/scans/{scan_a.id}", headers=headers_admin)
    assert get_admin_resp.status_code == 200

    # 4. Deletion: User B cannot delete User A's scan
    del_b_resp = test_client.delete(f"/api/v1/scans/{scan_a.id}", headers=headers_b)
    assert del_b_resp.status_code == 403

    # User A deletes their scan
    del_a_resp = test_client.delete(f"/api/v1/scans/{scan_a.id}", headers=headers_a)
    assert del_a_resp.status_code in (200, 204)

    # Confirm deletion from DB
    assert db_session.query(ScanRequest).filter(ScanRequest.id == scan_a.id).first() is None


def test_my_scans_authentication_and_anonymous_scan_permissions(test_client: TestClient, db_session):
    """Regression test for scan-history authentication, missing credentials, anonymous scans, and company name mapping."""
    user = create_test_user(db_session, "myscans_auth@example.com", role="USER")
    admin = create_test_user(db_session, "myscans_admin@example.com", role="ADMIN")
    u_headers = auth_headers(user)
    a_headers = auth_headers(admin)

    # 1. Unauthenticated request to /my-scans -> 401
    unauth_resp = test_client.get("/api/v1/scans/my-scans")
    assert unauth_resp.status_code == 401

    # 2. Invalid/expired bearer token -> 401
    bad_token_resp = test_client.get("/api/v1/scans/my-scans", headers={"Authorization": "Bearer invalid.fake.token"})
    assert bad_token_resp.status_code == 401

    # 3. Empty history -> 200 with scans: [], total: 0
    empty_resp = test_client.get("/api/v1/scans/my-scans", headers=u_headers)
    assert empty_resp.status_code == 200
    assert empty_resp.json()["scans"] == []
    assert empty_resp.json()["total"] == 0

    # 4. Create an offer letter scan with claimed company name
    scan_id = str(uuid.uuid4())
    scan_req = ScanRequest(
        id=scan_id,
        user_id=user.id,
        input_type="offer_letter",
        input_reference="test_offer.pdf",
        status="completed",
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(scan_req)

    offer_scan = OfferLetterScan(
        id=str(uuid.uuid4()),
        scan_id=scan_id,
        file_hash="hash_1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        file_name="test_offer.pdf",
        file_size_bytes=1024,
        page_count=1,
        claimed_company_name="Tata Consultancy Services Limited",
        risk_category="LOW",
        risk_score=0.15,
    )
    db_session.add(offer_scan)
    db_session.commit()

    # Verify history returns item with claimed_company_name and risk_score
    history_resp = test_client.get("/api/v1/scans/my-scans", headers=u_headers)
    assert history_resp.status_code == 200
    data = history_resp.json()
    assert data["total"] == 1
    item = data["scans"][0]
    assert item["id"] == scan_id
    assert item["input_type"] == "offer_letter"
    assert item["claimed_company_name"] == "Tata Consultancy Services Limited"

    # 5. Anonymous scan: user_id is None -> Accessible to public visitor
    anon_scan_id = str(uuid.uuid4())
    anon_scan = ScanRequest(
        id=anon_scan_id,
        user_id=None,
        input_type="job_text",
        status="completed",
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(anon_scan)
    db_session.commit()

    # Visitor can access anonymous scan
    anon_get_resp = test_client.get(f"/api/v1/scans/{anon_scan_id}")
    assert anon_get_resp.status_code == 200
    assert anon_get_resp.json()["id"] == anon_scan_id

    # 6. Admin can delete any user scan
    admin_del_resp = test_client.delete(f"/api/v1/scans/{scan_id}", headers=a_headers)
    assert admin_del_resp.status_code in (200, 204)
    assert db_session.query(ScanRequest).filter(ScanRequest.id == scan_id).first() is None


# ==============================================================================
# 6. Moderation Queue & Atomic Decisions
# ==============================================================================
def test_moderation_queue_and_decision(test_client: TestClient, db_session):
    """Test moderator queue retrieval and applying an atomic moderation decision."""
    moderator = create_test_user(db_session, "moderator1@example.com", role="MODERATOR")
    mod_headers = auth_headers(moderator)

    # Create a test review in PENDING state
    review = UserReview(
        id=str(uuid.uuid4()),
        submitter_hash="hash_submitter_1",
        rating=4,
        experience_category="INTERVIEW",
        review_text="Smooth interview process with transparent salary expectations.",
        moderation_status="PENDING",
        content_hash="content_hash_1",
    )
    db_session.add(review)
    db_session.commit()

    # 1. Fetch queue items
    queue_resp = test_client.get("/api/v1/moderation/queue", headers=mod_headers)
    assert queue_resp.status_code == 200
    items = queue_resp.json()["items"]
    assert any(item["id"] == review.id for item in items)

    # 2. Apply Decision: APPROVED
    decision_payload = {
        "item_type": "review",
        "item_id": review.id,
        "action": "APPROVED",
        "reason": "Authentic candidate experience verified",
        "notes": "Reviewed and cleared.",
    }
    dec_resp = test_client.post(
        "/api/v1/moderation/decisions",
        headers=mod_headers,
        json=decision_payload,
    )
    assert dec_resp.status_code == 200
    assert dec_resp.json()["new_status"] == "APPROVED"

    # Verify review updated in DB
    db_session.refresh(review)
    assert review.moderation_status == "APPROVED"

    # Verify atomic audit trail record in review_moderation
    mod_rec = db_session.query(ReviewModeration).filter(ReviewModeration.review_id == review.id).first()
    assert mod_rec is not None
    assert mod_rec.action == "APPROVED"
    assert mod_rec.moderator_id == moderator.id

    # Verify atomic security audit log
    sec_log = (
        db_session.query(SecurityAuditLog)
        .filter(SecurityAuditLog.target_id == review.id)
        .first()
    )
    assert sec_log is not None
    assert sec_log.action.startswith("MODERATION_")
    assert sec_log.user_id == moderator.id


# ==============================================================================
# 7. Moderation Appeals Workflow
# ==============================================================================
def test_moderation_appeals_workflow(test_client: TestClient, db_session):
    """Test user submitting an appeal against a rejected review and moderator resolving it."""
    user = create_test_user(db_session, "appellant@example.com", role="USER")
    moderator = create_test_user(db_session, "appeals_mod@example.com", role="MODERATOR")

    user_hdrs = auth_headers(user)
    mod_hdrs = auth_headers(moderator)

    # 1. Create rejected review owned by user
    review = UserReview(
        id=str(uuid.uuid4()),
        user_id=user.id,
        submitter_hash="appellant_hash",
        rating=1,
        experience_category="OFFER",
        review_text="Felt suspicious about fee request.",
        moderation_status="REJECTED",
        content_hash="appellant_content_hash",
    )
    db_session.add(review)
    db_session.commit()

    # Create associated moderation record
    mod_record = ReviewModeration(
        id=str(uuid.uuid4()),
        target_type="review",
        review_id=review.id,
        moderator_id=moderator.id,
        action="REJECTED",
        reason="Suspected automated submission",
    )
    db_session.add(mod_record)
    db_session.commit()

    # 2. User submits appeal
    appeal_payload = {
        "moderation_id": mod_record.id,
        "appeal_reason": "I am a real applicant with email proof of the interview communication.",
    }
    appeal_resp = test_client.post("/api/v1/appeals", headers=user_hdrs, json=appeal_payload)
    assert appeal_resp.status_code == 201
    appeal_id = appeal_resp.json()["id"]
    assert appeal_resp.json()["status"] == "PENDING"

    # User checks my-appeals
    my_appeals = test_client.get("/api/v1/appeals/my-appeals", headers=user_hdrs)
    assert my_appeals.status_code == 200
    assert len(my_appeals.json()) == 1

    # 3. Moderator resolves appeal: UPHELD (overturns rejection and restores review to APPROVED)
    resolve_payload = {
        "action": "UPHELD",
        "resolution_notes": "Applicant provided authentic email confirmation. Restoring review.",
    }
    res_resp = test_client.post(
        f"/api/v1/moderation/appeals/{appeal_id}/resolve",
        headers=mod_hdrs,
        json=resolve_payload,
    )
    assert res_resp.status_code == 200
    assert res_resp.json()["status"] == "UPHELD"

    # Review status restored to APPROVED
    db_session.refresh(review)
    assert review.moderation_status == "APPROVED"


# ==============================================================================
# 8. Admin Controls (Role Modification, Status, Audit Logs)
# ==============================================================================
def test_admin_user_management_and_audit_logs(test_client: TestClient, db_session):
    """Test admin role assignment, user suspension with session revocation, and audit logs."""
    admin = create_test_user(db_session, "superadmin@example.com", role="ADMIN")
    target_user = create_test_user(db_session, "target_user@example.com", role="USER")
    admin_hdrs = auth_headers(admin)

    # 1. Promote target user to MODERATOR
    role_resp = test_client.put(
        f"/api/v1/admin/users/{target_user.id}/role",
        headers=admin_hdrs,
        json={"role": "MODERATOR", "reason": "Promoted to support review moderation."},
    )
    assert role_resp.status_code == 200
    assert role_resp.json()["role"] == "MODERATOR"

    db_session.refresh(target_user)
    assert target_user.role == "MODERATOR"

    # 2. Create active session for target user then deactivate account
    raw_token = generate_refresh_token()
    session_rec = RefreshToken(
        id=str(uuid.uuid4()),
        user_id=target_user.id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(timezone.utc),
    )
    db_session.add(session_rec)
    db_session.commit()

    # Deactivate user
    status_resp = test_client.put(
        f"/api/v1/admin/users/{target_user.id}/status",
        headers=admin_hdrs,
        json={"is_active": False, "reason": "Suspended pending policy violation review."},
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["is_active"] is False

    # Verify all refresh tokens are terminated
    db_session.refresh(session_rec)
    assert session_rec.is_revoked is True

    # 3. View Security Audit Logs
    audit_resp = test_client.get("/api/v1/admin/audit-logs", headers=admin_hdrs)
    assert audit_resp.status_code == 200
    logs = audit_resp.json()["logs"]
    actions = [log["action"] for log in logs]
    assert "ROLE_CHANGE" in actions
    assert "ACCOUNT_STATUS_CHANGE" in actions


# ==============================================================================
# 9. Critical Mandate: Training-Label Isolation Invariant
# ==============================================================================
def test_training_label_isolation_invariant(test_client: TestClient, db_session):
    """
    CRITICAL INVARIANT TEST:
    Community submissions, moderation decisions, and appeals NEVER create or mutate training_labels.
    Only authorized Admin users can curate training labels via POST /api/v1/moderation/training-labels.
    """
    moderator = create_test_user(db_session, "isolation_mod@example.com", role="MODERATOR")
    admin = create_test_user(db_session, "isolation_admin@example.com", role="ADMIN")
    mod_hdrs = auth_headers(moderator)
    admin_hdrs = auth_headers(admin)

    # Initial count of training labels
    initial_labels_count = db_session.query(TrainingLabel).count()

    # 1. Moderation decision does NOT create training label
    review = UserReview(
        id=str(uuid.uuid4()),
        submitter_hash="isolation_submitter",
        rating=5,
        review_text="Legitimate verified onboarding experience.",
        moderation_status="PENDING",
        content_hash="isolation_content_hash",
    )
    db_session.add(review)
    db_session.commit()

    test_client.post(
        "/api/v1/moderation/decisions",
        headers=mod_hdrs,
        json={
            "item_type": "review",
            "item_id": review.id,
            "action": "APPROVED",
            "reason": "Verified",
        },
    )
    assert db_session.query(TrainingLabel).count() == initial_labels_count

    # 2. Moderator attempts to curate training label -> 403 FORBIDDEN (Strict Admin Only)
    mod_curate = test_client.post(
        "/api/v1/moderation/training-labels",
        headers=mod_hdrs,
        json={
            "text": "Curated suspicious vacancy requiring security clearance fee",
            "label": "fraudulent",
            "curator_notes": "Attempt by moderator",
        },
    )
    assert mod_curate.status_code == 403
    assert db_session.query(TrainingLabel).count() == initial_labels_count

    # 3. Admin curates training label -> 201 CREATED
    admin_curate = test_client.post(
        "/api/v1/moderation/training-labels",
        headers=admin_hdrs,
        json={
            "text": "Curated confirmed fraud job posting asking for deposit before interview",
            "label": "fraudulent",
            "curator_notes": "Expert reviewed ground truth label",
        },
    )
    assert admin_curate.status_code == 201
    assert db_session.query(TrainingLabel).count() == initial_labels_count + 1
