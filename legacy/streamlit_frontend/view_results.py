import streamlit as st
import pandas as pd
import os
import json
import datetime
import pytz
from sqlalchemy import orm
from database import SessionLocal, ExperimentalResults, ScalarResults, ICPResults, ResultFiles
from frontend.config.variable_config import (
    SCALAR_RESULTS_CONFIG,
)
from frontend.components.utils import (
    generate_form_fields,
    format_value # Assuming format_value is moved or duplicated here/in utils
)
from frontend.components.experimental_results import (
    save_results,
    delete_experimental_results,
    delete_result_file,
)

# --- Main Rendering Function ---
def render_results_section(experiment):
    """
    Renders the entire 'Results' section for an experiment, including display and add/edit forms.
    """
    st.markdown("### Results")

    db = SessionLocal()
    try:
        # Fetch all results for the experiment, preloading related data
        # Sort by time_post_reaction
        all_results = db.query(ExperimentalResults).options(
            # Eager load specific result data and files
            orm.selectinload(ExperimentalResults.scalar_data),
            orm.selectinload(ExperimentalResults.icp_data),
            orm.selectinload(ExperimentalResults.files)
        ).filter(
            ExperimentalResults.experiment_fk == experiment['id']  # Use FK instead of experiment_id
        ).order_by(ExperimentalResults.time_post_reaction_days.asc().nulls_last()).all()  # Handle nulls

    finally:
        db.close()

    # Initialize session state for the results form
    if 'show_results_form' not in st.session_state:
        st.session_state.show_results_form = False
    if 'editing_result_id' not in st.session_state:
        st.session_state.editing_result_id = None # Store the ID of the result being edited
    if 'current_experiment_id_results' not in st.session_state:
         st.session_state.current_experiment_id_results = None

    # Determine if we are showing the form for THIS experiment
    showing_form_for_this_experiment = (
        st.session_state.show_results_form and
        st.session_state.current_experiment_id_results == experiment['id'] # Use DB id for state tracking
    )

    # --- Display Existing Results ---
    if all_results:
        st.write("Recorded Results:")
        for result in all_results:
            display_single_result(result, experiment['id']) # Pass experiment DB id
    elif not showing_form_for_this_experiment:
         st.info("No results recorded for this experiment yet.")

    # --- Add Results Button ---
    # Show button only if not currently showing the form for this experiment
    if not showing_form_for_this_experiment:
        if st.button("Add Results", key=f"add_results_btn_{experiment['id']}"):
            st.session_state.show_results_form = True
            st.session_state.editing_result_id = None # Ensure we are adding, not editing
            st.session_state.current_experiment_id_results = experiment['id']
            st.rerun()

    # --- Add/Edit Results Form ---
    if showing_form_for_this_experiment:
        render_results_form(experiment['id']) # Pass experiment DB id

# --- Helper to Display a Single Result Entry ---
def display_single_result(result, experiment_db_id):
    """Displays a single result entry (time point) in an expander."""
    # --- Build the expander title ---
    title_parts = [f"Results at {result.time_post_reaction_days:.1f} days"]
    
    # Get scalar data for use in title and body
    scalar_data = result.scalar_data
    icp_data = result.icp_data
    
    # Add concentration if available
    if scalar_data and scalar_data.gross_ammonium_concentration_mM is not None:
        conc_config = SCALAR_RESULTS_CONFIG['gross_ammonium_concentration_mM']
        formatted_conc = format_value(scalar_data.gross_ammonium_concentration_mM, conc_config)
        method_value = getattr(scalar_data, "ammonium_quant_method", None)
        method = f" ({method_value})" if method_value else ""
        title_parts.append(f"{formatted_conc} mM NH₄⁺{method}")
    
    # Add ICP data indicator if available
    if icp_data:
        all_elements = icp_data.get_all_detected_elements()
        detected_count = len([e for e in all_elements.values() if e is not None and e > 0])
        if detected_count > 0:
            title_parts.append(f"ICP: {detected_count} elements")
    
    # Add truncated description
    description = result.description
    if description:
        max_len = 50
        truncated_desc = (description[:max_len] + '...') if len(description) > max_len else description
        title_parts.append(truncated_desc)

    expander_title = " - ".join(title_parts)
    
    # Add measurement date to title if available
    if result.created_at:
        # Format the date for display
        date_str = result.created_at.strftime("%m/%d/%Y")
        expander_title += f" (Measured: {date_str})"
    
    with st.expander(expander_title):
        # --- Prepare Measurement Date for Table ---
        measurement_date_str = None
        if result.created_at:
            est = pytz.timezone('US/Eastern')
            if result.created_at.tzinfo is None:
                utc_time = pytz.utc.localize(result.created_at)
            else:
                utc_time = result.created_at
            eastern_time = utc_time.astimezone(est)
            measurement_date_str = eastern_time.strftime('%B %d, %Y at %I:%M %p')
        
        # --- Display Scalar Results First ---
        if scalar_data:
            st.markdown("##### Scalar Measurements") # Changed header slightly
            scalar_data_dict = {}
            # Insert measurement date as the first row
            if measurement_date_str:
                scalar_data_dict["Measurement Date"] = measurement_date_str
            # Display all scalar fields based on the order in SCALAR_RESULTS_CONFIG
            skip_fields = ['time_post_reaction'] # Already in expander title
            for field_name, config in SCALAR_RESULTS_CONFIG.items():
                if field_name not in skip_fields:
                    value = getattr(scalar_data, field_name, None)
                    if value is not None:  # Only add non-null values
                        scalar_data_dict[config['label']] = format_value(value, config)
            if scalar_data_dict:
                scalar_df = pd.DataFrame([scalar_data_dict]).T.rename(columns={0: "Value"})
                scalar_df["Value"] = scalar_df["Value"].astype(str) # Ensure string type
                st.table(scalar_df)
            # Display message only if no scalar_data object exists at all

        # --- Display ICP Elemental Analysis Data ---
        icp_data = result.icp_data
        if icp_data:
            st.markdown("##### ICP Elemental Analysis") 
            
            # Get all detected elements using the model's method
            all_elements = icp_data.get_all_detected_elements()
            
            if all_elements:
                # Create DataFrame similar to bulk_uploads preview
                icp_summary = {}
                
                # Add metadata first
                if icp_data.dilution_factor:
                    icp_summary["Dilution Factor"] = f"{icp_data.dilution_factor:.1f}x"
                if icp_data.measurement_date:
                    date_str = icp_data.measurement_date.strftime("%m/%d/%Y")
                    icp_summary["Measurement Date"] = date_str
                if icp_data.instrument_used:
                    icp_summary["Instrument"] = icp_data.instrument_used
                
                # Sort elements by concentration (descending) for better display
                sorted_elements = sorted(all_elements.items(), key=lambda x: x[1] if x[1] is not None else 0, reverse=True)
                
                # Display elements with concentrations
                element_count = 0
                for element, concentration in sorted_elements:
                    if concentration is not None and concentration > 0:  # Only show detected elements
                        element_title = element.capitalize()
                        icp_summary[f"{element_title} (ppm)"] = f"{concentration:.3f}"
                        element_count += 1
                        
                        # Limit display to first 10 elements to avoid overwhelming the UI
                        if element_count >= 10:
                            break
                
                if len(sorted_elements) > 10:
                    icp_summary["Note"] = f"Showing top 10 elements. Total detected: {len([e for e in sorted_elements if e[1] is not None and e[1] > 0])}"
                
                if icp_summary:
                    icp_df = pd.DataFrame([icp_summary]).T.rename(columns={0: "Value"})
                    icp_df["Value"] = icp_df["Value"].astype(str)
                    st.table(icp_df)

        # --- Display Primary Result Data (e.g., NMR) Second ---
        primary_data_displayed = False
        # Since NMRResults is removed, we no longer have a specific data block for it.
        # The ammonium concentration is now in ScalarResults and displayed above.
        # This structure is kept for future primary result types like GC, PXRF.
        
        # If no specific data was found/displayed for the primary type
        if not primary_data_displayed:
            pass  # File uploads are not routine for database uploading

        # --- Display Associated Files ---
        if result.files:
            st.markdown("##### Associated Files")
            for file_record in result.files:
                file_col1, file_col2, file_col3 = st.columns([3, 4, 1])
                with file_col1:
                    st.write(f"- {file_record.file_name}")
                with file_col2:
                    if os.path.exists(file_record.file_path):
                        try:
                            with open(file_record.file_path, 'rb') as fp:
                                st.download_button(
                                    label="Download",
                                    data=fp.read(),
                                    file_name=file_record.file_name,
                                    mime=file_record.file_type,
                                    key=f"download_file_{file_record.id}"
                                )
                        except Exception as e:
                            st.warning(f"Could not read file {file_record.file_name}: {e}")
                    else:
                        st.warning(f"File not found: {file_record.file_name}")
                with file_col3:
                     if st.button("❌", key=f"delete_file_{file_record.id}", help="Delete this file"):
                         delete_success = delete_result_file(file_record.id)
                         if delete_success:
                             st.session_state.experiment_updated = True
                             st.rerun()

        st.markdown("---") # Separator

        # --- Edit/Delete Buttons ---
        col1, col2, col3 = st.columns([1, 1, 5])
        with col1:
            # Button text reflects what can be edited
            edit_button_label = f"Edit Data"
            if st.button(edit_button_label, key=f"edit_result_{result.id}"):
                st.session_state.show_results_form = True
                st.session_state.editing_result_id = result.id
                st.session_state.current_experiment_id_results = experiment_db_id
                st.rerun()
        with col2:
            if st.button("Delete Measurement", key=f"delete_result_{result.id}"):
                try:
                    delete_experimental_results(result.id)
                    st.session_state.experiment_updated = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Error deleting result time point: {e}")

# --- Form Rendering Function ---
def render_results_form(experiment_db_id):
    """Renders the Add/Edit form for experiment results."""

    form_title = "Add New Results"
    current_data = {} # Combined dict for pre-populating
    editing_time = None

    # Generate base key parts using DB id
    base_key_part = f"results_{experiment_db_id}_{st.session_state.editing_result_id or 'new'}"
    form_key = f"{base_key_part}_form"
    buffer_key = f"{base_key_part}_buffer"
    file_uploader_key = f"{base_key_part}_uploader"

    # --- Initialize Session State for file buffer ---
    if buffer_key not in st.session_state:
        st.session_state[buffer_key] = {'uploaded_files': []}
    file_buffer = st.session_state[buffer_key]

    if st.session_state.editing_result_id:
        # Fetch the specific result being edited to pre-populate form
        db = SessionLocal()
        try:
            result_to_edit = db.query(ExperimentalResults).options(
                orm.selectinload(ExperimentalResults.scalar_data), # Always load scalar
                # No need to load nmr_data anymore
            ).filter(
                ExperimentalResults.id == st.session_state.editing_result_id
            ).first()

            if result_to_edit:
                form_title = f"Edit Results at {result_to_edit.time_post_reaction_days:.1f} days"
                editing_time = result_to_edit.time_post_reaction_days
                current_data['time_post_reaction'] = editing_time # Pre-populate time
                current_data['description'] = result_to_edit.description # Pre-populate description
                current_data['measurement_date'] = result_to_edit.created_at # Pre-populate date for editing

                # Pre-populate from ScalarResults first
                if result_to_edit.scalar_data:
                    scalar_config = SCALAR_RESULTS_CONFIG
                    for field_name in scalar_config.keys():
                        default_val = scalar_config[field_name].get('default')
                        current_data[field_name] = getattr(result_to_edit.scalar_data, field_name, default_val)
                else: # Populate with scalar defaults if no scalar record exists yet
                    for field_name, config in SCALAR_RESULTS_CONFIG.items():
                        current_data[field_name] = config['default']

            else:
                st.error("Could not find the result entry to edit.")
                # Reset state and rerun
                st.session_state.show_results_form = False
                st.session_state.editing_result_id = None
                st.session_state.current_experiment_id_results = None
                st.rerun()
        finally:
            db.close()
    else:
        # Adding new: All fields are now scalar.
        # Use defaults from SCALAR config
        for field_name, config in SCALAR_RESULTS_CONFIG.items():
            current_data[field_name] = config['default']
        current_data['description'] = "" # Default to empty for new results
        current_data['measurement_date'] = datetime.datetime.now().date()

    st.markdown(f"#### {form_title}")

    # --- File Upload Section (Outside Form) ---
    st.markdown("**Upload New Files** (Associated with this time point)")
    uploaded_files_widget = st.file_uploader(
        "Select files",
        accept_multiple_files=True,
        key=file_uploader_key,
        help="Upload data files, images, etc. related to these results."
    )

    # --- Update file buffer based on File Uploader ---
    current_widget_files = uploaded_files_widget if uploaded_files_widget else []
    current_widget_file_names = {f.name for f in current_widget_files}
    buffer_file_names = {f.name for f in file_buffer['uploaded_files']}

    # Add new files from widget to buffer
    for file in current_widget_files:
         if file.name not in buffer_file_names:
             file_buffer['uploaded_files'].append(file)

    # Remove files from buffer that are no longer in the widget
    new_buffer_files = []
    for file in file_buffer['uploaded_files']:
         if file.name in current_widget_file_names:
             new_buffer_files.append(file)

    file_buffer['uploaded_files'] = new_buffer_files

    with st.form(key=form_key, clear_on_submit=True):
        form_values = {} # Will store scalar values

        # --- Render form fields ---
        st.markdown("**Result Metadata**")
        col1_meta, col2_meta, col3_meta = st.columns(3)
        with col1_meta:
            form_values['time_post_reaction'] = st.number_input(
                label=SCALAR_RESULTS_CONFIG['time_post_reaction']['label'],
                value=current_data.get('time_post_reaction', 0.0),
                min_value=0.0,
                step=0.5,
                format="%.1f",
                help=SCALAR_RESULTS_CONFIG['time_post_reaction']['help'],
                disabled=(editing_time is not None) # Disable if editing
            )

        with col2_meta:
            form_values['description'] = st.text_input(
                "Add a general description for this result entry",
                value=current_data.get('description', ''),
                key=f"{base_key_part}_desc"
            )
            
        with col3_meta:
            # Measurement date field - show for new results and when editing
            measurement_date = st.date_input(
                "Measurement Date",
                value=current_data.get('measurement_date', datetime.datetime.now().date()),
                help="The date when this measurement was taken",
                format="MM/DD/YYYY"
            )
            # Convert date to datetime with timezone
            est = pytz.timezone('US/Eastern')
            measurement_datetime = datetime.datetime.combine(measurement_date, datetime.time.min).replace(tzinfo=est)
            form_values['measurement_date'] = measurement_datetime

        st.markdown("---")
        
        # All fields are now considered scalar, so we render them in a two-column layout
        st.markdown("**Scalar Measurements**")
        scalar_field_names = [f for f in SCALAR_RESULTS_CONFIG.keys() if f not in ['time_post_reaction', 'description']]
        
        col1, col2 = st.columns(2)
        midpoint = (len(scalar_field_names) + 1) // 2
        
        fields_col1 = scalar_field_names[:midpoint]
        fields_col2 = scalar_field_names[midpoint:]

        with col1:
            for field_name in fields_col1:
                config = SCALAR_RESULTS_CONFIG[field_name]
                default_val = current_data.get(field_name, config.get('default'))
                field_key = f"{base_key_part}_{field_name}"

                if config['type'] == 'number':
                    form_values[field_name] = st.number_input(
                        label=config['label'],
                        value=default_val,
                        min_value=config.get('min_value'),
                        max_value=config.get('max_value'),
                        step=config.get('step'),
                        format=config.get('format'),
                        help=config.get('help'),
                        key=field_key,
                        disabled=config.get('readonly', False)
                    )
                elif config['type'] == 'select':
                    # Find index for default value, default to 0 if not found
                    try:
                        index = config['options'].index(default_val)
                    except ValueError:
                        index = 0
                    form_values[field_name] = st.selectbox(
                        label=config['label'],
                        options=config['options'],
                        index=index,
                        help=config.get('help'),
                        key=field_key
                    )

        with col2:
            for field_name in fields_col2:
                config = SCALAR_RESULTS_CONFIG[field_name]
                default_val = current_data.get(field_name, config.get('default'))
                field_key = f"{base_key_part}_{field_name}"

                if config['type'] == 'number':
                    form_values[field_name] = st.number_input(
                        label=config['label'],
                        value=default_val,
                        min_value=config.get('min_value'),
                        max_value=config.get('max_value'),
                        step=config.get('step'),
                        format=config.get('format'),
                        help=config.get('help'),
                        key=field_key,
                        disabled=config.get('readonly', False)
                    )
                elif config['type'] == 'select':
                    # Find index for default value, default to 0 if not found
                    try:
                        index = config['options'].index(default_val)
                    except ValueError:
                        index = 0
                    form_values[field_name] = st.selectbox(
                        label=config['label'],
                        options=config['options'],
                        index=index,
                        help=config.get('help'),
                        key=field_key
                    )

        # --- Submit Button ---
        st.markdown("---")
        submitted = st.form_submit_button(
            "Save Results",
            type="primary",
            use_container_width=True
        )

    # --- Post-form processing ---
    if submitted:
        # Get description from form_values and validate it
        result_description = form_values.get('description', "").strip()
        if not result_description:
            st.error("The 'description' field is required. Please provide a brief summary of the result.")
            return # Stop processing if validation fails

        # Prepare list of files to be saved
        files_to_save = []
        if file_buffer.get('uploaded_files'):
             for uploaded_file in file_buffer['uploaded_files']:
                 # No description needed anymore
                 files_to_save.append({'file': uploaded_file})

        # Save all data
        save_results(
            experiment_id=experiment_db_id,
            time_post_reaction=form_values['time_post_reaction'],
            result_description=result_description,
            scalar_data=form_values,
            files_to_save=files_to_save,
            result_id_to_edit=st.session_state.editing_result_id,
            measurement_date=form_values.get('measurement_date')
        )

        # Clear buffer and reset state
        st.session_state[buffer_key] = {'uploaded_files': []}
        st.session_state.show_results_form = False
        st.session_state.editing_result_id = None
        st.session_state.current_experiment_id_results = None
        st.rerun()
