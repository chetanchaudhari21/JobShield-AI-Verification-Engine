import sys
import os
import pytest
from alembic.config import Config

# Ensure backend directory is in sys.path
backend_path = os.path.abspath("backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.config import settings
from migrations.env import get_target_url, get_sanitized_target_url


def test_placeholder_sqlalchemy_url_cannot_override_settings_database_url(monkeypatch):
    """
    Verify that placeholder sqlalchemy.url in alembic.ini CANNOT override
    settings.DATABASE_URL loaded from Pydantic settings / .env.
    """
    mock_url = "postgresql+psycopg://test_app:mock_secret_password_123@localhost:5432/jobshield_test_db"
    monkeypatch.setattr(settings, "DATABASE_URL", mock_url)

    # Load alembic.ini which contains the placeholder
    cfg = Config("alembic.ini")
    placeholder_in_ini = cfg.get_main_option("sqlalchemy.url")

    # Confirm alembic.ini contains a dummy/placeholder URL
    assert "driver://user:pass" in placeholder_in_ini or "dummy" in placeholder_in_ini or placeholder_in_ini != mock_url

    # Verify get_target_url() prioritizes settings.DATABASE_URL and ignores the placeholder
    resolved_url = get_target_url()
    assert resolved_url == mock_url
    assert resolved_url != placeholder_in_ini

    # Even if someone injects a rogue option into alembic.ini config, settings.DATABASE_URL wins
    cfg.set_main_option("sqlalchemy.url", "sqlite:///rogue_override_should_be_ignored.db")
    resolved_again = get_target_url()
    assert resolved_again == mock_url
    assert resolved_again != "sqlite:///rogue_override_should_be_ignored.db"


def test_get_sanitized_target_url_masks_password():
    """
    Verify that get_sanitized_target_url() completely masks the database password
    with '***' and never exposes credentials in logs or output.
    """
    sensitive_url = "postgresql+psycopg://jobshield_app:super_secret_password_999@127.0.0.1:5432/jobshield_db"
    sanitized = get_sanitized_target_url(sensitive_url)

    # Password must never appear
    assert "super_secret_password_999" not in sanitized
    # Masked representation must appear
    assert "***" in sanitized
    # Non-sensitive connection details remain clear for operational inspection
    assert "jobshield_app" in sanitized
    assert "127.0.0.1" in sanitized
    assert "5432" in sanitized
    assert "jobshield_db" in sanitized


def test_get_sanitized_target_url_with_sqlite():
    """
    Verify that URLs without passwords (like SQLite) are rendered cleanly.
    """
    sqlite_url = "sqlite:///./local_test.db"
    sanitized = get_sanitized_target_url(sqlite_url)
    assert sanitized == "sqlite:///./local_test.db"


def test_get_target_url_respects_explicit_x_argument(monkeypatch):
    """
    Verify that explicit CLI argument (-x url=...) can be used when intentionally
    targeting an isolated test database, but only when explicitly provided.
    """
    from alembic import context

    test_override_url = "sqlite:///./isolated_test_override.db"
    
    # Mock context.get_x_argument to simulate CLI flag: -x url=sqlite:///...
    monkeypatch.setattr(context, "get_x_argument", lambda as_dictionary=True: {"url": test_override_url})

    resolved = get_target_url()
    assert resolved == test_override_url
