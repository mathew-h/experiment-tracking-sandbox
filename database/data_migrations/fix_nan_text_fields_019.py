"""
One-time cleanup: clear brine_modification_description values that hold the
literal string 'nan', and the has_brine_modification flag set from them.

pandas reads an empty Excel cell as float('nan'), which is TRUTHY, so the
`str(cell or "").strip()` idiom in master_bulk_upload.py stored the text 'nan'
for a blank Modification cell. ExperimentalResults.sync_brine_flag then set
has_brine_modification from that string, so a timepoint with no brine
modification was flagged as having one -- on an indexed column that is exposed
in a reporting view (database/event_listeners.py) and rendered in the Results
tab. Measured on the 2026-08-10 production backup: 12 such rows, all 12
wrongly flagged, 8.5% of the 141 flagged rows. The parser now uses
_parse_text() and cannot create new ones; this script corrects the historical
rows.

Matching is case-insensitive and trimmed, so 'NaN' and ' nan ' are caught too
(0 such variants existed at the time of writing, but the cost is one lower()).

The UPDATE clears has_brine_modification explicitly rather than relying on
sync_brine_flag: that hook is an ORM @validates on the attribute, and raw SQL
does not fire it. Leaving the flag to the ORM here would null the text and
leave every flag still true -- the worse half of the bug.

experimental_results.description is NOT NULL, so a 'nan' description has no
correct null to fall back to. This script therefore REPORTS those rows and
never rewrites them: inventing free text that a researcher will read is worse
than telling the operator which rows to look at. 0 rows are affected in both
the dev DB and the 2026-08-10 production backup.

Usage:
    # Dry run (preview only, no writes)
    python database/data_migrations/fix_nan_text_fields_019.py

    # Apply
    python database/data_migrations/fix_nan_text_fields_019.py --apply

    # Against a specific database (defaults to $DATABASE_URL, then the dev DB)
    DATABASE_URL=postgresql://... python database/data_migrations/fix_nan_text_fields_019.py
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from database import get_db  # noqa: E402

_IS_NAN = "lower(btrim(brine_modification_description)) = 'nan'"
_DESC_IS_NAN = "lower(btrim(description)) = 'nan'"


def main(apply: bool) -> None:
    db = next(get_db())
    try:
        from sqlalchemy import text

        count_nan = db.execute(
            text(f"SELECT COUNT(*) FROM experimental_results WHERE {_IS_NAN}")
        ).scalar()
        count_flagged = db.execute(
            text(
                "SELECT COUNT(*) FROM experimental_results"
                f" WHERE {_IS_NAN} AND has_brine_modification"
            )
        ).scalar()
        total_flagged = db.execute(
            text(
                "SELECT COUNT(*) FROM experimental_results"
                " WHERE has_brine_modification"
            )
        ).scalar()
        count_desc = db.execute(
            text(f"SELECT COUNT(*) FROM experimental_results WHERE {_DESC_IS_NAN}")
        ).scalar()

        print(f"brine_modification_description = 'nan':   {count_nan}")
        print(f"  ...of those flagged has_brine=true:     {count_flagged}")
        print(f"has_brine_modification = true (total):    {total_flagged}")
        if total_flagged:
            share = 100.0 * count_flagged / total_flagged
            print(f"  ...false-positive share of the flag:    {share:.1f}%")

        # Reported, never rewritten -- see the module docstring.
        print(f"description = 'nan' (REPORTED, not fixed): {count_desc}")
        if count_desc:
            ids = db.execute(
                text(
                    "SELECT id, experiment_fk, time_post_reaction_days"
                    f" FROM experimental_results WHERE {_DESC_IS_NAN} ORDER BY id"
                )
            ).fetchall()
            print("  description is NOT NULL, so there is no correct null to")
            print("  write and this script will not invent replacement text.")
            print("  Review these rows by hand (id, experiment_fk, day):")
            for row in ids:
                print(f"    {row[0]}, {row[1]}, {row[2]}")

        if not apply:
            print("\nDry run — pass --apply to commit changes.")
            return

        result = db.execute(
            text(
                "UPDATE experimental_results"
                " SET brine_modification_description = NULL,"
                "     has_brine_modification = false"
                f" WHERE {_IS_NAN}"
            )
        )
        db.commit()

        remaining = db.execute(
            text(f"SELECT COUNT(*) FROM experimental_results WHERE {_IS_NAN}")
        ).scalar()
        still_flagged = db.execute(
            text(
                "SELECT COUNT(*) FROM experimental_results"
                " WHERE has_brine_modification"
                "   AND (brine_modification_description IS NULL"
                "        OR btrim(brine_modification_description) = '')"
            )
        ).scalar()
        total_flagged_after = db.execute(
            text(
                "SELECT COUNT(*) FROM experimental_results"
                " WHERE has_brine_modification"
            )
        ).scalar()

        print(f"\nApplied. Rows updated: {result.rowcount}")
        print(f"Remaining 'nan' values: {remaining}")
        print(f"Flagged rows with no description text: {still_flagged}")
        print(f"has_brine_modification = true (total): {total_flagged_after}")

    except Exception as exc:
        db.rollback()
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit changes (default: dry run)")
    args = parser.parse_args()
    main(apply=args.apply)
