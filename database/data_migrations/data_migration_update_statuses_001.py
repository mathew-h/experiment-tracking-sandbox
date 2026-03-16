import sys
import os
from sqlalchemy import create_engine, text, update # Removed select, column for this approach
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

# Add the project root to the Python path to allow importing models
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')) # Adjusted path
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from database.database import DATABASE_URL
from database import Experiment # Still needed for table metadata and update

def run_data_migration():
    """
    Updates existing experiment statuses according to the defined mapping:
    PLANNED -> ONGOING
    IN_PROGRESS -> ONGOING
    FAILED -> CANCELLED
    """
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    status_mapping = {
        "PLANNED": "ONGOING",
        "IN_PROGRESS": "ONGOING",
        "FAILED": "CANCELLED"
    }

    updated_count = 0
    failed_count = 0
    experiments_needing_update_info = []

    try:
        print("Starting experiment status data migration...")

        # Step 1: Fetch IDs and current statuses using a more direct SQL execution
        status_column_name = Experiment.status.property.columns[0].name
        id_column_name = Experiment.id.property.columns[0].name
        table_name = Experiment.__tablename__

        in_clause_values = ", ".join([f"'{s}'" for s in status_mapping.keys()])
        # Construct the raw SQL query string
        raw_sql_query = f"SELECT {id_column_name}, {status_column_name} FROM {table_name} WHERE {status_column_name} IN ({in_clause_values})"
        
        print(f"Executing raw SQL for fetching: {raw_sql_query}")

        # Use a connection to execute raw SQL and fetch results directly
        with engine.connect() as connection:
            result_proxy = connection.execute(text(raw_sql_query))
            # Iterate over the ResultProxy, which yields RowProxy objects (like tuples)
            for row in result_proxy:
                # Access by index: 0 for id, 1 for status
                experiments_needing_update_info.append({
                    "id": row[0],
                    "current_status": str(row[1]) # Ensure it's a string immediately
                })
            result_proxy.close() # Close the ResultProxy

        if not experiments_needing_update_info:
            print("No experiments found with statuses requiring update.")
            session.close()
            return

        print(f"Found {len(experiments_needing_update_info)} experiments to potentially update.")

        # Step 2: Iterate and update each experiment (using the existing session for transaction management)
        for exp_info in experiments_needing_update_info:
            exp_id = exp_info["id"]
            old_status_str = exp_info["current_status"]

            if old_status_str in status_mapping:
                new_status_str = status_mapping[old_status_str]
                try:
                    print(f"Updating Experiment DB ID {exp_id}: status from '{old_status_str}' to '{new_status_str}'")
                    # Use the session for the update operation to keep it within the transaction
                    update_stmt = (
                        update(Experiment)
                        .where(Experiment.id == exp_id)
                        .values(status=new_status_str) # new_status_str is valid in current Python enum
                    )
                    session.execute(update_stmt)
                    updated_count += 1
                except Exception as e_update:
                    print(f"Error updating experiment ID {exp_id}: {e_update}")
                    failed_count +=1 
            else:
                print(f"Skipping Experiment DB ID {exp_id}: status '{old_status_str}' not in explicit mapping.")

        if failed_count > 0:
             print(f"Warning: {failed_count} experiment(s) failed to update. Rolling back transaction.")
             session.rollback()
        else:
            session.commit()
            print(f"Successfully processed {updated_count} experiments for status update.")
            if updated_count > 0 and failed_count == 0:
                 print("All changes committed.")

    except SQLAlchemyError as e_outer:
        session.rollback()
        print(f"SQLAlchemyError during data migration: {e_outer}")
        print("Transaction rolled back.")
        if experiments_needing_update_info:
             failed_count = len(experiments_needing_update_info) - updated_count
    except Exception as e_general:
        session.rollback()
        print(f"An unexpected error occurred: {e_general}")
        print("Transaction rolled back.")
        if experiments_needing_update_info:
            failed_count = len(experiments_needing_update_info) - updated_count
    finally:
        if session.is_active:
             session.close()
        print("Data migration finished.")
        if failed_count > 0:
            print(f"Warning: {failed_count} experiment(s) may not have been updated or processing failed.")

if __name__ == "__main__":
    print("Attempting to run data migration for experiment statuses...")
    run_data_migration()
    print("Script execution complete.") 