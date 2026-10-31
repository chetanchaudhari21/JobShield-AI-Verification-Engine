"""Smoke tests verifying that import adapters parse the actual MCA and DPIIT CSV files in ml/data/."""

import os
import pytest
from sqlalchemy.orm import Session

from app.adapters.dpiit_adapter import DPIITImportAdapter
from app.adapters.mca_adapter import MCAImportAdapter
from app.models.company import Company, StartupRecognition

REAL_DPIIT_PATH = "ml/data/dpiit/startuplist_converted.csv"
REAL_MCA_PART1_PATH = "ml/data/mca/company_master_data_2026-10-13_part1.csv"


@pytest.mark.skipif(not os.path.exists(REAL_DPIIT_PATH), reason="Real DPIIT CSV not found")
def test_dpiit_real_file_structure_and_smoke_import(db_session: Session):
    """
    Verify real DPIIT converted CSV structure:
    - 1,886 extracted data rows from 87 pages
    - Headers: Source Page, Name Of Entity, DPIIT Number, Sector, Industry, District
    - Ingests first 5 rows and verifies source page and unverified caveat preservation.
    """
    # Count rows in real CSV
    with open(REAL_DPIIT_PATH, mode="r", encoding="utf-8-sig") as f:
        lines = [line for line in f if line.strip()]

    header = lines[0].strip().split(",")
    expected_header = ["Source Page", "Name Of Entity", "DPIIT Number", "Sector", "Industry", "District"]
    assert header == expected_header
    assert len(lines) == 1887  # 1 header + 1886 extracted rows

    adapter = DPIITImportAdapter()
    stats = adapter.import_file(
        db_session=db_session,
        file_path=REAL_DPIIT_PATH,
        limit=5,
    )

    assert stats.total_rows_read == 5
    assert stats.imported_recognitions == 5
    assert stats.error_count == 0

    # Verify first imported startup record
    first_startup = db_session.query(StartupRecognition).first()
    assert first_startup is not None
    assert first_startup.recognition_status == "UNVERIFIED"
    assert first_startup.status_details["is_confirmed_current_recognition"] is False
    assert first_startup.status_details["source_page"] is not None
    assert "unverified until confirmed" in first_startup.status_details["verification_caveat"]


@pytest.mark.skipif(not os.path.exists(REAL_MCA_PART1_PATH), reason="Real MCA part1 CSV not found")
def test_mca_real_file_structure_and_smoke_import(db_session: Session):
    """
    Verify real MCA part1 CSV structure and test streaming 5 records.
    """
    adapter = MCAImportAdapter()
    stats = adapter.import_files(
        db_session=db_session,
        file_paths=[REAL_MCA_PART1_PATH],
        limit=5,
    )

    assert stats.total_rows_read == 5
    assert stats.imported_companies == 5
    assert stats.error_count == 0

    first_company = db_session.query(Company).first()
    assert first_company is not None
    assert first_company.cin is not None
    assert first_company.legal_name is not None
    assert first_company.normalized_name is not None
    assert len(first_company.source_records) == 1
    assert first_company.source_records[0].source_name == "MCA_COMPANY_MASTER"


MCA_PART_FILES = [
    "ml/data/mca/company_master_data_2026-10-13_part1.csv",
    "ml/data/mca/company_master_data_2026-10-13_part2.csv",
    "ml/data/mca/company_master_data_2026-10-13_part3.csv",
    "ml/data/mca/company_master_data_2026-10-13_part4.csv",
]

EXPECTED_MCA_HEADER = [
    "CIN",
    "Company Name",
    "Company Registration Date",
    "Company Category",
    "Company Class",
    "Listing Status",
    "Authorized Capital",
    "Paidup Capital",
    "Company ROC",
    "Company Address",
    "Pin Code",
    "Company State",
    "Company Status",
    "Company Sub Category",
    "Company Industrial Classification",
]


@pytest.mark.skipif(not all(os.path.exists(p) for p in MCA_PART_FILES), reason="MCA CSV parts not found")
def test_all_mca_parts_exist_and_headers_valid():
    """Verify all 4 MCA part files exist with expected 15-column headers and valid sizes (>200MB)."""
    import csv

    for fp in MCA_PART_FILES:
        assert os.path.exists(fp), f"File {fp} does not exist"
        size = os.path.getsize(fp)
        assert size > 200 * 1024 * 1024, f"File {fp} size {size} is unexpectedly small"

        with open(fp, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == EXPECTED_MCA_HEADER, f"Header mismatch in {fp}"


@pytest.mark.skipif(not os.path.exists(REAL_MCA_PART1_PATH), reason="Real MCA CSV not found")
def test_mca_dry_run_guarantees_zero_writes(db_session: Session):
    """Verify dry_run=True mode performs zero persistent writes across companies and dataset_imports."""
    from app.models.ml import DatasetImport

    adapter = MCAImportAdapter()
    stats = adapter.import_files(
        db_session=db_session,
        file_paths=[REAL_MCA_PART1_PATH],
        limit=20,
        dry_run=True,
    )

    assert stats.total_rows_read == 20
    assert stats.accepted_rows == 20
    assert stats.imported_companies == 20

    # Ensure zero persistent writes in DB
    assert db_session.query(Company).count() == 0
    assert db_session.query(DatasetImport).count() == 0


@pytest.mark.skipif(not os.path.exists("ml/data/mca/company_master_data_2026-10-13_part2.csv"), reason="MCA Part 2 not found")
def test_infosys_source_record_validation(db_session: Session):
    """
    Verify Infosys record in source CSV part 2 without hardcoding Infosys into the adapter.
    Verify CIN L85110KA1981PLC013115, active status, legal name, and verifier matching.
    """
    import csv
    from app.verification.company_verifier import CompanyVerifier, VerificationStatus
    from app.verification.normalization import normalize_company_name

    target_cin = "L85110KA1981PLC013115"
    part2_path = "ml/data/mca/company_master_data_2026-10-13_part2.csv"
    infosys_row = None

    with open(part2_path, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("CIN") or "").strip() == target_cin:
                infosys_row = row
                break

    assert infosys_row is not None, f"Infosys CIN {target_cin} not found in part 2 CSV"
    assert infosys_row["CIN"] == target_cin
    assert infosys_row["Company Name"] == "INFOSYS LIMITED"
    assert infosys_row["Company Status"] == "Active"
    assert infosys_row["Listing Status"] == "Listed"
    assert infosys_row["Company Class"] == "Public"
    assert infosys_row["Company Registration Date"] == "1981-07-02"
    assert "ROC Bangalore" in infosys_row["Company ROC"]

    # Verify normalization logic
    norm_name = normalize_company_name(infosys_row["Company Name"])
    assert norm_name == "INFOSYS LIMITED"

    # Verify that once registered, CompanyVerifier accurately matches by CIN and by Name
    company = Company(
        legal_name=infosys_row["Company Name"],
        normalized_name=norm_name,
        cin=target_cin,
        entity_type=infosys_row["Company Class"],
        registry_status=infosys_row["Company Status"],
    )
    db_session.add(company)
    db_session.flush()

    verifier = CompanyVerifier()
    res_cin = verifier.verify_company(cin=target_cin, db=db_session)
    assert res_cin.status == VerificationStatus.MATCHED
    assert res_cin.company.legal_name == "INFOSYS LIMITED"
    assert res_cin.is_fraud_signal is False

    res_name = verifier.verify_company(query_name="Infosys Limited", db=db_session)
    assert res_name.status == VerificationStatus.MATCHED
    assert res_name.company.legal_name == "INFOSYS LIMITED"
    assert res_name.is_fraud_signal is False

