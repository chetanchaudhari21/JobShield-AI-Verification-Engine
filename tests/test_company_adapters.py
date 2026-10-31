"""Tests for MCA and DPIIT dataset import adapters using clearly-labelled synthetic data."""

import os
import subprocess
import sys
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.dpiit_adapter import DPIITImportAdapter
from app.adapters.mca_adapter import MCAImportAdapter
from app.models.company import Company, CompanySourceRecord, StartupRecognition
from app.models.ml import DatasetImport

SYNTHETIC_MCA_FILE = "tests/data/synthetic_mca_sample.csv"
SYNTHETIC_DPIIT_FILE = "tests/data/synthetic_dpiit_sample.csv"


def test_mca_adapter_synthetic_import(db_session: Session):
    """Verify that MCAImportAdapter imports synthetic records with full provenance."""
    adapter = MCAImportAdapter(
        source_name="MCA_COMPANY_MASTER",
        source_url="https://data.gov.in/catalog/company-master-data",
        license_text="Government Open Data License - India (GODL)",
        snapshot_date="2026-10-13",
    )

    stats = adapter.import_files(
        db_session=db_session,
        file_paths=[SYNTHETIC_MCA_FILE],
        batch_size=2,
    )

    assert stats.total_rows_read == 5
    assert stats.imported_companies == 5
    assert stats.imported_source_records == 5
    assert stats.error_count == 0
    assert "synthetic_mca_sample.csv" in stats.file_checksums

    # Verify Company records
    companies = db_session.execute(select(Company)).scalars().all()
    assert len(companies) == 5

    tech_co = db_session.execute(
        select(Company).where(Company.cin == "U72200SYN2026PTC000001")
    ).scalar_one()
    assert tech_co.legal_name == "SYNTHETIC TECH INNOVATIONS PRIVATE LIMITED"
    assert tech_co.normalized_name == "SYNTHETIC TECH INNOVATIONS PRIVATE LIMITED"
    assert tech_co.registry_status == "Active"

    # Verify CompanySourceRecord
    source_records = tech_co.source_records
    assert len(source_records) == 1
    assert source_records[0].source_name == "MCA_COMPANY_MASTER"
    assert source_records[0].source_url == "https://data.gov.in/catalog/company-master-data"
    assert source_records[0].raw_metadata["roc"] == "ROC Bangalore"
    assert source_records[0].raw_metadata["state"] == "Karnataka"

    # Verify Struck-off company status preservation
    struck_co = db_session.execute(
        select(Company).where(Company.cin == "U52100SYN2025PTC000004")
    ).scalar_one()
    assert struck_co.registry_status == "Strike Off"

    # Verify dataset_imports audit log
    import_audit = db_session.execute(
        select(DatasetImport).where(DatasetImport.dataset_name == "MCA_COMPANY_MASTER")
    ).scalar_one()
    assert import_audit.row_count == 5
    assert import_audit.license == "Government Open Data License - India (GODL)"
    assert import_audit.version_or_snapshot == "2026-10-13"
    assert "file_checksums" in import_audit.validation_summary


def test_mca_adapter_limit_and_dry_run(db_session: Session):
    """Verify MCA adapter respects limit and dry_run flags."""
    adapter = MCAImportAdapter()

    # Dry-run test: no records added to DB, including dataset_imports
    stats_dry = adapter.import_files(
        db_session=db_session,
        file_paths=[SYNTHETIC_MCA_FILE],
        dry_run=True,
    )
    assert stats_dry.total_rows_read == 5
    assert stats_dry.imported_companies == 5

    companies_count = db_session.execute(select(Company)).scalars().all()
    assert len(companies_count) == 0
    audit_count = db_session.execute(select(DatasetImport)).scalars().all()
    assert len(audit_count) == 0

    # Limit test: stop at 2 records
    stats_limit = adapter.import_files(
        db_session=db_session,
        file_paths=[SYNTHETIC_MCA_FILE],
        limit=2,
    )
    assert stats_limit.imported_companies == 2
    companies_limited = db_session.execute(select(Company)).scalars().all()
    assert len(companies_limited) == 2


def test_dpiit_adapter_synthetic_import_with_linkage(db_session: Session):
    """
    Verify DPIITImportAdapter:
    1. Preserves source page (1, 2, 3), sector, industry, and district.
    2. Explicitly records recognition status as UNVERIFIED (never confirmed current).
    3. Links to existing MCA company when normalized name matches without inventing CIN.
    4. Creates new company entity when entity not present in MCA.
    """
    # 1. Pre-load MCA synthetic records
    mca_adapter = MCAImportAdapter()
    mca_adapter.import_files(db_session=db_session, file_paths=[SYNTHETIC_MCA_FILE])

    # 2. Ingest DPIIT synthetic records
    dpiit_adapter = DPIITImportAdapter()
    stats = dpiit_adapter.import_file(
        db_session=db_session,
        file_path=SYNTHETIC_DPIIT_FILE,
    )

    assert stats.total_rows_read == 5
    assert stats.imported_recognitions == 5
    assert stats.error_count == 0
    assert "synthetic_dpiit_sample.csv" in stats.file_checksums

    # Check linkage: SYNTHETIC TECH INNOVATIONS PRIVATE LIMITED should link to existing MCA entity
    tech_co = db_session.execute(
        select(Company).where(Company.legal_name == "SYNTHETIC TECH INNOVATIONS PRIVATE LIMITED")
    ).scalar_one()

    # Should have two source records: MCA and DPIIT
    source_names = {sr.source_name for sr in tech_co.source_records}
    assert "MCA_COMPANY_MASTER" in source_names
    assert "DPIIT_STARTUP_LIST" in source_names

    # Check StartupRecognition on the company - marked UNVERIFIED
    assert len(tech_co.startup_recognitions) == 1
    reg = tech_co.startup_recognitions[0]
    assert reg.recognition_id == "DIPP_SYNTH_9001"
    assert reg.recognition_status == "UNVERIFIED"
    assert reg.status_details["source_page"] == 1
    assert reg.status_details["sector"] == "AI & Robotics"
    assert reg.status_details["district"] == "Bangalore Urban"
    assert reg.status_details["is_confirmed_current_recognition"] is False
    assert "unverified until confirmed" in reg.status_details["verification_caveat"]

    # Check unlinked entity: SYNTHETIC BIOTECH LABS PRIVATE LIMITED was not in MCA
    biotech_co = db_session.execute(
        select(Company).where(Company.legal_name == "SYNTHETIC BIOTECH LABS PRIVATE LIMITED")
    ).scalar_one()
    assert biotech_co.cin is None
    assert biotech_co.entity_type == "Startup"
    assert biotech_co.registry_status == "Unverified"
    assert len(biotech_co.startup_recognitions) == 1
    assert biotech_co.startup_recognitions[0].recognition_id == "DIPP_SYNTH_9003"
    assert biotech_co.startup_recognitions[0].recognition_status == "UNVERIFIED"
    assert biotech_co.startup_recognitions[0].status_details["source_page"] == 2

    # Check dataset_imports audit record
    dpiit_audit = db_session.execute(
        select(DatasetImport).where(DatasetImport.dataset_name == "DPIIT_STARTUP_LIST")
    ).scalar_one()
    assert dpiit_audit.row_count == 5
    assert dpiit_audit.license == "UNVERIFIED"
    assert dpiit_audit.validation_summary["source_page_count"] == 87
    assert dpiit_audit.validation_summary["coverage_verified"] is False
    assert dpiit_audit.validation_summary["recognition_confirmed"] is False


def test_idempotency_repeated_imports(db_session: Session):
    """Verify that running MCA and DPIIT imports repeatedly produces ZERO duplicate rows."""
    mca_adapter = MCAImportAdapter()
    dpiit_adapter = DPIITImportAdapter()

    # Initial import run
    mca_adapter.import_files(db_session=db_session, file_paths=[SYNTHETIC_MCA_FILE])
    dpiit_adapter.import_file(db_session=db_session, file_path=SYNTHETIC_DPIIT_FILE)

    companies_before = len(db_session.execute(select(Company)).scalars().all())
    source_recs_before = len(db_session.execute(select(CompanySourceRecord)).scalars().all())
    recognitions_before = len(db_session.execute(select(StartupRecognition)).scalars().all())

    # Second run of the exact same datasets
    mca_adapter.import_files(db_session=db_session, file_paths=[SYNTHETIC_MCA_FILE])
    dpiit_adapter.import_file(db_session=db_session, file_path=SYNTHETIC_DPIIT_FILE)

    companies_after = len(db_session.execute(select(Company)).scalars().all())
    source_recs_after = len(db_session.execute(select(CompanySourceRecord)).scalars().all())
    recognitions_after = len(db_session.execute(select(StartupRecognition)).scalars().all())

    # Zero duplication
    assert companies_after == companies_before
    assert source_recs_after == source_recs_before
    assert recognitions_after == recognitions_before


def test_dry_run_mode_non_mutation(db_session: Session):
    """Verify dry_run mode performs zero mutations across all tables, including dataset_imports."""
    mca_adapter = MCAImportAdapter()
    dpiit_adapter = DPIITImportAdapter()

    mca_adapter.import_files(db_session=db_session, file_paths=[SYNTHETIC_MCA_FILE], dry_run=True)
    dpiit_adapter.import_file(db_session=db_session, file_path=SYNTHETIC_DPIIT_FILE, dry_run=True)

    assert len(db_session.execute(select(Company)).scalars().all()) == 0
    assert len(db_session.execute(select(CompanySourceRecord)).scalars().all()) == 0
    assert len(db_session.execute(select(StartupRecognition)).scalars().all()) == 0
    assert len(db_session.execute(select(DatasetImport)).scalars().all()) == 0


def test_cli_scripts_execution(test_db_url: str):
    """Verify that CLI scripts run successfully and exit with code 0."""
    python_exe = sys.executable

    # Test import_mca.py
    mca_cmd = [
        python_exe,
        "backend/scripts/import_mca.py",
        "--files",
        SYNTHETIC_MCA_FILE,
        "--db-url",
        test_db_url,
        "--dry-run",
    ]
    res_mca = subprocess.run(mca_cmd, capture_output=True, text=True)
    assert res_mca.returncode == 0
    assert "MCA COMPANY MASTER DATA IMPORT REPORT" in res_mca.stdout

    # Test import_dpiit.py
    dpiit_cmd = [
        python_exe,
        "backend/scripts/import_dpiit.py",
        "--file",
        SYNTHETIC_DPIIT_FILE,
        "--db-url",
        test_db_url,
        "--dry-run",
    ]
    res_dpiit = subprocess.run(dpiit_cmd, capture_output=True, text=True)
    assert res_dpiit.returncode == 0
    assert "DPIIT STARTUP DATA IMPORT REPORT" in res_dpiit.stdout

    # Test unified import_datasets.py
    unified_cmd = [
        python_exe,
        "backend/scripts/import_datasets.py",
        "all",
        "--mca-files",
        SYNTHETIC_MCA_FILE,
        "--dpiit-file",
        SYNTHETIC_DPIIT_FILE,
        "--limit",
        "2",
        "--db-url",
        test_db_url,
        "--dry-run",
    ]
    res_uni = subprocess.run(unified_cmd, capture_output=True, text=True)
    assert res_uni.returncode == 0
    assert "[MCA Dry Run]" in res_uni.stdout
    assert "[DPIIT Dry Run]" in res_uni.stdout
