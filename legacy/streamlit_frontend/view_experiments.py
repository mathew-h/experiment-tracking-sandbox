import streamlit as st
import pandas as pd
import os
import json
from datetime import datetime, date, time
import re  # Add re module for regex support
from database import SessionLocal, Experiment, ExperimentStatus, ExperimentalResults, ExperimentNotes, ExperimentalConditions, ModificationsLog, SampleInfo, ExternalAnalysis, ChemicalAdditive, Compound

from frontend.components.experiment_details import display_experiment_details
from frontend.components.edit_experiment import edit_experiment, handle_delete_experiment
from frontend.components.utils import (
    generate_form_fields,
    extract_conditions,
    split_conditions_for_display,
    log_modification
)

from frontend.config.variable_config import (
    FIELD_CONFIG,
    EXPERIMENT_TYPES,
    EXPERIMENT_STATUSES,
    SCALAR_RESULTS_CONFIG,
)

from sqlalchemy.orm import selectinload
from sqlalchemy import or_, func
import pytz

def render_view_experiments():
    """
    Main function to render the experiments view page.
    
    This function handles:
    1. Setting up the page layout and styling
    2. Managing experiment list view and detail view
    3. Handling experiment filtering and search
    4. Managing experiment editing state
    """
    # Add custom CSS for better layout
    st.markdown("""
        <style>
            div[data-testid="column"] {
                padding: 0px;
                margin: 0px;
            }
            div[data-testid="stHorizontalBlock"] {
                padding: 0px;
                margin: 0px;
            }
            div[data-testid="stMarkdownContainer"] > hr {
                margin: 5px 0px;
            }
        </style>
    """, unsafe_allow_html=True)

    # Handle experiment update state
    if st.session_state.get('experiment_updated', False):
        st.session_state.experiment_updated = False
        st.rerun()

    st.markdown("### View Experiments")
    
    # Initialize session state for experiment viewing
    if 'view_experiment_id' not in st.session_state:
        st.session_state.view_experiment_id = None
    
    if 'edit_mode' not in st.session_state:
        st.session_state.edit_mode = False
    
    if 'confirm_delete_experiment_id' not in st.session_state: # Initialize confirmation state
        st.session_state.confirm_delete_experiment_id = None
    

    # Main view logic
    if st.session_state.view_experiment_id is None:
        # Show experiment list view
        render_experiment_list()
    else:
        # Show experiment detail view
        render_experiment_detail()

def render_experiment_list():
    """
    Renders the list view of all experiments with filtering options.
    
    This function:
    1. Fetches all experiments from the database with pagination
    2. Provides filtering options (search, status, date range)
    3. Displays experiments in a formatted table
    4. Handles navigation to experiment details
    """
    # Initialize pagination state
    if 'experiments_page' not in st.session_state:
        st.session_state.experiments_page = 1
    st.session_state.experiments_per_page = 25

    # Create filter/search options
    st.markdown("#### Search and Filter Experiments")
    
    # Create columns for filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Search filter
        search_term = st.text_input(
            "Search: Sample ID, Experiment ID or Researcher", 
            "",
            key="search_term",
            on_change=lambda: setattr(st.session_state, 'experiments_page', 1)
        )
        use_regex = st.checkbox("Use regex pattern matching", value=True)
    with col2:
        # Status filter
        status_filter = st.selectbox(
            "Filter by Status:",
            ["All"] + [status.name for status in ExperimentStatus],
            key="status_filter",
            on_change=lambda: setattr(st.session_state, 'experiments_page', 1)
        )
    
    with col3:
        # Date range filter
        date_col1, date_col2 = st.columns(2)
        with date_col1:
            start_date = st.date_input(
                "Start Date Range", 
                value=None,
                key="start_date",
                on_change=lambda: setattr(st.session_state, 'experiments_page', 1)
            )
        with date_col2:
            end_date = st.date_input(
                "End Date Range", 
                value=None,
                key="end_date",
                on_change=lambda: setattr(st.session_state, 'experiments_page', 1)
            )
    
    # Get experiments with search and filters applied at database level
    experiments, total_count = get_all_experiments(
        page=st.session_state.experiments_page,
        per_page=st.session_state.experiments_per_page,
        search_term=search_term if use_regex or not search_term else re.escape(search_term),
        status_filter=status_filter if status_filter != "All" else None,
        start_date=start_date,
        end_date=end_date
    )
    
    # Calculate total pages based on filtered count
    total_pages = (total_count + st.session_state.experiments_per_page - 1) // st.session_state.experiments_per_page
    
    if not experiments:
        st.info("No experiments found matching the selected criteria.")
        # Reset pagination if no results found
        if st.session_state.experiments_page > 1:
            st.session_state.experiments_page = 1
            st.rerun()
    else:
        # Display experiments in a table
        st.markdown("#### Experiments")
        
        # Create a custom table layout with headers
        col1, col2, col3, col4, col5, col6, col7, col8, col9 = st.columns([1, 1.2, 1.2, 1.4, 0.8, 0.9, 2.0, 1.1, 0.7])
        
        with col1:
            st.markdown("**Experiment ID**")
        with col2:
            st.markdown("**Rock / Substrate**")
        with col3:
            st.markdown("**Water (mL) / Rock Mass (g)**")
        with col4:
            st.markdown("**Compounds**")
        with col5:
            st.markdown(f"**{FIELD_CONFIG['initial_ph']['label']}**")
        with col6:
            st.markdown(f"**{FIELD_CONFIG['temperature_c']['label']}**")
        with col7:
            st.markdown("**Description**")
        with col8:
            st.markdown("**Status**")
        with col9:
            st.markdown("**Action**")
        
        # Add a separator line
        st.markdown("<hr style='margin: 1px 0px; background-color: #f0f0f0; height: 0.1px; border: none;'>", unsafe_allow_html=True)
        
        # Data rows
        for index, exp in enumerate(experiments):
            # Fetch full experiment details for conditions and notes
            exp_detail = get_experiment_by_id(exp['experiment_id'])
            conditions = exp_detail.get('conditions', {}) if exp_detail else {}
            notes = exp_detail.get('notes', []) if exp_detail else []

            # Water mL and Rock Mass g
            water_ml = conditions.get('water_volume_mL', 0.0)
            rock_mass_g = conditions.get('rock_mass_g', 0.0)
            
            water_ml_disp = f"{water_ml:.1f}" if isinstance(water_ml, (int, float)) else str(water_ml)
            rock_mass_g_disp = f"{rock_mass_g:.3f}" if isinstance(rock_mass_g, (int, float)) else str(rock_mass_g)
            water_rock_disp = f"{water_ml_disp} / {rock_mass_g_disp}"

            # Initial pH
            initial_ph = conditions.get('initial_ph', FIELD_CONFIG['initial_ph']['default'])
            initial_ph_disp = f"{initial_ph:.1f}" if isinstance(initial_ph, (int, float)) else str(initial_ph)
            # Compounds summary from ChemicalAdditives
            compounds_text = "None"
            try:
                db = SessionLocal()
                cond = db.query(ExperimentalConditions).filter(ExperimentalConditions.experiment_id == exp['experiment_id']).first()
                if cond:
                    names = [n[0] for n in db.query(Compound.name)
                                 .join(ChemicalAdditive, ChemicalAdditive.compound_id == Compound.id)
                                 .filter(ChemicalAdditive.experiment_id == cond.id)
                                 .order_by(Compound.name.asc())
                                 .all()]
                    if names:
                        if len(names) <= 2:
                            compounds_text = ", ".join(names)
                        else:
                            compounds_text = f"{', '.join(names[:2])} (+{len(names)-2})"
            except Exception:
                compounds_text = "None"
            finally:
                if 'db' in locals() and db:
                    db.close()
            # Temperature
            temperature = conditions.get('temperature_c', FIELD_CONFIG['temperature_c']['default'])
            temperature_disp = f"{temperature:.1f}" if isinstance(temperature, (int, float)) else str(temperature)
            # Description from first note (guard against None note_text)
            description = (notes[0]['note_text'] or '') if notes else ""
            # Status
            status = exp.get('status', '')
            # Row layout
            with st.container():
                col1, col2, col3, col4, col5, col6, col7, col8, col9 = st.columns([1, 1.2, 1.2, 1.4, 0.8, 0.9, 2.0, 1.1, 0.7])
                with col1:
                    st.write(f"<div style='margin: 0px; padding: 2px;'>{exp['experiment_id']}</div>", unsafe_allow_html=True)
                with col2:
                    st.write(f"<div style='margin: 0px; padding: 2px;'>{exp['sample_id']}</div>", unsafe_allow_html=True)
                with col3:
                    st.write(f"<div style='margin: 0px; padding: 2px;'>{water_rock_disp}</div>", unsafe_allow_html=True)
                with col4:
                    st.write(f"<div style='margin: 0px; padding: 2px;'>{compounds_text}</div>", unsafe_allow_html=True)
                with col5:
                    st.write(f"<div style='margin: 0px; padding: 2px;'>{initial_ph_disp}</div>", unsafe_allow_html=True)
                with col6:
                    st.write(f"<div style='margin: 0px; padding: 2px;'>{temperature_disp}</div>", unsafe_allow_html=True)
                with col7:
                    st.write(f"<div style='margin: 0px; padding: 2px; white-space: pre-line; overflow-x: auto; max-width: 100%;'>{description}</div>", unsafe_allow_html=True)
                with col8:
                    new_status = st.selectbox(
                        "Status",
                        options=EXPERIMENT_STATUSES,
                        index=EXPERIMENT_STATUSES.index(status) if status in EXPERIMENT_STATUSES else 0,
                        key=f"status_{exp['experiment_id']}",
                        label_visibility="collapsed"
                    )
                    if new_status != status:
                        try:
                            db = SessionLocal()
                            experiment = db.query(Experiment).filter(Experiment.experiment_id == exp['experiment_id']).first()
                            if experiment:
                                old_status = experiment.status.name
                                experiment.status = getattr(ExperimentStatus, new_status)
                                # Log the modification
                                log_modification(
                                    db=db,
                                    experiment_id=exp['experiment_id'],
                                    modified_table="experiments",
                                    modification_type="update",
                                    old_values={'status': old_status},
                                    new_values={'status': new_status}
                                )
                                db.commit()
                                st.rerun()
                        except Exception as e:
                            st.error(f"Error updating status: {str(e)}")
                        finally:
                            if db:
                                db.close()
                with col9:
                    if st.button("Details", key=f"view_{index}"):
                        st.session_state.view_experiment_id = exp['experiment_id']
                        st.rerun()
                st.markdown("<hr style='margin: 2px 0px; background-color: #f0f0f0; height: 1px; border: none;'>", unsafe_allow_html=True)
        # Pagination controls
        st.markdown("---")
        pagination_cols = st.columns([1, 2, 1])
        with pagination_cols[0]:
            if st.session_state.experiments_page > 1:
                if st.button("← Previous"):
                    st.session_state.experiments_page -= 1
                    st.rerun()
        with pagination_cols[1]:
            st.markdown(f"<div style='text-align: center'>Page {st.session_state.experiments_page} of {total_pages}</div>", unsafe_allow_html=True)
        with pagination_cols[2]:
            if st.session_state.experiments_page < total_pages:
                if st.button("Next →"):
                    st.session_state.experiments_page += 1
                    st.rerun()

def render_experiment_detail():
    """
    Renders the detail view for a specific experiment.
    
    This function:
    1. Fetches the experiment details
    2. Handles navigation back to list view
    3. Manages edit mode state
    4. Displays experiment details or edit form
    """
    # Initial fetch to check if experiment exists and handle navigation/edit buttons first
    initial_experiment_check = get_experiment_by_id(st.session_state.view_experiment_id)

    if initial_experiment_check is None:
        st.error(f"Experiment with ID {st.session_state.view_experiment_id} not found.")
        if st.button("Back to Experiment List"):
            st.session_state.view_experiment_id = None
            st.session_state.edit_mode = False
            st.session_state.confirm_delete_experiment_id = None # Reset confirmation on back
            st.rerun() # Rerun to go back to the list
    else:
        # Back to List button - Place it consistently at the top left
        if st.button("← Back to List"):
            st.session_state.view_experiment_id = None
            st.session_state.edit_mode = False
            st.session_state.confirm_delete_experiment_id = None # Reset confirmation on back
            st.rerun() # Rerun to go back to the list
        
        # --- Refetch the experiment data HERE ---
        # This ensures we have the latest data before displaying/editing,
        # especially after a rerun triggered by saving sub-components like notes or data.
        experiment = get_experiment_by_id(st.session_state.view_experiment_id)

        # Check again in case something went wrong between the initial check and now
        if experiment is None:
             st.error(f"Could not reload experiment with ID {st.session_state.view_experiment_id}.")
             # Optionally add a back button here too
             return # Stop rendering if reload failed

        # Display experiment info header
        st.subheader(f"Experiment: {experiment['experiment_id']}")

        # Now display either the details or the edit form with the freshly fetched data
        if not st.session_state.edit_mode:
            # View mode - display experiment details
            display_experiment_details(experiment)
            
            # Place Edit button *after* details in view mode
            if st.button("Edit Experiment"):
                st.session_state.edit_mode = True
                st.session_state.confirm_delete_experiment_id = None # Reset delete confirmation if going to edit
                st.rerun() # Rerun to switch to edit mode

            # Delete Experiment Button and Confirmation Logic
            st.markdown("--- Configuraton ---") # Adding a separator for clarity
            if st.session_state.confirm_delete_experiment_id == experiment['id']:
                st.warning(f"**Are you sure you want to delete experiment {experiment['experiment_id']}?** This action cannot be undone.")
                col_confirm, col_cancel, _ = st.columns([1,1,3])
                with col_confirm:
                    if st.button("Confirm Delete", key="confirm_delete_btn", type="primary"):
                        if handle_delete_experiment(experiment['id']):
                            st.success(f"Experiment {experiment['experiment_id']} deleted successfully.")
                            st.session_state.view_experiment_id = None
                            st.session_state.edit_mode = False
                            st.session_state.confirm_delete_experiment_id = None
                            st.session_state.experiment_updated = True # To refresh list view if it depends on it
                            st.rerun()
                        else:
                            # Error is handled by handle_delete_experiment
                            st.session_state.confirm_delete_experiment_id = None # Reset to hide confirmation
                            st.rerun()
                with col_cancel:
                    if st.button("Cancel Delete", key="cancel_delete_btn"):
                        st.session_state.confirm_delete_experiment_id = None
                        st.rerun()
            else:
                if st.button("Delete Experiment", key="delete_experiment_btn"):
                    st.session_state.confirm_delete_experiment_id = experiment['id']
                    st.rerun()
        else:
            # Edit mode - show editable form
            edit_experiment(experiment)
            
            # Place Cancel button *after* edit form in edit mode
            if st.button("Cancel Edit"):
                st.session_state.edit_mode = False
                st.rerun() # Rerun to switch back to view mode

def get_total_experiments_count(db=None):
    """
    Get total count of experiments for pagination.
    """
    try:
        if db is None:
            db = SessionLocal()
        return db.query(Experiment).count()
    except Exception as e:
        st.error(f"Error getting experiment count: {str(e)}")
        return 0
    finally:
        if db:
            db.close()

def get_all_experiments(page=1, per_page=10, search_term=None, status_filter=None, start_date=None, end_date=None):
    """
    Retrieves experiments from the database with pagination and filtering.
    
    Args:
        page (int): Current page number (1-based)
        per_page (int): Number of items per page
        search_term (str): Optional search term for filtering
        status_filter (str): Optional status filter
        start_date (date): Optional start date for date range filter
        end_date (date): Optional end date for date range filter
        
    Returns:
        list: List of dictionaries containing basic experiment information
    """
    try:
        db = SessionLocal()
        query = db.query(Experiment)

        # Apply search filter at database level if provided
        if search_term:
            try:
                pattern = re.compile(search_term, re.IGNORECASE)
                # For regex pattern, we need to use custom SQL for regex matching
                # SQLite doesn't support regex directly, so we'll use LIKE with wildcards
                search_pattern = f"%{search_term}%"
                query = query.filter(
                    or_(
                        Experiment.sample_id.like(search_pattern),
                        Experiment.researcher.like(search_pattern),
                        Experiment.experiment_id.like(search_pattern)
                    )
                )
            except re.error:
                # If invalid regex, fall back to simple LIKE search
                search_term_lower = f"%{search_term.lower()}%"
                query = query.filter(
                    or_(
                        func.lower(Experiment.sample_id).like(search_term_lower),
                        func.lower(Experiment.researcher).like(search_term_lower),
                        func.lower(Experiment.experiment_id).like(search_term_lower)
                    )
                )

        # Apply status filter if provided
        if status_filter:
            query = query.filter(Experiment.status == status_filter)

        # Apply date range filter if provided
        if start_date:
            query = query.filter(Experiment.date >= datetime.combine(start_date, time.min))
        if end_date:
            query = query.filter(Experiment.date <= datetime.combine(end_date, time.max))

        # Get total count for pagination after applying filters
        total_count = query.count()
        
        # Apply ordering and pagination
        offset = (page - 1) * per_page
        experiments_query = query.order_by(Experiment.date.desc()).offset(offset).limit(per_page).all()
        
        # Convert to list of dictionaries for easy display
        experiments = []
        for exp in experiments_query:
            experiments.append({
                'id': exp.id,
                'experiment_id': exp.experiment_id,
                'sample_id': exp.sample_id,
                'date': exp.date,
                'researcher': exp.researcher,
                'status': exp.status.name
            })
        
        return experiments, total_count
    except Exception as e:
        st.error(f"Error retrieving experiments: {str(e)}")
        return [], 0
    finally:
        db.close()

def get_experiment_by_id(experiment_id):
    """
    Retrieves a specific experiment by ID with all related data.
    
    This function fetches an experiment and all its related data (conditions, notes,
    modifications, results) and formats them for display.
    
    Args:
        experiment_id: Either a string (experiment_id) or integer (database id)
        
    Returns:
        dict: Dictionary containing all experiment data and related information
    """
    try:
        db = SessionLocal()
        # Check if input is a string (experiment_id) or integer (database id)
        if isinstance(experiment_id, str):
            experiment = db.query(Experiment).options(
                selectinload(Experiment.conditions),
                selectinload(Experiment.notes),
                selectinload(Experiment.modifications),
                selectinload(Experiment.results).selectinload(ExperimentalResults.scalar_data), # Eager load scalar data
                selectinload(Experiment.results).selectinload(ExperimentalResults.icp_data),   # Eager load ICP data
                selectinload(Experiment.results).selectinload(ExperimentalResults.files)       # Eager load files
            ).filter(Experiment.experiment_id == experiment_id).first()
        else:
            experiment = db.query(Experiment).options(
                selectinload(Experiment.conditions),
                selectinload(Experiment.notes),
                selectinload(Experiment.modifications),
                selectinload(Experiment.results).selectinload(ExperimentalResults.scalar_data), # Eager load scalar data
                selectinload(Experiment.results).selectinload(ExperimentalResults.icp_data),   # Eager load ICP data
                selectinload(Experiment.results).selectinload(ExperimentalResults.files)       # Eager load files
            ).filter(Experiment.id == experiment_id).first()
        
        if experiment is None:
            return None
        
        # Access related data (already loaded due to selectinload)
        conditions = experiment.conditions
        notes = experiment.notes
        modifications = experiment.modifications
        results = experiment.results
        
        # Convert to dictionary for display
        exp_dict = {
            'id': experiment.id,
            'experiment_number': experiment.experiment_number,
            'experiment_id': experiment.experiment_id,
            'sample_id': experiment.sample_id,
            'date': experiment.date,
            'researcher': experiment.researcher,
            'status': experiment.status.name,
            'created_at': experiment.created_at,
            'updated_at': experiment.updated_at,
            'conditions': {},
            'notes': [],
            'modifications': [],
            'experimental_results': []
        }
        
        # Add conditions if they exist with default values for missing fields
        if conditions:
            exp_dict['conditions'] = extract_conditions(conditions)
        
        # Add notes if they exist
        if notes:
            exp_dict['notes'] = [
                {
                    'id': note.id,
                    'note_text': note.note_text,
                    'created_at': note.created_at,
                    'updated_at': note.updated_at
                }
                for note in notes
            ]
        
        # Add modifications if they exist
        if modifications:
            exp_dict['modifications'] = [
                {
                    'id': mod.id,
                    'modified_by': mod.modified_by,
                    'modification_type': mod.modification_type,
                    'modified_table': mod.modified_table,
                    'old_values': mod.old_values,
                    'new_values': mod.new_values,
                    'created_at': mod.created_at
                }
                for mod in modifications
            ]
        
        # Add experimental data if they exist
        if results:
            exp_dict['experimental_results'] = [] # Initialize list
            for data in results: # data is an ExperimentalResults object
                result_item = {
                    'id': data.id,
                    'time_post_reaction': data.time_post_reaction_days,  
                    'description': data.description,
                    'created_at': data.created_at,
                    'updated_at': data.updated_at,
                    'scalar_data': None, # Placeholder for scalar data
                    # Add placeholders for other data types (GC, PXRF, etc.) as needed
                    'files': []          # List to hold associated files
                }

                # Extract scalar data if present (independent of primary result type)
                if data.scalar_data:
                    scalar_dict = {}
                    for field_name in SCALAR_RESULTS_CONFIG.keys():
                        if hasattr(data.scalar_data, field_name):
                            scalar_dict[field_name] = getattr(data.scalar_data, field_name)
                    result_item['scalar_data'] = scalar_dict

                # Extract files if they exist
                if data.files:
                    for file_obj in data.files:
                        result_item['files'].append({
                            'id': file_obj.id,
                            'file_path': file_obj.file_path,
                            'file_name': file_obj.file_name,
                            'file_type': file_obj.file_type,
                            'created_at': file_obj.created_at
                        })

                exp_dict['experimental_results'].append(result_item)
        else:
            pass # No results to process
            
        return exp_dict
    except Exception as e:
        st.error(f"Error retrieving experiment: {str(e)}")
        return None
    finally:
        db.close()

def filter_experiments(query, filters):
    """
    Apply filters to the experiment query.
    """
    if filters.get('start_date'):
        # Convert EST date to UTC for database query
        est = pytz.timezone('US/Eastern')
        start_date = filters['start_date']
        start_datetime = datetime.combine(start_date, time.min)
        start_datetime = est.localize(start_datetime).astimezone(pytz.UTC)
        query = query.filter(Experiment.date >= start_datetime)
    
    if filters.get('end_date'):
        # Convert EST date to UTC for database query
        est = pytz.timezone('US/Eastern')
        end_date = filters['end_date']
        end_datetime = datetime.combine(end_date, time.max)
        end_datetime = est.localize(end_datetime).astimezone(pytz.UTC)
        query = query.filter(Experiment.date <= end_datetime)
    
    if filters.get('status'):
        query = query.filter(Experiment.status == filters['status'])
    
    if filters.get('researcher'):
        query = query.filter(Experiment.researcher.ilike(f"%{filters['researcher']}%"))
    
    if filters.get('sample_id'):
        query = query.filter(Experiment.sample_id.ilike(f"%{filters['sample_id']}%"))
    
    return query

