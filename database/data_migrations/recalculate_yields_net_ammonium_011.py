import sys
import os
from sqlalchemy.orm import Session, joinedload

# Add the project root to the Python path to allow for module imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from database import SessionLocal, ScalarResults, ExperimentalResults, Experiment

def run_migration():
    """
    Recalculates yield values for all existing ScalarResults entries using the new
    background-corrected ammonium logic.
    
    This script iterates through every 'ScalarResults' entry, ensuring its
    parent relationships (ExperimentalResults, Experiment, ExperimentalConditions) are loaded.
    It then calls the 'calculate_yields' method to apply the latest calculation
    logic (gross - background, clamped to 0) and commits the updated values to the database.
    """
    db: Session = SessionLocal()
    try:
        print("Starting data migration: Recalculating yields with background ammonium correction...")
        
        # We need to eagerly load the results and their parent experiment/conditions
        # to ensure the calculation has all the data it needs and to avoid N+1 queries.
        results_to_update = db.query(ScalarResults).options(
            joinedload(ScalarResults.result_entry).
            joinedload(ExperimentalResults.experiment).
            joinedload(Experiment.conditions)
        ).all()
        
        if not results_to_update:
            print("No scalar results found to update.")
            return

        updated_count = 0
        for scalar_result in results_to_update:
            # The calculation logic is encapsulated in the model's method.
            # Calling it recalculates and sets the values on the instance.
            scalar_result.calculate_yields()
            updated_count += 1

        print(f"Recalculated yields for {updated_count} result entries. Committing changes...")
        db.commit()
        print("Data migration for yields completed successfully.")
        
    except Exception as e:
        print(f"An error occurred during the yield migration: {e}")
        print("Rolling back changes...")
        db.rollback()
    finally:
        print("Closing database session.")
        db.close()

if __name__ == "__main__":
    run_migration()
