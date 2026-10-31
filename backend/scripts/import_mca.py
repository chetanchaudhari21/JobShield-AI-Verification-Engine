"""CLI script for importing MCA Company Master Data into JobShield AI.

Usage:
    python backend/scripts/import_mca.py [--files FILE [FILE ...]] [--batch-size 1000] [--limit 5000] [--dry-run]
"""

import argparse
import json
import logging
import os
import sys

# Ensure backend directory is in sys.path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adapters.mca_adapter import (
    DEFAULT_MCA_FILES,
    DEFAULT_MCA_LICENSE,
    DEFAULT_MCA_SNAPSHOT_DATE,
    DEFAULT_MCA_SOURCE_NAME,
    DEFAULT_MCA_SOURCE_URL,
    MCAImportAdapter,
)
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("import_mca")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import Ministry of Corporate Affairs (MCA) Company Master Data CSV files."
    )
    parser.add_argument(
        "--files",
        nargs="+",
        default=None,
        help="One or more CSV file paths to import. Defaults to standard ml/data/mca part files.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Number of records to buffer before committing to database (default: 5000).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of records to import (useful for testing or partial loads).",
    )
    parser.add_argument(
        "--source-name",
        type=str,
        default=DEFAULT_MCA_SOURCE_NAME,
        help=f"Dataset identifier name (default: {DEFAULT_MCA_SOURCE_NAME}).",
    )
    parser.add_argument(
        "--source-url",
        type=str,
        default=DEFAULT_MCA_SOURCE_URL,
        help=f"Data catalog URL (default: {DEFAULT_MCA_SOURCE_URL}).",
    )
    parser.add_argument(
        "--license",
        type=str,
        default=DEFAULT_MCA_LICENSE,
        help=f"License terms string (default: {DEFAULT_MCA_LICENSE}).",
    )
    parser.add_argument(
        "--snapshot-date",
        type=str,
        default=DEFAULT_MCA_SNAPSHOT_DATE,
        help=f"Snapshot / update date (default: {DEFAULT_MCA_SNAPSHOT_DATE}).",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Optional database connection URL override.",
    )
    parser.add_argument(
        "--cins",
        nargs="+",
        default=None,
        help="Optional list of specific CINs to target for selective/idempotent import.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate CSV files without committing to database.",
    )

    args = parser.parse_args()

    adapter = MCAImportAdapter(
        source_name=args.source_name,
        source_url=args.source_url,
        license_text=args.license,
        snapshot_date=args.snapshot_date,
    )

    if args.dry_run:
        logger.info("Running in DRY-RUN mode: Database will not be accessed or modified.")
        stats = adapter.import_files(
            db_session=None,
            file_paths=args.files,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=True,
            target_cins=args.cins,
        )
    else:
        db_url = args.db_url or settings.DATABASE_URL
        logger.info("Initializing database connection (sanitized: %s)...", db_url.split("@")[-1] if "@" in db_url else db_url)
        engine_kwargs = {}
        if "sqlite" in db_url:
            engine_kwargs["connect_args"] = {"check_same_thread": False}

        engine = create_engine(db_url, **engine_kwargs)
        Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

        with Session() as session:
            stats = adapter.import_files(
                db_session=session,
                file_paths=args.files,
                batch_size=args.batch_size,
                limit=args.limit,
                dry_run=False,
                target_cins=args.cins,
            )

    print("\n" + "=" * 60)
    print(" MCA COMPANY MASTER DATA IMPORT REPORT")
    print("=" * 60)
    print(f"Dataset Name:         {stats.dataset_name}")
    print(f"Snapshot / Date:      {stats.version_or_snapshot}")
    print(f"Source URL:           {stats.source_url}")
    print(f"License:              {stats.license}")
    print(f"Total Rows Read:      {stats.total_rows_read:,}")
    print(f"Accepted Rows:        {stats.accepted_rows:,}")
    print(f"Rejected Rows:        {stats.rejected_rows:,}")
    print(f"Skipped (Dups):       {stats.skipped_rows:,}")
    print(f"Duplicate Identifiers:{stats.duplicate_identifiers:,}")
    print(f"Companies Prospective:{stats.imported_companies:,}")
    print(f"Source Records:       {stats.imported_source_records:,}")
    print(f"Errors:               {stats.error_count}")
    print(f"Elapsed Time:         {stats.duration_seconds:.2f} seconds")
    print(f"Dry Run:              {args.dry_run}")
    print("-" * 60)
    if stats.file_checksums:
        print("File Checksums (SHA-256):")
        for fn, cs in stats.file_checksums.items():
            print(f"  {fn}: {cs}")
    if stats.validation_summary.get("per_file_metrics"):
        print("Per-File Ingestion Breakdown:")
        for fn, pfm in stats.validation_summary["per_file_metrics"].items():
            print(
                f"  [{fn}] Size: {pfm['size_bytes']:,} B | Read: {pfm['rows_read']:,} | "
                f"Accepted: {pfm['accepted_rows']:,} | Skipped: {pfm['skipped_rows']:,} | "
                f"Rejected: {pfm['rejected_rows']:,} | Time: {pfm['duration_seconds']}s"
            )
    if stats.rejection_reasons:
        print("Rejection Breakdown:")
        for r, cnt in stats.rejection_reasons.items():
            print(f"  - {r}: {cnt:,}")
    print("=" * 60)

    if stats.errors:
        print("Encountered errors:")
        for err in stats.errors[:10]:
            print(f"  - {err}")

    return 0 if stats.error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
