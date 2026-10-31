"""Company Name Matching and Verification Service for JobShield AI.

Conforms to Feature F2 and Section 8 of PROJECT_SPECIFICATION.md:
- Matches company entities using legal name, trade name, abbreviations, punctuation normalization, and CIN.
- Returns explicit status: MATCHED, NO_MATCH, UNKNOWN, STALE, and SOURCE_UNAVAILABLE.
- Enforces strict rule: NO_MATCH MUST NEVER BE PRESENTED AS FRAUD.
- MCA registration and DPIIT recognition are separate statuses; neither validates a specific job or recruiter.
- Embeds source, timestamp, and dataset version into evidence records.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
import logging
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.company import Company, CompanySourceRecord, StartupRecognition
from app.models.ml import DatasetImport
from app.schemas.analysis import CompanyVerificationSummary, EvidenceItem
from app.verification.normalization import (
    extract_company_stem,
    normalize_company_name,
)

logger = logging.getLogger("jobshield.verification.company")

# Default staleness threshold: records older than 365 days without updates are flagged as STALE
DEFAULT_STALENESS_DAYS = 365


class VerificationStatus(str, Enum):
    MATCHED = "MATCHED"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
    NO_MATCH = "NO_MATCH"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


class MatchMethod(str, Enum):
    CIN_EXACT = "CIN_EXACT"
    LEGAL_NAME_EXACT = "LEGAL_NAME_EXACT"
    NORMALIZED_NAME_EXACT = "NORMALIZED_NAME_EXACT"
    ABBREVIATION_MATCH = "ABBREVIATION_MATCH"
    TRADE_NAME_EXACT = "TRADE_NAME_EXACT"
    STEM_SIMILARITY = "STEM_SIMILARITY"
    AMBIGUOUS_BRAND = "AMBIGUOUS_BRAND"
    NO_MATCH = "NO_MATCH"
    NO_QUERY = "NO_QUERY"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    SOURCE_NOT_LOADED = "SOURCE_NOT_LOADED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


@dataclass
class CompanyMatchResult:
    status: VerificationStatus
    match_method: MatchMethod
    confidence: float
    company: Optional[Company]
    summary: str
    limitations: str
    mca_status: Optional[str]
    dpiit_status: Optional[str]
    source_name: Optional[str]
    dataset_version: Optional[str]
    checked_at: datetime
    queried_name: Optional[str] = None
    is_fraud_signal: bool = False  # NO_MATCH is NEVER a fraud signal
    candidate_entities: Optional[List[Dict[str, Any]]] = None


class CompanyVerifier:
    """Verifies employer legal entities against sourced MCA-21 and DPIIT registries."""

    def __init__(self, staleness_days: int = DEFAULT_STALENESS_DAYS):
        self.staleness_days = staleness_days

    def verify_company(
        self,
        query_name: Optional[str] = None,
        cin: Optional[str] = None,
        db: Optional[Session] = None,
        is_ambiguous: bool = False,
        candidate_names: Optional[List[str]] = None,
    ) -> CompanyMatchResult:
        now = datetime.now(timezone.utc)
        clean_name = query_name.strip() if query_name else ""
        clean_cin = cin.strip().upper() if cin else ""

        # 0. Ambiguous query check (conflicting candidate names found in text)
        if is_ambiguous:
            cands_str = ", ".join(repr(c) for c in (candidate_names or []))
            return CompanyMatchResult(
                status=VerificationStatus.UNKNOWN,
                match_method=MatchMethod.NO_QUERY,
                confidence=0.0,
                company=None,
                summary=f"Ambiguous company name: multiple conflicting candidates identified in text ({cands_str}).",
                limitations="Company verification could not be performed because the claimed employer name is ambiguous. Please specify the company name explicitly in the separate company-name field.",
                mca_status=None,
                dpiit_status=None,
                source_name=None,
                dataset_version=None,
                checked_at=now,
                queried_name=None,
                is_fraud_signal=False,
            )

        # 1. Edge Case: Empty or insufficient query
        if not clean_name and not clean_cin:
            return CompanyMatchResult(
                status=VerificationStatus.UNKNOWN,
                match_method=MatchMethod.NO_QUERY,
                confidence=0.0,
                company=None,
                summary="No company name or Corporate Identification Number (CIN) provided for entity corroboration.",
                limitations="Entity verification requires a company name or registration identifier.",
                mca_status=None,
                dpiit_status=None,
                source_name=None,
                dataset_version=None,
                checked_at=now,
                queried_name=None,
                is_fraud_signal=False,
            )

        # 2. Edge Case: Database session unavailable
        if db is None:
            return CompanyMatchResult(
                status=VerificationStatus.SOURCE_UNAVAILABLE,
                match_method=MatchMethod.DATABASE_UNAVAILABLE,
                confidence=0.0,
                company=None,
                summary="MCA-21 / DPIIT registry databases are currently unavailable for verification lookup.",
                limitations="Database connection unavailable; entity existence cannot be confirmed.",
                mca_status="SOURCE_UNAVAILABLE",
                dpiit_status="SOURCE_UNAVAILABLE",
                source_name=None,
                dataset_version=None,
                checked_at=now,
                queried_name=clean_name or None,
                is_fraud_signal=False,
            )

        try:
            # 2b. Check if required official MCA registry source is loaded in the database
            mca_loaded = self.is_mca_source_loaded(db)
            dpiit_loaded = self.is_dpiit_source_loaded(db)

            if not mca_loaded:
                return CompanyMatchResult(
                    status=VerificationStatus.SOURCE_UNAVAILABLE,
                    match_method=MatchMethod.SOURCE_NOT_LOADED,
                    confidence=0.0,
                    company=None,
                    summary=(
                        f"Official MCA-21 company registry dataset is not loaded in the database. "
                        f"Entity verification for '{clean_name or clean_cin}' could not be completed against the required source."
                    ),
                    limitations=(
                        "Entity verification requires the official MCA-21 company registry dataset to be imported into the database. "
                        "NO_MATCH is not returned because the registry dataset has not been loaded or searched."
                    ),
                    mca_status="NOT_LOADED",
                    dpiit_status="NOT_LOADED" if not dpiit_loaded else "NOT_RECOGNIZED",
                    source_name="MCA_COMPANY_MASTER (NOT_LOADED)",
                    dataset_version=None,
                    checked_at=now,
                    queried_name=clean_name or None,
                    is_fraud_signal=False,
                )

            matched_company: Optional[Company] = None
            method: MatchMethod = MatchMethod.NO_MATCH
            confidence: float = 0.0

            # 3. Match by CIN if available (highest confidence: 1.0)
            if clean_cin:
                matched_company = db.execute(
                    select(Company).where(func.upper(Company.cin) == clean_cin)
                ).scalar_one_or_none()
                if matched_company:
                    method = MatchMethod.CIN_EXACT
                    confidence = 1.0

            # 4. Match by Name if CIN not provided or CIN did not match
            if not matched_company and clean_name:
                norm_query = normalize_company_name(clean_name)
                stem_query = extract_company_stem(norm_query)

                # 4a. Exact raw legal name (case-insensitive)
                matched_company = db.execute(
                    select(Company).where(func.upper(Company.legal_name) == clean_name.upper())
                ).scalar_one_or_none()
                if matched_company:
                    method = MatchMethod.LEGAL_NAME_EXACT
                    confidence = 1.0

                # 4b. Exact normalized name (case-insensitive)
                if not matched_company and norm_query:
                    candidates = db.execute(
                        select(Company).where(func.upper(Company.normalized_name) == norm_query.upper())
                    ).scalars().all()
                    if len(candidates) == 1:
                        matched_company = candidates[0]
                        # Check if abbreviation difference was reconciled
                        if norm_query != clean_name.upper():
                            method = MatchMethod.ABBREVIATION_MATCH
                            confidence = 0.95
                        else:
                            method = MatchMethod.NORMALIZED_NAME_EXACT
                            confidence = 0.98
                    elif len(candidates) > 1:
                        # Ambiguous: multiple companies have the same normalized name
                        # Pick matching active one if available, but lower confidence
                        matched_company = next(
                            (c for c in candidates if (c.registry_status or "").upper() == "ACTIVE"), candidates[0]
                        )
                        method = MatchMethod.NORMALIZED_NAME_EXACT
                        confidence = 0.90

                # 4c. Stem match (if query stem is sufficiently distinctive >= 5 chars, case-insensitive)
                brand_candidates: List[Company] = []
                if not matched_company and stem_query and len(stem_query) >= 5:
                    stem_candidates = db.execute(
                        select(Company).where(Company.normalized_name.ilike(f"{stem_query}%"))
                    ).scalars().all()

                    # Find exact stem matches among candidates
                    exact_stem_matches = [
                        c for c in stem_candidates if extract_company_stem(c.normalized_name) == stem_query
                    ]
                    if len(exact_stem_matches) == 1:
                        matched_company = exact_stem_matches[0]
                        method = MatchMethod.STEM_SIMILARITY
                        confidence = 0.85
                    elif len(exact_stem_matches) > 1:
                        matched_company = next(
                            (c for c in exact_stem_matches if (c.registry_status or "").upper() == "ACTIVE"),
                            exact_stem_matches[0],
                        )
                        method = MatchMethod.STEM_SIMILARITY
                        confidence = 0.80

                    # 4d. Trade Name / Brand Prefix match (distinctive brand query >= 5 chars)
                    # When no exact stem matches were found, check if candidates start with brand prefix on a word boundary
                    if not matched_company:
                        brand_candidates = [
                            c for c in stem_candidates
                            if c.normalized_name.upper().startswith(f"{stem_query} ")
                        ]
                        if len(brand_candidates) == 1:
                            # Unique brand-to-entity match
                            matched_company = brand_candidates[0]
                            method = MatchMethod.TRADE_NAME_EXACT
                            confidence = 0.85
                        elif len(brand_candidates) > 1:
                            # Multiple plausible entities exist under this brand name (e.g. Capgemini)
                            # Invariants:
                            # - Do NOT automatically select an entity solely because it is Active, a PLC, or has higher capital.
                            # - Retain a safe non-match and explicitly explain the ambiguity.
                            matched_company = None

            # 5. Handle NO_MATCH (source was successfully searched, but entity was not found)
            if not matched_company:
                coverage = self.get_mca_coverage_status(db)
                candidate_dicts: Optional[List[Dict[str, Any]]] = None

                if brand_candidates and len(brand_candidates) > 1:
                    # Ambiguous trade-name / brand-prefix query with multiple plausible entities
                    cands_list = [
                        f"'{c.legal_name}' ({c.registry_status or 'Unknown'}, CIN: {c.cin or 'N/A'})"
                        for c in brand_candidates[:4]
                    ]
                    cands_str = "; ".join(cands_list)
                    if len(brand_candidates) > 4:
                        cands_str += f"; and {len(brand_candidates) - 4} more"

                    summary = (
                        f"Query '{clean_name}' matches {len(brand_candidates)} distinct registered entities "
                        f"in the official MCA-21 company registry with differing corporate statuses: {cands_str}. "
                        f"Verification cannot automatically select an entity without an explicit statutory legal name or CIN."
                    )
                    limitations = (
                        f"IMPORTANT: Multiple legal entities operate under or share the brand prefix '{clean_name}'. "
                        f"To verify corporate standing, submit the exact registered legal name or 21-character Corporate "
                        f"Identification Number (CIN). Neither AMBIGUOUS_MATCH nor NO_MATCH is a fraud signal."
                    )
                    candidate_dicts = [
                        {
                            "legal_name": c.legal_name,
                            "cin": c.cin,
                            "registry_status": c.registry_status,
                            "entity_type": c.entity_type,
                        }
                        for c in brand_candidates
                    ]
                    return CompanyMatchResult(
                        status=VerificationStatus.AMBIGUOUS_MATCH,
                        match_method=MatchMethod.AMBIGUOUS_BRAND,
                        confidence=0.0,
                        company=None,
                        summary=summary,
                        limitations=limitations,
                        mca_status="AMBIGUOUS",
                        dpiit_status="NOT_FOUND" if dpiit_loaded else "NOT_LOADED",
                        source_name="MCA_COMPANY_MASTER",
                        dataset_version=self._get_dataset_version(db),
                        checked_at=now,
                        queried_name=clean_name or None,
                        is_fraud_signal=False,  # Core mandate: AMBIGUOUS_MATCH is NEVER fraud
                        candidate_entities=candidate_dicts,
                    )

                if coverage["is_partial"]:
                    source_desc = f"MCA_COMPANY_MASTER (Partial Sample: {coverage['indexed_count']:,} records indexed)"
                    summary = (
                        f"No corporate entity matching '{clean_name or clean_cin}' was found "
                        f"in the indexed MCA registry sample ({coverage['indexed_count']:,} records). "
                        f"This indexed sample does not represent the complete nationwide MCA-21 registry."
                    )
                    limitations = (
                        f"IMPORTANT: The local database currently indexes a partial development sample "
                        f"({coverage['indexed_count']:,} records) of the official MCA-21 company registry. "
                        f"Absence from this sample does NOT mean the company is missing from the nationwide "
                        f"MCA-21 registry. Furthermore, NO_MATCH is NOT proof of fraud."
                    )
                else:
                    source_desc = "MCA_COMPANY_MASTER"
                    summary = (
                        f"No corporate entity matching '{clean_name or clean_cin}' was found "
                        f"in the official MCA-21 company registry."
                    )
                    limitations = (
                        "IMPORTANT: NO_MATCH is NOT proof of fraud. Legitimate entities, LLPs, "
                        "sole proprietorships, foreign organizations, and newly formed ventures "
                        "may not be indexed in this registry snapshot."
                    )

                return CompanyMatchResult(
                    status=VerificationStatus.NO_MATCH,
                    match_method=MatchMethod.NO_MATCH,
                    confidence=0.0,
                    company=None,
                    summary=summary,
                    limitations=limitations,
                    mca_status="NOT_FOUND",
                    dpiit_status="NOT_FOUND" if dpiit_loaded else "NOT_LOADED",
                    source_name=source_desc,
                    dataset_version=self._get_dataset_version(db),
                    checked_at=now,
                    queried_name=clean_name or None,
                    is_fraud_signal=False,  # Core mandate: NO_MATCH is NEVER fraud
                    candidate_entities=None,
                )

            # 6. Check for STALE data
            is_stale, record_date, dataset_ver = self._check_staleness(matched_company, db, now)
            status = VerificationStatus.STALE if is_stale else VerificationStatus.MATCHED

            # 7. Extract separate MCA and DPIIT statuses
            mca_status = matched_company.registry_status or "Unknown"

            # Check DPIIT startup recognition independently
            dpiit_rec = next(iter(matched_company.startup_recognitions), None)
            if dpiit_rec:
                dpiit_status = dpiit_rec.recognition_status
                if dpiit_rec.status_details and dpiit_rec.status_details.get("claimed_status"):
                    dpiit_status = f"{dpiit_rec.recognition_status} (Extracted: {dpiit_rec.status_details['claimed_status']})"
            elif dpiit_loaded:
                dpiit_status = "NOT_RECOGNIZED"
            else:
                dpiit_status = "NOT_LOADED"

            source_name = "MCA_COMPANY_MASTER"
            if matched_company.source_records:
                source_name = ", ".join(sorted({sr.source_name for sr in matched_company.source_records}))

            summary = (
                f"Matched registered entity '{matched_company.legal_name}' "
                f"(CIN: {matched_company.cin or 'None'}, MCA Status: {mca_status}, "
                f"DPIIT Recognition: {dpiit_status}) using {method.value} "
                f"(confidence: {int(confidence * 100)}%)."
            )
            if is_stale:
                summary += f" [CAUTION: Sourced record is STALE; last updated {record_date}]."
            if method == MatchMethod.TRADE_NAME_EXACT:
                summary += f" [NOTE: Matched via brand/trade name prefix '{clean_name}'; the queried brand name differs from the official registered legal name '{matched_company.legal_name}']."

            limitations = (
                "MCA registration validates company existence and corporate registry standing only; "
                "it does NOT authenticate any individual recruiter, email sender, or job opening. "
                "DPIIT recognition is a separate status and does not certify recruitment legitimacy."
            )

            return CompanyMatchResult(
                status=status,
                match_method=method,
                confidence=confidence,
                company=matched_company,
                summary=summary,
                limitations=limitations,
                mca_status=mca_status,
                dpiit_status=dpiit_status,
                source_name=source_name,
                dataset_version=dataset_ver,
                checked_at=now,
                queried_name=clean_name or (matched_company.legal_name if matched_company else None),
                is_fraud_signal=False,
            )

        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            logger.error("Error executing company verification: %s", exc, exc_info=True)
            return CompanyMatchResult(
                status=VerificationStatus.SOURCE_UNAVAILABLE,
                match_method=MatchMethod.DATABASE_UNAVAILABLE,
                confidence=0.0,
                company=None,
                summary=f"Registry lookup encountered an unexpected error: {type(exc).__name__}.",
                limitations="Verification could not be completed due to a temporary internal database error.",
                mca_status="SOURCE_UNAVAILABLE",
                dpiit_status="SOURCE_UNAVAILABLE",
                source_name=None,
                dataset_version=None,
                checked_at=now,
                queried_name=clean_name or None,
                is_fraud_signal=False,
            )

    def is_mca_source_loaded(self, db: Session) -> bool:
        """Determines if the official MCA company master data has been loaded into the database."""
        # 1. Check if dataset_imports recorded an MCA import
        has_mca_import = db.execute(
            select(DatasetImport.id).where(DatasetImport.dataset_name.ilike("%MCA%")).limit(1)
        ).scalar()
        if has_mca_import is not None:
            return True

        # 2. Check if company_source_records contains any MCA records
        has_mca_source = db.execute(
            select(CompanySourceRecord.id).where(CompanySourceRecord.source_name.ilike("%MCA%")).limit(1)
        ).scalar()
        if has_mca_source is not None:
            return True

        # 3. If companies table is completely empty, MCA data is definitely not loaded
        has_any_company = db.execute(select(Company.id).limit(1)).scalar()
        if has_any_company is None:
            return False

        # 4. If companies exist, check whether they are exclusively from other sources (e.g. DPIIT)
        has_other_import = db.execute(
            select(DatasetImport.id).where(~DatasetImport.dataset_name.ilike("%MCA%")).limit(1)
        ).scalar()
        has_other_source = db.execute(
            select(CompanySourceRecord.id).where(~CompanySourceRecord.source_name.ilike("%MCA%")).limit(1)
        ).scalar()
        has_startup_rec = db.execute(select(StartupRecognition.id).limit(1)).scalar()

        if (
            (has_other_import is not None or has_other_source is not None or has_startup_rec is not None)
            and (has_mca_import is None and has_mca_source is None)
        ):
            return False

        # 5. Otherwise companies exist without explicit non-MCA source flags (e.g. basic unit test fixtures)
        return True

    def get_mca_coverage_status(self, db: Session) -> Dict[str, Any]:
        """
        Determines the coverage status of MCA data in the database.
        Returns a dictionary with:
        - is_loaded: bool
        - is_partial: bool
        - indexed_count: int
        - coverage_label: str
        """
        mca_loaded = self.is_mca_source_loaded(db)
        if not mca_loaded:
            return {
                "is_loaded": False,
                "is_partial": False,
                "indexed_count": 0,
                "coverage_label": "NOT_LOADED",
            }

        # Check total MCA records in database
        mca_count = db.execute(
            select(func.count(Company.id)).where(Company.cin.isnot(None))
        ).scalar() or 0

        # Check latest dataset_imports for MCA
        latest_import = db.execute(
            select(DatasetImport).where(DatasetImport.dataset_name.ilike("%MCA%")).order_by(DatasetImport.imported_at.desc()).limit(1)
        ).scalar_one_or_none()

        # If total indexed MCA companies < 1,000,000, this is a bounded/partial sample
        # (Full MCA dataset has 3,192,605 companies across 4 parts)
        is_partial = False
        if mca_count < 1_000_000:
            is_partial = True
        elif latest_import and latest_import.validation_summary:
            per_file = latest_import.validation_summary.get("per_file_metrics", {})
            if len(per_file) < 4:
                is_partial = True

        label = f"Partial Sample ({mca_count:,} records indexed)" if is_partial else "Full Registry Snapshot"

        return {
            "is_loaded": True,
            "is_partial": is_partial,
            "indexed_count": mca_count,
            "coverage_label": label,
        }

    def is_dpiit_source_loaded(self, db: Session) -> bool:
        """Determines if the DPIIT startup dataset has been loaded into the database."""
        has_import = db.execute(
            select(DatasetImport.id).where(DatasetImport.dataset_name.ilike("%DPIIT%")).limit(1)
        ).scalar()
        if has_import is not None:
            return True

        has_rec = db.execute(select(StartupRecognition.id).limit(1)).scalar()
        return has_rec is not None

    def _check_staleness(
        self,
        company: Company,
        db: Session,
        now: datetime,
    ) -> tuple[bool, str, str]:
        """Determines whether matched record is older than staleness threshold."""
        dataset_version = self._get_dataset_version(db)
        staleness_cutoff = now - timedelta(days=self.staleness_days)

        latest_dt: Optional[datetime] = None
        for sr in company.source_records:
            cand_dt = sr.source_updated_at or sr.retrieved_at
            if cand_dt:
                # Ensure timezone aware
                if cand_dt.tzinfo is None:
                    cand_dt = cand_dt.replace(tzinfo=timezone.utc)
                if latest_dt is None or cand_dt > latest_dt:
                    latest_dt = cand_dt

        if latest_dt is None:
            latest_dt = company.updated_at or company.created_at
            if latest_dt and latest_dt.tzinfo is None:
                latest_dt = latest_dt.replace(tzinfo=timezone.utc)

        if latest_dt and latest_dt < staleness_cutoff:
            return True, latest_dt.strftime("%Y-%m-%d"), dataset_version

        return False, latest_dt.strftime("%Y-%m-%d") if latest_dt else "current", dataset_version

    def _get_dataset_version(self, db: Session) -> str:
        """Retrieves most recent snapshot version recorded in dataset_imports."""
        try:
            latest_import = db.execute(
                select(DatasetImport).order_by(DatasetImport.imported_at.desc()).limit(1)
            ).scalar_one_or_none()
            if latest_import:
                return latest_import.version_or_snapshot
        except Exception:
            pass
        return "2026-10-13"

    def to_evidence_item(self, match: CompanyMatchResult) -> EvidenceItem:
        """Converts CompanyMatchResult into standard EvidenceItem schema."""
        details: Dict[str, Any] = {
            "source": match.source_name,
            "timestamp": match.checked_at.isoformat(),
            "dataset_version": match.dataset_version,
            "match_method": match.match_method.value,
            "match_confidence": match.confidence,
            "mca_status": match.mca_status,
            "dpiit_status": match.dpiit_status,
            "queried_name": match.queried_name,
        }
        if match.company:
            details["company_id"] = match.company.id
            details["legal_name"] = match.company.legal_name
            details["cin"] = match.company.cin
            details["entity_type"] = match.company.entity_type
        if match.candidate_entities:
            details["candidate_entities"] = match.candidate_entities
            details["is_ambiguous_brand"] = True
            details["brand_candidate_count"] = len(match.candidate_entities)

        ev_status = (
            "DETECTED"
            if match.status == VerificationStatus.MATCHED
            else "AMBIGUOUS"
            if match.status == VerificationStatus.AMBIGUOUS_MATCH
            else "UNVERIFIED"
        )
        return EvidenceItem(
            evidence_type="rule_signal",
            source_name="MCA-21 & DPIIT Registry Verifier",
            status=ev_status,
            confidence=match.confidence,
            summary=match.summary,
            limitations=match.limitations,
            details=details,
        )

    def to_summary_schema(self, match: CompanyMatchResult) -> CompanyVerificationSummary:
        """Converts CompanyMatchResult into CompanyVerificationSummary schema."""
        return CompanyVerificationSummary(
            status=match.status.value,
            company_id=match.company.id if match.company else None,
            queried_name=match.queried_name,
            matched_name=match.company.legal_name if match.company else None,
            cin=match.company.cin if match.company else None,
            match_method=match.match_method.value,
            match_confidence=match.confidence,
            mca_status=match.mca_status,
            dpiit_status=match.dpiit_status,
            source=match.source_name,
            dataset_version=match.dataset_version,
            checked_at=match.checked_at,
            summary=match.summary,
            limitations=match.limitations,
            is_fraud_signal=False,
            candidate_entities=match.candidate_entities,
        )
