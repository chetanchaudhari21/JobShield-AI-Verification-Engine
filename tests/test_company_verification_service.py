"""Comprehensive test suite for Company Verification Engine and Endpoints.

Tests all requirements from Feature F2 and PROJECT_SPECIFICATION.md:
- Matching methods: CIN exact, legal name exact, normalized name exact, abbreviations, stem similarity
- Statuses: MATCHED, NO_MATCH, UNKNOWN, STALE, SOURCE_UNAVAILABLE
- Non-fraud guarantee: NO_MATCH is never presented as fraud and does not increase risk score
- Separation of MCA registration and DPIIT startup recognition
- Evidence completeness: source name, timestamp, dataset version, and provenance
- API Endpoint: GET /api/v1/companies/{id} (200 with complete profile and 404)
- Integration: POST /api/v1/analyze/job-text with company_name and cin
- Edge cases: abbreviations, punctuation, similar lookalike names, stale records (>365 days)
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app.models.company import (
    Company,
    CompanyDomain,
    CompanySourceRecord,
    StartupRecognition,
)
from app.schemas.analysis import CompanyVerificationSummary
from app.verification.company_verifier import CompanyVerifier


@pytest.fixture
def populated_companies(db_session: Session):
    """Seed test database with known synthetic companies for matching and edge-case testing."""
    now = datetime.now(timezone.utc)
    one_year_and_ten_days_ago = now - timedelta(days=375)

    # 1. Standard active MCA registered company
    c1 = Company(
        legal_name="ACME DYNAMIC CLOUD PRIVATE LIMITED",
        normalized_name="ACME DYNAMIC CLOUD PRIVATE LIMITED",
        cin="U72200MH2020PTC123456",
        entity_type="PRIVATE LIMITED",
        registry_status="ACTIVE",
    )
    db_session.add(c1)
    db_session.flush()

    sr1 = CompanySourceRecord(
        company_id=c1.id,
        source_name="MCA Company Master Data",
        source_url="https://data.gov.in/resource/company-master-data",
        source_record_id="U72200MH2020PTC123456",
        source_status="ACTIVE",
        retrieved_at=now,
        source_updated_at=now - timedelta(days=30),
        match_method="EXACT_CIN",
        match_confidence=1.0,
        raw_metadata={"roc": "ROC Mumbai", "authorized_capital": 1000000},
    )
    db_session.add(sr1)

    # Also recognized as DPIIT startup
    rec1 = StartupRecognition(
        company_id=c1.id,
        recognition_status="RECOGNIZED",
        recognition_id="DIPP12345",
        source_url="ml/data/dpiit/startuplist_converted.csv",
        checked_at=now,
        status_details={
            "sector": "Information Technology",
            "industry": "Software Solutions",
            "source_page": 12,
            "is_confirmed_current_recognition": False,
        },
    )
    db_session.add(rec1)

    dom1 = CompanyDomain(
        company_id=c1.id,
        domain="acmedynamiccloud.example.com",
        source_url="https://data.gov.in",
        verification_status="VERIFIED",
        is_primary=True,
    )
    db_session.add(dom1)

    # 2. Stale company (>365 days since last updated)
    c2 = Company(
        legal_name="ANCIENT TRADING VENTURES LIMITED",
        normalized_name="ANCIENT TRADING VENTURES LIMITED",
        cin="L51100DL1995PLC098765",
        entity_type="LIMITED",
        registry_status="ACTIVE",
    )
    db_session.add(c2)
    db_session.flush()

    sr2 = CompanySourceRecord(
        company_id=c2.id,
        source_name="MCA Company Master Data",
        source_url="https://data.gov.in/resource/company-master-data",
        source_record_id="L51100DL1995PLC098765",
        source_status="ACTIVE",
        retrieved_at=one_year_and_ten_days_ago,
        source_updated_at=one_year_and_ten_days_ago,
        match_method="EXACT_CIN",
        match_confidence=1.0,
    )
    db_session.add(sr2)

    # 3. Company with special characters and abbreviation variations
    c3 = Company(
        legal_name="GLOBAL & SMART TECHNOLOGIES (OPC) PRIVATE LIMITED",
        normalized_name="GLOBAL AND SMART TECHNOLOGIES OPC PRIVATE LIMITED",
        cin="U74999KA2021OPC543210",
        entity_type="OPC PRIVATE LIMITED",
        registry_status="ACTIVE",
    )
    db_session.add(c3)
    db_session.flush()

    sr3 = CompanySourceRecord(
        company_id=c3.id,
        source_name="MCA Company Master Data",
        source_url="https://data.gov.in",
        source_record_id="U74999KA2021OPC543210",
        retrieved_at=now,
        source_updated_at=now - timedelta(days=10),
        match_method="EXACT_CIN",
        match_confidence=1.0,
    )
    db_session.add(sr3)

    db_session.commit()
    return {"active": c1, "stale": c2, "abbrev": c3}


class TestCompanyVerificationEngine:
    """Test suite for the deterministic & fuzzy CompanyVerifier matching logic."""

    def test_cin_exact_match(self, db_session: Session, populated_companies):
        verifier = CompanyVerifier()
        result = verifier.verify_company(
            query_name="Any Arbitrary Name",
            cin="u72200mh2020ptc123456",  # Case insensitive test
            db=db_session,
        )
        assert result.status == "MATCHED"
        assert result.match_method == "CIN_EXACT"
        assert result.confidence == 1.0
        assert result.company is not None
        assert result.company.id == populated_companies["active"].id
        assert result.company.legal_name == "ACME DYNAMIC CLOUD PRIVATE LIMITED"
        assert result.mca_status == "ACTIVE"
        assert result.dpiit_status == "RECOGNIZED"
        assert result.source_name == "MCA Company Master Data"

    def test_legal_name_exact_match(self, db_session: Session, populated_companies):
        verifier = CompanyVerifier()
        result = verifier.verify_company(
            query_name="ACME DYNAMIC CLOUD PRIVATE LIMITED",
            db=db_session,
        )
        assert result.status == "MATCHED"
        assert result.match_method == "LEGAL_NAME_EXACT"
        assert result.confidence == 1.0
        assert result.company.legal_name == "ACME DYNAMIC CLOUD PRIVATE LIMITED"

    def test_normalized_name_exact_match(self, db_session: Session, populated_companies):
        verifier = CompanyVerifier()
        # Mixed casing, extra spaces, trailing period
        result = verifier.verify_company(
            query_name="  acme   dynamic   cloud   private   limited.  ",
            db=db_session,
        )
        assert result.status == "MATCHED"
        assert result.match_method in ("LEGAL_NAME_EXACT", "NORMALIZED_NAME_EXACT", "ABBREVIATION_MATCH")
        assert result.confidence >= 0.95

    def test_abbreviation_expansion_match(self, db_session: Session, populated_companies):
        verifier = CompanyVerifier()
        # Query uses standard Indian corporate abbreviations: "Pvt Ltd" instead of "PRIVATE LIMITED"
        result = verifier.verify_company(
            query_name="Acme Dynamic Cloud Pvt. Ltd.",
            db=db_session,
        )
        assert result.status == "MATCHED"
        assert result.match_method in ("NORMALIZED_NAME_EXACT", "ABBREVIATION_MATCH")
        assert result.confidence >= 0.95
        assert result.company.legal_name == "ACME DYNAMIC CLOUD PRIVATE LIMITED"

    def test_ampersand_and_opc_abbreviation_match(self, db_session: Session, populated_companies):
        verifier = CompanyVerifier()
        # Query uses "&" instead of "AND", "Pvt. Ltd." instead of "PRIVATE LIMITED", "(OPC)" preserved
        result = verifier.verify_company(
            query_name="Global & Smart Technologies (OPC) Pvt Ltd",
            db=db_session,
        )
        assert result.status == "MATCHED"
        assert result.confidence >= 0.85
        assert result.company.id == populated_companies["abbrev"].id

    def test_stem_similarity_match(self, db_session: Session, populated_companies):
        verifier = CompanyVerifier()
        # Drop entity designator entirely: "Acme Dynamic Cloud"
        result = verifier.verify_company(
            query_name="Acme Dynamic Cloud",
            db=db_session,
        )
        assert result.status == "MATCHED"
        assert result.confidence >= 0.80
        assert result.company.id == populated_companies["active"].id

    def test_stale_record_detection(self, db_session: Session, populated_companies):
        """Records older than staleness_days (default 365 days) must report STALE status."""
        verifier = CompanyVerifier(staleness_days=365)
        result = verifier.verify_company(
            query_name="Ancient Trading Ventures Limited",
            cin="L51100DL1995PLC098765",
            db=db_session,
        )
        assert result.status == "STALE"
        assert result.company is not None
        assert "STALE" in result.summary

    def test_no_match_behavior(self, db_session: Session, populated_companies):
        """Non-existent entities must return NO_MATCH with non-fraud indication."""
        verifier = CompanyVerifier()
        result = verifier.verify_company(
            query_name="Nonexistent Phantom Corporation 9999",
            cin="U00000XX2099PTC000000",
            db=db_session,
        )
        assert result.status == "NO_MATCH"
        assert result.company is None
        assert result.confidence == 0.0

        # Convert to summary schema and test non-fraud guarantee
        summary = verifier.to_summary_schema(result)
        assert summary.status == "NO_MATCH"
        assert summary.is_fraud_signal is False
        assert "NO_MATCH is NOT proof of fraud" in summary.limitations

    def test_similar_lookalike_names_no_unsafe_merge(self, db_session: Session, populated_companies):
        """Ensure distinct companies with slight word additions do NOT falsely match if confidence is insufficient."""
        verifier = CompanyVerifier()
        # "Acme Global Solutions" has common words with "Acme Dynamic Cloud", but is distinctly different
        result = verifier.verify_company(
            query_name="Acme Global Solutions Private Limited",
            db=db_session,
        )
        # Should either be NO_MATCH or not match Acme Dynamic Cloud if similarity is low
        if result.status == "MATCHED":
            assert result.company.id != populated_companies["active"].id or result.confidence < 0.80
        else:
            assert result.status == "NO_MATCH"

    def test_empty_query_returns_unknown(self, db_session: Session):
        verifier = CompanyVerifier()
        result = verifier.verify_company(query_name="", cin="", db=db_session)
        assert result.status == "UNKNOWN"
        summary = verifier.to_summary_schema(result)
        assert summary.status == "UNKNOWN"

    def test_database_unavailable_returns_source_unavailable(self):
        """If the database session is None or throws a connection error, return SOURCE_UNAVAILABLE and rollback."""
        verifier = CompanyVerifier()
        result = verifier.verify_company(
            query_name="Acme Dynamic Cloud Private Limited",
            cin="U72200MH2020PTC123456",
            db=None,
        )
        assert result.status == "SOURCE_UNAVAILABLE"

        # Mock a session that raises an OperationalError
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("DB Connection Refused")
        result_err = verifier.verify_company(
            query_name="Acme Dynamic Cloud",
            db=mock_db,
        )
        assert result_err.status == "SOURCE_UNAVAILABLE"
        mock_db.rollback.assert_called_once()

    def test_verify_company_db_error_rolls_back_session_for_subsequent_writes(
        self, db_session: Session
    ):
        """Verify that when verify_company catches a database query error,
        it calls db.rollback() so the session is restored to a clean state
        and subsequent writes/commits succeed without PendingRollbackError."""
        from unittest.mock import patch
        from app.models.scan import ScanRequest
        import uuid

        verifier = CompanyVerifier()
        orig_execute = db_session.execute
        called = False

        def fail_first_execute(*args, **kwargs):
            nonlocal called
            if not called:
                called = True
                raise Exception("Simulated DB query failure in verification")
            return orig_execute(*args, **kwargs)

        with patch.object(db_session, "execute", side_effect=fail_first_execute):
            result = verifier.verify_company(
                query_name="Acme Dynamic Cloud Private Limited",
                db=db_session,
            )
            assert result.status == "SOURCE_UNAVAILABLE"

        # Session must be clean and able to persist records
        test_id = str(uuid.uuid4())
        scan = ScanRequest(
            id=test_id,
            input_type="job_text",
            input_reference="sha256:test",
            status="completed",
        )
        db_session.add(scan)
        db_session.commit()

        persisted = db_session.query(ScanRequest).filter(ScanRequest.id == test_id).first()
        assert persisted is not None
        assert persisted.id == test_id


class TestCompanyApiEndpoints:
    """Test suite for GET /api/v1/companies/{id} and analysis integration."""

    def test_get_company_profile_success(self, test_client: TestClient, populated_companies):
        company_id = populated_companies["active"].id
        response = test_client.get(f"/api/v1/companies/{company_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == company_id
        assert data["legal_name"] == "ACME DYNAMIC CLOUD PRIVATE LIMITED"
        assert data["cin"] == "U72200MH2020PTC123456"
        assert data["entity_type"] == "PRIVATE LIMITED"
        assert data["registry_status"] == "ACTIVE"

        # Check source records provenance
        assert len(data["source_records"]) >= 1
        sr = data["source_records"][0]
        assert sr["source_name"] == "MCA Company Master Data"
        assert "data.gov.in" in sr["source_url"]

        # Check startup recognition separation
        assert len(data["startup_recognitions"]) >= 1
        rec = data["startup_recognitions"][0]
        assert rec["recognition_status"] == "RECOGNIZED"
        assert rec["recognition_id"] == "DIPP12345"

        # Check observed domains
        assert len(data["domains"]) >= 1
        assert data["domains"][0]["domain"] == "acmedynamiccloud.example.com"

        # Check live verification summary and statutory disclaimer
        assert data["verification_summary"]["status"] == "MATCHED"
        assert "Neither status validates" in data["disclaimer"]

    def test_get_company_profile_not_found(self, test_client: TestClient):
        response = test_client.get("/api/v1/companies/9999999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_analyze_job_text_integration_with_company_name_and_cin(
        self, test_client: TestClient, populated_companies
    ):
        """Verify that POST /api/v1/analyze/job-text properly triggers CompanyVerifier."""
        sample_text = (
            "Position: Senior Backend Engineer\n"
            "Company: Acme Dynamic Cloud Pvt. Ltd.\n"
            "We are seeking a senior python engineer with 5 years experience in building APIs. "
            "Competitive salary, private medical insurance, and 28 days leave."
        )

        response = test_client.post(
            "/api/v1/analyze/job-text",
            json={
                "text": sample_text,
                "company_name": "Acme Dynamic Cloud Pvt. Ltd.",
                "cin": "U72200MH2020PTC123456",
            },
        )
        assert response.status_code == 200
        data = response.json()

        # Verify company_verification summary
        cv = data["company_verification"]
        assert cv is not None
        assert cv["status"] == "MATCHED"
        assert cv["matched_name"] == "ACME DYNAMIC CLOUD PRIVATE LIMITED"
        assert cv["cin"] == "U72200MH2020PTC123456"
        assert cv["mca_status"] == "ACTIVE"
        assert cv["dpiit_status"] == "RECOGNIZED"
        assert cv["is_fraud_signal"] is False

        # Verify evidence list contains company verification item with source & timestamp
        company_evidence = [
            e for e in data["evidence"]
            if e["source_name"] == "MCA-21 & DPIIT Registry Verifier"
        ]
        assert len(company_evidence) >= 1
        ev = company_evidence[0]
        assert ev["status"] == "DETECTED"
        assert ev["details"]["source"] == "MCA Company Master Data"
        assert ev["details"]["timestamp"] is not None
        assert ev["details"]["dataset_version"] is not None

    def test_analyze_job_text_no_match_does_not_inflate_fraud_score(
        self, test_client: TestClient, populated_companies
    ):
        """Guarantee: NO_MATCH on company verification never increases fraud score or flags fraud."""
        sample_legitimate_text = (
            "Position: Customer Service Representative\n"
            "Company: Nonexistent Greenfield Enterprise LLC\n"
            "We are hiring a representative to answer incoming customer support requests. "
            "Work from office, salary INR 30000 per month, standard shifts, laptop provided at office."
        )

        response = test_client.post(
            "/api/v1/analyze/job-text",
            json={
                "text": sample_legitimate_text,
                "company_name": "Nonexistent Greenfield Enterprise LLC",
            },
        )
        assert response.status_code == 200
        data = response.json()

        cv = data["company_verification"]
        assert cv["status"] == "NO_MATCH"
        assert cv["is_fraud_signal"] is False

        # Company verification evidence item must have is_fraud_signal=False and not be counted as scam
        for ev in data["evidence"]:
            if ev["source_name"] == "MCA-21 & DPIIT Registry Verifier":
                assert ev["status"] == "UNVERIFIED"
                assert "NO_MATCH is NOT proof of fraud" in ev["limitations"]

        # Risk score must remain low or moderate based strictly on text, NOT marked high fraud due to NO_MATCH
        if data["risk_score"] is not None:
            assert data["risk_score"] < 60.0
            assert data["risk_category"] in ("LOW", "MODERATE")

    def test_analyze_job_text_persists_when_company_verification_db_errors(
        self, test_client: TestClient, db_session: Session
    ):
        """Regression test for UI error: 'Database persistence failed. Scan record could not be saved.'

        Verifies that when company registry lookup raises an unexpected DB exception,
        the transaction is rolled back cleanly, company status is reported as SOURCE_UNAVAILABLE,
        and scan records are successfully persisted without triggering HTTP 503.
        """
        from unittest.mock import patch
        from app.models.scan import ScanRequest

        sample_text = (
            "Position: Senior Backend Engineer\n"
            "We are seeking a senior python engineer with 5 years experience in building APIs. "
            "Competitive salary, private medical insurance, and 28 days leave."
        )

        orig_execute = db_session.execute
        called = False

        def fail_first_execute(*args, **kwargs):
            nonlocal called
            if not called:
                called = True
                raise Exception("Simulated relation failure / aborted transaction")
            return orig_execute(*args, **kwargs)

        with patch.object(db_session, "execute", side_effect=fail_first_execute):
            response = test_client.post(
                "/api/v1/analyze/job-text",
                json={
                    "text": sample_text,
                    "company_name": "Acme Dynamic Cloud Pvt. Ltd.",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["company_verification"]["status"] == "SOURCE_UNAVAILABLE"

        report_id = data["report_id"]
        persisted_scan = db_session.query(ScanRequest).filter(ScanRequest.id == report_id).first()
        assert persisted_scan is not None
        assert persisted_scan.status == "completed"
        assert len(persisted_scan.evidence_records) > 0
        assert len(persisted_scan.prediction_records) == 1


class TestMCARegressionSuite:
    """Regression test suite for MCA company verification conforming to requirements:
    1. A company present in the MCA source matches successfully and independently of DPIIT.
    2. A company absent from a successfully searched source returns NO_MATCH (not fraud).
    3. A source that has not been loaded returns SOURCE_UNAVAILABLE (never false NO_MATCH).
    4. MCA registration and DPIIT recognition remain strictly independent.
    """

    def test_company_present_in_mca_source_matches_independently(self, db_session: Session):
        """Verifies that an MCA-registered company matches without requiring a DPIIT record."""
        now = datetime.now(timezone.utc)
        company = Company(
            legal_name="INFOSYS LIMITED",
            normalized_name="INFOSYS LIMITED",
            cin="L85110KA1981PLC013115",
            entity_type="Public",
            registry_status="Active",
        )
        db_session.add(company)
        db_session.flush()

        source_rec = CompanySourceRecord(
            company_id=company.id,
            source_name="MCA_COMPANY_MASTER",
            source_url="https://data.gov.in/catalog/company-master-data",
            source_record_id="L85110KA1981PLC013115",
            source_status="Active",
            retrieved_at=now,
            source_updated_at=now - timedelta(days=30),
            match_method="CIN_EXACT",
            match_confidence=1.0,
            raw_metadata={"roc": "ROC Bangalore", "state": "Karnataka"},
        )
        db_session.add(source_rec)
        db_session.commit()

        verifier = CompanyVerifier()

        # 1. Match by legal name
        res_name = verifier.verify_company(query_name="Infosys Limited", db=db_session)
        assert res_name.status == "MATCHED"
        assert res_name.match_method in ("LEGAL_NAME_EXACT", "NORMALIZED_NAME_EXACT")
        assert res_name.company is not None
        assert res_name.company.legal_name == "INFOSYS LIMITED"
        assert res_name.mca_status == "Active"
        # DPIIT recognition is independent and not required
        assert res_name.dpiit_status in ("NOT_LOADED", "NOT_RECOGNIZED")
        assert res_name.is_fraud_signal is False

        # 2. Match by CIN
        res_cin = verifier.verify_company(cin="L85110KA1981PLC013115", db=db_session)
        assert res_cin.status == "MATCHED"
        assert res_cin.match_method == "CIN_EXACT"
        assert res_cin.company.cin == "L85110KA1981PLC013115"

        # 3. Match by abbreviation
        res_abbrev = verifier.verify_company(query_name="Infosys Ltd.", db=db_session)
        assert res_abbrev.status == "MATCHED"
        assert res_abbrev.confidence >= 0.95

    def test_company_absent_from_successfully_searched_mca_source(
        self, db_session: Session, populated_companies
    ):
        """Verifies that when MCA source IS loaded, an absent company returns NO_MATCH (not fraud)."""
        verifier = CompanyVerifier()
        result = verifier.verify_company(
            query_name="Totally Nonexistent Random Enterprise 12345",
            cin="U99999XX2099PTC999999",
            db=db_session,
        )

        assert result.status == "NO_MATCH"
        assert result.match_method == "NO_MATCH"
        assert result.confidence == 0.0
        assert result.company is None
        assert result.mca_status == "NOT_FOUND"
        assert result.is_fraud_signal is False
        assert "NO_MATCH is NOT proof of fraud" in result.limitations

    def test_mca_source_not_loaded_returns_source_unavailable(self, db_session: Session):
        """Verifies that when MCA dataset is NOT loaded into database, verifier returns SOURCE_UNAVAILABLE,
        never falsely returning NO_MATCH as though the dataset was searched.
        """
        # Ensure database is completely empty (no companies, no source records, no dataset imports)
        verifier = CompanyVerifier()
        assert verifier.is_mca_source_loaded(db_session) is False

        result = verifier.verify_company(
            query_name="Infosys Limited",
            cin="L85110KA1981PLC013115",
            db=db_session,
        )

        assert result.status == "SOURCE_UNAVAILABLE"
        assert result.match_method == "SOURCE_NOT_LOADED"
        assert result.confidence == 0.0
        assert result.company is None
        assert result.mca_status == "NOT_LOADED"
        assert result.dpiit_status == "NOT_LOADED"
        assert result.is_fraud_signal is False
        assert "not loaded in the database" in result.summary
        assert "NO_MATCH is not returned because the registry dataset has not been loaded" in result.limitations

    def test_analyze_job_text_endpoint_source_not_loaded_truthful_status(
        self, test_client: TestClient, db_session: Session
    ):
        """Integration test: When DB has no MCA records, API returns SOURCE_UNAVAILABLE and does not flag fraud."""
        sample_text = (
            "Position: Software Engineer\n"
            "Company: Infosys Limited\n"
            "We are hiring a software engineer for full stack cloud applications. "
            "Competitive compensation, standard benefits, Bangalore location."
        )

        response = test_client.post(
            "/api/v1/analyze/job-text",
            json={
                "text": sample_text,
                "company_name": "Infosys Limited",
            },
        )
        assert response.status_code == 200
        data = response.json()

        cv = data["company_verification"]
        assert cv["status"] == "SOURCE_UNAVAILABLE"
        assert cv["match_method"] == "SOURCE_NOT_LOADED"
        assert cv["mca_status"] == "NOT_LOADED"
        assert cv["is_fraud_signal"] is False
        assert "not loaded in the database" in cv["summary"]

        # Risk score must remain low/moderate based strictly on text; NOT flagged as fraud
        if data["risk_score"] is not None:
            assert data["risk_score"] < 60.0
            assert data["risk_category"] in ("LOW", "MODERATE")

    def test_partial_mca_import_truthful_scope_disclosure(self, db_session: Session):
        """Regression test: Partial MCA import discloses sample scope in NO_MATCH, never claiming complete search."""
        from app.models.ml import DatasetImport

        # Seed a small sample import audit record
        audit = DatasetImport(
            dataset_name="MCA_COMPANY_MASTER",
            version_or_snapshot="2026-10-13",
            license="Government Open Data License - India (GODL)",
            row_count=50,
            validation_summary={"total_rows_read": 50, "per_file_metrics": {"part1.csv": {"rows_read": 50}}},
        )
        db_session.add(audit)

        # Seed 1 active company
        c = Company(
            legal_name="SAMPLE ACTIVE CORP PRIVATE LIMITED",
            normalized_name="SAMPLE ACTIVE CORP PRIVATE LIMITED",
            cin="U72200MH2021PTC999999",
            entity_type="PRIVATE LIMITED",
            registry_status="ACTIVE",
        )
        db_session.add(c)
        db_session.flush()

        sr = CompanySourceRecord(
            company_id=c.id,
            source_name="MCA_COMPANY_MASTER",
            source_record_id="U72200MH2021PTC999999",
            retrieved_at=datetime.now(timezone.utc),
            match_method="DIRECT_IMPORT",
            match_confidence=1.0,
        )
        db_session.add(sr)
        db_session.commit()

        verifier = CompanyVerifier()
        coverage = verifier.get_mca_coverage_status(db_session)
        assert coverage["is_loaded"] is True
        assert coverage["is_partial"] is True

        # Query a company not in this 1-record sample (e.g. Infosys)
        res = verifier.verify_company(
            query_name="Infosys Limited",
            cin="L85110KA1981PLC013115",
            db=db_session,
        )

        assert res.status == "NO_MATCH"
        assert res.is_fraud_signal is False
        assert "indexed MCA registry sample" in res.summary
        assert "does not represent the complete nationwide MCA-21 registry" in res.summary
        assert "Partial Sample" in res.source_name
        assert "partial development sample" in res.limitations
        assert "NO_MATCH is NOT proof of fraud" in res.limitations

    def test_partial_mca_import_matched_company_keeps_dpiit_independent(self, db_session: Session):
        """Regression test: MCA match succeeds in partial dataset while keeping DPIIT status independent."""
        from app.models.ml import DatasetImport

        audit = DatasetImport(
            dataset_name="MCA_COMPANY_MASTER",
            version_or_snapshot="2026-10-13",
            license="GODL",
            row_count=100,
        )
        db_session.add(audit)

        c = Company(
            legal_name="SAMPLE CORP PRIVATE LIMITED",
            normalized_name="SAMPLE CORP PRIVATE LIMITED",
            cin="U12345KA2020PTC111111",
            entity_type="PRIVATE LIMITED",
            registry_status="ACTIVE",
        )
        db_session.add(c)
        db_session.flush()

        sr = CompanySourceRecord(
            company_id=c.id,
            source_name="MCA_COMPANY_MASTER",
            source_record_id="U12345KA2020PTC111111",
            retrieved_at=datetime.now(timezone.utc),
            match_method="CIN_EXACT",
            match_confidence=1.0,
        )
        db_session.add(sr)
        db_session.commit()

        verifier = CompanyVerifier()
        res = verifier.verify_company(
            cin="U12345KA2020PTC111111",
            db=db_session,
        )

        assert res.status == "MATCHED"
        assert res.match_method == "CIN_EXACT"
        assert res.confidence == 1.0
        assert res.mca_status == "ACTIVE"
        # DPIIT status is independently NOT_LOADED when DPIIT data is not present
        assert res.dpiit_status == "NOT_LOADED"
        assert res.is_fraud_signal is False

