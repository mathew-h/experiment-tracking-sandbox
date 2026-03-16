from frontend.config.variable_config import (
    FIELD_CONFIG,
)
import os
import streamlit as st
from database import ModificationsLog, SampleInfo
import json # Added for JSON serialization in logging
import datetime # Added for timestamp in logging and date input
from database import SessionLocal
import pandas as pd
from pathlib import Path
import logging
# Import the centralized storage functions
from utils.storage import save_file, get_file, delete_file
from sqlalchemy.orm import Session, joinedload
from database import ExperimentalResults, ScalarResults, ExperimentalConditions, Experiment
import pytz
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)

def get_condition_display_dict(conditions):
    """
    Build a display dictionary for experimental conditions.
    
    It leverages FIELD_CONFIG to determine:
      - Which fields to display,
      - The expected type of the field (numeric if the default is a float, string otherwise),
      - And a friendly label with units.
    """
    display_dict = {}
    
    for field_name, config in FIELD_CONFIG.items():
        # Get the friendly label from the config
        label = config['label']
        value = conditions.get(field_name)
        
        # If value is None or an empty string, display as "N/A"
        if value is None or (isinstance(value, str) and not value.strip()):
            display_value = "N/A"
        else:
            # If the field type is number and has a format, use it
            if config['type'] == 'number' and config.get('format') and isinstance(value, (int, float)):
                try:
                    display_value = config['format'] % float(value)
                except (ValueError, TypeError):
                    display_value = str(value)
            else:
                display_value = str(value)
        
        display_dict[label] = display_value
    return display_dict

def split_conditions_for_display(conditions):
    """
    Splits conditions into required and optional fields for display purposes.
    
    It uses get_condition_display_dict to build the full display dict, and then
    separates the required fields (based on FIELD_CONFIG) from the rest.
    """
    display_dict = get_condition_display_dict(conditions)
    
    # Build a set of display labels for required fields using FIELD_CONFIG
    required_labels = {config['label'] for field_name, config in FIELD_CONFIG.items() if config.get('required', False)}
    
    required_fields = {label: value for label, value in display_dict.items() if label in required_labels}
    optional_fields = {label: value for label, value in display_dict.items() if label not in required_labels}
    
    return required_fields, optional_fields

def build_conditions(data, experiment_id):
    """
    Builds a complete conditions dictionary for an experiment.
    
    This function creates a conditions dictionary using FIELD_CONFIG defaults
    and provided data, then adds the experiment_id.
    
    Args:
        data (dict): Dictionary containing actual values to use
        experiment_id (int): ID of the experiment these conditions belong to
        
    Returns:
        dict: Complete conditions dictionary ready for database storage
    """
    # Start with default values from FIELD_CONFIG
    conditions = {name: config['default'] for name, config in FIELD_CONFIG.items()}
    
    # Override with values provided in 'data'
    conditions.update({key: data.get(key, default) for key, default in conditions.items()})
    
    # Add experiment_id for the relationship
    conditions['experiment_id'] = experiment_id
    
    return conditions

# --- File Storage Helpers (Using utils.storage) ---

# Removed the FileStorage class and get_upload_dir function

def save_uploaded_file(file, storage_folder):
    """
    Saves an uploaded file using the centralized utils.storage.save_file.

    Args:
        file (UploadedFile): The file object from st.file_uploader.
        storage_folder (str): The target folder/prefix in the storage backend (e.g., "photos/sample_123").

    Returns:
        str or None: The storage path/URL of the saved file, or None if error.
    """
    if not file:
        return None

    try:
        file_bytes = file.getvalue()
        original_filename = file.name
        # Note: filename_prefix might be redundant if storage_folder provides uniqueness
        # Construct the final file name (e.g., keep original name within the folder)
        final_file_name = os.path.basename(original_filename).replace(" ", "_") 

        # Use the centralized save_file function
        file_path_url = save_file(
            file_data=file_bytes,
            file_name=final_file_name, # Use the cleaned original filename
            folder=storage_folder
        )
        return file_path_url
    except Exception as e:
        st.error(f"Error saving file {file.name}: {str(e)}")
        logger.error(f"Error in save_uploaded_file: {e}", exc_info=True)
        return None

def delete_file_if_exists(file_path):
    """
    Deletes a file using the centralized utils.storage.delete_file.

    Args:
        file_path (str): The storage path/URL of the file to delete.

    Returns:
        bool: True if deletion was successful or file didn't exist, False otherwise.
    """
    if not file_path:
        return True # Nothing to delete
    try:
        delete_file(file_path)
        return True
    except FileNotFoundError:
        logger.warning(f"File not found for deletion (already deleted?): {file_path}")
        return True # Consider file not found as success in deletion context
    except Exception as e:
        st.warning(f"Could not delete file {file_path}: {e}")
        logger.error(f"Error in delete_file_if_exists: {e}", exc_info=True)
        return False

# --- Formatting Utility ---

def format_value(value, config):
    """Formats a value based on its config (type, format string)."""
    if value is None:
        return "N/A"
    if config['type'] == 'number' and config.get('format') and isinstance(value, (int, float)):
        try:
           return config['format'] % float(value)
        except (ValueError, TypeError):
           # Fallback if format string fails
           return str(value)
    else:
        # Handle non-numeric types or numbers without specific format
        return str(value)

# --- New Form Generation Utility ---
def generate_form_fields(config, current_values, field_names, key_prefix=""):
    """
    Generate form fields based on the provided configuration.
    
    Args:
        config (dict): The configuration dictionary for the fields.
        current_values (dict): The current values for the fields.
        field_names (list): A list of field names to generate.
        key_prefix (str): A prefix for the widget keys to ensure uniqueness.
        
    Returns:
        dict: A dictionary of the new values from the form fields.
    """
    new_values = {}
    for name in field_names:
        if name in config:
            field_config = config[name]
            field_type = field_config.get('type', 'text')
            
            # Use a unique key for each widget
            widget_key = f"{key_prefix}_{name}"
            
            # Get the current value for this field, or its default
            current_value = current_values.get(name, field_config.get('default'))

            if field_type == 'select':
                options = field_config.get('options', [])
                try:
                    # Find index of current value, default to 0 if not found
                    index = options.index(current_value) if current_value in options else 0
                except (ValueError, TypeError):
                    index = 0
                new_values[name] = st.selectbox(
                    label=field_config['label'],
                    options=options,
                    index=index,
                    help=field_config.get('help', ''),
                    key=widget_key
                )
            elif field_type == 'number':
                # Get number-specific config values, providing sensible defaults
                min_val = field_config.get('min_value')
                max_val = field_config.get('max_value')
                step = field_config.get('step', 1.0)
                format_str = field_config.get('format', "%.2f")

                # Ensure the value passed to the widget is a valid number, or a default if None
                val = current_value
                if val is None:
                    val = field_config.get('default')

                # Cast to the correct type (int or float) based on config
                try:
                    if format_str == '%d':
                        # Ensure step is also an int for integer types
                        step = int(step) if step is not None else 1
                        val = int(float(val)) # Safely cast to float first, then int
                    else:
                        step = float(step) if step is not None else 1.0
                        val = float(val)
                except (ValueError, TypeError):
                    val = 0 if format_str == '%d' else 0.0 # Fallback to correct type

                new_values[name] = st.number_input(
                    label=field_config['label'],
                    min_value=min_val,
                    max_value=max_val,
                    value=val,
                    step=step,
                    format=format_str,
                    help=field_config.get('help', ''),
                    key=widget_key
                )
            elif field_type == 'date':
                # Ensure value passed is either None or a datetime.date/datetime.datetime
                date_value = current_value if isinstance(current_value, (datetime.date, datetime.datetime)) else None
                if isinstance(date_value, datetime.datetime):
                    if date_value.tzinfo is None:
                        date_value = date_value.replace(tzinfo=pytz.UTC)
                    # Convert to EST for display
                    est = pytz.timezone('US/Eastern')
                    date_value = date_value.astimezone(est)
                
                new_values[name] = st.date_input(
                    label=field_config['label'],
                    value=date_value,
                    key=widget_key
                )
            else:
                # Handle other field types as before
                new_values[name] = st.text_input(
                    label=field_config['label'],
                    value=str(current_value) if current_value is not None else "",
                    key=widget_key
                )
    return new_values

# --- Excel Utilities ---

def autosize_excel_columns(writer, sheet_name: str, min_width: int = 10, max_width: int = 60) -> None:
    """
    Autosize columns for a given sheet in an openpyxl-backed ExcelWriter.

    Args:
        writer: pandas.ExcelWriter with engine='openpyxl'
        sheet_name: Name of the sheet that has already been written
        min_width: Minimum width to apply
        max_width: Maximum width to apply
    """
    try:
        ws = writer.sheets.get(sheet_name)
        if ws is None:
            return
        for col_cells in ws.columns:
            try:
                first_cell = next(iter(col_cells), None)
                if first_cell is None:
                    continue
                col_letter = get_column_letter(first_cell.column)
                max_len = 0
                for cell in col_cells:
                    val = cell.value
                    if val is None:
                        continue
                    try:
                        length = len(str(val))
                        if length > max_len:
                            max_len = length
                    except Exception:
                        continue
                ws.column_dimensions[col_letter].width = max(min_width, min(max_len + 2, max_width))
            except Exception:
                # Ignore per-column sizing errors
                continue
    except Exception:
        # Ignore if engine is not openpyxl or sheets not accessible
        pass

# --- Modification Logging Utility ---

def log_modification(
    db: Session, 
    modified_table: str, 
    modification_type: str, 
    experiment_id: str = None, 
    experiment_fk: int = None, 
    old_values: dict = None, 
    new_values: dict = None
):
    """
    Log a modification to the database. Does NOT commit.
    The caller is responsible for handling the session and transaction.
    """
    try:
        # Get current user if available in session state
        modified_by = st.session_state.get("user", {}).get("email", "unknown")

        # Convert any datetime objects for JSON serialization
        if old_values:
            old_values = {k: v.isoformat() if isinstance(v, datetime.datetime) else v for k, v in old_values.items()}
        
        if new_values:
            new_values = {k: v.isoformat() if isinstance(v, datetime.datetime) else v for k, v in new_values.items()}
        
        # Create the log entry
        log_entry = ModificationsLog(
            experiment_id=experiment_id,
            experiment_fk=experiment_fk,
            modified_by=modified_by,
            modified_table=modified_table,
            modification_type=modification_type,
            old_values=old_values,
            new_values=new_values
        )
        
        db.add(log_entry)
        # NO COMMIT HERE. The caller is responsible for the transaction.
        
    except Exception as e:
        # Re-raise to ensure the parent transaction can be rolled back.
        logger.error(f"Error creating log entry (will be rolled back): {e}", exc_info=True)
        raise e

# --- Moved from view_experiments.py ---
def extract_conditions(conditions_obj):
    """
    Extracts experimental conditions from an ORM object.
    
    This function uses FIELD_CONFIG to provide default values
    for any missing conditions.
    
    Args:
        conditions_obj: SQLAlchemy ORM object containing experimental conditions
        
    Returns:
        dict: Dictionary of conditions with default values for missing fields
    """
    extracted = {}
    for field_name, config in FIELD_CONFIG.items():
        # Try to get the attribute from the conditions object;
        # if it's None or missing, use the default
        value = getattr(conditions_obj, field_name, None)
        extracted[field_name] = value if value is not None else config['default']
    return extracted

def remove_duplicate_samples(excel_path: str = "data/20250404_Master Data Migration Sheet.xlsx") -> None:
    """
    Reads the sample_info sheet from the Excel file, identifies and removes rows with duplicate sample_ids.
    Keeps the first occurrence of each sample_id and removes subsequent duplicates.
    Saves the modified Excel file with '_cleaned' suffix.
    
    Args:
        excel_path (str): Path to the Excel file
    """
    try:
        # Read the Excel file
        excel_file = pd.ExcelFile(excel_path)
        
        # Check if sample_info sheet exists
        if 'sample_info' not in excel_file.sheet_names:
            logger.error("No 'sample_info' sheet found in the Excel file")
            return
        
        # Read all sheets into a dictionary
        all_sheets = {}
        for sheet_name in excel_file.sheet_names:
            all_sheets[sheet_name] = pd.read_excel(excel_file, sheet_name=sheet_name, engine='openpyxl')
        
        # Get the sample_info sheet
        sample_df = all_sheets['sample_info']
        
        # Check if sample_id column exists
        if 'sample_id' not in sample_df.columns:
            logger.error("No 'sample_id' column found in sample_info sheet")
            return
        
        # Find duplicates
        duplicates = sample_df[sample_df['sample_id'].duplicated()]['sample_id'].unique()
        
        if len(duplicates) == 0:
            logger.info("No duplicate sample_ids found")
            return
        
        # Log the duplicates found
        logger.info(f"Found {len(duplicates)} duplicate sample_ids: {', '.join(str(d) for d in duplicates)}")
        
        # Keep first occurrence of each sample_id
        original_count = len(sample_df)
        sample_df = sample_df.drop_duplicates(subset=['sample_id'], keep='first')
        removed_count = original_count - len(sample_df)
        
        # Update the dictionary with cleaned sample_info
        all_sheets['sample_info'] = sample_df
        
        # Create new filename with '_cleaned' suffix
        file_path = Path(excel_path)
        new_path = file_path.parent / f"{file_path.stem}_cleaned{file_path.suffix}"
        
        # Save all sheets to new Excel file
        with pd.ExcelWriter(new_path) as writer:
            for sheet_name, df in all_sheets.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        logger.info(f"Removed {removed_count} duplicate rows")
        logger.info(f"Saved cleaned file to: {new_path}")
        
    except Exception as e:
        logger.error(f"Error processing Excel file: {str(e)}")
        raise

def check_experiment_duplicates(excel_path: str = "data/20250404_Master Data Migration Sheet.xlsx") -> None:
    """
    Checks for duplicate experiment_numbers and experiment_ids in the experiments sheet.
    
    Args:
        excel_path (str): Path to the Excel file
    """
    try:
        # Read the Excel file
        excel_file = pd.ExcelFile(excel_path)
        
        # Check if experiments sheet exists
        if 'experiments' not in excel_file.sheet_names:
            logger.error("No 'experiments' sheet found in the Excel file")
            return
        
        # Read experiments sheet
        df = pd.read_excel(excel_file, sheet_name='experiments', engine='openpyxl')
        
        # Check for experiment_number duplicates
        if 'experiment_number' in df.columns:
            num_duplicates = df[df['experiment_number'].duplicated()]
            if not num_duplicates.empty:
                logger.error("\nDuplicate experiment_numbers found:")
                for _, row in num_duplicates.iterrows():
                    logger.error(f"experiment_number {row['experiment_number']} is duplicated (experiment_id: {row['experiment_id']})")
        else:
            logger.error("No 'experiment_number' column found")
            
        # Check for experiment_id duplicates
        if 'experiment_id' in df.columns:
            id_duplicates = df[df['experiment_id'].duplicated()]
            if not id_duplicates.empty:
                logger.error("\nDuplicate experiment_ids found:")
                for _, row in id_duplicates.iterrows():
                    logger.error(f"experiment_id {row['experiment_id']} is duplicated (experiment_number: {row['experiment_number']})")
        else:
            logger.error("No 'experiment_id' column found")
            
        # Show all experiment records for verification
        logger.info("\nAll experiments in sheet:")
        for _, row in df.iterrows():
            logger.info(f"experiment_number: {row['experiment_number']}, experiment_id: {row['experiment_id']}")
            
    except Exception as e:
        logger.error(f"Error checking experiment duplicates: {str(e)}")
        raise

def clean_external_analyses(excel_path: str = "data/20250404_Master Data Migration Sheet.xlsx") -> None:
    """
    Reads the external_analyses sheet from the Excel file, removes rows where pxrf_reading_no is blank,
    and ensures proper sample_info_id relationships are maintained.
    Saves the modified Excel file with '_cleaned' suffix.
    
    Args:
        excel_path (str): Path to the Excel file
    """
    try:
        # Read the Excel file
        excel_file = pd.ExcelFile(excel_path)
        
        # Check if required sheets exist
        required_sheets = {'external_analyses', 'sample_info'}
        missing_sheets = required_sheets - set(excel_file.sheet_names)
        if missing_sheets:
            logger.error(f"Missing required sheets: {', '.join(missing_sheets)}")
            return
        
        # Read all sheets into a dictionary
        all_sheets = {}
        for sheet_name in excel_file.sheet_names:
            all_sheets[sheet_name] = pd.read_excel(excel_file, sheet_name=sheet_name, engine='openpyxl')
        
        # Get the relevant sheets
        analyses_df = all_sheets['external_analyses']
        sample_info_df = all_sheets['sample_info']
        
        # Check if required columns exist
        if 'pxrf_reading_no' not in analyses_df.columns:
            logger.error("No 'pxrf_reading_no' column found in external_analyses sheet")
            return
        if 'sample_id' not in analyses_df.columns or 'sample_id' not in sample_info_df.columns:
            logger.error("'sample_id' column missing in one or both sheets")
            return
            
        # Count rows before cleaning
        original_count = len(analyses_df)
        
        # Remove rows where pxrf_reading_no is blank (NaN, None, or empty string)
        analyses_df = analyses_df.dropna(subset=['pxrf_reading_no'])
        analyses_df = analyses_df[analyses_df['pxrf_reading_no'].astype(str).str.strip() != '']
        
        # Create a mapping of sample_id to auto-incrementing sample_info_id
        sample_id_mapping = {row['sample_id']: idx + 1 
                           for idx, row in sample_info_df.iterrows()}
        
        # Add/update sample_info_id based on sample_id
        analyses_df['sample_info_id'] = analyses_df['sample_id'].map(sample_id_mapping)
        
        # Remove rows where we couldn't find a matching sample_info_id
        invalid_samples = analyses_df[analyses_df['sample_info_id'].isna()]['sample_id'].unique()
        if len(invalid_samples) > 0:
            logger.warning(f"Found {len(invalid_samples)} samples in external_analyses with no matching sample_info: {invalid_samples}")
            
        analyses_df = analyses_df.dropna(subset=['sample_info_id'])
        
        # Convert sample_info_id to integer
        analyses_df['sample_info_id'] = analyses_df['sample_info_id'].astype(int)
        
        # Count removed rows
        removed_count = original_count - len(analyses_df)
        
        # Update the dictionary with cleaned external_analyses
        all_sheets['external_analyses'] = analyses_df
        
        # Create new filename with '_cleaned' suffix
        file_path = Path(excel_path)
        new_path = file_path.parent / f"{file_path.stem}_cleaned{file_path.suffix}"
        
        # Save all sheets to new Excel file
        with pd.ExcelWriter(new_path) as writer:
            for sheet_name, df in all_sheets.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        logger.info(f"Removed {removed_count} rows with blank pxrf_reading_no values or invalid sample_ids")
        logger.info(f"Successfully mapped sample_info_ids for {len(analyses_df)} rows")
        logger.info(f"Saved cleaned file to: {new_path}")
        
    except Exception as e:
        logger.error(f"Error cleaning external_analyses sheet: {str(e)}")
        raise

def backfill_calculated_fields(db: Session):
    """
    Recalculates derived fields for all relevant records.
    This now focuses on scalar results and experimental conditions.
    """
    logger.info("Starting backfill of calculated fields...")

    # Backfill for ExperimentalConditions
    try:
        conditions_to_update = db.query(ExperimentalConditions).all()
        logger.info(f"Found {len(conditions_to_update)} experimental conditions to check for backfill.")
        updated_conditions_count = 0
        for conditions in conditions_to_update:
            # Create a temporary dictionary of current values to check for changes
            original_values = {
                'water_to_rock_ratio': conditions.water_to_rock_ratio,
                'catalyst_percentage': conditions.catalyst_percentage,
                'catalyst_ppm': conditions.catalyst_ppm
            }
            # The method directly modifies the object
            conditions.calculate_derived_conditions()
            # Check if any values were actually changed
            if (conditions.water_to_rock_ratio != original_values['water_to_rock_ratio'] or
                conditions.catalyst_percentage != original_values['catalyst_percentage'] or
                conditions.catalyst_ppm != original_values['catalyst_ppm']):
                updated_conditions_count += 1
        
        if updated_conditions_count > 0:
            logger.info(f"Updated {updated_conditions_count} experimental conditions with new calculated values.")
        else:
            logger.info("No experimental conditions required updates.")
            
    except Exception as e:
        logger.error(f"Error during ExperimentalConditions backfill: {e}", exc_info=True)
        db.rollback() # Rollback on error for this section
        # Decide if you want to stop or continue
    
    # Backfill for ChemicalAdditives derived values (depends on conditions)
    try:
        all_conditions = conditions_to_update if 'conditions_to_update' in locals() else db.query(ExperimentalConditions).all()
        updated_additives_count = 0
        for conditions in all_conditions:
            for additive in list(getattr(conditions, 'chemical_additives', []) or []):
                # Snapshot if needed (not logged per-item to keep output concise)
                additive.calculate_derived_values()
                updated_additives_count += 1
        if updated_additives_count > 0:
            logger.info(f"Recalculated derived values for {updated_additives_count} chemical additives.")
        else:
            logger.info("No chemical additives found for derived value recalculation.")
    except Exception as e:
        logger.error(f"Error during ChemicalAdditives backfill: {e}", exc_info=True)
        db.rollback()

    # Backfill for ScalarResults
    try:
        # Eagerly load experiment and conditions to avoid N+1 queries
        results_to_update = db.query(ScalarResults).options(
            joinedload(ScalarResults.result_entry)
            .joinedload(ExperimentalResults.experiment)
            .joinedload(Experiment.conditions)
        ).all()

        logger.info(f"Found {len(results_to_update)} scalar results to check for backfill.")
        updated_scalar_count = 0

        for scalar_result in results_to_update:
            original_yield = scalar_result.grams_per_ton_yield
            # This method now calculates yield based on its own gross_ammonium_concentration
            scalar_result.calculate_yields()
            if scalar_result.grams_per_ton_yield != original_yield:
                updated_scalar_count += 1

        if updated_scalar_count > 0:
            logger.info(f"Updated {updated_scalar_count} scalar results with new calculated yields.")
        else:
            logger.info("No scalar results required updates.")

    except Exception as e:
        logger.error(f"Error during ScalarResults backfill: {e}", exc_info=True)
        db.rollback() # Rollback this part of the transaction
    
    # If both sections complete without raising an error, commit the changes
    try:
        db.commit()
        logger.info("Successfully committed all backfilled fields.")
    except Exception as e:
        logger.error(f"Failed to commit backfill changes: {e}", exc_info=True)
        db.rollback()

def get_sample_options():
    """
    Fetch all samples from the database and format them for the selectbox.
    
    This function queries the SampleInfo table to retrieve all available samples
    and formats them into a user-friendly display format that includes sample ID,
    rock classification, and location information.
    
    Returns:
        tuple: A tuple containing:
            - options_list (list): List of formatted display strings for the selectbox
            - sample_dict (dict): Dictionary mapping display text to sample_id
    """
    try:
        with SessionLocal() as db:
            samples = db.query(
                SampleInfo.sample_id,
                SampleInfo.rock_classification,
                SampleInfo.locality,
                SampleInfo.state,
                SampleInfo.country
            ).order_by(SampleInfo.sample_id).all()
            
            if not samples:
                logger.info("No samples found in database")
                return [""], {}
            
            # Create formatted options and mapping dictionary
            options = [""]  # Empty option for no selection
            sample_dict = {"": ""}  # Map empty option to empty string
            
            for sample in samples:
                # Ensure sample_id is not None or empty
                if not sample.sample_id or not sample.sample_id.strip():
                    logger.warning(f"Skipping sample with empty sample_id: {sample}")
                    continue
                
                # Create a descriptive display text
                display_parts = [sample.sample_id.strip()]
                
                if sample.rock_classification and sample.rock_classification.strip():
                    display_parts.append(sample.rock_classification.strip())
                
                if sample.locality and sample.locality.strip():
                    location_parts = [sample.locality.strip()]
                    if sample.state and sample.state.strip():
                        location_parts.append(sample.state.strip())
                    if sample.country and sample.country.strip():
                        location_parts.append(sample.country.strip())
                    display_parts.append(f"({', '.join(location_parts)})")
                
                display_text = " - ".join(display_parts)
                options.append(display_text)
                sample_dict[display_text] = sample.sample_id.strip()
                
                # Debug logging for the first few samples
                if len(options) <= 4:  # Log first 3 samples (plus empty option)
                    logger.debug(f"Sample mapping: '{display_text}' -> '{sample.sample_id.strip()}'")
            
            logger.info(f"Loaded {len(samples)} samples for selection")
            return options, sample_dict
    except Exception as e:
        st.error(f"Error loading samples: {str(e)}")
        logger.error(f"Error in get_sample_options: {e}", exc_info=True)
        return [""], {}

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Run the duplicate checks
    # check_experiment_duplicates()
    # Run the sample duplicate removal if needed
    # remove_duplicate_samples()
    # Clean external analyses if needed
    clean_external_analyses()