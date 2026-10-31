"""CLI script for importing DPIIT Recognized Startup Data into JobShield AI.

Usage:
    python backend/scripts/import_dpiit.py [--file FILE] [--batch-size 500] [--limit 1000] [--dry-run]
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

from app.adapters.dpiit_adapter import (
    DEFAULT_DPIIT_FILE,
    DEFAULT_DPIIT_LICENSE,
    DEFAULT_DPIIT_SNAPSHOT_DATE,
    DEFAULT_DPIIT_SOURCE_NAME,
    DEFAULT_DPIIT_SOURCE_URL,
    DPIITImportAdapter,
)
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("import_dpiit")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import DPIIT Recognized Startup Data CSV extracted from PDF catalog."
    )
    parser.add_argument(
        "--file",
        type=str,
        default=DEFAULT_DPIIT_FILE,
        help=f"Path to DPIIT startup converted CSV file (default: {DEFAULT_DPIIT_FILE}).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of records to buffer before committing to database (default: 500).",
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
        default=DEFAULT_DPIIT_SOURCE_NAME,
        help=f"Dataset identifier name (default: {DEFAULT_DPIIT_SOURCE_NAME}).",
    )
    parser.add_argument(
        "--source-url",
        type=str,
        default=DEFAULT_DPIIT_SOURCE_URL,
        help=f"Data catalog URL (default: {DEFAULT_DPIIT_SOURCE_URL}).",
    )
    parser.add_argument(
        "--license",
        type=str,
        default=DEFAULT_DPIIT_LICENSE,
        help=f"License terms string (default: {DEFAULT_DPIIT_LICENSE}).",
    )
    parser.add_argument(
        "--snapshot-date",
        type=str,
        default=DEFAULT_DPIIT_SNAPSHOT_DATE,
        help=f"Snapshot / update date (default: {DEFAULT_DPIIT_SNAPSHOT_DATE}).",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Optional database connection URL override.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate CSV file without committing to database.",
    )

    args = parser.parse_args()

    adapter = DPIITImportAdapter(
        source_name=args.source_name,
        source_url=args.source_url,
        license_text=args.license,
        snapshot_date=args.snapshot_date,
    )

    if args.dry_run:
        logger.info("Running in DRY-RUN mode: Database will not be accessed or modified.")
        stats = adapter.import_file(
            db_session=None,
            file_path=args.file,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=True,
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
            stats = adapter.import_file(
                db_session=session,
                file_path=args.file,
                batch_size=args.batch_size,
                limit=args.limit,
                dry_run=False,
            )

    print("\n" + "=" * 60)
    print(" DPIIT STARTUP DATA IMPORT REPORT")
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
    print(f"Startup Recognitions: {stats.imported_recognitions:,}")
    print(f"Errors:               {stats.error_count}")
    print(f"Elapsed Time:         {stats.duration_seconds:.2f} seconds")
    print(f"Dry Run:              {args.dry_run}")
    print("-" * 60)
    if stats.file_checksums:
        print("File Checksums (SHA-256):")
        for fn, cs in stats.file_checksums.items():
            print(f"  {fn}: {cs}")
    if stats.rejection_reasons:
        print("Rejection Breakdown:")
        for r, cnt in stats.rejection_reasons.items():
            print(f"  - {r}: {cnt:,}")
    print("-" * 60)
    print("IMPORTANT CAVEAT:")
    print("  Coverage, license, and currency are UNVERIFIED until confirmed.")
    print("  Extracted from 87-page PDF (1,886 rows). Preserved source page.")
    print("  Incomplete extract; do not assume nationwide registry completeness.")
    print("  All entities recorded as UNVERIFIED, not confirmed current recognition.")
    print("=" * 60)

    if stats.errors:
        print("Encountered errors:")
        for err in stats.errors[:10]:
            print(f"  - {err}")

    return 0 if stats.error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
