import streamlit as st
import pandas as pd
import datetime
import json
import os
from sqlalchemy import orm
from database import SessionLocal, SampleInfo, ExperimentNotes, Experiment, ExperimentStatus, ExperimentalConditions, ChemicalAdditive, Compound
from frontend.config.variable_config import (
    FIELD_CONFIG,
    EXPERIMENT_TYPES,
    EXPERIMENT_STATUSES,
    FEEDSTOCK_TYPES,
    PXRF_ELEMENT_COLUMNS
)
from frontend.components.utils import (
    split_conditions_for_display,
    get_condition_display_dict,
    format_value
)
from frontend.components.load_info import get_sample_info, get_external_analyses

from frontend.components.edit_experiment import (
    save_note,
    submit_note_edit
)
from frontend.components.view_results import render_results_section


import pytz

def display_experiment_details(experiment):
    """
    Displays the complete details of an experiment.

    This function renders all sections of the experiment details page:
    1. Basic Information, Required Parameters, and Secondary Parameters in a 3-column layout, each with Key-Value pairs.
    2. Results (delegated to render_results_section)
    3. Sample Information (including External Analyses like pXRF)
    4. Lab Notes

    Args:
        experiment (dict): Dictionary containing all experiment data
    """
    
    # Convert UTC times to EST for display
    est = pytz.timezone('US/Eastern')
    
    # Convert experiment date
    if isinstance(experiment['date'], datetime.datetime):
        if experiment['date'].tzinfo is None:
            experiment['date'] = experiment['date'].replace(tzinfo=pytz.UTC)
        display_date = experiment['date'].astimezone(est)
    else:
        display_date = experiment['date']
    
    # Convert updated_at
    if isinstance(experiment['updated_at'], datetime.datetime):
        if experiment['updated_at'].tzinfo is None:
            experiment['updated_at'] = experiment['updated_at'].replace(tzinfo=pytz.UTC)
        display_updated = experiment['updated_at'].astimezone(est)
    else:
        display_updated = experiment['updated_at']
    
    # Prepare basic info
    basic_info = {
        "Experiment Number": str(experiment['experiment_number']),
        "Experiment ID": str(experiment['experiment_id']),
        "Sample ID": str(experiment['sample_id']),
        "Researcher": str(experiment['researcher']),
        "Status": str(experiment['status']),
        "Date Created": display_date.strftime("%Y-%m-%d %H:%M %Z") if isinstance(display_date, datetime.datetime) else str(display_date),
        "Date Updated": display_updated.strftime("%Y-%m-%d %H:%M %Z") if isinstance(display_updated, datetime.datetime) else "N/A"
    }

    # Get conditions if they exist
    if experiment['conditions']:
        required_conditions, optional_conditions = split_conditions_for_display(experiment['conditions'])
    else:
        required_conditions = {}
        optional_conditions = {}

    # Create 3 main columns
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### Basic Information")
        if basic_info:
            df_basic = pd.DataFrame(list(basic_info.items()), columns=['Parameter', 'Value'])
            df_basic['Value'] = df_basic['Value'].astype(str)
            st.dataframe(df_basic, hide_index=True, use_container_width=True)
        else:
            st.info("No basic information available.")

    with col2:
        st.markdown("#### Required Parameters")
        if required_conditions:
            df_req = pd.DataFrame(list(required_conditions.items()), columns=['Parameter', 'Value'])
            df_req['Value'] = df_req['Value'].astype(str)
            st.dataframe(df_req, hide_index=True, use_container_width=True)
        else:
            st.info("No required parameters recorded.")

    with col3:
        st.markdown("#### Secondary Parameters")
        if optional_conditions:
            df_opt = pd.DataFrame(list(optional_conditions.items()), columns=['Parameter', 'Value'])
            df_opt['Value'] = df_opt['Value'].astype(str)
            st.dataframe(df_opt, hide_index=True, use_container_width=True)
        else:
            st.info("No secondary parameters recorded.")

    # --- Compounds used in this experiment ---
    try:
        db = SessionLocal()
        conditions_row = db.query(ExperimentalConditions).filter(ExperimentalConditions.experiment_fk == experiment['id']).first()
        if conditions_row:
            additives = (
                db.query(ChemicalAdditive, Compound)
                .join(Compound, ChemicalAdditive.compound_id == Compound.id)
                .filter(ChemicalAdditive.experiment_id == conditions_row.id)
                .order_by(Compound.name.asc(), ChemicalAdditive.addition_order.asc().nulls_last())
                .all()
            )
            if additives:
                st.markdown("#### Compounds")
                rows = []
                for add, comp in additives:
                    row = {
                        'Compound': comp.name,
                        'Amount': add.amount,
                        'Unit': getattr(add.unit, 'value', str(add.unit))
                    }
                    
                    # Add calculated mass if available
                    if add.mass_in_grams is not None:
                        row['Mass (g)'] = f"{add.mass_in_grams:.4f}"
                    
                    # Add final concentration if available
                    if add.final_concentration is not None and add.concentration_units:
                        row['Final Conc.'] = f"{add.final_concentration:.2f} {add.concentration_units}"
                    
                    # Add catalyst-specific values if available
                    if add.elemental_metal_mass is not None:
                        row['Elemental Mass (g)'] = f"{add.elemental_metal_mass:.4f}"
                    if add.catalyst_percentage is not None:
                        row['Catalyst %'] = f"{add.catalyst_percentage:.3f}%"
                    if add.catalyst_ppm is not None:
                        row['Catalyst (ppm)'] = f"{add.catalyst_ppm:.0f}"
                    
                    rows.append(row)
                df_compounds = pd.DataFrame(rows)
                st.dataframe(df_compounds, hide_index=True, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not load compounds: {e}")
    finally:
        try:
            db.close()
        except Exception:
            pass

    # --- Results Section (Delegated) ---
    render_results_section(experiment)

    # Sample Information Section
    st.markdown("### Sample Information")
    sample_info = get_sample_info(experiment['sample_id'])

    if sample_info:
        # Display existing sample info
        sample_info_df = pd.DataFrame([{
            "Rock Classification": str(sample_info['rock_classification']),
            "Location": f"{str(sample_info['state'])}, {str(sample_info['country'])}",
            "Coordinates": f"{str(sample_info['latitude'])}, {str(sample_info['longitude'])}",
            "Description": str(sample_info['description'])
        }]).T.rename(columns={0: "Value"})
        sample_info_df['Value'] = sample_info_df['Value'].astype(str)
        st.table(sample_info_df)

        # External Analyses
        st.markdown("#### External Analyses")
        external_analyses = get_external_analyses(experiment['sample_id'])

        if external_analyses:
            for analysis in external_analyses:
                # Format the date safely, handling None case
                date_str = analysis['analysis_date'].strftime('%Y-%m-%d') if analysis['analysis_date'] else 'Date not specified'

                with st.expander(f"{analysis['analysis_type']} Analysis - {date_str}"):

                    # --- Conditional Display based on analysis_type ---
                    if analysis['analysis_type'] == 'pXRF':
                        pxrf_reading_nos_str = analysis.get('pxrf_reading_no', 'Not Specified')
                        st.write(f"**pXRF Reading No(s):** {pxrf_reading_nos_str}")

                        # Access the pre-fetched data from the database
                        pxrf_readings_data = analysis.get('pxrf_readings')

                        if pxrf_readings_data: # Check if the list is not empty
                            try:
                                readings_df = pd.DataFrame(pxrf_readings_data)
                                # Use PXRF_ELEMENT_COLUMNS from config
                                element_cols_lower = [col.lower() for col in PXRF_ELEMENT_COLUMNS]
                                display_cols = ['reading_no'] + element_cols_lower

                                # --- FIX: Ensure numeric types ---
                                for col in element_cols_lower:
                                    if col in readings_df.columns:
                                        readings_df[col] = pd.to_numeric(readings_df[col], errors='coerce')
                                    else:
                                        # Add missing element columns defined in config with NaN
                                        readings_df[col] = pd.NA

                                # Define formatters for numeric columns only
                                formatters = {
                                    col: "{:.2f}".format
                                    for col in element_cols_lower
                                    if col in readings_df.columns and pd.api.types.is_numeric_dtype(readings_df[col])
                                }
                                valid_display_cols = [col for col in display_cols if col in readings_df.columns]

                                # Display individual readings table
                                st.markdown("##### Individual Readings")
                                st.dataframe(
                                    # Apply formatting and handle NaN display
                                    readings_df[valid_display_cols].style.format(formatters, na_rep='N/A'),
                                    use_container_width=True,
                                    hide_index=True
                                )

                                # Calculate and display averages (mean skips NaN)
                                numeric_element_cols = [col for col in element_cols_lower if col in readings_df.columns and pd.api.types.is_numeric_dtype(readings_df[col])]
                                if numeric_element_cols:
                                    averages = readings_df[numeric_element_cols].mean().to_dict()
                                    st.markdown("##### Average Values")
                                    avg_df = pd.DataFrame([averages])
                                    st.dataframe(
                                        avg_df[numeric_element_cols].style.format("{:.2f}"),
                                        use_container_width=True,
                                        hide_index=True
                                    )
                                else:
                                    st.info("No numeric element data available to calculate averages.")

                            except Exception as e:
                                st.error(f"Error displaying pXRF data: {e}")
                                # Optionally show raw pxrf_readings data as fallback
                                # st.write("Raw pXRF Data (Fallback):")
                                # st.json(pxrf_readings_data)

                        else:
                            # This means either no readings were associated OR DB query failed/returned empty
                            if analysis.get('pxrf_reading_no'):
                                 st.info(f"No pXRF data found in the database for Reading No(s): {analysis['pxrf_reading_no']}")
                            else:
                                 st.warning("pXRF analysis selected, but no Reading Number(s) were associated with this analysis record.")
                                 # Optionally display raw metadata if it exists as a fallback
                                 if analysis.get('analysis_metadata'):
                                      st.write("Raw Metadata (Fallback):")
                                      try:
                                          metadata = json.loads(analysis['analysis_metadata']) if isinstance(analysis['analysis_metadata'], str) else analysis['analysis_metadata']
                                          st.json(metadata)
                                      except:
                                          st.text(analysis['analysis_metadata'])

                        # Always show description if available for pXRF
                        if analysis['description']:
                            st.write("Description:")
                            st.write(analysis['description'])

                    else: # For other analysis types
                        st.write(f"Laboratory: {analysis.get('laboratory', 'N/A')}")
                        st.write(f"Analyst: {analysis.get('analyst', 'N/A')}")
                        if analysis['description']:
                            st.write("Description:")
                            st.write(analysis['description'])
                        if analysis['analysis_metadata']:
                             st.write("Additional Data:")
                             try:
                                 # Attempt to parse and display JSON metadata
                                 metadata_dict = json.loads(analysis['analysis_metadata'])
                                 st.json(metadata_dict)
                             except (json.JSONDecodeError, TypeError):
                                 # Fallback for non-JSON or unparsable metadata
                                 st.write(str(analysis['analysis_metadata']))

                    # --- Common Section: Display Files (for all types) ---
                    if analysis['analysis_files']:
                        st.write("Analysis Files:")
                        for file in analysis['analysis_files']:
                            file_col1, file_col2 = st.columns([3, 1]) # Adjust columns if needed
                            with file_col1:
                                st.write(f"- {file['file_name']}")
                            with file_col2:
                                # Use centralized storage utils to check existence/get download URL?
                                # For now, assume local path check is sufficient
                                if file['file_path'] and os.path.exists(file['file_path']):
                                    try:
                                        with open(file['file_path'], 'rb') as fp:
                                            st.download_button(
                                                f"Download", # Simpler label
                                                fp.read(),
                                                file_name=file['file_name'],
                                                mime=file.get('file_type', 'application/octet-stream'), # Default MIME type
                                                key=f"download_analysis_{file['id']}" # Unique key
                                            )
                                    except Exception as e:
                                        st.warning(f"Could not read analysis file {file['file_name']}: {e}")
                                else:
                                    st.warning(f"File not found: {file['file_name']}")
                    else:
                        # Only show this if not pXRF or if pXRF has no files either
                        # Note: get_external_analyses needs to provide 'pxrf_readings' if this check is needed
                        # if analysis['analysis_type'] != 'pXRF' or not analysis.get('pxrf_readings'):
                        if analysis['analysis_type'] != 'pXRF': # Simpler check for now
                             st.info("No analysis files available for this analysis.")

                    # --- REMOVED Delete button ---
                    # Delete button was here, now removed for this view
                    # Consider adding edit functionality for external analyses?
        else:
            st.info("No external analyses recorded for this sample.")
    else:
        st.info("No sample information recorded.")

    # Notes Section
    st.markdown("### Lab Notes")

    # Initialize session state for notes
    if 'note_form_state' not in st.session_state:
        st.session_state.note_form_state = {
            'adding_note': False,
            'editing_note_id': None,
            'note_to_delete': None # Consider removing if delete not implemented
        }

    # Add Note Button
    if st.button("Add Note", key=f"add_note_{experiment['id']}"):
        st.session_state.note_form_state['adding_note'] = True
        st.session_state.note_form_state['editing_note_id'] = None # Ensure not editing
        st.rerun()

    # Note Form
    if st.session_state.note_form_state['adding_note']:
        with st.form("note_form", clear_on_submit=True):
            st.markdown("#### Add New Note")
            note_text = st.text_area(
                "Note Text",
                height=150,
                key=f"new_note_text_{experiment['id']}",
                help="Enter your lab note here."
            )
            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("Save Note"):
                    if note_text:
                        # Assumes save_note takes experiment DB ID
                        save_note(experiment['id'], note_text)
                        st.session_state.note_form_state['adding_note'] = False
                        st.session_state.experiment_updated = True
                        st.rerun()
                    else:
                        st.warning("Note text cannot be empty.")
            with col2:
                if st.form_submit_button("Cancel"):
                    st.session_state.note_form_state['adding_note'] = False
                    st.rerun()

    # Display existing notes
    if 'notes' in experiment and experiment['notes']:
        # Sort notes by creation date, newest first (guard against None created_at)
        sorted_notes = sorted(
            experiment['notes'],
            key=lambda x: x['created_at'] or datetime.datetime.min,
            reverse=True,
        )
        for note in sorted_notes:
            note_date_label = (
                note['created_at'].strftime('%Y-%m-%d %H:%M')
                if note.get('created_at') else 'Unknown date'
            )
            with st.expander(f"Note from {note_date_label}"):
                # Check if editing this specific note
                is_editing_this_note = st.session_state.note_form_state.get('editing_note_id') == note['id']

                if is_editing_this_note:
                    # Edit mode for this note
                    with st.form(f"edit_note_{note['id']}"):
                        edited_text = st.text_area(
                            "Edit Note",
                            value=note['note_text'] or '',
                            height=150,
                            key=f"edit_text_{note['id']}",
                            help="Edit your lab note here."
                        )
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.form_submit_button("Save Changes"):
                                submit_note_edit(note['id'], edited_text)
                                st.session_state.experiment_updated = True
                                st.rerun() # Rerun after saving changes
                        with col2:
                            if st.form_submit_button("Cancel Edit"):
                                st.session_state.note_form_state['editing_note_id'] = None
                                st.rerun() # Rerun to exit edit mode
                else:
                    # View mode for this note
                    st.markdown(note['note_text'] or '')
                    if note.get('updated_at') and note.get('created_at') and note['updated_at'] > note['created_at']:
                        st.caption(f"Last updated: {note['updated_at'].strftime('%Y-%m-%d %H:%M')}")

                    # Edit button (only show if not adding a new note)
                    if not st.session_state.note_form_state.get('adding_note', False):
                        # Simplified layout for edit button
                        if st.button("Edit", key=f"edit_{note['id']}"):
                            st.session_state.note_form_state['editing_note_id'] = note['id']
                            st.session_state.note_form_state['adding_note'] = False # Ensure not adding
                            st.rerun() # Rerun to show edit form
                        # Delete button removed for now, can be added later if needed
    else:
        # Only show if not adding or editing a note
        if not st.session_state.note_form_state.get('adding_note', False) and not st.session_state.note_form_state.get('editing_note_id'):
             st.info("No lab notes recorded for this experiment.")