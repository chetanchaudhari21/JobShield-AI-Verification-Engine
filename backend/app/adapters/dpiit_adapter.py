"""DPIIT Recognized Startup Data Import Adapter for JobShield AI.

Conforms to Feature F2 and Section 8 of PROJECT_SPECIFICATION.md:
- Ingests DPIIT startup catalog extract from converted PDF CSV
- Explicitly treats source, coverage, license, and currency as unverified until confirmed
- Preserves the original source page from the 87-page PDF extraction
- Retains unverified status: unverified DPIIT data is NEVER presented as confirmed current recognition
- Prevents unsafe entity merges from name similarity alone (creates separate entity if ambiguous)
- Enforces strict idempotency on repeated imports
- Dry-run mode performs zero database mutations
"""

import csv
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import ImportStats, compute_file_sha256
from app.models.company import Company, CompanySourceRecord, StartupRecognition
from app.models.ml import DatasetImport
from app.verification.normalization import normalize_company_name

logger = logging.getLogger("jobshield.adapters.dpiit")

DEFAULT_DPIIT_SOURCE_NAME = "DPIIT_STARTUP_LIST"
DEFAULT_DPIIT_SOURCE_URL = "UNVERIFIED"
DEFAULT_DPIIT_LICENSE = "UNVERIFIED"
DEFAULT_DPIIT_SNAPSHOT_DATE = "UNVERIFIED"
DEFAULT_DPIIT_FILE = "ml/data/dpiit/startuplist_converted.csv"

PROVENANCE_CAVEAT = (
    "Extracted from 87-page PDF startuplist (1,886 extracted rows). "
    "Source, coverage, license, and currency are unverified until confirmed. "
    "Incomplete extract; do not assume nationwide registry completeness."
)


class DPIITImportAdapter:
    """Import adapter for DPIIT-recognized startup data extracted from PDF."""

    def __init__(
        self,
        source_name: str = DEFAULT_DPIIT_SOURCE_NAME,
        source_url: str = DEFAULT_DPIIT_SOURCE_URL,
        license_text: str = DEFAULT_DPIIT_LICENSE,
        snapshot_date: str = DEFAULT_DPIIT_SNAPSHOT_DATE,
    ):
        self.source_name = source_name
        self.source_url = source_url
        self.license_text = license_text
        self.snapshot_date = snapshot_date

    def resolve_file_path(self, file_path: Optional[Any] = None) -> Optional[str]:
        """Resolves target DPIIT CSV file path."""
        if isinstance(file_path, list):
            target = file_path[0] if file_path else DEFAULT_DPIIT_FILE
        else:
            target = file_path if file_path else DEFAULT_DPIIT_FILE
        if os.path.exists(target):
            return os.path.abspath(target)
        logger.warning("DPIIT CSV file not found: %s", target)
        return None

    def import_file(
        self,
        db_session: Optional[Session] = None,
        file_path: Optional[str] = None,
        batch_size: int = 500,
        limit: Optional[int] = None,
        dry_run: bool = False,
    ) -> ImportStats:
        """
        Executes import of converted DPIIT startup CSV data with source page preservation,
        strict unverified status tracking, and safe non-merging protections.
        """
        resolved_path = self.resolve_file_path(file_path)
        stats = ImportStats(
            dataset_name=self.source_name,
            version_or_snapshot=self.snapshot_date,
            source_url=self.source_url,
            license=self.license_text,
        )

        if not resolved_path:
            stats.errors.append(f"Target DPIIT CSV file does not exist: {file_path or DEFAULT_DPIIT_FILE}")
            stats.end_time = datetime.now(timezone.utc)
            return stats

        # Compute file checksum (SHA-256)
        try:
            stats.file_checksums[os.path.basename(resolved_path)] = compute_file_sha256(resolved_path)
        except Exception as e:
            logger.warning("Could not calculate checksum for %s: %s", resolved_path, e)

        try:
            snapshot_dt = datetime.strptime(self.snapshot_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            snapshot_dt = None  # None for UNVERIFIED

        linked_to_existing = 0
        new_companies_created = 0
        seen_dpiit_numbers: set = set()

        try:
            with open(resolved_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f)

                for row_idx, row in enumerate(reader, start=1):
                    stats.total_rows_read += 1

                    raw_name = (row.get("Name Of Entity") or "").strip()
                    dpiit_num = (row.get("DPIIT Number") or "").strip()
                    source_page_str = (row.get("Source Page") or "").strip()
                    sector = (row.get("Sector") or "").strip()
                    industry = (row.get("Industry") or "").strip()
                    district = (row.get("District") or "").strip()

                    # Rejection check: Missing entity name
                    if not raw_name:
                        stats.rejected_rows += 1
                        stats.rejection_reasons["missing_entity_name"] = (
                            stats.rejection_reasons.get("missing_entity_name", 0) + 1
                        )
                        continue

                    # Deduplicate in run if duplicate recognition id
                    if dpiit_num:
                        if dpiit_num in seen_dpiit_numbers:
                            stats.skipped_rows += 1
                            stats.duplicate_identifiers += 1
                            stats.rejection_reasons["duplicate_dpiit_number_in_batch"] = (
                                stats.rejection_reasons.get("duplicate_dpiit_number_in_batch", 0) + 1
                            )
                            continue
                        seen_dpiit_numbers.add(dpiit_num)

                    stats.accepted_rows += 1

                    # Preserve source page (convert to int if possible, else keep string)
                    try:
                        source_page_val: Any = int(source_page_str)
                    except ValueError:
                        source_page_val = source_page_str or None

                    normalized = normalize_company_name(raw_name)

                    # Metadata payload containing explicit unverified status
                    raw_meta = {
                        "original_row_number": row_idx,
                        "source_page": source_page_val,
                        "dpiit_number": dpiit_num or None,
                        "sector": sector or None,
                        "industry": industry or None,
                        "district": district or None,
                        "coverage_status": "unverified",
                        "license_status": "unverified",
                        "currency_status": "unverified",
                        "is_confirmed_current_recognition": False,
                        "registry_completeness": "incomplete_extract",
                        "provenance_caveat": PROVENANCE_CAVEAT,
                    }

                    status_details = {
                        "original_row_number": row_idx,
                        "source_page": source_page_val,
                        "sector": sector or None,
                        "industry": industry or None,
                        "district": district or None,
                        "claimed_status": "RECOGNIZED",
                        "verification_status": "UNVERIFIED",
                        "is_confirmed_current_recognition": False,
                        "coverage_verified": False,
                        "currency_verified": False,
                        "verification_caveat": PROVENANCE_CAVEAT,
                    }

                    if not dry_run and db_session is not None:
                        # Check if this exact DPIIT recognition already exists (Idempotency)
                        existing_recognition = None
                        if dpiit_num:
                            existing_recognition = db_session.execute(
                                select(StartupRecognition).where(StartupRecognition.recognition_id == dpiit_num)
                            ).scalar_one_or_none()

                        if existing_recognition:
                            # Update existing recognition idempotently
                            existing_recognition.checked_at = datetime.now(timezone.utc)
                            existing_recognition.status_details = status_details
                            existing_recognition.recognition_status = "UNVERIFIED"

                            # Update source record
                            existing_src = db_session.execute(
                                select(CompanySourceRecord).where(
                                    CompanySourceRecord.company_id == existing_recognition.company_id,
                                    CompanySourceRecord.source_name == self.source_name,
                                    CompanySourceRecord.source_record_id == dpiit_num,
                                )
                            ).scalar_one_or_none()
                            if existing_src:
                                existing_src.retrieved_at = datetime.now(timezone.utc)
                                existing_src.raw_metadata = raw_meta
                                existing_src.source_status = "UNVERIFIED_EXTRACT"
                        else:
                            # Safe merge check: Only merge if exactly ONE unambiguous company matches
                            matching_companies = db_session.execute(
                                select(Company).where(Company.normalized_name == normalized)
                            ).scalars().all()

                            if len(matching_companies) == 1:
                                # Safe single match
                                linked_to_existing += 1
                                company_target = matching_companies[0]
                                match_method = "NAME_EXACT_UNVERIFIED_LINK"
                                match_confidence = 0.85
                            else:
                                # Either 0 matches, or >1 matches (ambiguous!).
                                # When multiple exist, NEVER guess or merge unsafely.
                                new_companies_created += 1
                                company_target = Company(
                                    legal_name=raw_name,
                                    normalized_name=normalized,
                                    cin=None,
                                    entity_type="Startup",
                                    registry_status="Unverified",
                                )
                                match_method = "DIRECT_IMPORT"
                                match_confidence = 1.0
                                if len(matching_companies) > 1:
                                    raw_meta["ambiguous_candidates_detected"] = len(matching_companies)
                                    status_details["ambiguous_candidates_detected"] = len(matching_companies)

                                db_session.add(company_target)
                                db_session.flush()

                            source_rec = CompanySourceRecord(
                                company_id=company_target.id,
                                source_name=self.source_name,
                                source_url=self.source_url,
                                source_record_id=dpiit_num or None,
                                source_status="UNVERIFIED_EXTRACT",
                                source_updated_at=snapshot_dt,
                                match_method=match_method,
                                match_confidence=match_confidence,
                                raw_metadata=raw_meta,
                            )
                            # Crucial: Marked 'UNVERIFIED', never presented as confirmed current recognition
                            recognition = StartupRecognition(
                                company_id=company_target.id,
                                recognition_status="UNVERIFIED",
                                recognition_id=dpiit_num or None,
                                source_url=self.source_url,
                                status_details=status_details,
                            )
                            db_session.add(source_rec)
                            db_session.add(recognition)
                            stats.imported_recognitions += 1
                            stats.imported_source_records += 1
                            if match_method == "DIRECT_IMPORT":
                                stats.imported_companies += 1

                            if stats.accepted_rows % batch_size == 0:
                                db_session.commit()
                    else:
                        # In dry-run mode, count prospective imports
                        stats.imported_recognitions += 1
                        stats.imported_source_records += 1

                    if limit is not None and stats.accepted_rows >= limit:
                        break

        except Exception as exc:
            logger.error("Error processing DPIIT CSV file %s: %s", resolved_path, exc, exc_info=True)
            stats.error_count += 1
            stats.errors.append(f"{os.path.basename(resolved_path)}: {str(exc)}")

        stats.end_time = datetime.now(timezone.utc)
        stats.validation_summary = {
            "source_file": os.path.basename(resolved_path),
            "file_checksums": stats.file_checksums,
            "source_page_count": 87,
            "total_rows_read": stats.total_rows_read,
            "accepted_rows": stats.accepted_rows,
            "imported_recognitions": stats.imported_recognitions,
            "linked_to_existing_companies": linked_to_existing,
            "new_companies_created": new_companies_created,
            "skipped_rows": stats.skipped_rows,
            "rejected_rows": stats.rejected_rows,
            "duplicate_identifiers": stats.duplicate_identifiers,
            "rejection_reasons": stats.rejection_reasons,
            "error_count": stats.error_count,
            "dry_run": dry_run,
            "coverage_verified": False,
            "license_verified": False,
            "currency_verified": False,
            "recognition_confirmed": False,
            "provenance_caveat": PROVENANCE_CAVEAT,
            "provenance_preserved": True,
            "duration_seconds": round(stats.duration_seconds, 2),
        }

        # Audit log in dataset_imports table ONLY when NOT in dry-run mode
        if not dry_run and db_session is not None:
            try:
                db_session.commit()
                import_audit = DatasetImport(
                    dataset_name=self.source_name,
                    version_or_snapshot=self.snapshot_date,
                    license=self.license_text,
                    source_url=self.source_url,
                    row_count=stats.imported_recognitions,
                    validation_summary=stats.validation_summary,
                )
                db_session.add(import_audit)
                db_session.commit()
            except Exception as audit_exc:
                logger.error("Failed to write dataset_imports audit log for DPIIT: %s", audit_exc)
                db_session.rollback()

        return stats
