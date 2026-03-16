"""
Data Migration 010: Split pXRF ExternalAnalysis Entries

Purpose
-------
Convert any ExternalAnalysis records of type "pXRF" that currently store
multiple reading numbers in a single row (comma-separated) into distinct rows
— one per reading. This restores the intended one-to-many relationship between
`SampleInfo` and pXRF readings.

The migration performs the following steps:

1. Locate ExternalAnalysis rows where `analysis_type == 'pXRF'` and
   `pxrf_reading_no` contains multiple values.
2. Normalize each reading number (handles whitespace, Excel float formats such
   as "12.0", etc.).
3. Update the original row to hold only the first reading number.
4. Create additional ExternalAnalysis rows for the remaining readings, copying
   metadata from the original record.
5. Avoid creating duplicates when a normalized reading already exists for the
   same sample.

Run in DRY RUN mode first. Pass "--apply" to commit changes.

Usage
-----

```
# Preview changes
python database/data_migrations/split_pxrf_external_analyses_010.py

# Apply changes
python database/data_migrations/split_pxrf_external_analyses_010.py --apply
```
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import List

# Ensure project root is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from sqlalchemy import and_
from sqlalchemy.orm import Session

from database import SessionLocal
from database.models.analysis import ExternalAnalysis
from utils.pxrf import split_normalized_pxrf_readings, normalize_pxrf_value


@dataclass
class MigrationStats:
    analyses_inspected: int = 0
    analyses_split: int = 0
    new_rows_created: int = 0
    duplicates_skipped: int = 0
    legacy_rows_deleted: int = 0


def split_pxrf_analysis(db: Session, analysis: ExternalAnalysis, stats: MigrationStats) -> None:
    stats.analyses_inspected += 1

    readings = split_normalized_pxrf_readings(analysis.pxrf_reading_no)
    if len(readings) <= 1:
        # Ensure single reading is normalized even if no split required
        if readings:
            normalized_value = readings[0]
            if analysis.pxrf_reading_no != normalized_value:
                analysis.pxrf_reading_no = normalized_value
        return

    stats.analyses_split += 1

    # Update existing row with first reading
    primary_reading = readings[0]
    analysis.pxrf_reading_no = primary_reading

    # Create new entries for remaining readings
    for reading_no in readings[1:]:
        existing = (
            db.query(ExternalAnalysis)
            .filter(
                ExternalAnalysis.sample_id == analysis.sample_id,
                ExternalAnalysis.analysis_type == 'pXRF',
                ExternalAnalysis.pxrf_reading_no == reading_no,
            )
            .first()
        )

        if existing:
            stats.duplicates_skipped += 1
            continue

        new_analysis = ExternalAnalysis(
            sample_id=analysis.sample_id,
            analysis_type='pXRF',
            pxrf_reading_no=reading_no,
            analysis_date=analysis.analysis_date,
            laboratory=analysis.laboratory,
            analyst=analysis.analyst,
            description=analysis.description,
            analysis_metadata=analysis.analysis_metadata,
            magnetic_susceptibility=analysis.magnetic_susceptibility,
        )
        db.add(new_analysis)
        stats.new_rows_created += 1


def run_migration(dry_run: bool = True) -> MigrationStats:
    stats = MigrationStats()

    with SessionLocal() as db:
        analyses: List[ExternalAnalysis] = (
            db.query(ExternalAnalysis)
            .filter(ExternalAnalysis.analysis_type == 'pXRF')
            .all()
        )

        for analysis in analyses:
            # Only split if multiple readings present
            normalized_value = normalize_pxrf_value(analysis.pxrf_reading_no)
            if not normalized_value:
                db.delete(analysis)
                stats.legacy_rows_deleted += 1
                continue

            if ',' not in normalized_value:
                if analysis.pxrf_reading_no != normalized_value:
                    analysis.pxrf_reading_no = normalized_value
                continue

            # Update the value first, then split
            analysis.pxrf_reading_no = normalized_value
            split_pxrf_analysis(db, analysis, stats)

        if dry_run:
            db.rollback()
        else:
            db.commit()

    return stats


def print_summary(stats: MigrationStats, dry_run: bool) -> None:
    mode = "DRY RUN" if dry_run else "APPLY"
    print("=" * 80)
    print(f"Split pXRF Analyses Migration ({mode})")
    print("=" * 80)
    print(f"Analyses inspected   : {stats.analyses_inspected}")
    print(f"Analyses split       : {stats.analyses_split}")
    print(f"New rows created     : {stats.new_rows_created}")
    print(f"Duplicates skipped   : {stats.duplicates_skipped}")
    print(f"Legacy rows removed  : {stats.legacy_rows_deleted}")
    print("=" * 80)
    if dry_run:
        print("No changes committed (dry run).")
    else:
        print("Changes committed successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Split multi-reading pXRF analyses")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes instead of running in dry-run mode",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    stats = run_migration(dry_run=dry_run)
    print_summary(stats, dry_run)


if __name__ == "__main__":
    main()


