"""
Data migration: set any negative ICP concentration values to 0.

Scans all ICPResults rows and, for both fixed element columns and the
all_elements JSON, replaces values < 0 with 0. Concentrations (ppm) must
be non-negative.

Run from project root: python -m database.data_migrations.zero_negative_icp
"""
import sys
import os
import math
from sqlalchemy.orm import Session

# Add the project root to the Python path to allow for module imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from database import SessionLocal, ICPResults

# Fixed element columns on ICPResults (concentrations in ppm)
ICP_ELEMENT_COLUMNS = [
    'fe', 'si', 'ni', 'cu', 'mo', 'ca', 'zn', 'mn', 'cr', 'co', 'mg', 'al',
    'sr', 'y', 'nb', 'sb', 'cs', 'ba', 'nd', 'gd', 'pt', 'rh', 'ir',
    'pd', 'ru', 'os', 'tl',
]


def _is_negative(val) -> bool:
    """Return True if val is a finite negative number."""
    if not isinstance(val, (int, float)):
        return False
    if math.isnan(val) or math.isinf(val):
        return False
    return val < 0


def run_migration():
    """
    Find all ICP concentrations that are < 0 and set them to 0.
    Updates both fixed columns and all_elements JSON on icp_results.
    """
    db: Session = SessionLocal()
    try:
        print("Starting data migration: Zeroing negative ICP concentrations...")

        rows = db.query(ICPResults).all()
        total_row_count = len(rows)
        print(f"Total ICP result rows in database: {total_row_count}")

        if not rows:
            print("No ICP results found. Nothing to do.")
            return

        rows_modified = 0
        total_values_zeroed = 0
        change_log = []

        for row in rows:
            changed = False
            row_changes = []

            # Fixed columns
            for col in ICP_ELEMENT_COLUMNS:
                val = getattr(row, col, None)
                if val is not None and _is_negative(val):
                    row_changes.append(f"  {col}: {val} -> 0.0")
                    setattr(row, col, 0.0)
                    changed = True
                    total_values_zeroed += 1

            # all_elements JSON (assign new dict so SQLAlchemy marks column dirty)
            if row.all_elements and isinstance(row.all_elements, dict):
                all_elems_changed = False
                new_all = {}
                for key, val in row.all_elements.items():
                    if _is_negative(val):
                        row_changes.append(f"  all_elements[{key}]: {val} -> 0.0")
                        new_all[key] = 0.0
                        all_elems_changed = True
                        changed = True
                        total_values_zeroed += 1
                    else:
                        new_all[key] = val
                if all_elems_changed:
                    row.all_elements = new_all

            if changed:
                rows_modified += 1
                change_log.append(f"ICPResults id={row.id} (result_id={row.result_id}):")
                change_log.extend(row_changes)

        # Print detailed change log
        if change_log:
            print("\n--- Changes to be committed ---")
            for line in change_log:
                print(line)
            print("--- End of changes ---\n")

        print(f"Rows scanned: {total_row_count}")
        print(f"Rows with at least one value changed: {rows_modified}")
        print(f"Total concentration values set to 0: {total_values_zeroed}")

        if rows_modified == 0:
            print("No negative values found. Nothing to commit.")
            return

        db.commit()
        print("Data migration completed successfully.")

    except Exception as e:
        print(f"An error occurred during the migration: {e}")
        print("Rolling back changes...")
        db.rollback()
        raise
    finally:
        db.close()
        print("Database session closed.")


if __name__ == "__main__":
    run_migration()
