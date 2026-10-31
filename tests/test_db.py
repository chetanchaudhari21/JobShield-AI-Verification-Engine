import os
import tempfile
import uuid
from typing import Generator
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker
from starlette.testclient import TestClient

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    DatasetImport,
    ModelVersion,
    PredictionHistory,
    ScanRequest,
    VerificationEvidence,
)



def test_alembic_tables_created(test_engine):
    """
    Verify that alembic upgrade head created all 5 MVP tables on the fresh database.
    """
    inspector = inspect(test_engine)
    table_names = set(inspector.get_table_names())
    expected_tables = {
        "scan_requests",
        "verification_evidence",
        "prediction_history",
        "model_versions",
        "dataset_imports",
    }
    assert expected_tables.issubset(table_names), f"Missing tables: {expected_tables - table_names}"


def test_scan_request_and_evidence_crud(db_session: Session):
    """
    Test creating, reading, and cascading relationships between
    ScanRequest, VerificationEvidence, and PredictionHistory.
    """
    scan = ScanRequest(
        id=str(uuid.uuid4()),
        input_type="job_text",
        input_reference="Software Engineer Job Description",
        status="completed",
    )
    db_session.add(scan)
    db_session.flush()

    evidence = VerificationEvidence(
        scan_id=scan.id,
        evidence_type="mca_registry",
        source_name="MCA Master Data",
        source_url="https://mcacdm.nic.in",
        status="MATCHED",
        confidence=0.95,
        summary="Company registration successfully verified.",
        raw_metadata={"cin": "U72200KA2020PTC123456", "status": "ACTIVE"},
    )
    prediction = PredictionHistory(
        scan_id=scan.id,
        model_version="baseline_tfidf_v1",
        predicted_class="LEGITIMATE",
        model_probability=0.08,
        risk_score=12.5,
        risk_category="LOW",
        threshold_version="v1.0",
        explanation={"top_signals": ["official_domain_match", "no_upfront_fee"]},
    )
    db_session.add_all([evidence, prediction])
    db_session.commit()

    # Query back
    fetched_scan = db_session.get(ScanRequest, scan.id)
    assert fetched_scan is not None
    assert fetched_scan.status == "completed"
    assert len(fetched_scan.evidence_records) == 1
    assert fetched_scan.evidence_records[0].source_name == "MCA Master Data"
    assert fetched_scan.evidence_records[0].raw_metadata["cin"] == "U72200KA2020PTC123456"

    assert len(fetched_scan.prediction_records) == 1
    assert fetched_scan.prediction_records[0].risk_category == "LOW"
    assert fetched_scan.prediction_records[0].explanation["top_signals"][0] == "official_domain_match"


def test_model_version_and_dataset_import_crud(db_session: Session):
    """
    Test ModelVersion and DatasetImport persistence with structured JSON metadata.
    """
    mv = ModelVersion(
        version="v1.0.0-rc1",
        artifact_path="/artifacts/models/baseline_tfidf.joblib",
        dataset_snapshot="emscad_cleaned_20261012",
        metrics={"f1": 0.91, "precision": 0.89, "recall": 0.93},
        calibration_summary={"brier_score": 0.045},
        evaluation_status="approved",
    )
    ds = DatasetImport(
        dataset_name="EMSCAD",
        version_or_snapshot="2026.10",
        license="CC BY-NC 4.0",
        source_url="https://example.com/emscad.csv",
        row_count=17880,
        validation_summary={"fraud_ratio": 0.048, "missing_descriptions": 0},
    )
    db_session.add_all([mv, ds])
    db_session.commit()

    queried_mv = db_session.query(ModelVersion).filter_by(version="v1.0.0-rc1").first()
    assert queried_mv is not None
    assert queried_mv.metrics["f1"] == 0.91
    assert queried_mv.evaluation_status == "approved"

    queried_ds = db_session.query(DatasetImport).filter_by(dataset_name="EMSCAD").first()
    assert queried_ds is not None
    assert queried_ds.row_count == 17880
    assert queried_ds.validation_summary["fraud_ratio"] == 0.048


def test_readiness_probe_with_healthy_and_unhealthy_db(monkeypatch, test_engine):
    """
    Test that readiness probe returns 200 when DB is available,
    and 503 without leaking secrets when DB is unavailable.
    """
    # 1. Healthy test DB
    monkeypatch.setattr("app.db.session.engine", test_engine)
    client = TestClient(app)

    res_ok = client.get("/api/v1/health/ready")
    assert res_ok.status_code == 200
    data_ok = res_ok.json()
    assert data_ok["status"] == "ready"
    assert data_ok["dependencies"]["database"] == "ready"

    # 2. Unhealthy DB (simulate broken connection)
    broken_engine = create_engine("sqlite:///nonexistent/path/cannot/create.db")
    monkeypatch.setattr("app.db.session.engine", broken_engine)

    res_err = client.get("/api/v1/health/ready")
    assert res_err.status_code == 503
    data_err = res_err.json()
    assert data_err["status"] == "not_ready"
    assert data_err["dependencies"]["database"] == "unavailable"

    # Ensure no passwords or sensitive connection strings leaked
    assert "password" not in res_err.text.lower()
    assert "secret" not in res_err.text.lower()
