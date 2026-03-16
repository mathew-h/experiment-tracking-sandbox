"""
Data Migration 009: Backfill and Normalize pXRF Readings

Purpose
-------
Ensure that every pXRF reading referenced by `ExternalAnalysis.pxrf_reading_no`
exists in the `PXRFReading` table (defined in `database/models/analysis.py`).
The script performs the following steps:

1. Iterates all samples and their external analyses of type "pXRF".
2. Splits and normalizes the recorded `pxrf_reading_no` values (handles comma-
   separated lists, trims whitespace, and removes Excel float artifacts such as
   "1.0").
3. For each normalized reading number:
   - Attempts to locate an existing `PXRFReading` record.
   - If only a non-normalized variant exists (e.g., "1.0"), renames it to the
     canonical form when safe to do so.
   - Creates placeholder `PXRFReading` rows (with null element values) when a
     referenced reading does not yet exist in the database.
4. Writes the normalized comma-separated reading list back to
   `ExternalAnalysis.pxrf_reading_no` so future ingestion logic works with the
   canonical identifiers expected by `backend/services/bulk_uploads/pxrf_data.py`.

Run this script in DRY RUN mode first to review the planned changes. Pass
"--apply" to persist modifications.

Usage
-----

```
# Dry run (no database changes)
python database/data_migrations/backfill_pxrf_readings_009.py

# Apply changes
python database/data_migrations/backfill_pxrf_readings_009.py --apply
```
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Dict, List

# Add project root to PYTHONPATH so we can import application modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from sqlalchemy.orm import Session

from database import SessionLocal
from database.models.analysis import ExternalAnalysis, PXRFReading
from database.models.samples import SampleInfo


def canonicalize_reading_number(value: object) -> str:
    """Return the canonical string representation of a pXRF reading number."""
    if value is None:
        return ""

    text = str(value).strip()
    if not text:
        return ""

    # Remove Excel float artifacts (e.g., "12.0" -> "12") when the string is numeric
    numeric_candidate = text.replace(".", "", 1).replace("-", "", 1)
    if numeric_candidate.isdigit():
        try:
            as_float = float(text)
            if as_float.is_integer():
                return str(int(as_float))
        except ValueError:
            pass

    return text


def split_reading_numbers(raw_value: str) -> List[str]:
    """Split a comma-separated list of reading numbers into canonical tokens."""
    if not raw_value:
        return []

    tokens: List[str] = []
    for token in raw_value.split(","):
        canonical = canonicalize_reading_number(token)
        if canonical:
            tokens.append(canonical)
    return tokens


@dataclass
class MigrationStats:
    analyses_processed: int = 0
    analyses_updated: int = 0
    readings_created: int = 0
    readings_renamed: int = 0
    readings_already_present: int = 0
    samples_with_pxrf: int = 0
    missing_after_attempt: int = 0
    legacy_rows_deleted: int = 0


class PXRFBackfillService:
    """Encapsulate the backfill logic for easier testing and reuse."""

    def __init__(self, db: Session, stats: MigrationStats) -> None:
        self.db = db
        self.stats = stats
        self._load_existing_readings()

    def _load_existing_readings(self) -> None:
        self.readings_by_exact: Dict[str, PXRFReading] = {}
        self.readings_by_canonical: Dict[str, PXRFReading] = {}

        all_rows = self.db.query(PXRFReading).all()
        for row in all_rows:
            exact = row.reading_no
            canonical = canonicalize_reading_number(exact)
            self.readings_by_exact[exact] = row
            # Prefer first occurrence; if duplicates exist canonical map will keep the first
            self.readings_by_canonical.setdefault(canonical, row)

    def ensure_reading(self, token: str) -> PXRFReading:
        """Ensure a PXRFReading row exists for the supplied token."""
        # 1. Exact match
        existing = self.readings_by_exact.get(token)
        if existing:
            self.stats.readings_already_present += 1
            return existing

        # 2. Canonical match
        existing = self.readings_by_canonical.get(token)
        if existing:
            self.stats.readings_already_present += 1
            return existing

        # 3. Attempt to find variant (e.g., "12.0" vs "12") and rename if safe
        variant = None
        for exact_value, reading in list(self.readings_by_exact.items()):
            canonical = canonicalize_reading_number(exact_value)
            if canonical == token:
                variant = reading
                break

        if variant is not None:
            # Only rename when the canonical target is unused
            if token in self.readings_by_exact:
                # Another row already claims the canonical key; keep existing definition
                self.stats.readings_already_present += 1
                return variant

            old_key = variant.reading_no
            variant.reading_no = token
            self.readings_by_exact.pop(old_key, None)
            self.readings_by_exact[token] = variant
            self.readings_by_canonical[token] = variant
            self.stats.readings_renamed += 1
            return variant

        # 4. Create placeholder row
        placeholder = PXRFReading(reading_no=token)
        self.db.add(placeholder)
        self.readings_by_exact[token] = placeholder
        self.readings_by_canonical[token] = placeholder
        self.stats.readings_created += 1
        return placeholder

    def process_analysis(self, analysis: ExternalAnalysis) -> None:
        reading_tokens = split_reading_numbers(analysis.pxrf_reading_no or "")
        if not reading_tokens:
            self.db.delete(analysis)
            self.stats.legacy_rows_deleted += 1
            return

        canonical_tokens: List[str] = []
        unresolved_tokens: List[str] = []

        for token in reading_tokens:
            if not token:
                continue

            reading = self.ensure_reading(token)
            if reading:
                canonical_tokens.append(token)
            else:
                unresolved_tokens.append(token)

        if unresolved_tokens:
            self.stats.missing_after_attempt += len(unresolved_tokens)

        original_value = analysis.pxrf_reading_no
        normalized_value = ",".join(canonical_tokens)

        if normalized_value != (original_value or ""):
            analysis.pxrf_reading_no = normalized_value
            self.stats.analyses_updated += 1


def process(dry_run: bool = True) -> MigrationStats:
    stats = MigrationStats()

    with SessionLocal() as db:
        service = PXRFBackfillService(db, stats)

        samples = (
            db.query(SampleInfo)
            .join(ExternalAnalysis, SampleInfo.sample_id == ExternalAnalysis.sample_id)
            .filter(ExternalAnalysis.analysis_type == "pXRF")
            .all()
        )

        stats.samples_with_pxrf = len(samples)

        for sample in samples:
            analyses = [
                analysis
                for analysis in sample.external_analyses
                if analysis.analysis_type == "pXRF"
            ]

            if not analyses:
                continue

            for analysis in analyses:
                stats.analyses_processed += 1
                service.process_analysis(analysis)

        if dry_run:
            db.rollback()
        else:
            db.commit()

    return stats


def print_summary(stats: MigrationStats, dry_run: bool) -> None:
    mode = "DRY RUN" if dry_run else "APPLY"
    print("=" * 80)
    print(f"PXRF Backfill Migration ({mode} mode)")
    print("=" * 80)
    print(f"Samples with pXRF analyses        : {stats.samples_with_pxrf}")
    print(f"pXRF analyses processed           : {stats.analyses_processed}")
    print(f"Analyses normalized               : {stats.analyses_updated}")
    print(f"PXRF readings already present     : {stats.readings_already_present}")
    print(f"PXRF readings renamed (canonical) : {stats.readings_renamed}")
    print(f"PXRF readings created (placeholder): {stats.readings_created}")
    print(f"Legacy empty pXRF analyses removed  : {stats.legacy_rows_deleted}")
    if stats.missing_after_attempt:
        print(f"WARNING: {stats.missing_after_attempt} readings still unresolved")
    print("=" * 80)
    if dry_run:
        print("No changes were committed (dry run).")
    else:
        print("Changes committed successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill canonical PXRF readings")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes to the database (default: dry run)",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    stats = process(dry_run=dry_run)
    print_summary(stats, dry_run)


if __name__ == "__main__":
    main()


