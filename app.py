import streamlit as st
from config import APP_NAME, APP_LAYOUT, APP_ICON
from frontend.components.sidebar import render_sidebar
from frontend.components.header import render_header
from frontend.components.new_experiment import render_new_experiment
from frontend.components.view_experiments import render_view_experiments
from frontend.components.new_rock import render_new_rock_sample
from frontend.components.view_samples import render_sample_inventory
from frontend.components.auth_components import init_auth_state, render_login_page, render_logout_button
from frontend.components.issue_submission import render_issue_submission_form
from frontend.components.bulk_uploads import render_bulk_uploads_page
from frontend.components.chemical_additives import render_compound_management, render_edit_compound_form
from frontend.components.reactor_dashboard import render_reactor_dashboard
from utils.scheduler import setup_backup_scheduler, shutdown_scheduler
from utils.database_backup import update_public_db_copy
from database import SessionLocal
from database.models import Experiment
import os
import logging
import atexit

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize session state for current page if not exists
if 'current_page' not in st.session_state:
    st.session_state.current_page = "New Experiment"

# Initialize authentication state with error handling
try:
    init_auth_state()
    logger.info("Authentication state initialized successfully")
except Exception as e:
    logger.error(f"Error initializing authentication state: {str(e)}")
    st.error("Failed to initialize authentication. Please check your configuration.")
    st.stop()

# Streamlit app configuration
st.set_page_config(
    page_title=APP_NAME,
    page_icon=APP_ICON,
    layout=APP_LAYOUT,
    initial_sidebar_state="expanded"
)

# Create an initial public copy of the database
try:
    public_path = update_public_db_copy()
    if public_path:
        logger.info(f"Created initial public database copy at: {public_path}")
except Exception as e:
    logger.error(f"Error creating initial public database copy: {str(e)}")

# Initialize the backup scheduler
try:
    backup_scheduler = setup_backup_scheduler()
    # Register shutdown handler
    atexit.register(shutdown_scheduler)
    logger.info("Database backup scheduler initialized successfully")
except Exception as e:
    logger.error(f"Error initializing backup scheduler: {str(e)}")

def render_compound_management_page():
    """Render the compound management page"""
    # Check if we're editing a compound
    if st.session_state.get('edit_compound_id'):
        render_edit_compound_form(st.session_state.edit_compound_id)
    else:
        render_compound_management()

def main():
    try:
        # Show login page if user is not authenticated
        if not st.session_state.get('user'):
            render_login_page()
            return

        # Show main app content if user is authenticated
        page = render_sidebar()
        st.session_state.current_page = page
        
        # Add logout button to sidebar
        render_logout_button()
        
        # Render header after setting the current page
        render_header()
        
        if page == "Reactor Dashboard":
            render_reactor_dashboard()
        elif page == "New Experiment":
            render_new_experiment()
        elif page == "View Experiments":
            render_view_experiments()
        elif page == "New Rock Sample":
            render_new_rock_sample()
        elif page == "View Sample Inventory":
            render_sample_inventory()
        elif page == "Compound Management":
            render_compound_management_page()
        elif page == "Bulk Uploads":
            render_bulk_uploads_page()
        elif page == "Issue Submission":
            render_issue_submission_form()
        # elif page == "Settings":
        #     render_settings()

        if st.sidebar.button("Sync Public DB"):
            try:
                with st.spinner("Syncing public database..."):
                    public_path = update_public_db_copy()
                    if public_path:
                        st.sidebar.success(f"DB synced to {public_path}")
            except Exception as e:
                logger.error(f"Error syncing public database: {str(e)}")
                st.sidebar.error("An error occurred while syncing the public database. Please try again later.")
    except Exception as e:
        logger.error(f"Error in main application: {str(e)}", exc_info=True)
        st.error(f"An error occurred while running the application: {str(e)}")

if __name__ == "__main__":
    main()
