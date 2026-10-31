"""MCA Company Master Data Import Adapter for JobShield AI.

Conforms to Feature F2 and Section 8 of PROJECT_SPECIFICATION.md:
- Streams CSV datasets without loading the full multi-gigabyte dataset into memory
- Records source name, URL, snapshot/last-updated date, license, checksums, and row counts in dataset_imports
- Normalizes company names while preserving original legal names and source provenance
- Keeps detailed metadata (ROC, state, capital, registration date) in company_source_records
- Enforces strict idempotency on repeated runs
- Dry-run mode performs zero database mutations
"""

import csv
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import ImportStats, compute_file_sha256
from app.models.company import Company, CompanySourceRecord
from app.models.ml import DatasetImport
from app.verification.normalization import normalize_company_name

logger = logging.getLogger("jobshield.adapters.mca")

DEFAULT_MCA_SOURCE_NAME = "MCA_COMPANY_MASTER"
DEFAULT_MCA_SOURCE_URL = "https://data.gov.in/catalog/company-master-data"
DEFAULT_MCA_LICENSE = "Government Open Data License - India (GODL)"
DEFAULT_MCA_SNAPSHOT_DATE = "2026-10-13"

DEFAULT_MCA_FILES = [
    "ml/data/mca/company_master_data_2026-10-13_part1.csv",
    "ml/data/mca/company_master_data_2026-10-13_part2.csv",
    "ml/data/mca/company_master_data_2026-10-13_part3.csv",
    "ml/data/mca/company_master_data_2026-10-13_part4.csv",
]


class MCAImportAdapter:
    """Import adapter for Ministry of Corporate Affairs (MCA) Company Master Data CSV files."""

    def __init__(
        self,
        source_name: str = DEFAULT_MCA_SOURCE_NAME,
        source_url: str = DEFAULT_MCA_SOURCE_URL,
        license_text: str = DEFAULT_MCA_LICENSE,
        snapshot_date: str = DEFAULT_MCA_SNAPSHOT_DATE,
    ):
        self.source_name = source_name
        self.source_url = source_url
        self.license_text = license_text
        self.snapshot_date = snapshot_date

    def resolve_file_paths(self, file_paths: Optional[List[str]] = None) -> List[str]:
        """Resolves target files, checking ml/data/mca and fallback ml/mca directories."""
        resolved: List[str] = []
        candidates = file_paths if file_paths else DEFAULT_MCA_FILES

        for path in candidates:
            if os.path.exists(path):
                resolved.append(os.path.abspath(path))
            else:
                alt_path = path.replace("ml/data/mca", "ml/mca").replace("ml\\data\\mca", "ml\\mca")
                if os.path.exists(alt_path):
                    resolved.append(os.path.abspath(alt_path))
                else:
                    logger.warning("Specified MCA CSV file not found: %s", path)

        return resolved

    def import_files(
        self,
        db_session: Optional[Session] = None,
        file_paths: Optional[List[str]] = None,
        batch_size: int = 1000,
        limit: Optional[int] = None,
        dry_run: bool = False,
        target_cins: Optional[List[str]] = None,
    ) -> ImportStats:
        """
        Executes streaming batch import of MCA company master data CSV files.
        Enforces idempotency and guarantees zero database mutations when dry_run=True.
        Supports selective targeted CIN imports when target_cins is specified.
        """
        files_to_process = self.resolve_file_paths(file_paths)
        stats = ImportStats(
            dataset_name=self.source_name,
            version_or_snapshot=self.snapshot_date,
            source_url=self.source_url,
            license=self.license_text,
        )

        if not files_to_process:
            stats.errors.append("No valid MCA CSV files found to process.")
            stats.end_time = datetime.now(timezone.utc)
            return stats

        target_cin_set = {c.strip().upper() for c in target_cins if c.strip()} if target_cins else None

        # Compute file checksums (SHA-256)
        for fp in files_to_process:
            try:
                stats.file_checksums[os.path.basename(fp)] = compute_file_sha256(fp)
            except Exception as e:
                logger.warning("Could not calculate checksum for %s: %s", fp, e)

        try:
            snapshot_dt = datetime.strptime(self.snapshot_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            snapshot_dt = datetime.now(timezone.utc)

        seen_cins_in_run: set = set()
        per_file_metrics: Dict[str, Any] = {}
        batch_buffer: List[Dict[str, Any]] = []

        def _flush_buffer() -> None:
            if not batch_buffer or dry_run or db_session is None:
                batch_buffer.clear()
                return

            batch_cins = [item["cin"] for item in batch_buffer if item["cin"]]
            existing_companies: Dict[str, Company] = {}
            if batch_cins:
                stmt_c = select(Company).where(Company.cin.in_(batch_cins))
                for comp in db_session.execute(stmt_c).scalars().all():
                    existing_companies[comp.cin] = comp

            existing_sources: Dict[Tuple[int, Optional[str]], CompanySourceRecord] = {}
            if existing_companies:
                comp_ids = [c.id for c in existing_companies.values()]
                stmt_s = select(CompanySourceRecord).where(
                    CompanySourceRecord.company_id.in_(comp_ids),
                    CompanySourceRecord.source_name == self.source_name,
                )
                for sr in db_session.execute(stmt_s).scalars().all():
                    existing_sources[(sr.company_id, sr.source_record_id)] = sr

            new_companies: List[Company] = []
            for item in batch_buffer:
                cin = item["cin"]
                raw_name = item["raw_name"]
                normalized = item["normalized"]
                company_class = item["company_class"]
                company_status = item["company_status"]
                raw_meta = item["raw_meta"]

                existing_comp = existing_companies.get(cin) if cin else None
                if existing_comp:
                    existing_comp.legal_name = raw_name
                    existing_comp.normalized_name = normalized
                    existing_comp.registry_status = company_status
                    existing_comp.updated_at = datetime.now(timezone.utc)

                    sr_key = (existing_comp.id, cin)
                    existing_sr = existing_sources.get(sr_key)
                    if existing_sr:
                        existing_sr.retrieved_at = datetime.now(timezone.utc)
                        existing_sr.source_updated_at = snapshot_dt
                        existing_sr.source_status = company_status
                        existing_sr.raw_metadata = raw_meta
                    else:
                        source_rec = CompanySourceRecord(
                            company_id=existing_comp.id,
                            source_name=self.source_name,
                            source_url=self.source_url,
                            source_record_id=cin or None,
                            source_status=company_status,
                            source_updated_at=snapshot_dt,
                            match_method="CIN_EXACT",
                            match_confidence=1.0,
                            raw_metadata=raw_meta,
                        )
                        db_session.add(source_rec)
                    stats.imported_companies += 1
                    stats.imported_source_records += 1
                else:
                    company = Company(
                        legal_name=raw_name,
                        normalized_name=normalized,
                        cin=cin or None,
                        entity_type=company_class or "Company",
                        registry_status=company_status,
                    )
                    source_rec = CompanySourceRecord(
                        company=company,
                        source_name=self.source_name,
                        source_url=self.source_url,
                        source_record_id=cin or None,
                        source_status=company_status,
                        source_updated_at=snapshot_dt,
                        match_method="DIRECT_IMPORT",
                        match_confidence=1.0,
                        raw_metadata=raw_meta,
                    )
                    company.source_records.append(source_rec)
                    new_companies.append(company)
                    stats.imported_companies += 1
                    stats.imported_source_records += 1

            if new_companies:
                db_session.add_all(new_companies)

            db_session.commit()
            db_session.expunge_all()
            batch_buffer.clear()

        for file_path in files_to_process:
            file_basename = os.path.basename(file_path)
            file_start_time = datetime.now(timezone.utc)
            file_stats = {
                "file_path": file_path,
                "file_name": file_basename,
                "size_bytes": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                "sha256": stats.file_checksums.get(file_basename),
                "rows_read": 0,
                "accepted_rows": 0,
                "skipped_rows": 0,
                "rejected_rows": 0,
                "rejection_reasons": {},
                "duration_seconds": 0.0,
            }

            logger.info("Reading MCA dataset file: %s", file_path)
            try:
                with open(file_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
                    reader = csv.DictReader(f)

                    for line_idx, row in enumerate(reader, start=2):
                        cin = (row.get("CIN") or "").strip()

                        # If targeted CINs specified, skip non-matching rows
                        if target_cin_set is not None and cin.upper() not in target_cin_set:
                            continue

                        stats.total_rows_read += 1
                        file_stats["rows_read"] += 1
                        raw_name = (row.get("Company Name") or "").strip()

                        # Rejection check: Missing mandatory company name
                        if not raw_name:
                            stats.rejected_rows += 1
                            file_stats["rejected_rows"] += 1
                            stats.rejection_reasons["missing_company_name"] = (
                                stats.rejection_reasons.get("missing_company_name", 0) + 1
                            )
                            file_stats["rejection_reasons"]["missing_company_name"] = (
                                file_stats["rejection_reasons"].get("missing_company_name", 0) + 1
                            )
                            continue

                        # Deduplicate across files if identical CIN encountered in the same run
                        if cin:
                            if cin in seen_cins_in_run:
                                stats.skipped_rows += 1
                                file_stats["skipped_rows"] += 1
                                stats.duplicate_identifiers += 1
                                stats.rejection_reasons["duplicate_cin_in_batch"] = (
                                    stats.rejection_reasons.get("duplicate_cin_in_batch", 0) + 1
                                )
                                file_stats["rejection_reasons"]["duplicate_cin_in_batch"] = (
                                    file_stats["rejection_reasons"].get("duplicate_cin_in_batch", 0) + 1
                                )
                                continue
                            seen_cins_in_run.add(cin)

                        stats.accepted_rows += 1
                        file_stats["accepted_rows"] += 1
                        normalized = normalize_company_name(raw_name)
                        company_class = (row.get("Company Class") or "").strip() or None
                        company_status = (row.get("Company Status") or "").strip() or "Active"

                        raw_meta = {
                            "cin": cin or None,
                            "registration_date": (row.get("Company Registration Date") or "").strip() or None,
                            "category": (row.get("Company Category") or "").strip() or None,
                            "sub_category": (row.get("Company Sub Category") or "").strip() or None,
                            "class": company_class,
                            "listing_status": (row.get("Listing Status") or "").strip() or None,
                            "authorized_capital": (row.get("Authorized Capital") or "").strip() or None,
                            "paidup_capital": (row.get("Paidup Capital") or "").strip() or None,
                            "roc": (row.get("Company ROC") or "").strip() or None,
                            "address": (row.get("Company Address") or "").strip() or None,
                            "pin_code": (row.get("Pin Code") or "").strip() or None,
                            "state": (row.get("Company State") or "").strip() or None,
                            "status": company_status,
                            "industrial_classification": (row.get("Company Industrial Classification") or "").strip() or None,
                            "source_file": file_basename,
                            "source_line": line_idx,
                            "source_checksum": stats.file_checksums.get(file_basename),
                        }

                        if dry_run or db_session is None:
                            # In dry-run mode, count as prospective import
                            stats.imported_companies += 1
                            stats.imported_source_records += 1
                        else:
                            batch_buffer.append({
                                "cin": cin,
                                "raw_name": raw_name,
                                "normalized": normalized,
                                "company_class": company_class,
                                "company_status": company_status,
                                "raw_meta": raw_meta,
                            })
                            if len(batch_buffer) >= batch_size:
                                _flush_buffer()
                                if stats.accepted_rows % 50000 == 0:
                                    logger.info(
                                        "File %s: Ingested %s rows so far (elapsed: %.1fs)...",
                                        file_basename,
                                        f"{stats.accepted_rows:,}",
                                        (datetime.now(timezone.utc) - stats.start_time).total_seconds(),
                                    )

                        if limit is not None and stats.accepted_rows >= limit:
                            break

                    _flush_buffer()

            except Exception as exc:
                logger.error("Error processing file %s: %s", file_path, exc, exc_info=True)
                stats.error_count += 1
                stats.errors.append(f"{os.path.basename(file_path)}: {str(exc)}")

            file_stats["duration_seconds"] = round(
                (datetime.now(timezone.utc) - file_start_time).total_seconds(), 2
            )
            per_file_metrics[file_basename] = file_stats

            if limit is not None and stats.accepted_rows >= limit:
                break

        stats.end_time = datetime.now(timezone.utc)
        stats.validation_summary = {
            "processed_files": [os.path.basename(p) for p in files_to_process],
            "file_checksums": stats.file_checksums,
            "per_file_metrics": per_file_metrics,
            "total_rows_read": stats.total_rows_read,
            "accepted_rows": stats.accepted_rows,
            "imported_companies": stats.imported_companies,
            "imported_source_records": stats.imported_source_records,
            "skipped_rows": stats.skipped_rows,
            "rejected_rows": stats.rejected_rows,
            "duplicate_identifiers": stats.duplicate_identifiers,
            "rejection_reasons": stats.rejection_reasons,
            "error_count": stats.error_count,
            "dry_run": dry_run,
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
                    row_count=stats.imported_companies,
                    validation_summary=stats.validation_summary,
                )
                db_session.add(import_audit)
                db_session.commit()
            except Exception as audit_exc:
                logger.error("Failed to write dataset_imports audit log: %s", audit_exc)
                db_session.rollback()

        return stats
