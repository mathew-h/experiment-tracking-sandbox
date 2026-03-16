import sys
import os
from sqlalchemy.orm import Session

# Add the project root to the Python path to allow for module imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from database import SessionLocal, ExperimentalConditions

def run_migration():
    """
    Recalculates derived conditions for all existing experiments to apply the
    new rounding logic for the 'catalyst_ppm' field.
    """
    db: Session = SessionLocal()
    try:
        print("Starting data migration: Applying catalyst PPM rounding for all experiments...")
        
        conditions_to_update = db.query(ExperimentalConditions).all()
        
        if not conditions_to_update:
            print("No experimental conditions found to update.")
            return

        updated_count = 0
        for conditions in conditions_to_update:
            # The updated rounding logic is in the model's method.
            # Calling it will recalculate and set the values on the instance.
            conditions.calculate_derived_conditions()
            updated_count += 1

        print(f"Recalculated conditions for {updated_count} experiments. Committing changes to the database...")
        db.commit()
        print("Data migration for catalyst PPM rounding completed successfully.")
        
    except Exception as e:
        print(f"An error occurred during the migration: {e}")
        print("Rolling back changes...")
        db.rollback()
    finally:
        print("Closing database session.")
        db.close()

if __name__ == "__main__":
    run_migration() 