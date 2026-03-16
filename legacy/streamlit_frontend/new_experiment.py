import datetime
import streamlit as st
from database import SessionLocal
from database import Experiment, ExperimentalConditions, ExperimentNotes, ExperimentStatus
from frontend.components.utils import log_modification, generate_form_fields, get_sample_options
from frontend.config.variable_config import FIELD_CONFIG, EXPERIMENT_STATUSES
# Import the new service
from backend.services.experimental_conditions_service import ExperimentalConditionsService
from backend.services.bulk_uploads.experiment_status import ExperimentStatusService
import pytz
from frontend.components.chemical_managing import render_compound_manager
from backend.services.experiment_validation import parse_experiment_id, validate_experiment_id, format_validation_warning

# Helper function to get default values from FIELD_CONFIG
def get_default_conditions():
    return {name: config['default'] for name, config in FIELD_CONFIG.items()}

def render_new_experiment():
    """
    Render the interface for creating a new experiment.
    
    This function creates a multi-step form interface that allows users to:
    - Enter basic experiment information (ID, sample ID, researcher, status)
    - Set experimental conditions (temperature, pressure, pH, etc.)
    - Configure optional parameters
    - Add initial notes
    
    The function uses Streamlit's session state to manage form data, the 
    `generate_form_fields` utility for creating inputs, and handles the 
    submission process with proper validation and error handling.
    
    The interface is divided into two steps:
    1. Data collection form
    2. Success message and option to create another experiment
    """
    # Initialize session state
    if 'step' not in st.session_state:
        st.session_state.step = 1

    if 'experiment_data' not in st.session_state:
        st.session_state.experiment_data = {
            'experiment_id': '',
            'sample_id': '',
            'researcher': '',
            'status': EXPERIMENT_STATUSES[0], # Default status
            'conditions': get_default_conditions(), # Load defaults from FIELD_CONFIG
            'notes': [], # Keep notes separate, initial note handled in form
            'initial_note': '', # Clear initial note field
            'created_at': datetime.datetime.now() # Added created_at field
        }
    else:
        # Always merge defaults with current conditions
        current = st.session_state.experiment_data.get('conditions', {})
        st.session_state.experiment_data['conditions'] = {**{**get_default_conditions(), **current}, **current}
    
    # STEP 1: Collect experiment data
    if st.session_state.step == 1:
        with st.form(key="experiment_form"):
            st.subheader("Experiment Details")

            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### Basic Information")
                
                # ID builder helper and naming guide
                with st.expander("💡 Experiment ID Naming Guide", expanded=False):
                    st.markdown("""
                    **Supported Formats:**
                    - `ExperimentType_ResearcherInitials_Index` (3-part, e.g., `Serum_MH_101`)
                    - `ExperimentType_Index` (2-part, e.g., `HPHT_001`)
                    
                    **Examples:**
                    - **Base experiment (3-part):** `Serum_MH_101`
                    - **Base experiment (2-part):** `HPHT_001`
                    - **Sequential runs:** `Serum_MH_101-2` or `HPHT_001-2` (2nd brine)
                    - **Treatment variants:** `Serum_MH_101_Desorption` or `HPHT_001_Desorption`
                    - **Combined:** `Serum_MH_101-2_Desorption` or `HPHT_001-2_Desorption`
                    
                    **Delimiter Rules:**
                    - Use **hyphen-NUMBER** (`-2`, `-3`) for sequential lineage tracking
                    - Use **underscore_TEXT** (`_Desorption`, `_Annealing`) for special treatments
                    - Underscores within names are fine (e.g., `Core_Flood`)
                    
                    **Experiment Types:** Serum, Autoclave, HPHT, CF (Core Flood), Other
                    """)
                    
                    # Quick ID builder
                    st.markdown("**Quick ID Builder:**")
                    st.caption("Build a compliant ID and copy it manually to the Experiment ID field above.")
                    use_3_part = st.checkbox("Use 3-part format (with initials)", value=True, key="id_builder_format")
                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        exp_type_input = st.text_input("Type", placeholder="Serum", key="id_builder_type")
                        if use_3_part:
                            researcher_init = st.text_input("Initials", placeholder="MH", key="id_builder_init")
                        else:
                            researcher_init = None
                    with col_b:
                        exp_index = st.text_input("Index", placeholder="101", key="id_builder_index")
                        seq_num = st.number_input("Sequential #", min_value=0, value=0, step=1, key="id_builder_seq",
                                                   help="0 = base, 1+ = that run number")
                    with col_c:
                        treatment = st.text_input("Treatment", placeholder="Desorption", key="id_builder_treat")
                    
                    if exp_type_input and exp_index:
                        if use_3_part and researcher_init:
                            built_id = f"{exp_type_input}_{researcher_init}_{exp_index}"
                        else:
                            built_id = f"{exp_type_input}_{exp_index}"
                        if seq_num > 0:
                            built_id += f"-{seq_num}"
                        if treatment:
                            built_id += f"_{treatment}"
                        st.code(built_id)
                        st.caption("↑ Copy this ID and paste into the Experiment ID field above")
                
                experiment_id = st.text_input(
                    "Experiment ID", 
                    value=st.session_state.experiment_data.get('experiment_id', ''),
                    help="Enter a unique identifier: ExperimentType_Index or ExperimentType_ResearcherInitials_Index"
                )
                
                # Real-time validation display (wrapped in try-except for safety)
                if experiment_id:
                    try:
                        is_valid, warnings = validate_experiment_id(experiment_id)
                        if warnings:
                            st.warning(format_validation_warning(warnings))
                        else:
                            parsed = parse_experiment_id(experiment_id)
                            if parsed.experiment_type:
                                if parsed.researcher_initials:
                                    st.success(f"✓ Valid format: {parsed.experiment_type.value} experiment by {parsed.researcher_initials}")
                                else:
                                    st.success(f"✓ Valid format: {parsed.experiment_type.value} experiment")
                            if parsed.sequential_number:
                                st.info(f"Sequential run #{parsed.sequential_number}")
                            if parsed.treatment_variant:
                                st.info(f"Treatment variant: {parsed.treatment_variant}")
                    except Exception:
                        # Silently skip validation display if Streamlit context not ready
                        pass
                
                created_at = st.date_input(
                    "Creation Date",
                    value=st.session_state.experiment_data.get('created_at', datetime.datetime.now()),
                    help="The date when the experiment was created",
                    format="MM/DD/YYYY"
                )
                
                # Sample selection - allow blank for control runs or experiments without rock samples
                # Get sample options from database using utils function
                sample_options, sample_dict = get_sample_options()
                
                # Find current selection if any
                current_sample_id = st.session_state.experiment_data.get('sample_id', '')
                current_index = 0
                if current_sample_id:
                    for i, option in enumerate(sample_options):
                        if sample_dict.get(option) == current_sample_id:
                            current_index = i
                            break
                
                selected_sample_display = st.selectbox(
                    "Rock Sample",
                    options=sample_options,
                    index=current_index,
                    help="Select a rock sample from the database, or leave blank for control runs/experiments without rock samples. You can type to search.",
                    format_func=lambda x: "None (Control Run)" if x == "" else x
                )
                
                # Get the actual sample_id from the selection
                sample_id = sample_dict.get(selected_sample_display, "")
                
                # Additional safety: if mapping fails, extract sample_id from display text
                if not sample_id and selected_sample_display and selected_sample_display != "":
                    # Extract just the sample_id part (everything before the first " - ")
                    sample_id = selected_sample_display.split(" - ")[0].strip()
                    # Verify this is a valid sample_id by checking if it exists in our sample_dict values
                    if sample_id not in sample_dict.values():
                        sample_id = ""  # Reset to empty if not valid
                
                # Auto-populate researcher from experiment_id, but allow override
                default_researcher = st.session_state.experiment_data.get('researcher', '')
                if experiment_id and not default_researcher:
                    try:
                        parsed = parse_experiment_id(experiment_id)
                        if parsed.researcher_initials:
                            default_researcher = parsed.researcher_initials
                    except Exception:
                        pass  # Skip auto-population if parsing fails
                
                researcher = st.text_input(
                    "Researcher Name", 
                    value=default_researcher,
                    help="Auto-populated from Experiment ID, but you can override it"
                )
                status = st.selectbox(
                    "Experiment Status",
                    options=EXPERIMENT_STATUSES,
                    index=EXPERIMENT_STATUSES.index(st.session_state.experiment_data.get('status', EXPERIMENT_STATUSES[0]))
                )
                
                st.markdown("#### Required Conditions")
                # Get required field names from FIELD_CONFIG
                required_field_names = [name for name, config in FIELD_CONFIG.items() if config.get('required', False)]
                required_values = generate_form_fields(
                    FIELD_CONFIG, 
                    st.session_state.experiment_data['conditions'], 
                    required_field_names,
                    key_prefix="new_req"
                )
                
                # --- Moved Initial Notes Section Here ---
                st.markdown("#### Experiment Description") # Changed header to reflect new purpose
                initial_note = st.text_area(
                    "Experiment Description",
                    value=st.session_state.experiment_data.get('initial_note', ''),
                    height=150,
                    max_chars=100,
                    help="Provide a brief description of the experiment (required, max 100 characters)."
                )
                
            with col2:
                st.markdown("#### Optional Parameters")
                # Get optional field names from FIELD_CONFIG
                optional_field_names = [name for name, config in FIELD_CONFIG.items() if not config.get('required', False) and not config.get('readonly', False)]
                optional_values = generate_form_fields(
                    FIELD_CONFIG, 
                    st.session_state.experiment_data['conditions'], 
                    optional_field_names,
                    key_prefix="new_opt"
                )

            # Combine required and optional values into a single dictionary
            all_condition_values = {**required_values, **optional_values}
            
            # --- Form Submission ---
            st.markdown("---") # Separator
            submit_button = st.form_submit_button("💾 Save Experiment")

            if submit_button:                
                # --- Data Validation (Basic Example) ---
                if not experiment_id or not researcher or not initial_note:
                     st.error("Experiment ID, Researcher Name, and Experiment Description are required.")
                # Note: sample_id is now optional - blank is allowed for control runs
                # Add more specific validation based on FIELD_CONFIG if needed 
                # (e.g., check numeric ranges beyond what st.number_input enforces)
                else:
                    # Update session state with collected data
                    st.session_state.experiment_data.update({
                        'experiment_id': experiment_id,
                        'sample_id': sample_id,  # Can be empty string for control runs
                        'researcher': researcher,
                        'status': status,
                        'conditions': all_condition_values,
                        'initial_note': initial_note.strip() # Store the initial note text
                    })
                    
                    # Call save_experiment
                    success = save_experiment() # No need to pass data, it reads from session state
                    # Success/error messages are handled within save_experiment
                    # If successful, save_experiment sets step to 2 and reruns
                    if success:
                        st.rerun()

    # STEP 2: Show a success message and allow another experiment
    elif st.session_state.step == 2:
        st.success(f"Experiment {st.session_state.get('last_created_experiment_id', '')} (Number: {st.session_state.get('last_created_experiment_number', '')}) created successfully!")

        # Render compound manager to add associated compounds immediately after creation
        created_conditions_id = st.session_state.get('created_conditions_id')
        if created_conditions_id:
            st.markdown("---")
            st.subheader("Add Compounds to This Experiment")
            render_compound_manager(conditions_id=created_conditions_id, key_prefix="newexp")
        else:
            st.info("Experimental conditions are not available yet for compound assignment.")
        if st.button("Create Another Experiment"):
            st.session_state.step = 1
            
            if 'previous_experiment_data' in st.session_state:
                # Pre-fill with previous data
                previous_data = st.session_state.previous_experiment_data
                st.session_state.experiment_data = {
                    'experiment_id': '',  # Clear for new experiment
                    'sample_id': previous_data.get('sample_id', ''),
                    'researcher': previous_data.get('researcher', ''),
                    'status': EXPERIMENT_STATUSES[0],  # Default for new experiments
                    'conditions': previous_data.get('conditions', get_default_conditions()),
                    'notes': [], # Notes are experiment-specific
                    'initial_note': '',  # Description is experiment-specific
                    'created_at': datetime.datetime.now() # Reset created_at
                }
                del st.session_state['previous_experiment_data'] # Clear after use
            else:
                # Default reset if no previous data
                st.session_state.experiment_data = {
                    'experiment_id': '',
                    'sample_id': '',
                    'researcher': '',
                    'status': EXPERIMENT_STATUSES[0],
                    'conditions': get_default_conditions(), # Reset conditions to defaults
                    'notes': [], # Keep notes separate, initial note handled in form
                    'initial_note': '', # Clear initial note field
                    'created_at': datetime.datetime.now() # Reset created_at
                }

            if 'last_created_experiment_number' in st.session_state:
                del st.session_state['last_created_experiment_number']
            if 'last_created_experiment_id' in st.session_state:
                del st.session_state['last_created_experiment_id']
            if 'created_conditions_id' in st.session_state:
                del st.session_state['created_conditions_id']
            if 'created_experiment_fk' in st.session_state:
                del st.session_state['created_experiment_fk']
            st.rerun()

def save_experiment():
    """
    Save the new experiment data to the database using services.
    """
    db = None # Initialize db to None
    try:
        # Create a database session
        db = SessionLocal()
        
        # Get data from session state
        exp_data = st.session_state.experiment_data
        
        # Validate experiment ID and display warnings (but allow creation)
        experiment_id_str = exp_data['experiment_id']
        experiment_type_enum = None
        
        try:
            is_valid, warnings = validate_experiment_id(experiment_id_str)
            if warnings:
                for warning in warnings:
                    st.warning(f"Experiment ID validation: {warning}")
            
            # Parse experiment_id to extract type and researcher
            parsed = parse_experiment_id(experiment_id_str)
            experiment_type_enum = parsed.experiment_type  # ExperimentType enum or None
        except Exception as e:
            st.warning(f"Could not validate experiment ID format: {e}")
        
        # Get the next experiment number, with a lock to prevent race conditions
        last_experiment = db.query(Experiment).order_by(Experiment.experiment_number.desc()).with_for_update().first()
        next_experiment_number = 1 if last_experiment is None else last_experiment.experiment_number + 1
        
        # For experiments without rock samples, set sample_id to None
        sample_id = exp_data['sample_id'] if exp_data['sample_id'] else None
        
        # Create a new experiment
        experiment = Experiment(
            experiment_number=next_experiment_number,
            experiment_id=exp_data['experiment_id'],
            sample_id=sample_id,
            researcher=exp_data['researcher'],
            date=datetime.datetime.now(),
            status=getattr(ExperimentStatus, exp_data['status'])
        )
        
        # Add the experiment to the session
        db.add(experiment)
        db.flush() # Flush to ensure experiment exists in the transaction before service query
        
        # --- Use the Service to Create Experimental Conditions ---
        conditions_data = exp_data['conditions'].copy() # Get condition values

        # Convert empty strings to None for numeric fields
        for key, value in conditions_data.items():
            if key in FIELD_CONFIG and FIELD_CONFIG[key]['type'] == 'number' and value == '':
                conditions_data[key] = None
        
        # Add experiment_type from parsed ID if available
        if experiment_type_enum:
            conditions_data['experiment_type'] = experiment_type_enum.value
        
        # The service expects the string experiment_id
        conditions = ExperimentalConditionsService.create_experimental_conditions(
            db=db, 
            experiment_id=experiment.experiment_id, # Pass the string ID
            conditions_data=conditions_data
        )

        if conditions is None:
            # Handle error if conditions couldn't be created (e.g., experiment not found by service)
            # This case might be redundant if experiment is created right above, but good practice
            raise Exception(f"Failed to create experimental conditions for {experiment.experiment_id}")
        # Note: The service adds 'conditions' to the session and calls calculate_derived_conditions
        # --- End Service Usage ---
        
        # Manage reactor occupancy: if experiment is ONGOING and has reactor_number,
        # mark other ONGOING experiments in same reactor as COMPLETED
        if conditions.reactor_number and experiment.status == ExperimentStatus.ONGOING:
            marked, reactor_warnings = ExperimentStatusService.manage_reactor_occupancy(
                db, experiment, conditions.reactor_number, commit=False
            )
            # Display warnings/info to user
            for warning in reactor_warnings:
                st.info(warning)
        
        # Store created identifiers for immediate compound management (step 2)
        try:
            st.session_state.created_conditions_id = conditions.id
            st.session_state.created_experiment_fk = experiment.id
        except Exception:
            pass

        # Add initial notes if any
        initial_note_text = exp_data.get('initial_note')
        if initial_note_text:
            # Ensure experiment has an ID before associating note if FK is on Experiment.id
            # If FK is on experiment_id (string), this flush isn't strictly needed here
            # db.flush() # Uncomment if ExperimentNotes.experiment_id links to Experiment.id (PK) -> Already flushed earlier
            note = ExperimentNotes(
                experiment_fk=experiment.id, # Assign the integer PK of the experiment
                experiment_id=experiment.experiment_id, # Assuming FK is on the string ID -> Keep string ID too
                note_text=initial_note_text
            )
            db.add(note)
        
        # Use utility for logging
        log_modification(
            db=db,
            experiment_fk=experiment.id,
            experiment_id=experiment.experiment_id,
            modified_table="experiments",
            modification_type="create",
            new_values={
                'experiment_number': experiment.experiment_number,
                'experiment_id': experiment.experiment_id,
                'sample_id': experiment.sample_id,
                'researcher': experiment.researcher,
                'date': experiment.date.isoformat(),
                'status': experiment.status.name,
                # Log the conditions *after* potential calculation by the service
                # Need to refresh 'conditions' to get calculated values if service doesn't refresh
                # The service currently does refresh, so this should be fine
                'conditions': {k: v.isoformat() if isinstance(v, datetime.datetime) else v 
                               for k, v in conditions.__dict__.items() 
                               if not k.startswith('_') and k not in ['id', 'experiment_id', 'experiment_fk']},
                'initial_note': initial_note_text if initial_note_text else None
            }
        )

        # Commit the transaction
        db.commit()
        
        # Store data for pre-filling the next form
        st.session_state.previous_experiment_data = exp_data.copy()
        
        # Show experiment number and ID for reference in step 2
        st.session_state.last_created_experiment_number = next_experiment_number
        st.session_state.last_created_experiment_id = exp_data['experiment_id']
        
        st.session_state.step = 2 # Move to success step
        
        return True # Indicate success
        
    except Exception as e:
        if db: # Check if db was initialized before trying to rollback
            db.rollback()
        # Check for unique constraint violations
        error_str = str(e).lower()
        if "unique constraint failed: experiments.experiment_id" in error_str:
            st.error(f"An experiment with ID '{st.session_state.experiment_data['experiment_id']}' already exists. Please choose a different experiment ID.")
        elif "unique constraint failed: experiments.experiment_number" in error_str:
            st.error("There was a conflict creating a new experiment number. This can happen if multiple experiments are created at the same time. Please try saving again.")
        else:
            st.error(f"Error saving experiment: {str(e)}")
        return False # Indicate failure
    finally:
        if db: # Check if db was initialized before trying to close
            db.close()