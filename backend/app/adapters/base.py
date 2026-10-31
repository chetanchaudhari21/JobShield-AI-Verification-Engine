"""Base classes and data transfer structures for dataset import adapters.

Enforces Section 8 & Feature F2 of PROJECT_SPECIFICATION.md:
- Full provenance recording in dataset_imports
- Structured execution metrics and validation summaries
- Transactional chunking and error tracking
"""

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def compute_file_sha256(file_path: str, chunk_size: int = 1024 * 1024) -> str:
    """Computes SHA-256 checksum for a file streaming in chunks."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class ImportStats:
    """Runtime statistics collected during dataset ingestion."""

    dataset_name: str
    version_or_snapshot: str
    source_url: Optional[str]
    license: str
    total_rows_read: int = 0
    imported_companies: int = 0
    imported_source_records: int = 0
    imported_recognitions: int = 0
    accepted_rows: int = 0
    skipped_rows: int = 0
    rejected_rows: int = 0
    duplicate_identifiers: int = 0
    error_count: int = 0
    errors: List[str] = field(default_factory=list)
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    file_checksums: Dict[str, str] = field(default_factory=dict)
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    validation_summary: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return (datetime.now(timezone.utc) - self.start_time).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "version_or_snapshot": self.version_or_snapshot,
            "source_url": self.source_url,
            "license": self.license,
            "total_rows_read": self.total_rows_read,
            "accepted_rows": self.accepted_rows,
            "imported_companies": self.imported_companies,
            "imported_source_records": self.imported_source_records,
            "imported_recognitions": self.imported_recognitions,
            "skipped_rows": self.skipped_rows,
            "rejected_rows": self.rejected_rows,
            "duplicate_identifiers": self.duplicate_identifiers,
            "rejection_reasons": self.rejection_reasons,
            "file_checksums": self.file_checksums,
            "error_count": self.error_count,
            "duration_seconds": round(self.duration_seconds, 2),
            "validation_summary": self.validation_summary,
        }
