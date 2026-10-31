"""Pytest configuration and shared fixtures for JobShield AI test suite."""

import os
import sys

# Prevent OpenBLAS / MKL memory allocation errors on Windows test environments
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import tempfile
from typing import Generator
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Ensure backend directory is in sys.path
backend_path = os.path.abspath("backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.config import settings


@pytest.fixture(scope="session")
def test_db_url() -> Generator[str, None, None]:
    """Creates an isolated temporary SQLite database URL for the test session."""
    env_test_url = os.getenv("TEST_DATABASE_URL")
    if env_test_url:
        yield env_test_url
    else:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
            tmp_path = tmp_file.name
        db_url = f"sqlite:///{tmp_path}"
        yield db_url
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@pytest.fixture(scope="session")
def test_engine(test_db_url: str):
    """Engine bound to the isolated test database."""
    engine = create_engine(
        test_db_url,
        connect_args={"check_same_thread": False} if "sqlite" in test_db_url else {},
    )
    yield engine
    engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def run_migrations_on_test_db(test_db_url: str, test_engine):
    """Applies alembic upgrade head on the fresh test database."""
    import argparse

    original_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.cmd_opts = argparse.Namespace(x=["url=" + test_db_url])

    command.upgrade(alembic_cfg, "head")
    yield
    try:
        command.downgrade(alembic_cfg, "base")
    except Exception:
        pass
    settings.DATABASE_URL = original_db_url


@pytest.fixture
def db_session(test_engine) -> Generator[Session, None, None]:
    """Yields an isolated transactional session for a test function."""
    connection = test_engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = TestingSessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()
    import gc
    gc.collect()


@pytest.fixture
def test_client(db_session) -> Generator:
    """Provides a TestClient with get_db overridden to use the isolated test db_session."""
    from starlette.testclient import TestClient
    from app.main import app
    from app.db.session import get_db

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_db, None)
    import gc
    gc.collect()
