"""Tests for Alembic migrations covering companies, company_source_records, startup_recognition, and company_domains."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.company import Company, CompanyDomain, CompanySourceRecord, StartupRecognition


def test_migration_0002_creates_all_company_tables(test_engine):
    """Verify that all four required tables exist with expected schema and indexes."""
    inspector = inspect(test_engine)
    tables = set(inspector.get_table_names())

    required_tables = {
        "companies",
        "company_source_records",
        "startup_recognition",
        "company_domains",
    }
    assert required_tables.issubset(tables), f"Missing tables: {required_tables - tables}"

    # Verify columns in 'companies'
    company_cols = {col["name"] for col in inspector.get_columns("companies")}
    expected_company_cols = {
        "id",
        "legal_name",
        "normalized_name",
        "cin",
        "entity_type",
        "registry_status",
        "created_at",
        "updated_at",
    }
    assert expected_company_cols.issubset(company_cols)

    # Verify columns in 'company_source_records'
    source_cols = {col["name"] for col in inspector.get_columns("company_source_records")}
    expected_source_cols = {
        "id",
        "company_id",
        "source_name",
        "source_url",
        "source_record_id",
        "source_status",
        "retrieved_at",
        "source_updated_at",
        "match_method",
        "match_confidence",
        "raw_metadata",
    }
    assert expected_source_cols.issubset(source_cols)

    # Verify columns in 'startup_recognition'
    startup_cols = {col["name"] for col in inspector.get_columns("startup_recognition")}
    expected_startup_cols = {
        "id",
        "company_id",
        "recognition_status",
        "recognition_id",
        "source_url",
        "checked_at",
        "status_details",
    }
    assert expected_startup_cols.issubset(startup_cols)

    # Verify columns in 'company_domains'
    domain_cols = {col["name"] for col in inspector.get_columns("company_domains")}
    expected_domain_cols = {
        "id",
        "company_id",
        "domain",
        "source_url",
        "verification_status",
        "evidence_summary",
        "checked_at",
        "is_primary",
    }
    assert expected_domain_cols.issubset(domain_cols)


def test_company_relationships_and_cascade_delete(db_session: Session):
    """Verify foreign key cascading and ORM relationships across company tables."""
    company = Company(
        legal_name="ACME TESTING TECHNOLOGIES PRIVATE LIMITED",
        normalized_name="ACME TESTING TECHNOLOGIES PRIVATE LIMITED",
        cin="U72200MH2026PTC123456",
        entity_type="Private",
        registry_status="Active",
    )
    db_session.add(company)
    db_session.flush()

    source_record = CompanySourceRecord(
        company_id=company.id,
        source_name="MCA_COMPANY_MASTER",
        source_url="https://data.gov.in/catalog/company-master-data",
        source_record_id=company.cin,
        source_status="Active",
        match_method="DIRECT_IMPORT",
        match_confidence=1.0,
        raw_metadata={"state": "Maharashtra", "roc": "ROC Mumbai"},
    )
    startup_rec = StartupRecognition(
        company_id=company.id,
        recognition_status="RECOGNIZED",
        recognition_id="DIPP12345",
        source_url="https://data.gov.in/catalog/startup-recognized-dpiit",
        status_details={"sector": "AI", "source_page": 12},
    )
    domain_rec = CompanyDomain(
        company_id=company.id,
        domain="acmetesting.example.in",
        verification_status="VERIFIED",
        evidence_summary="Domain registered in official MCA filing",
        is_primary=True,
    )

    db_session.add_all([source_record, startup_rec, domain_rec])
    db_session.commit()

    # Query back
    queried = db_session.get(Company, company.id)
    assert queried is not None
    assert len(queried.source_records) == 1
    assert len(queried.startup_recognitions) == 1
    assert len(queried.domains) == 1
    assert queried.domains[0].domain == "acmetesting.example.in"

    # Test cascade delete
    db_session.delete(queried)
    db_session.commit()

    assert db_session.get(Company, company.id) is None
    assert db_session.execute(
        select(CompanySourceRecord).where(CompanySourceRecord.company_id == company.id)
    ).scalar_one_or_none() is None
    assert db_session.execute(
        select(StartupRecognition).where(StartupRecognition.company_id == company.id)
    ).scalar_one_or_none() is None
    assert db_session.execute(
        select(CompanyDomain).where(CompanyDomain.company_id == company.id)
    ).scalar_one_or_none() is None


def test_alembic_downgrade_and_reupgrade(test_db_url: str, test_engine):
    """Verify that Alembic downgrade and upgrade execute safely without losing existing MVP data."""
    import argparse
    from sqlalchemy.orm import sessionmaker
    from app.models.scan import ScanRequest

    # 1. Insert data in 0001 table
    Session = sessionmaker(bind=test_engine)
    with Session() as s:
        test_scan = ScanRequest(
            id="migration-test-uuid-001",
            input_type="job_text",
            input_reference="Test text",
            status="pending",
        )
        s.add(test_scan)
        s.commit()

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.cmd_opts = argparse.Namespace(x=["url=" + test_db_url])

    # Downgrade revision 0002 to 0001_initial_mvp
    command.downgrade(alembic_cfg, "0001_initial_mvp")

    # Verify 0001 data is preserved
    with Session() as s:
        scan_after_downgrade = s.get(ScanRequest, "migration-test-uuid-001")
        assert scan_after_downgrade is not None
        assert scan_after_downgrade.status == "pending"

    # Re-upgrade to head
    command.upgrade(alembic_cfg, "head")

    # Verify 0001 data is still intact
    with Session() as s:
        scan_after_upgrade = s.get(ScanRequest, "migration-test-uuid-001")
        assert scan_after_upgrade is not None
        s.delete(scan_after_upgrade)
        s.commit()
