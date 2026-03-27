"""Data migration 013 — Backfill sample_photos rows from filesystem.

Purpose
-------
When photos are dropped directly into the ``sample_photos/`` folder (instead
of being uploaded through the API), no database rows exist for them and the
frontend shows nothing.  This script walks the folder, compares against
existing ``sample_photos`` rows, and inserts a row for every file that is not
yet registered — without touching files that are already tracked.

Folder structure expected::

    <sample_photos_dir>/
        <sample_id>/
            photo1.jpg
            photo2.png
            ...

- Each subdirectory name is treated as a ``sample_id``.
- Only ``.jpg``, ``.jpeg``, and ``.png`` files are registered.
- Subdirectories whose name does not match any ``sample_info.sample_id`` row
  are skipped with a warning.
- Files already present in ``sample_photos.file_path`` are skipped (idempotent).

Usage
-----
Dry run (default — no database changes)::

    .venv\\Scripts\\python database/data_migrations/backfill_sample_photos_013.py

Apply changes::

    .venv\\Scripts\\python database/data_migrations/backfill_sample_photos_013.py --apply

Point at a different photos directory::

    .venv\\Scripts\\python database/data_migrations/backfill_sample_photos_013.py --apply --photos-dir /path/to/photos
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# sys.path bootstrap — make project root importable regardless of cwd
# ---------------------------------------------------------------------------
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal
from database.models.samples import SampleInfo, SamplePhotos

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png"})

MIME_MAP: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _known_sample_ids(db: Session) -> frozenset[str]:
    rows = db.execute(select(SampleInfo.sample_id)).scalars().all()
    return frozenset(rows)


def _existing_file_paths(db: Session) -> frozenset[str]:
    """Return the set of file_path values already registered in sample_photos."""
    rows = db.execute(select(SamplePhotos.file_path)).scalars().all()
    return frozenset(rows)


def _scan_photos_dir(photos_dir: Path) -> list[tuple[str, Path]]:
    """
    Walk ``photos_dir`` and return ``(sample_id, file_path)`` pairs for every
    supported image file found one level deep.
    """
    results: list[tuple[str, Path]] = []
    if not photos_dir.exists():
        print(f"[WARN] photos directory does not exist: {photos_dir}")
        return results

    for subdir in sorted(photos_dir.iterdir()):
        if not subdir.is_dir():
            continue
        sample_id = subdir.name
        for f in sorted(subdir.iterdir()):
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                results.append((sample_id, f))

    return results


# ---------------------------------------------------------------------------
# Main migration
# ---------------------------------------------------------------------------

def run(photos_dir: Path, apply: bool = False) -> None:
    db: Session = SessionLocal()
    try:
        print("=== Migration 013: backfill_sample_photos ===")
        if not apply:
            print("[INFO] DRY RUN — no changes will be committed. Pass --apply to persist.")
        print(f"[INFO] Scanning: {photos_dir.resolve()}\n")

        known_ids = _known_sample_ids(db)
        existing_paths = _existing_file_paths(db)

        candidates = _scan_photos_dir(photos_dir)
        print(f"[INFO] Found {len(candidates)} image file(s) across all subdirectories.\n")

        inserted = 0
        skipped_existing = 0
        skipped_unknown = 0

        for sample_id, file_path in candidates:
            if sample_id not in known_ids:
                print(f"  [SKIP] {sample_id}/{file_path.name} — sample_id not in sample_info")
                skipped_unknown += 1
                continue

            stored_path = str(file_path)
            if stored_path in existing_paths:
                skipped_existing += 1
                continue

            ext = file_path.suffix.lower()
            photo = SamplePhotos(
                sample_id=sample_id,
                file_path=stored_path,
                file_name=file_path.name,
                file_type=MIME_MAP[ext],
                description=None,
            )
            db.add(photo)
            print(f"  [ADD]  {sample_id}/{file_path.name}")
            inserted += 1

        print(f"\n--- Summary ---")
        print(f"  To insert : {inserted}")
        print(f"  Skipped (already registered) : {skipped_existing}")
        print(f"  Skipped (unknown sample_id)   : {skipped_unknown}")

        if apply:
            db.commit()
            print(f"\n[INFO] Committed {inserted} new row(s) to sample_photos.")
        else:
            db.rollback()
            print("\n[INFO] DRY RUN complete — nothing committed.")

    except Exception as exc:
        db.rollback()
        print(f"\n[ERROR] Migration aborted: {exc}")
        raise
    finally:
        db.close()
        print("=== Migration 013 finished ===")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migration 013: register filesystem photos into sample_photos table."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes to the database (default is dry run).",
    )
    parser.add_argument(
        "--photos-dir",
        default=None,
        help=(
            "Path to the sample photos directory. "
            "Defaults to the value of SAMPLE_PHOTOS_DIR env var, "
            "or 'sample_photos' relative to the project root."
        ),
    )
    args = parser.parse_args()

    if args.photos_dir:
        resolved_dir = Path(args.photos_dir)
    else:
        # Import settings only when not overridden so the script can run
        # without a full env setup when --photos-dir is provided explicitly.
        from backend.config.settings import get_settings
        resolved_dir = Path(get_settings().sample_photos_dir)

    run(photos_dir=resolved_dir, apply=args.apply)
