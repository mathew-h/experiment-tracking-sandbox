"""
One-time cleanup: set final_ph = NULL and final_conductivity_mS_cm = NULL
where the stored value is 0.

These 0 values entered the database from Excel template cells that produce 0
(not NaN) when left blank.  The parsers now guard against this going forward;
this script corrects the historical rows.

Usage:
    # Dry run (preview only, no writes)
    python database/data_migrations/zero_ph_conductivity_016.py

    # Apply
    python database/data_migrations/zero_ph_conductivity_016.py --apply
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from database import get_db  # noqa: E402


def main(apply: bool) -> None:
    db = next(get_db())
    try:
        from sqlalchemy import text

        count_ph = db.execute(
            text('SELECT COUNT(*) FROM scalar_results WHERE final_ph = 0')
        ).scalar()
        count_cond = db.execute(
            text('SELECT COUNT(*) FROM scalar_results WHERE "final_conductivity_mS_cm" = 0')
        ).scalar()

        print(f"Rows with final_ph = 0:                  {count_ph}")
        print(f'Rows with "final_conductivity_mS_cm" = 0: {count_cond}')

        if not apply:
            print("\nDry run — pass --apply to commit changes.")
            return

        db.execute(
            text("UPDATE scalar_results SET final_ph = NULL WHERE final_ph = 0")
        )
        db.execute(
            text(
                'UPDATE scalar_results'
                ' SET "final_conductivity_mS_cm" = NULL'
                ' WHERE "final_conductivity_mS_cm" = 0'
            )
        )
        db.commit()

        remaining_ph = db.execute(
            text("SELECT COUNT(*) FROM scalar_results WHERE final_ph = 0")
        ).scalar()
        remaining_cond = db.execute(
            text('SELECT COUNT(*) FROM scalar_results WHERE "final_conductivity_mS_cm" = 0')
        ).scalar()

        print(f"\nApplied. Remaining zeros — pH: {remaining_ph}, conductivity: {remaining_cond}")

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
