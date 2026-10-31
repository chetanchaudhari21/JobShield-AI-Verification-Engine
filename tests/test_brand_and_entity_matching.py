"""Regression test suite for Brand Name, Trade Name, and Ambiguity Matching.

Conforms to safety requirements:
1. Trade-name / brand-prefix matching logic.
2. Identifies all relevant candidates for ambiguous brands (e.g. Capgemini).
3. Does not automatically select an entity solely because it is Active, a PLC, or has higher capital.
4. Retains safe non-match and explains ambiguity when multiple plausible entities exist.
5. For uniquely identified brand matches, uses TRADE_NAME_EXACT with calibrated confidence (0.85).
6. Preserves actual registry status (Active, Amalgamated, Strike Off).
7. Ensures NO_MATCH is never a fraud signal.
8. Tests exact legal names, struck-off entities, Infosys, and unrelated names.
"""

from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app.models.company import Company, CompanySourceRecord
from app.models.ml import DatasetImport
from app.verification.normalization import normalize_company_name
from app.verification.company_verifier import (
    CompanyVerifier,
    MatchMethod,
    VerificationStatus,
)


@pytest.fixture(autouse=True)
def seed_mca_test_data(db_session: Session):
    """Seed test session with Capgemini, Infosys, and 008Techuit entities and MCA dataset import."""
    now = datetime.now(timezone.utc)

    # 1. Dataset import record representing completed MCA import
    ds_import = DatasetImport(
        dataset_name="MCA Company Master Data",
        version_or_snapshot="2026-10-13",
        license="Government Open Data License - India (GODL)",
        source_url="https://data.gov.in/resource/company-master-data",
        imported_at=now,
        row_count=3192605,
        validation_summary={
            "per_file_metrics": {
                "company_master_data_2026-10-13_part1.csv": {"imported": 799999},
                "company_master_data_2026-10-13_part2.csv": {"imported": 799999},
                "company_master_data_2026-10-13_part3.csv": {"imported": 799999},
                "company_master_data_2026-10-13_part4.csv": {"imported": 592608},
            }
        },
    )
    db_session.add(ds_import)

    # 2. Capgemini entities (all 7 verified from MCA)
    capgemini_entities = [
        ("CAPGEMINI TECHNOLOGY SERVICES INDIA LIMITED", "U85110PN1993PLC145950", "Active", "PLC"),
        ("CAPGEMINI IT SOLUTIONS INDIA PRIVATE LIMITED", "U74995MH2018FTC330429", "Active", "FTC"),
        ("CAPGEMINI INDIA PRIVATE LIMITED", "U72200MH1992PTC197069", "Amalgamated", "PTC"),
        ("CAPGEMINI BUSINESS SERVICES (INDIA) PRIVATE LIMITED", "U74140MH2008PTC187989", "Amalgamated", "PTC"),
        ("CAPGEMINI FINANCIAL SERVICES INDIA PRIVATE LIMITED", "U72200MH2006PTC160533", "Amalgamated", "PTC"),
        ("CAPGEMINI CONSULTING INDIA PRIVATE LIMITED", "U74140MH2000PTC126581", "Amalgamated", "PTC"),
        ("CAPGEMINI CONSULTING INDIA SERVICES PRIVATE LIMITED", "U45200MH1999PTC123118", "Strike Off", "PTC"),
    ]

    for legal_name, cin, reg_status, entity_type in capgemini_entities:
        comp = Company(
            legal_name=legal_name,
            normalized_name=normalize_company_name(legal_name),
            cin=cin,
            entity_type=entity_type,
            registry_status=reg_status,
        )
        db_session.add(comp)
        db_session.flush()

        sr = CompanySourceRecord(
            company_id=comp.id,
            source_name="MCA_COMPANY_MASTER",
            source_url="ml/data/mca/company_master_data_2026-10-13_part2.csv",
            source_record_id=cin,
            source_status=reg_status,
            retrieved_at=now,
            source_updated_at=now,
            match_method="EXACT_CIN",
            match_confidence=1.0,
        )
        db_session.add(sr)

    # 3. Infosys Limited
    infy = Company(
        legal_name="INFOSYS LIMITED",
        normalized_name=normalize_company_name("INFOSYS LIMITED"),
        cin="L85110KA1981PLC013115",
        entity_type="PLC",
        registry_status="Active",
    )
    db_session.add(infy)
    db_session.flush()

    sr_infy = CompanySourceRecord(
        company_id=infy.id,
        source_name="MCA_COMPANY_MASTER",
        source_url="ml/data/mca/company_master_data_2026-10-13_part2.csv",
        source_record_id="L85110KA1981PLC013115",
        source_status="Active",
        retrieved_at=now,
        source_updated_at=now,
        match_method="EXACT_CIN",
        match_confidence=1.0,
    )
    db_session.add(sr_infy)

    # 4. 008TECHUIT INDIA PRIVATE LIMITED
    techuit = Company(
        legal_name="008TECHUIT INDIA PRIVATE LIMITED",
        normalized_name=normalize_company_name("008TECHUIT INDIA PRIVATE LIMITED"),
        cin="U31900WB2020PTC239446",
        entity_type="PTC",
        registry_status="Active",
    )
    db_session.add(techuit)
    db_session.flush()

    sr_techuit = CompanySourceRecord(
        company_id=techuit.id,
        source_name="MCA_COMPANY_MASTER",
        source_url="ml/data/mca/company_master_data_2026-10-13_part1.csv",
        source_record_id="U31900WB2020PTC239446",
        source_status="Active",
        retrieved_at=now,
        source_updated_at=now,
        match_method="EXACT_CIN",
        match_confidence=1.0,
    )
    db_session.add(sr_techuit)

    db_session.flush()


def test_capgemini_ambiguous_brand_returns_safe_non_match(db_session: Session):
    """
    Querying 'Capgemini' matches 7 distinct registered entities in MCA.
    It must NOT automatically guess an entity, but return a safe non-match
    explaining the ambiguity with the candidate entities.
    """
    verifier = CompanyVerifier()
    res = verifier.verify_company(query_name="Capgemini", db=db_session)

    assert res.status == VerificationStatus.AMBIGUOUS_MATCH
    assert res.match_method == MatchMethod.AMBIGUOUS_BRAND
    assert res.confidence == 0.0
    assert res.company is None
    assert res.is_fraud_signal is False
    assert res.mca_status == "AMBIGUOUS"
    assert "Query 'Capgemini' matches 7 distinct registered entities" in res.summary
    assert "Verification cannot automatically select an entity" in res.summary
    assert "Multiple legal entities operate under or share the brand prefix 'Capgemini'" in res.limitations
    assert res.candidate_entities is not None
    assert len(res.candidate_entities) == 7

    statuses = {c["registry_status"] for c in res.candidate_entities}
    assert "Active" in statuses
    assert "Amalgamated" in statuses
    assert "Strike Off" in statuses

    cins = {c["cin"] for c in res.candidate_entities}
    assert "U85110PN1993PLC145950" in cins  # Capgemini Technology Services India Limited
    assert "U74995MH2018FTC330429" in cins  # Capgemini IT Solutions India Private Limited
    assert "U45200MH1999PTC123118" in cins  # Capgemini Consulting India Services Private Limited


def test_capgemini_exact_legal_name_active(db_session: Session):
    """Providing the exact legal name for an active entity matches with 100% confidence."""
    verifier = CompanyVerifier()
    res = verifier.verify_company(
        query_name="Capgemini Technology Services India Limited", db=db_session
    )

    assert res.status == VerificationStatus.MATCHED
    assert res.match_method in (MatchMethod.LEGAL_NAME_EXACT, MatchMethod.NORMALIZED_NAME_EXACT)
    assert res.confidence == 1.0
    assert res.company is not None
    assert res.company.cin == "U85110PN1993PLC145950"
    assert res.company.legal_name == "CAPGEMINI TECHNOLOGY SERVICES INDIA LIMITED"
    assert res.mca_status == "Active"
    assert res.is_fraud_signal is False


def test_capgemini_exact_legal_name_struck_off(db_session: Session):
    """Providing the exact legal name for a struck-off entity matches with Strike Off status preserved."""
    verifier = CompanyVerifier()
    res = verifier.verify_company(
        query_name="Capgemini Consulting India Services Private Limited", db=db_session
    )

    assert res.status == VerificationStatus.MATCHED
    assert res.confidence == 1.0
    assert res.company is not None
    assert res.company.cin == "U45200MH1999PTC123118"
    assert res.mca_status == "Strike Off"
    assert res.is_fraud_signal is False


def test_capgemini_exact_legal_name_amalgamated(db_session: Session):
    """Providing the exact legal name for an amalgamated entity matches with Amalgamated status preserved."""
    verifier = CompanyVerifier()
    res = verifier.verify_company(
        query_name="Capgemini India Private Limited", db=db_session
    )

    assert res.status == VerificationStatus.MATCHED
    assert res.confidence == 1.0
    assert res.company is not None
    assert res.company.cin == "U72200MH1992PTC197069"
    assert res.mca_status == "Amalgamated"
    assert res.is_fraud_signal is False


def test_infosys_exact_legal_name(db_session: Session):
    """Exact statutory legal name 'Infosys Limited' matches with 100% confidence."""
    verifier = CompanyVerifier()
    res = verifier.verify_company(query_name="Infosys Limited", db=db_session)

    assert res.status == VerificationStatus.MATCHED
    assert res.confidence >= 0.98
    assert res.company is not None
    assert res.company.cin == "L85110KA1981PLC013115"
    assert res.mca_status == "Active"


def test_infosys_stem_match(db_session: Session):
    """Brand query 'Infosys' resolves to 'INFOSYS LIMITED' via unique stem match."""
    verifier = CompanyVerifier()
    res = verifier.verify_company(query_name="Infosys", db=db_session)

    assert res.status == VerificationStatus.MATCHED
    assert res.match_method == MatchMethod.STEM_SIMILARITY
    assert res.confidence == 0.85
    assert res.company is not None
    assert res.company.cin == "L85110KA1981PLC013115"
    assert res.mca_status == "Active"


def test_unique_brand_trade_name_match(db_session: Session):
    """A uniquely identified brand-to-entity match uses TRADE_NAME_EXACT and notes name difference."""
    verifier = CompanyVerifier()
    # Query '008TECHUIT' matches '008TECHUIT INDIA PRIVATE LIMITED' uniquely
    res = verifier.verify_company(query_name="008TECHUIT", db=db_session)

    assert res.status == VerificationStatus.MATCHED
    assert res.match_method == MatchMethod.TRADE_NAME_EXACT
    assert res.confidence == 0.85
    assert res.company is not None
    assert res.company.cin == "U31900WB2020PTC239446"
    assert "Matched via brand/trade name prefix '008TECHUIT'" in res.summary
    assert "the queried brand name differs from the official registered legal name" in res.summary


def test_unrelated_name_no_match(db_session: Session):
    """Non-existent entities return genuine NO_MATCH with is_fraud_signal=False and candidate_entities=None."""
    verifier = CompanyVerifier()
    res = verifier.verify_company(
        query_name="NonExistentRandomCorp999", db=db_session
    )

    assert res.status == VerificationStatus.NO_MATCH
    assert res.match_method == MatchMethod.NO_MATCH
    assert res.confidence == 0.0
    assert res.company is None
    assert res.is_fraud_signal is False
    assert res.mca_status == "NOT_FOUND"
    assert res.candidate_entities is None


def test_analyze_job_text_integration_capgemini(test_client: TestClient):
    """Integration test: POST /api/v1/analyze/job-text with Capgemini returns AMBIGUOUS_MATCH with candidates."""
    payload = {
        "text": "Join our team at Capgemini. We are hiring a Senior Software Engineer for cloud platforms in Bangalore and Pune.",
        "company_name": "Capgemini",
    }
    resp = test_client.post("/api/v1/analyze/job-text", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    cv = data["company_verification"]
    assert cv["status"] == "AMBIGUOUS_MATCH"
    assert cv["is_fraud_signal"] is False
    assert cv["match_confidence"] == 0.0
    assert cv["mca_status"] == "AMBIGUOUS"
    assert "Query 'Capgemini' matches 7 distinct registered entities" in cv["summary"]
    assert cv["candidate_entities"] is not None
    assert len(cv["candidate_entities"]) == 7

    # Check evidence item details
    mca_evidence = next(e for e in data["evidence"] if "MCA" in e["source_name"])
    assert mca_evidence["status"] == "AMBIGUOUS"
    assert mca_evidence["details"]["is_ambiguous_brand"] is True
    assert mca_evidence["details"]["brand_candidate_count"] == 7
    assert len(mca_evidence["details"]["candidate_entities"]) == 7
