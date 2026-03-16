import datetime
import streamlit as st
import os
import json
from sqlalchemy.orm import Session, selectinload # Import Session and selectinload for type hinting and eager loading
from database import SessionLocal, Experiment, ExperimentalResults, ResultFiles, ModificationsLog, ScalarResults
# Import utilities and config
from frontend.components.utils import log_modification, save_uploaded_file, delete_file_if_exists
from frontend.config.variable_config import SCALAR_RESULTS_CONFIG# Import the main config mapping
from backend.services.result_merge_utils import (
    normalize_timepoint,
    ensure_primary_result_for_timepoint,
    update_cumulative_times_for_chain,
)

# TODO: Define a base class or interface for different result types (e.g., Scalar, pXRF, NMR)
# class BaseResultHandler:
#     def process(self, data):
#         raise NotImplementedError
#     def save(self, db, experiment_id, processed_data):
#         raise NotImplementedError

# TODO: Implement specific handlers for different result types inheriting from BaseResultHandler

# --- Helper function to save/update scalar data ---
def _save_or_update_scalar(db: Session, result: ExperimentalResults, scalar_data: dict):
    """Helper to save or update the ScalarResults associated with an ExperimentalResults entry."""
    scalar_entry = result.scalar_data
    old_values = {}
    new_values = {}

    if scalar_entry:
        # Updating existing scalar data
        modification_type = "update"
        for field_name in SCALAR_RESULTS_CONFIG.keys():
             # Skip time_post_reaction as it's on the parent result
             if field_name == 'time_post_reaction':
                  continue
             if hasattr(scalar_entry, field_name):
                  old_values[field_name] = getattr(scalar_entry, field_name)

        # Update fields from provided scalar_data dictionary
        for field_name, value in scalar_data.items():
             if field_name in SCALAR_RESULTS_CONFIG and hasattr(scalar_entry, field_name):
                  setattr(scalar_entry, field_name, value)
                  new_values[field_name] = value
    else:
        # Creating new scalar data
        modification_type = "create"
        scalar_kwargs = {'result_id': result.id}
        for field_name, config in SCALAR_RESULTS_CONFIG.items():
            if field_name == 'time_post_reaction': continue # Skip time
            # Get value from form data, fall back to config default
            value = scalar_data.get(field_name, config.get('default'))
            scalar_kwargs[field_name] = value
            new_values[field_name] = value

        scalar_entry = ScalarResults(**scalar_kwargs)
        db.add(scalar_entry)
        result.scalar_data = scalar_entry # Associate with the main result

    # Calculate derived scalar values automatically
    if hasattr(scalar_entry, 'calculate_yields'):
        # Store the calculated yield value for logging
        calculated_yield = scalar_entry.grams_per_ton_yield
        scalar_entry.calculate_yields()
        
        # If the yield was calculated and it's different from what was in new_values, update the log
        if (scalar_entry.grams_per_ton_yield is not None and 
            calculated_yield != scalar_entry.grams_per_ton_yield):
            new_values['grams_per_ton_yield'] = scalar_entry.grams_per_ton_yield

    # Log the modification
    log_modification(
        db=db,
        experiment_id=result.experiment.experiment_id,
        modified_table=ScalarResults.__tablename__,
        modification_type=modification_type,
        old_values=old_values if old_values else None,
        new_values=new_values if new_values else None
    )
    return scalar_entry # Return the saved/updated entry

# --- Main Save Function (Refactored) ---
def save_results(experiment_id, time_post_reaction, result_description, scalar_data, files_to_save=None, result_id_to_edit=None, measurement_date=None):
    """
    Save or update experiment results for a specific time point.
    Handles creation/update of ExperimentalResults and ScalarResults.

    Args:
        experiment_id (int): The primary key (DB ID) of the experiment.
        time_post_reaction (float): Time in hours post-reaction.
        result_description (str): The description for this result entry.
        scalar_data (dict): Dictionary of scalar field values.
        files_to_save (list[dict], optional): List of file upload data.
        result_id_to_edit (int, optional): The ID of the ExperimentalResults entry to update.
        measurement_date (datetime, optional): Custom measurement date to override created_at.

    Returns:
        bool: True if save was successful, False otherwise.
    """
    if time_post_reaction is None:
        st.error("Time post reaction (days) is required.")
        return False

    db = SessionLocal()
    try:
        # --- Get or Create Main ExperimentalResults Entry ---
        if result_id_to_edit:
            # Editing existing entry - Load result and related data
            result = db.query(ExperimentalResults).options(
                selectinload(ExperimentalResults.scalar_data),
            ).filter(ExperimentalResults.id == result_id_to_edit).first()

            if not result:
                st.error(f"Result entry with ID {result_id_to_edit} not found for editing.")
                return False

            # Update measurement date if it has changed
            if measurement_date and result.created_at.date() != measurement_date.date():
                old_date = result.created_at
                result.created_at = measurement_date
                log_modification(
                    db=db,
                    experiment_id=result.experiment.experiment_id,
                    modified_table=ExperimentalResults.__tablename__,
                    modification_type="update",
                    old_values={"created_at": old_date.isoformat()},
                    new_values={"created_at": measurement_date.isoformat()}
                )
            
            # Update description if it has changed
            if result.description != result_description:
                old_desc = result.description
                result.description = result_description
                log_modification(
                    db=db,
                    experiment_id=result.experiment.experiment_id,
                    modified_table=ExperimentalResults.__tablename__,
                    modification_type="update",
                    old_values={"description": old_desc},
                    new_values={"description": result_description}
                )
            # No need to log main entry update unless fields on ExperimentalResults itself change

        else:
            # Creating new entry - Check for existing entry at this timepoint first
            existing_result_at_time = db.query(ExperimentalResults).filter(
                ExperimentalResults.experiment_fk == experiment_id, # Filter by FK
                ExperimentalResults.time_post_reaction_days == time_post_reaction
            ).first()
            if existing_result_at_time:
                 # Use existing_result_at_time.experiment.experiment_id for user-friendly message if needed
                 st.error(f"An entry already exists for this experiment at time {time_post_reaction:.1f}h. Please edit the existing entry instead of adding a new one.")
                 return False

            # Fetch the parent Experiment object using the database ID
            parent_experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
            if not parent_experiment:
                st.error(f"Parent experiment with DB ID {experiment_id} not found.")
                return False

            # Create the main result entry
            result = ExperimentalResults(
                experiment_fk=parent_experiment.id, # Foreign Key
                time_post_reaction_days=time_post_reaction,
                time_post_reaction_bucket_days=normalize_timepoint(time_post_reaction),
                description=result_description # Set the description
            )
            
            # Override created_at with measurement_date if provided
            if measurement_date:
                result.created_at = measurement_date
            db.add(result)
            # Log creation of the main entry? Optional, depends on desired log granularity.
            log_modification(
                db=db,
                experiment_id=parent_experiment.experiment_id,
                modified_table=ExperimentalResults.__tablename__,
                modification_type="create",
                new_values={
                    "time_post_reaction": time_post_reaction,
                    "description": result_description
                }
            )
            db.flush() # Flush to get result.id before using it below


        # --- Save/Update Scalar Data (Always happens) ---
        scalar_entry = _save_or_update_scalar(db, result, scalar_data)

        # --- Handle File Uploads ---
        if files_to_save:
            # Define storage folder outside the loop, as it's the same for all files in this result
            storage_folder = f"results/{result.experiment.experiment_id}/{result.id}"
            for file_info in files_to_save:
                uploaded_file = file_info['file']
                # Check if file already exists for this result to prevent duplicates
                file_exists = db.query(ResultFiles).filter_by(
                    result_id=result.id,
                    file_name=uploaded_file.name
                ).first()

                if not file_exists:
                    # Save the file to disk/cloud storage
                    file_path = save_uploaded_file(
                        file=uploaded_file,
                        storage_folder=storage_folder
                    )
                    if file_path:
                        # Create a new ResultFiles entry without description
                        new_file = ResultFiles(
                            result_id=result.id,
                            file_path=file_path,
                            file_name=uploaded_file.name,
                            file_type=uploaded_file.type
                        )
                        db.add(new_file)
                        # Log file addition
                        log_modification(
                            db=db,
                            experiment_id=result.experiment.experiment_id,
                            modified_table=ResultFiles.__tablename__,
                            modification_type="create",
                            new_values={
                                "file_name": uploaded_file.name,
                                "result_id": result.id
                            }
                        )
        
        # Ensure correct primary result designation for this timepoint
        ensure_primary_result_for_timepoint(
            db=db,
            experiment_fk=result.experiment_fk,
            time_post_reaction=time_post_reaction,
        )

        # Recalculate cumulative times for the entire lineage chain
        update_cumulative_times_for_chain(db, result.experiment_fk)

        db.commit()
        st.success("Results saved successfully!")
        return True

    except Exception as e:
        db.rollback()
        st.error(f"An error occurred while saving the results: {e}")
        # Log the exception for debugging
        print(f"Error in save_results: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

def delete_experimental_results(result_id):
    """
    Delete an experimental result time point entry. Cascade delete handles specific data and files.

    Args:
        result_id (int): The unique identifier (DB ID) of the ExperimentalResults entry.
    """
    db = SessionLocal()
    try:
        # Get the main result entry, eager load related data needed for logging/file deletion
        result_entry = db.query(ExperimentalResults).options(
            selectinload(ExperimentalResults.files),
            selectinload(ExperimentalResults.experiment)  # Correctly load the experiment relationship
        ).filter(ExperimentalResults.id == result_id).first()

        if result_entry is None:
            st.error(f"Result entry with ID {result_id} not found.")
            return

        experiment_str_id = result_entry.experiment.experiment_id if result_entry.experiment else None
        time_point = result_entry.time_post_reaction_days

        # --- Delete associated files from storage FIRST ---
        associated_files = result_entry.files
        deleted_file_info = []
        if associated_files:
            for file_record in associated_files:
                deleted = delete_file_if_exists(file_record.file_path)
                deleted_file_info.append({
                    'name': file_record.file_name,
                    'path': file_record.file_path,
                    'deleted': deleted
                })
                if not deleted:
                     st.warning(f"Could not delete file from storage: {file_record.file_path}")

        # Prepare old values for the main log entry
        old_values_log = {
            'result_id': result_entry.id,
            'time_post_reaction': time_point,
            'experiment_id': experiment_str_id,
            'deleted_files_info': deleted_file_info
        }

        # --- Log the deletion of the main result entry ---
        log_modification(
            db=db,
            experiment_id=experiment_str_id,
            modified_table="experimental_results",
            modification_type="delete",
            old_values=old_values_log
        )

        # --- Delete the ExperimentalResults record ---
        db.delete(result_entry)

        # --- Commit the transaction ---
        db.commit()

        st.success(f"Result entry for time {time_point:.1f}h deleted successfully!")

    except Exception as e:
        db.rollback()
        st.error(f"Error deleting result entry (ID: {result_id}): {str(e)}")
    finally:
        db.close()

def delete_result_file(file_id):
    """
    Delete an individual result file record and its corresponding file from storage.

    Args:
        file_id (int): The unique identifier of the ResultFiles entry to delete.

    Returns:
        bool: True if deletion was successful, False otherwise.
    """
    db = SessionLocal()
    try:
        # Find the file record, eager load parent result and experiment for logging context
        file_record = db.query(ResultFiles).options(
            selectinload(ResultFiles.result_entry).selectinload(ExperimentalResults.experiment)
        ).filter(ResultFiles.id == file_id).first()

        if file_record is None:
            st.error(f"File record with ID {file_id} not found.")
            return False

        # Store info for logging
        old_values = {
            'file_id': file_record.id,
            'result_id': file_record.result_id,
            'file_path': file_record.file_path,
            'file_name': file_record.file_name,
        }

        # Get the associated experiment string ID for logging context
        experiment_str_id_for_log = None
        if file_record.result_entry and file_record.result_entry.experiment:
             experiment_str_id_for_log = file_record.result_entry.experiment.experiment_id
        else:
             st.warning(f"Could not determine experiment ID for logging file deletion (File ID: {file_id}, Result ID: {file_record.result_id})")


        # --- Delete the actual file from storage FIRST ---
        file_deleted_from_storage = delete_file_if_exists(file_record.file_path)

        if not file_deleted_from_storage:
            st.warning(f"Could not delete file from storage: {file_record.file_path}. Proceeding to remove database record.")
            old_values['storage_deletion_failed'] = True

        # --- Delete the database record ---
        db.delete(file_record)

        # --- Log the deletion ---
        log_modification(
            db=db,
            experiment_id=experiment_str_id_for_log,
            modified_table=ResultFiles.__tablename__,
            modification_type="delete",
            old_values=old_values
        )

        # --- Commit the transaction ---
        db.commit()
        st.success(f"File '{old_values.get('file_name', 'Unknown')}' deleted successfully.")
        return True

    except Exception as e:
        db.rollback()
        st.error(f"Error deleting file record (ID: {file_id}): {str(e)}")
        return False
    finally:
        db.close()



