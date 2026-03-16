import sys
import os
from typing import List
from sqlalchemy.orm import Session, joinedload

# Add the project root to the Python path to allow for module imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from database import SessionLocal, ExperimentalConditions, ScalarResults, ExperimentalResults, Experiment


def _chunked(iterable: List, size: int):
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]


def run_migration(chunk_size: int = 1000):
    """
    Unified backfill for calculated fields:
      1) ExperimentalConditions.calculate_derived_conditions() (W:R)
      2) ChemicalAdditive.calculate_derived_values() for each additive (elemental mass, catalyst %, ppm)
      3) ScalarResults.calculate_yields() (ammonia using sampling volume fallback; H2 yield g/ton)

    Processes in chunks to avoid very large transactions.
    """
    db: Session = SessionLocal()
    try:
        print("Starting unified data migration: recompute calculated fields...")

        # Eager-load relationships for conditions → experiment → results
        all_conditions: List[ExperimentalConditions] = (
            db.query(ExperimentalConditions)
            .options(
                joinedload(ExperimentalConditions.chemical_additives),
                joinedload(ExperimentalConditions.experiment)
                .joinedload(Experiment.results)
                .joinedload(ExperimentalResults.scalar_data),
            )
            .all()
        )

        if not all_conditions:
            print("No experimental conditions found.")
            return

        total_conditions = len(all_conditions)
        cond_updated = add_updated = scalar_updated = 0

        for batch in _chunked(all_conditions, chunk_size):
            for conditions in batch:
                # 1) Conditions
                try:
                    conditions.calculate_derived_conditions()
                    cond_updated += 1
                except Exception as e:
                    print(f"Warning: failed to recalc conditions id={conditions.id}: {e}")

                # 2) Additives
                try:
                    for additive in list(getattr(conditions, 'chemical_additives', []) or []):
                        additive.calculate_derived_values()
                        add_updated += 1
                except Exception as e:
                    print(f"Warning: failed to recalc additives for conditions id={conditions.id}: {e}")

                # 3) Scalar results
                try:
                    exp = getattr(conditions, 'experiment', None)
                    if exp is not None:
                        for res in list(getattr(exp, 'results', []) or []):
                            if getattr(res, 'scalar_data', None) is not None:
                                res.scalar_data.calculate_yields()
                                scalar_updated += 1
                except Exception as e:
                    print(f"Warning: failed to recalc scalar results for experiment_fk={conditions.experiment_fk}: {e}")

            db.commit()
            print(f"Committed batch: conditions updated so far={cond_updated}, additives recalculated so far={add_updated}, scalar results updated so far={scalar_updated}")

        print("Unified migration complete.")
        print(f"Summary: conditions={cond_updated}/{total_conditions}, additives={add_updated}, scalar_results={scalar_updated}")

    except Exception as e:
        print(f"Error during unified migration: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_migration()


