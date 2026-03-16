import streamlit as st
from database import SessionLocal, SampleInfo, ModificationsLog
import os
from frontend.components.utils import save_uploaded_file, log_modification, generate_form_fields
from frontend.config.variable_config import ROCK_SAMPLE_CONFIG

def render_new_rock_sample():
    """
    Render the interface for creating a new rock sample.
    
    This function creates a form interface that allows users to:
    - Enter basic sample information (ID, classification, location)
    - Add geographical coordinates
    - Provide a sample description
    - Upload a sample photo
    
    The form includes validation and proper error handling for the submission process.
    """
    st.header("New Rock Sample")
    
    with st.form("new_rock_sample_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            # Generate form fields using the configuration
            excluded_fields = {"characterized"}
            field_names = [k for k in ROCK_SAMPLE_CONFIG.keys() if k not in excluded_fields]
            form_values = generate_form_fields(
                ROCK_SAMPLE_CONFIG,
                {},  # Empty dict for new sample
                field_names,
                'rock_sample'
            )
        with col2:
            # Add pXRF Reading No input (not in config, so hardcoded)
            pxrf_reading_no = st.text_input(
                "pXRF Reading No (optional)",
                help="If this sample has a pXRF reading, enter the reading number(s) here (comma-separated for multiple)."
            )
            # Add Magnetic Susceptibility input (hardcoded, not in config)
            mag_susc = st.text_input(
                "Magnetic Susceptibility (optional)",
                value="",
                help="Enter the magnetic susceptibility value or range (e.g., 0.5-1). Units: 1x10^-3. Leave blank if not measured."
            )
            # Add Sample Photo uploader and description
            photo_file = st.file_uploader(
                "Sample Photo (optional)",
                type=["jpg", "jpeg", "png"],
                help="Upload a photo of the rock sample (optional)."
            )
            photo_desc = st.text_area("Photo Description (Optional)")
        if st.form_submit_button("Save Rock Sample"):
            # Pass all form values, pxrf_reading_no, and mag_susc to save_rock_sample
            save_rock_sample(form_values, pxrf_reading_no, mag_susc, photo_file, photo_desc)

def save_rock_sample(form_values, pxrf_reading_no=None, mag_susc=None, photo_file=None, photo_desc=None):
    """
    Save a new rock sample to the database (optionally with initial photo).
    Optionally, create an ExternalAnalysis entry if pxrf_reading_no is provided.
    Optionally, add a sample photo if provided.
    Args:
        form_values (dict): Dictionary containing all form field values from ROCK_SAMPLE_CONFIG
        pxrf_reading_no (str): Optional pXRF reading number(s)
        mag_susc (str): Optional magnetic susceptibility value or range
        photo_file (UploadedFile): Optional photo file
        photo_desc (str): Optional photo description
    """
    # Validate required fields using ROCK_SAMPLE_CONFIG (exclude computed fields like 'characterized')
    excluded_fields = {"characterized"}
    required_fields = [
        field for field, config in ROCK_SAMPLE_CONFIG.items()
        if config.get('required', False) and field not in excluded_fields
    ]
    missing_fields = []
    for field in required_fields:
        value = form_values.get(field)
        config = ROCK_SAMPLE_CONFIG[field]
        is_missing = False
        if config['type'] == 'number':
            # For required numbers, only None is missing (assuming 0 is valid)
            if value is None:
                is_missing = True
        else:
            # For other required types (text, select, etc.), None or empty string is missing
            if value is None or value == '':
                is_missing = True
        if is_missing:
            missing_fields.append(config['label']) # Use label for error message
    if missing_fields:
        st.error(f"Please fill in all required fields: {', '.join(missing_fields)}")
        with st.expander("What does this mean?", expanded=False):
            st.markdown("- Ensure required text fields are not blank\n- Ensure required numbers are provided (0 is allowed where applicable)")
        return
    try:
        db = SessionLocal()
        # Check if sample ID already exists
        existing_sample = db.query(SampleInfo).filter(SampleInfo.sample_id == form_values['sample_id']).first()
        if existing_sample:
            st.error(f"Sample ID '{form_values['sample_id']}' already exists.")
            with st.expander("How to proceed", expanded=False):
                st.markdown("- Choose a different `sample_id` for a new record\n- Or open the existing sample in 'View Sample Inventory' to edit")
            db.close()
            return
        # Create sample using allowed fields only (exclude computed fields)
        allowed_fields = [k for k in ROCK_SAMPLE_CONFIG.keys() if k not in excluded_fields]
        sample = SampleInfo(**{field: form_values.get(field) for field in allowed_fields})
        # Ensure boolean field has a proper bool type (avoid string 'False')
        try:
            if hasattr(sample, 'characterized'):
                # Force to False on creation; it will be updated by listeners later if analyses exist
                sample.characterized = False
        except Exception:
            pass
        db.add(sample)
        # Log modification using allowed fields, plus mag_susc if provided
        log_modification(
            db=db,
            modified_table="sample_info",
            modification_type="create",
            new_values={
                **{field: getattr(sample, field) for field in allowed_fields},
                **({"magnetic_susceptibility": mag_susc} if mag_susc else {})
            }
        )
        # If pXRF Reading No is provided, create an ExternalAnalysis entry
        if pxrf_reading_no and pxrf_reading_no.strip():
            from database import ExternalAnalysis, PXRFReading
            reading_no_clean = pxrf_reading_no.strip()
            ext_analysis = ExternalAnalysis(
                sample_id=sample.sample_id,
                analysis_type='pXRF',
                pxrf_reading_no=reading_no_clean,
            )
            db.add(ext_analysis)
            # Warn if the referenced pXRF reading is not yet in the database
            try:
                exists_reading = db.query(PXRFReading).filter(PXRFReading.reading_no == reading_no_clean).first()
                if not exists_reading:
                    st.warning(f"pXRF reading '{reading_no_clean}' not found in database yet. You can upload it later via Bulk Uploads → pXRF Readings.")
            except Exception:
                # Non-fatal warning, continue
                pass
            log_modification(
                db=db,
                modified_table="external_analyses",
                modification_type="create",
                new_values={
                    'sample_id': sample.sample_id,
                    'analysis_type': 'pXRF',
                    'pxrf_reading_no': pxrf_reading_no.strip()
                }
            )
        # If Magnetic Susceptibility is provided, create an ExternalAnalysis entry
        if mag_susc and mag_susc.strip():
            from database import ExternalAnalysis
            mag_susc_analysis = ExternalAnalysis(
                sample_id=sample.sample_id,
                analysis_type='Magnetic Susceptibility',
                description=f"Magnetic susceptibility: {mag_susc} (1x10^-3)"
            )
            db.add(mag_susc_analysis)
            log_modification(
                db=db,
                modified_table="external_analyses",
                modification_type="create",
                new_values={
                    'sample_id': sample.sample_id,
                    'analysis_type': 'Magnetic Susceptibility',
                    'description': f"Magnetic susceptibility: {mag_susc} (1x10^-3)"
                }
            )
        db.commit()
        st.success(f"Rock sample {form_values['sample_id']} saved successfully!" + (f" (Magnetic susceptibility: {mag_susc} 1x10^-3)" if mag_susc else ""))
        # --- Add sample photo if provided ---
        if photo_file is not None:
            from frontend.components.edit_sample import add_sample_photo
            photo_success = add_sample_photo(sample.sample_id, photo_file, photo_desc)
            if photo_success:
                st.success("Sample photo uploaded successfully!")
            else:
                st.warning("Sample saved, but photo upload failed.")
    except Exception as e:
        db.rollback()
        err_text = str(e)
        st.error("Error saving rock sample.")
        if "UNIQUE constraint failed" in err_text and "sample_info.sample_id" in err_text:
            st.error("Duplicate sample_id. Please use a unique identifier.")
        elif "FOREIGN KEY constraint failed" in err_text:
            st.error("Foreign key error. Please ensure related records exist (e.g., valid references).")
        elif "database is locked" in err_text.lower():
            st.error("Database is locked. Please wait a moment and try again.")
        else:
            st.error(err_text)
        with st.expander("Troubleshooting", expanded=False):
            st.markdown("- Verify required fields\n- Check for duplicate `sample_id`\n- Ensure DB is reachable and not locked\n- Retry after refreshing the page")
    finally:
        if 'db' in locals() and db.is_active:
            db.close()