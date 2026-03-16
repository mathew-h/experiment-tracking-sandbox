import datetime
import streamlit as st
import os
import json
from sqlalchemy.orm import Session # Import Session for type hinting
from database import SessionLocal, Experiment, ExperimentStatus, ExperimentalConditions, ModificationsLog, ExperimentNotes, ExternalAnalysis
# Import utilities and config
from frontend.components.utils import log_modification, save_uploaded_file, delete_file_if_exists, generate_form_fields, get_sample_options
from frontend.config.variable_config import EXPERIMENT_TYPES, EXPERIMENT_STATUSES, FIELD_CONFIG, SCALAR_RESULTS_CONFIG
# Import the service
from backend.services.experimental_conditions_service import ExperimentalConditionsService
import pytz

def edit_experiment(experiment):
    """
    Render the interface for editing an existing experiment.
    
    Args:
        experiment (dict): Dictionary containing the experiment data to edit
        
    This function creates a form interface that allows users to:
    - Edit basic experiment information (experiment ID, sample ID, researcher, status, date)
    - Modify experimental conditions (temperature, pressure, pH, etc.)
    - Update optional parameters
    - Save changes to the database
    
    The form includes validation and proper error handling for the submission process.
    """
    # --- State management for edit form ---
    # Use session state to hold the data being edited to persist changes across reruns
    if 'edit_form_data' not in st.session_state or st.session_state.edit_form_data.get('id') != experiment.get('id'):
        st.session_state.edit_form_data = experiment.copy()
        if 'conditions' in st.session_state.edit_form_data:
            st.session_state.edit_form_data['conditions'] = st.session_state.edit_form_data['conditions'].copy()
    
    # Work with the session state copy
    form_data = st.session_state.edit_form_data
    conditions = form_data.get('conditions', {})

    with st.form(key="edit_experiment_form"):
        st.markdown("### Basic Information")
        col1, col2 = st.columns(2)
        
        with col1:
            experiment_id = st.text_input("Experiment ID", value=form_data['experiment_id'])
            
            created_at = st.date_input(
                "Creation Date",
                value=form_data.get('created_at', datetime.datetime.now()),
                help="The date when the experiment was created",
                format="MM/DD/YYYY"
            )
            
            # Get sample options from database using utils function
            sample_options, sample_dict = get_sample_options()
            
            # Find current selection
            current_sample_id = form_data.get('sample_id', '')
            current_index = 0
            if current_sample_id:
                # Find the display text that maps to the current_sample_id
                for display_text, s_id in sample_dict.items():
                    if s_id == current_sample_id:
                        if display_text in sample_options:
                             current_index = sample_options.index(display_text)
                        break 
                # Fallback if current_sample_id is not in sample_dict (e.g. old data)
                # or if the display_text is no longer in sample_options (e.g. sample deleted)
                # In such cases, we try to find a partial match if possible or default to "None"
                if current_index == 0 and current_sample_id != "": # if not found and not intentionally blank
                    # Try to find by exact sample_id if it exists as an option (should not happen with current get_sample_options)
                    if current_sample_id in sample_options:
                        current_index = sample_options.index(current_sample_id)
                    else: # if still not found, try to find a display text that starts with the sample_id
                        for i, option_text in enumerate(sample_options):
                            if option_text.startswith(current_sample_id):
                                current_index = i
                                break
            
            selected_sample_display = st.selectbox(
                "Sample ID",
                options=sample_options,
                index=current_index,
                help="Select a rock sample from the database, or leave blank for control runs/experiments without rock samples. You can type to search.",
                format_func=lambda x: "None (Control Run)" if x == "" else x
            )
            
            # Get the actual sample_id from the selection
            sample_id = sample_dict.get(selected_sample_display, "")

            # Additional safety: if mapping fails, extract sample_id from display text
            if not sample_id and selected_sample_display and selected_sample_display != "" and selected_sample_display != "None (Control Run)":
                # Extract just the sample_id part (everything before the first " - ")
                sample_id = selected_sample_display.split(" - ")[0].strip()
                # Verify this is a valid sample_id by checking if it exists in our sample_dict values
                if sample_id not in sample_dict.values():
                    sample_id = "" # Reset to empty if not valid

            researcher = st.text_input("Researcher Name", value=form_data['researcher'])
        
        with col2:
            status = st.selectbox(
                "Experiment Status",
                options=EXPERIMENT_STATUSES,
                index=EXPERIMENT_STATUSES.index(form_data['status']) if form_data['status'] in EXPERIMENT_STATUSES else 0
            )
            # Convert UTC datetime to EST for display
            est = pytz.timezone('US/Eastern')
            if isinstance(form_data['date'], datetime.datetime):
                if form_data['date'].tzinfo is None:
                    # If naive datetime, assume it's UTC
                    form_data['date'] = form_data['date'].replace(tzinfo=pytz.UTC)
                display_date = form_data['date'].astimezone(est)
            else:
                display_date = datetime.datetime.now(est)
            
            exp_date = st.date_input(
                "Experiment Date", 
                value=display_date
            )
        
        st.markdown("### Experimental Conditions")
        col3, col4 = st.columns(2)
        
        with col3:
            st.markdown("#### Required Parameters")
            
            # Get required field names from FIELD_CONFIG
            required_field_names = [name for name, config in FIELD_CONFIG.items() if config.get('required', False)]
            required_values = generate_form_fields(
                FIELD_CONFIG, 
                conditions, 
                required_field_names,
                key_prefix="edit_req"
            )
            
        with col4:
            st.markdown("#### Optional Parameters")
            # Get optional field names from FIELD_CONFIG
            optional_field_names = [name for name, config in FIELD_CONFIG.items() if not config.get('required', False) and not config.get('readonly', False)]
            optional_values = generate_form_fields(
                FIELD_CONFIG, 
                conditions, 
                optional_field_names,
                key_prefix="edit_opt"
            )
        
        # Combine required and optional values into a single dictionary
        all_condition_values = {**required_values, **optional_values}
        
        # Convert EST date to UTC for storage
        est = pytz.timezone('US/Eastern')
        current_time = datetime.datetime.now(est)
        utc_time = current_time.astimezone(pytz.UTC)
        
        # Prepare data for submission
        submission_data = {
            'experiment_id': experiment_id,
            'sample_id': sample_id,
            'researcher': researcher,
            'status': status,
            'date': datetime.datetime.combine(exp_date, utc_time.time()).replace(tzinfo=pytz.UTC),
            'conditions': all_condition_values
        }
        
        # Submit button
        submit_button = st.form_submit_button("Save Changes")
        if submit_button:
            submit_experiment_edit(experiment['id'], submission_data)

def submit_experiment_edit(experiment_id, data):
    """
    Handle the submission of experiment edit form.
    
    Args:
        experiment_id (int): The unique identifier of the experiment to update
        data (dict): Dictionary containing the updated experiment data
        
    This function:
    - Calls update_experiment to save changes
    - Updates the session state to reflect the changes
    - Handles success/failure states
    """
    success = update_experiment(experiment_id, data)
    if success:
        st.session_state.edit_mode = False

def update_experiment(experiment_id, data):
    """
    Update an experiment in the database.
    
    Args:
        experiment_id (int): The unique identifier of the experiment to update
        data (dict): Dictionary containing the updated experiment data
        
    This function:
    - Retrieves the existing experiment
    - Logs old values before updating
    - Updates basic experiment information
    - Updates or creates experimental conditions
    - Creates a modification log entry
    - Handles database transactions and error cases
    
    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        db = SessionLocal()
        
        # Get the experiment
        experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
        
        if experiment is None:
            st.error(f"Experiment with ID {experiment_id} not found.")
            return False
        
        # Check if the new experiment_id already exists (if it's being changed)
        if data['experiment_id'] != experiment.experiment_id:
            existing = db.query(Experiment).filter(Experiment.experiment_id == data['experiment_id']).first()
            if existing:
                st.error(f"Experiment ID '{data['experiment_id']}' already exists. Please choose a different ID.")
                return False
        
        # Log old values before updating
        old_values = {
            'experiment_id': experiment.experiment_id,
            'sample_id': experiment.sample_id,
            'researcher': experiment.researcher,
            'status': experiment.status.name,
            'date': experiment.date.isoformat() if experiment.date else None
        }
        
        # Update basic experiment information
        experiment.experiment_id = data['experiment_id']
        experiment.sample_id = data['sample_id']
        experiment.researcher = data['researcher']
        experiment.status = getattr(ExperimentStatus, data['status'])
        experiment.date = data['date']
        
        # Prepare conditions data by converting empty strings in numeric fields to None
        conditions_data = data['conditions'].copy()
        for key, value in conditions_data.items():
            if key in FIELD_CONFIG and FIELD_CONFIG[key]['type'] == 'number' and value == '':
                conditions_data[key] = None

        # Update or create conditions using the service
        if experiment.conditions:
            # Update existing conditions
            updated_conditions = ExperimentalConditionsService.update_experimental_conditions(
                db=db,
                conditions_id=experiment.conditions.id,
                conditions_data=conditions_data # Use the processed conditions_data
            )
            if not updated_conditions:
                # Handle error if conditions couldn't be updated
                raise Exception(f"Failed to update experimental conditions for experiment ID {experiment.experiment_id}")
            experiment.conditions = updated_conditions # Re-assign to ensure the session tracks the potentially new object from service
        else:
            # Create new conditions using the service
            # The service expects the string experiment_id
            created_conditions = ExperimentalConditionsService.create_experimental_conditions(
                db=db,
                experiment_id=experiment.experiment_id, # Pass the string ID
                conditions_data=conditions_data # Use the processed conditions_data
            )
            if not created_conditions:
                # Handle error if conditions couldn't be created
                raise Exception(f"Failed to create experimental conditions for experiment ID {experiment.experiment_id}")
            experiment.conditions = created_conditions # Assign the newly created conditions
        
        # Prepare new values for logging
        new_values = {
            'experiment_id': data['experiment_id'],
            'sample_id': data['sample_id'],
            'researcher': data['researcher'],
            'status': data['status'],
            'date': data['date'].isoformat() if data['date'] else None,
            'conditions': conditions_data # Log the processed conditions
        }
        
        # Use utility for logging
        log_modification(
            db=db,
            experiment_fk=experiment.id,
            experiment_id=experiment.experiment_id,
            modified_table="experiments",
            modification_type="update",
            old_values=old_values,
            new_values=new_values
        )
        
        # Commit the changes
        db.commit()
        
        # Set a flag in session state to trigger a rerun
        st.session_state.experiment_updated = True
        
        st.success("Experiment updated successfully!")
        return True
    except Exception as e:
        db.rollback()
        st.error(f"Error updating experiment: {str(e)}")
        return False
    finally:
        db.close()

def handle_delete_experiment(db_experiment_id: int):
    """
    Deletes an experiment and its associated data from the database.

    Args:
        db_experiment_id (int): The primary key (id) of the experiment to delete.

    Returns:
        bool: True if deletion was successful, False otherwise.
        
    Note: This function assumes that cascade deletes are properly configured
    in the SQLAlchemy models (e.g., using cascade="all, delete-orphan" on
    relationships from Experiment to its related tables like ExperimentalConditions,
    ExperimentNotes, ExperimentalResults, ModificationsLog, and from
    ExperimentalResults to its own related data like ScalarData, NMRData, ResultFiles).
    If cascades are not set up, related records must be deleted manually here.
    """
    try:
        db = SessionLocal()
        experiment = db.query(Experiment).filter(Experiment.id == db_experiment_id).first()

        if experiment is None:
            st.error(f"Experiment with ID {db_experiment_id} not found for deletion.")
            return False

        # Log this action before deleting
        log_modification(
            db=db,
            experiment_fk=experiment.id,
            experiment_id=experiment.experiment_id,
            modified_table="experiments",
            modification_type="delete",
            old_values={'experiment_id': experiment.experiment_id, 'id': experiment.id}
        )

        # If cascade deletes are properly configured in the models,
        # deleting the experiment object will also delete all its related data.
        db.delete(experiment)
        
        # Commit the transaction
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        st.error(f"Error deleting experiment: {str(e)}")
        return False
    finally:
        if 'db' in locals() and db:
            db.close()

def save_note(experiment_id, note_text):
    """
    Save a new note to the database.
    
    Args:
        experiment_id (int): The unique identifier of the experiment
        note_text (str): The text content of the note
        
    This function:
    - Creates a new note entry
    - Associates it with the specified experiment
    - Handles database transactions and error cases
    """
    try:
        db = SessionLocal()
        
        # Get the experiment to get its string ID
        experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
        if not experiment:
            raise Exception(f"Experiment with ID {experiment_id} not found")
        
        # Create a new note
        note = ExperimentNotes(
            experiment_fk=experiment_id,  # Set the foreign key to the experiment's primary key
            experiment_id=experiment.experiment_id,  # Set the string ID
            note_text=note_text.strip()
        )
        
        # Add the note to the session
        db.add(note)
        db.flush() # Flush to get note ID for logging if needed, and to ensure it's in the transaction

        # Log the creation of the note
        log_modification(
            db=db,
            experiment_fk=experiment.id,
            experiment_id=experiment.experiment_id,
            modified_table="experiment_notes",
            modification_type="create",
            new_values={'note_id': note.id, 'note_text': note.note_text}
        )
        
        # Commit the transaction
        db.commit()
        
        st.success("Note saved successfully!")
        
    except Exception as e:
        db.rollback()
        st.error(f"Error saving note: {str(e)}")
        raise e
    finally:
        db.close()

def submit_note_edit(note_id, edited_text):
    """
    Handle note edit submission.
    
    Args:
        note_id (int): The unique identifier of the note to edit
        edited_text (str): The new text content for the note
        
    This function:
    - Validates the edited text
    - Calls update_note to save changes
    - Updates the session state
    """
    if not edited_text.strip():
        st.error("Note text cannot be empty")
        return
    
    update_note(note_id, edited_text)
    st.session_state.note_form_state['editing_note_id'] = None

def update_note(note_id, note_text):
    """
    Update an existing note in the database.
    
    Args:
        note_id (int): The unique identifier of the note to update
        note_text (str): The new text content for the note
        
    This function:
    - Retrieves the existing note
    - Updates its content
    - Handles database transactions and error cases
    """
    try:
        db = SessionLocal()
        
        # Get the note
        note = db.query(ExperimentNotes).filter(ExperimentNotes.id == note_id).first()
        
        if note is None:
            st.error("Note not found")
            return
        
        old_text = note.note_text
        # Update the note
        note.note_text = note_text.strip()

        # Log the update
        log_modification(
            db=db,
            experiment_fk=note.experiment_fk,
            experiment_id=note.experiment_id,
            modified_table="experiment_notes",
            modification_type="update",
            old_values={'note_id': note.id, 'note_text': old_text},
            new_values={'note_id': note.id, 'note_text': note.note_text}
        )
        
        # Commit the transaction
        db.commit()
        
        st.success("Note updated successfully!")
        
    except Exception as e:
        db.rollback()
        st.error(f"Error updating note: {str(e)}")
        raise e
    finally:
        db.close()