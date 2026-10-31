import pytest
from starlette.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_liveness():
    """
    Test GET /health (liveness probe).
    Must return 200 OK with 'healthy' status.
    """
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["app"] == "JobShield AI"
    assert "environment" in payload


def test_health_readiness_does_not_expose_secrets():
    """
    Test GET /api/v1/health/ready (readiness probe).
    Must return dependency readiness without leaking database credentials or secrets.
    """
    response = client.get("/api/v1/health/ready")
    assert response.status_code in (200, 503)
    payload = response.json()
    assert "status" in payload
    assert payload["status"] in ("ready", "not_ready")
    assert "dependencies" in payload
    assert "database" in payload["dependencies"]

    # Explicitly verify no connection strings, passwords, or secrets are exposed
    raw_text = response.text.lower()
    for sensitive in ["password", "secret", "postgresql://", "postgresql+psycopg://"]:
        assert sensitive not in raw_text, f"Potential secret leak detected: '{sensitive}' in response"


def test_cors_headers_allowed_origin():
    """
    Test that CORS preflight request with an allowed origin returns the CORS header.
    """
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
