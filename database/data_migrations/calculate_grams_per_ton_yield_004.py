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
    Calculates grams_per_ton_yield for all existing ScalarResults entries.
    
    This script iterates through every 'ScalarResults' entry, ensuring its
    parent relationships (ExperimentalResults, Experiment, ExperimentalConditions) are loaded.
    It then calls the 'calculate_yields' method to apply the calculation
    logic for 'grams_per_ton_yield' and commits the updated values to the database.
    
    The calculation uses:
    - gross_ammonium_concentration (mM)
    - water_volume from experimental conditions (mL)
    - rock_mass from experimental conditions (g)
    
    Formula: grams_per_ton_yield = 1,000,000 * (ammonia_mass_g / rock_mass)
    where ammonia_mass_g = (gross_ammonium_concentration / 1000) * (water_volume / 1000) * 18.04
    """
    db: Session = SessionLocal()
    try:
        print("Starting data migration: Calculating grams_per_ton_yield for all scalar results...")
        
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
        skipped_count = 0
        
        for scalar_result in results_to_update:
            # Store the old value for logging
            old_yield = scalar_result.grams_per_ton_yield
            
            # The calculation logic is encapsulated in the model's method.
            # Calling it recalculates and sets the values on the instance.
            scalar_result.calculate_yields()
            
            # Check if the value actually changed
            if old_yield != scalar_result.grams_per_ton_yield:
                updated_count += 1
                print(f"Updated yield for result {scalar_result.result_id}: {old_yield} -> {scalar_result.grams_per_ton_yield}")
            else:
                skipped_count += 1

        print(f"Updated grams_per_ton_yield for {updated_count} result entries.")
        print(f"Skipped {skipped_count} entries (no change or insufficient data).")
        print("Committing changes...")
        db.commit()
        print("Data migration for grams_per_ton_yield completed successfully.")
        
    except Exception as e:
        print(f"An error occurred during the grams_per_ton_yield migration: {e}")
        print("Rolling back changes...")
        db.rollback()
        raise
    finally:
        print("Closing database session.")
        db.close()

if __name__ == "__main__":
    run_migration() 