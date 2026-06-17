"""
Backfill total_ferrous_iron_g for ExperimentalConditions where it is NULL
but the necessary inputs are available (rock_mass_g > 0 and the experiment's
sample has an 'Elemental' or 'Bulk Elemental Composition' analysis with FeO wt%).

Background
----------
total_ferrous_iron_g is a stored derived field computed by recalculate_conditions()
in the calculation registry.  It was added to the registry after many experiments
had already been created, so those older conditions rows were never recalculated.
CF-015 and CF-015-2 are the motivating cases: their conditions have rock_mass_g = 40
and the Tamarack sample has FeO = 10.5 %, but total_ferrous_iron_g remained NULL.
This caused ferrous_iron_yield_h2_pct (and ferrous_iron_yield_nh3_pct) to be NULL
for all their scalar results, hiding the cumulative Fe conversion charts in Power BI.

111 experiments are affected across the Olivine (Ward Sci) and Tamarack sample sets.

The migration calls recalculate() — the same registry path used by the API on every
save — for each affected ExperimentalConditions.  recalculate_conditions() cascades
to recalculate_scalar() for every linked ScalarResults row, so yield percentages are
updated in the same pass without a separate loop.

Run with:
    python database/data_migrations/backfill_total_ferrous_iron_017.py
or:
    python database/data_migrations/backfill_total_ferrous_iron_017.py --dry-run
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from database import SessionLocal
from database.models.conditions import ExperimentalConditions
from backend.services.calculations.registry import recalculate


def backfill_total_ferrous_iron(dry_run: bool = False) -> dict:
    """
    Recalculate total_ferrous_iron_g (and cascade to scalar yield fields) for all
    ExperimentalConditions where the field is currently NULL.

    Only conditions with rock_mass_g > 0 will produce a non-NULL result; conditions
    without rock mass are recalculated anyway so they are correctly set to NULL rather
    than left in an ambiguous uncomputed state.

    Args:
        dry_run: If True, roll back all changes without committing.

    Returns:
        Dict with keys: conditions_scanned, conditions_updated, scalar_cascades,
        already_populated, errors.
    """
    db = SessionLocal()
    summary = {
        "conditions_scanned": 0,
        "conditions_updated": 0,
        "scalar_cascades": 0,
        "already_populated": 0,
        "errors": 0,
    }

    try:
        # Only target rows where total_ferrous_iron_g is NULL — rows that already
        # have a value are skipped to avoid unnecessary writes.
        conditions = (
            db.query(ExperimentalConditions)
            .filter(ExperimentalConditions.total_ferrous_iron_g.is_(None))
            .all()
        )
        summary["conditions_scanned"] = len(conditions)

        print(f"Found {len(conditions)} conditions rows with NULL total_ferrous_iron_g")

        for ec in conditions:
            try:
                before = ec.total_ferrous_iron_g
                recalculate(ec, db)

                after = ec.total_ferrous_iron_g
                if after is not None and after != before:
                    summary["conditions_updated"] += 1
                    print(f"  {ec.experiment_id}: total_ferrous_iron_g = {after:.4f} g")

                    # Count scalar cascades
                    experiment = getattr(ec, 'experiment', None)
                    if experiment is not None:
                        n_scalars = sum(
                            1 for r in (getattr(experiment, 'results', None) or [])
                            if getattr(r, 'scalar_data', None) is not None
                        )
                        summary["scalar_cascades"] += n_scalars
                else:
                    summary["already_populated"] += 1

            except Exception as e:
                summary["errors"] += 1
                print(f"  ERROR {ec.experiment_id}: {e}")

        if dry_run:
            print("\n=== DRY RUN: Rolling back changes ===")
            db.rollback()
        else:
            db.commit()
            print("\n=== Changes committed ===")

        return summary

    except Exception as e:
        print(f"\nCritical error: {e}")
        db.rollback()
        raise

    finally:
        db.close()


def run_migration():
    """Entry point for scripts/run_data_migration.py runner."""
    print("=" * 60)
    print("BACKFILL total_ferrous_iron_g (migration 017)")
    print("=" * 60)

    summary = backfill_total_ferrous_iron(dry_run=False)

    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)
    print(f"Conditions scanned:     {summary['conditions_scanned']}")
    print(f"Conditions updated:     {summary['conditions_updated']}")
    print(f"Scalar rows cascaded:   {summary['scalar_cascades']}")
    print(f"Already populated:      {summary['already_populated']}")
    print(f"Errors:                 {summary['errors']}")
    print("=" * 60)

    return True


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("Running in DRY RUN mode (no changes will be saved)\n")

    summary = backfill_total_ferrous_iron(dry_run=dry_run)

    print("\nSummary:")
    print(f"  Conditions scanned:   {summary['conditions_scanned']}")
    print(f"  Conditions updated:   {summary['conditions_updated']}")
    print(f"  Scalar rows cascaded: {summary['scalar_cascades']}")
    print(f"  Already populated:    {summary['already_populated']}")
    print(f"  Errors:               {summary['errors']}")
