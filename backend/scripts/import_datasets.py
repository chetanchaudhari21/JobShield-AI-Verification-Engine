"""Unified CLI script for importing company and startup datasets into JobShield AI.

Usage:
    python backend/scripts/import_datasets.py [mca|dpiit|all] [--limit N] [--dry-run]
"""

import argparse
import logging
import os
import sys

# Ensure backend directory is in sys.path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adapters.dpiit_adapter import DPIITImportAdapter
from app.adapters.mca_adapter import MCAImportAdapter
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("import_datasets")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified import tool for MCA Company Master and DPIIT Startup datasets."
    )
    parser.add_argument(
        "target",
        choices=["mca", "dpiit", "all"],
        default="all",
        nargs="?",
        help="Dataset to import: 'mca', 'dpiit', or 'all' (default: all).",
    )
    parser.add_argument(
        "--mca-files",
        nargs="+",
        default=None,
        help="Optional MCA CSV files to process.",
    )
    parser.add_argument(
        "--dpiit-file",
        type=str,
        default=None,
        help="Optional DPIIT CSV file path.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional row limit per dataset (useful for testing or partial import).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Batch insert commit size (default: 1000).",
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
        help="Parse and validate data without writing to database.",
    )

    args = parser.parse_args()

    total_errors = 0

    if args.dry_run:
        logger.info("Running in DRY-RUN mode: Database will not be accessed or modified.")
        if args.target in ("mca", "all"):
            mca_adapter = MCAImportAdapter()
            mca_stats = mca_adapter.import_files(
                db_session=None,
                file_paths=args.mca_files,
                batch_size=args.batch_size,
                limit=args.limit,
                dry_run=True,
            )
            print(f"\n[MCA Dry Run] Read: {mca_stats.total_rows_read:,}, Accepted: {mca_stats.accepted_rows:,}, Skipped: {mca_stats.skipped_rows:,} in {mca_stats.duration_seconds:.2f}s")
            total_errors += mca_stats.error_count

        if args.target in ("dpiit", "all"):
            dpiit_adapter = DPIITImportAdapter()
            dpiit_stats = dpiit_adapter.import_file(
                db_session=None,
                file_path=args.dpiit_file,
                batch_size=args.batch_size,
                limit=args.limit,
                dry_run=True,
            )
            print(f"\n[DPIIT Dry Run] Read: {dpiit_stats.total_rows_read:,}, Accepted: {dpiit_stats.accepted_rows:,}, Skipped: {dpiit_stats.skipped_rows:,} in {dpiit_stats.duration_seconds:.2f}s")
            print("Note: DPIIT source/coverage/license treated as UNVERIFIED. Source page preserved.")
            total_errors += dpiit_stats.error_count
    else:
        db_url = args.db_url or settings.DATABASE_URL
        engine_kwargs = {}
        if "sqlite" in db_url:
            engine_kwargs["connect_args"] = {"check_same_thread": False}

        engine = create_engine(db_url, **engine_kwargs)
        Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

        with Session() as session:
            if args.target in ("mca", "all"):
                mca_adapter = MCAImportAdapter()
                mca_stats = mca_adapter.import_files(
                    db_session=session,
                    file_paths=args.mca_files,
                    batch_size=args.batch_size,
                    limit=args.limit,
                    dry_run=False,
                )
                print(f"\n[MCA] Processed: {mca_stats.total_rows_read:,} rows, Ingested: {mca_stats.imported_companies:,} companies in {mca_stats.duration_seconds:.2f}s")
                total_errors += mca_stats.error_count

            if args.target in ("dpiit", "all"):
                dpiit_adapter = DPIITImportAdapter()
                dpiit_stats = dpiit_adapter.import_file(
                    db_session=session,
                    file_path=args.dpiit_file,
                    batch_size=args.batch_size,
                    limit=args.limit,
                    dry_run=False,
                )
                print(f"\n[DPIIT] Processed: {dpiit_stats.total_rows_read:,} rows, Recognitions: {dpiit_stats.imported_recognitions:,} in {dpiit_stats.duration_seconds:.2f}s")
                total_errors += dpiit_stats.error_count

    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
