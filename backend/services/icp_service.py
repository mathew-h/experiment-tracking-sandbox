import pandas as pd
import re
import datetime as dt
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import Experiment, ExperimentalResults, ICPResults, ModificationsLog
from io import StringIO
from frontend.config.variable_config import ICP_FIXED_ELEMENT_FIELDS
from backend.services.result_merge_utils import (
    create_experimental_result_row,
    ensure_primary_result_for_timepoint,
    find_timepoint_candidates,
    choose_parent_candidate,
    update_cumulative_times_for_chain,
)

class ICPService:
    """Service for handling ICP elemental analysis data operations."""
    NON_ELEMENT_FIELDS = {
        'experiment_id', 'time_post_reaction', 'dilution_factor', 'raw_label',
        'instrument_used', 'detection_limits', 'measurement_date', 'sample_date'
    }

    @staticmethod
    def _infer_delimiter_from_line(line: str) -> str:
        """Infer the delimiter used in an ICP export header/data line."""
        delimiter_candidates = [",", "\t", ";"]
        delimiter_counts = {d: line.count(d) for d in delimiter_candidates}
        best_delimiter = max(delimiter_counts, key=delimiter_counts.get)
        return best_delimiter if delimiter_counts[best_delimiter] > 0 else ","

    @staticmethod
    def _detect_header_row_and_delimiter(lines: List[str]) -> Tuple[int, str]:
        """
        Detect header row and delimiter.

        Primary rule: header is the row containing a true `Label` column token.
        """
        max_scan = min(80, len(lines))

        # Pass 1 (strict): look for a tokenized "Label" column.
        for i, raw_line in enumerate(lines[:max_scan]):
            line = raw_line.strip()
            if not line:
                continue
            delimiter = ICPService._infer_delimiter_from_line(line)
            columns = [c.strip().strip('"').lower() for c in line.split(delimiter)]
            if "label" in columns and 5 <= len(columns) <= 80:
                return i, delimiter

        # Pass 2 (fallback): existing keyword-style detection, delimiter-aware.
        for i, raw_line in enumerate(lines[:max_scan]):
            line = raw_line.strip()
            if not line:
                continue
            lower_line = line.lower()
            if any(pattern in lower_line for pattern in ["label", "element", "concentration", "intensity", "date time"]):
                delimiter = ICPService._infer_delimiter_from_line(line)
                columns = line.split(delimiter)
                if 5 <= len(columns) <= 80:
                    return i, delimiter

        # Legacy fallback
        return 2, ","
    
    @staticmethod
    def parse_csv_file(file_content: bytes, manual_header_row: int = None) -> pd.DataFrame:
        """
        Parse CSV file with flexible header detection.
        Automatically detects the header row and data start row.
        
        Args:
            file_content: Raw bytes content of the CSV file
            
        Returns:
            DataFrame with CSV data starting from detected header row
        """
        try:
            # Convert bytes to string and tolerate UTF-8 BOM
            csv_string = file_content.decode('utf-8-sig', errors='replace')
            lines = csv_string.split('\n')

            # Use manual header row if provided, otherwise auto-detect.
            if manual_header_row is not None and manual_header_row > 0:
                header_row = manual_header_row
                source_line = lines[header_row] if header_row < len(lines) else ""
                delimiter = ICPService._infer_delimiter_from_line(source_line)
            else:
                header_row, delimiter = ICPService._detect_header_row_and_delimiter(lines)
            
            # Read CSV with detected header row and flexible error handling
            try:
                df = pd.read_csv(
                    StringIO(csv_string),
                    skiprows=header_row,
                    sep=delimiter,
                    engine='python',
                    on_bad_lines='skip'
                )
            except TypeError:
                # Fallback for older pandas versions that don't support on_bad_lines
                df = pd.read_csv(
                    StringIO(csv_string),
                    skiprows=header_row,
                    sep=delimiter,
                    engine='python',
                    error_bad_lines=False,
                    warn_bad_lines=False
                )
            
            # Clean up any unnamed columns or empty columns
            df.columns = [str(col).strip() for col in df.columns]
            df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
            df = df.dropna(how='all')  # Remove completely empty rows
            
            return df
            
        except Exception as e:
            # Provide more detailed error information
            error_msg = f"Error parsing CSV file: {str(e)}"
            try:
                # Try to provide context about the file structure
                csv_string = file_content.decode('utf-8')
                lines = csv_string.split('\n')
                error_msg += f"\nFile has {len(lines)} lines."
                if len(lines) > 0:
                    error_msg += f" First line has {len(lines[0].split(','))} columns."
                if len(lines) > 6:
                    error_msg += f" Line 7 has {len(lines[6].split(','))} columns."
            except:
                pass  # Don't let error reporting cause additional errors
            raise ValueError(error_msg)
    
    @staticmethod
    def extract_sample_info(label: str) -> Dict[str, Any]:
        """
        Extract experiment ID, time point, and dilution factor from label column.
        
        Expected format: 'Serum_MH_011_Day5_5x' or 'Serum-MH-011_Day5_5x'
        Supports dashes and underscores in experiment IDs.
        
        Args:
            label: Sample label string
            
        Returns:
            Dictionary with experiment_id, time_post_reaction, and dilution_factor
            Returns None if label doesn't match expected pattern (e.g., "Standard 1", "Blank")
        """
        try:
            # Pattern to match: ExpID_(Day|Time)Number_DilutionFactorx
            # More robust approach to handle dashes/underscores in experiment IDs
            # Examples: Serum_MH_011_Day5_5x, Serum-MH-025_Time3_10x, Test_Sample_A_Day1_2x
            
            # Use search from the end to find the last occurrence of the time pattern
            time_pattern = r'_(Day|Time)(\d+(?:\.\d+)?)_(\d+(?:\.\d+)?)x?$'
            time_match = re.search(time_pattern, label, re.IGNORECASE)
            
            if not time_match:
                # Return None for non-matching labels (Standards, Blanks, etc.)
                return None
            
            # Extract the experiment ID by removing the time pattern from the end
            experiment_id = label[:time_match.start()]
            time_unit = time_match.group(1).lower()
            time_value = float(time_match.group(2))
            dilution_factor = float(time_match.group(3))
            
            # Clean up trailing underscore/hyphen if present after stripping time
            if experiment_id and experiment_id[-1] in ['_', '-']:
                experiment_id = experiment_id[:-1]
            
            # Convert time to days if needed
            if time_unit == 'time':
                # Assume 'Time' units are in days (adjust if different)
                time_post_reaction = time_value
            else:  # 'day'
                time_post_reaction = time_value
            
            return {
                'experiment_id': experiment_id,
                'time_post_reaction': time_post_reaction,
                'dilution_factor': dilution_factor
            }
            
        except Exception as e:
            # Return None for any parsing errors instead of raising
            return None
    
    @staticmethod
    def apply_dilution_correction(df: pd.DataFrame, dilution_factor: float) -> pd.DataFrame:
        """
        Apply dilution factor to concentration values to get absolute concentrations.
        For long-format data, this applies to the Concentration column.
        
        Args:
            df: DataFrame with long-format elemental data
            dilution_factor: Dilution factor to apply (e.g., 5.0 for 5x dilution)
            
        Returns:
            DataFrame with corrected concentrations
        """
        df_corrected = df.copy()
        
        if 'Concentration' in df_corrected.columns:
            # Apply dilution correction to Concentration column
            df_corrected['Corrected_Concentration'] = (
                pd.to_numeric(df_corrected['Concentration'], errors='coerce') * dilution_factor
            )
        else:
            raise ValueError("DataFrame must contain 'Concentration' column for dilution correction")
        
        return df_corrected

    @staticmethod
    def extract_measurement_date(sample_df: pd.DataFrame) -> Optional[dt.datetime]:
        """
        Extract measurement date from ICP long-format rows.

        The raw column is expected as 'Date Time'. We normalize to calendar day
        by setting time to midnight (e.g., '2/9/2026 1:14:27 PM' -> 2026-02-09 00:00:00).
        """
        if sample_df is None or sample_df.empty:
            return None
        if 'Date Time' not in sample_df.columns:
            return None

        parsed = pd.to_datetime(sample_df['Date Time'], errors='coerce')
        parsed = parsed.dropna()
        if parsed.empty:
            return None

        first_valid = parsed.iloc[0]
        return dt.datetime.combine(first_valid.date(), dt.time.min)
    
    @staticmethod
    def select_best_lines(df: pd.DataFrame) -> pd.DataFrame:
        """
        Select the row with highest intensity for each element per sample.
        Handles long-format data where each row is one element measurement.
        
        Expected columns: Label, Element Label, Intensity
        
        Args:
            df: DataFrame with long-format elemental data
            
        Returns:
            DataFrame with best line selected for each element per sample
        """
        required_columns = ['Label', 'Element Label', 'Intensity']
        if not all(col in df.columns for col in required_columns):
            raise ValueError(f"DataFrame must contain columns: {required_columns}")
        
        # Convert Intensity to numeric, handling any non-numeric values
        df = df.copy()
        df['Intensity'] = pd.to_numeric(df['Intensity'], errors='coerce')
        
        # Group by Label and Element, select row with maximum intensity
        # This handles multiple wavelengths/lines per element
        best_rows = []
        
        for (label, element), group in df.groupby(['Label', 'Element Label']):
            if len(group) == 1:
                # Only one measurement for this element
                best_rows.append(group.iloc[0])
            else:
                # Multiple lines for this element, select the one with highest intensity
                max_intensity_idx = group['Intensity'].idxmax()
                if pd.notna(max_intensity_idx):  # Check for valid max index
                    best_rows.append(df.loc[max_intensity_idx])
                else:
                    # If all intensities are NaN, take the first row
                    best_rows.append(group.iloc[0])
        
        return pd.DataFrame(best_rows).reset_index(drop=True)
    
    @staticmethod
    def process_icp_dataframe(df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Process the entire ICP DataFrame from long-format to sample-based data for upload.
        
        Expected DataFrame structure:
        - Label: Sample identifiers (e.g., 'Serum_MH_011_Day5_5x')  
        - Element Label: Element with wavelength (e.g., 'Al 394.401', 'Fe 238.204')
        - Concentration: Raw concentration values
        - Intensity: Measurement values (for quality assessment)
        - Type: Sample type (filter out 'BLK' blanks)
        
        Args:
            df: Raw ICP DataFrame in long format
            
        Returns:
            Tuple of (processed_data_list, error_messages)
        """
        processed_data = []
        errors = []
        
        if df.empty:
            errors.append("DataFrame is empty")
            return processed_data, errors
        
        # Validate required columns
        required_columns = ['Label', 'Element Label', 'Concentration', 'Intensity']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            errors.append(f"Missing required columns: {missing_columns}")
            return processed_data, errors
        
        try:
            # Filter out blank samples (Type = 'BLK' or Label contains 'Blank')
            if 'Type' in df.columns:
                df_samples = df[df['Type'] != 'BLK'].copy()
            else:
                df_samples = df[~df['Label'].str.contains('Blank', case=False, na=False)].copy()
            
            if df_samples.empty:
                errors.append("No non-blank samples found in data")
                return processed_data, errors
            
            # Get unique sample labels
            unique_labels = df_samples['Label'].unique()
            
            for label in unique_labels:
                try:
                    # Extract sample information (experiment_id, time, dilution)
                    sample_info = ICPService.extract_sample_info(label)
                    
                    # Skip rows that don't match expected pattern (Standards, Blanks, etc.)
                    if sample_info is None:
                        errors.append(f"Sample '{label}': Skipped - Label format not recognized (likely Standard/Blank/QC sample)")
                        continue
                    
                    # Get all data for this sample
                    sample_data = df_samples[df_samples['Label'] == label].copy()
                    measurement_date = ICPService.extract_measurement_date(sample_data)
                    
                    # Apply dilution correction to this sample's data
                    sample_data_corrected = ICPService.apply_dilution_correction(
                        sample_data, sample_info['dilution_factor']
                    )
                    
                    # Select best lines for each element
                    best_lines = ICPService.select_best_lines(sample_data_corrected)
                    
                    # Pivot from long format to wide format (one row per sample)
                    elemental_data = {}
                    for _, row in best_lines.iterrows():
                        # Extract element symbol from 'Element Label' (e.g., 'Al 394.401' -> 'Al')
                        element_label = str(row['Element Label']).strip()
                        element = element_label.split()[0]  # Get first part before space
                        concentration = row['Corrected_Concentration']
                        concentration_val = float(concentration) if pd.notna(concentration) else 0.0
                        element_key = ICPService._standardize_element_name(element)
                        elemental_data[element_key] = concentration_val
                    
                    # Combine sample info with elemental data
                    result_data = {
                        **sample_info,
                        **elemental_data,
                        'raw_label': label,
                        'measurement_date': measurement_date,
                        'sample_date': None,
                    }
                    
                    processed_data.append(result_data)
                    
                except Exception as e:
                    errors.append(f"Sample '{label}': Error processing - {str(e)}")
        
        except Exception as e:
            errors.append(f"Error processing DataFrame: {str(e)}")
        
        return processed_data, errors
    
    @staticmethod
    def _standardize_element_name(element_symbol: str) -> str:
        """
        Standardize element symbols to database field names.
        
        Args:
            element_symbol: Element symbol from CSV (e.g., 'Fe', 'Mg', 'Al')
            
        Returns:
            Standardized element name for database (lowercase)
        """
        # Clean element symbol
        clean_symbol = element_symbol.strip().lower()
        
        # Map element symbols to standard lowercase versions
        # Most symbols are already correct, but handle special cases
        symbol_mapping = {
            'al': 'al',   # Aluminum
            'ba': 'ba',   # Barium
            'ca': 'ca',   # Calcium  
            'co': 'co',   # Cobalt
            'cr': 'cr',   # Chromium
            'cs': 'cs',   # Cesium
            'cu': 'cu',   # Copper
            'fe': 'fe',   # Iron
            'gd': 'gd',   # Gadolinium
            'ir': 'ir',   # Iridium
            'k': 'k',     # Potassium
            'mg': 'mg',   # Magnesium
            'mn': 'mn',   # Manganese
            'mo': 'mo',   # Molybdenum
            'na': 'na',   # Sodium
            'nb': 'nb',   # Niobium
            'nd': 'nd',   # Neodymium
            'ni': 'ni',   # Nickel
            'os': 'os',   # Osmium
            'p': 'p',     # Phosphorus
            'pd': 'pd',   # Palladium
            'pt': 'pt',   # Platinum
            'rh': 'rh',   # Rhodium
            'ru': 'ru',   # Ruthenium
            's': 's',     # Sulfur
            'sb': 'sb',   # Antimony
            'si': 'si',   # Silicon
            'sr': 'sr',   # Strontium
            'ti': 'ti',   # Titanium
            'tl': 'tl',   # Thallium
            'v': 'v',     # Vanadium
            'y': 'y',     # Yttrium
            'zn': 'zn',   # Zinc
            
        }
        
        # Return mapped symbol or original if not found
        return symbol_mapping.get(clean_symbol, clean_symbol)
    
    @staticmethod
    def create_icp_result(db: Session, experiment_id: str, result_data: Dict[str, Any]) -> Tuple[Optional[ExperimentalResults], bool]:
        """
        Create an experimental result with ICP elemental analysis data.
        Uses unique result tracking improvements to allow multiple data types per time point.
        
        Args:
            db: Database session
            experiment_id: String experiment ID
            result_data: Dictionary containing result data fields and elemental concentrations
            
        Returns:
            Tuple of (ExperimentalResults object, was_update: bool)
            was_update is True if existing ICP data was updated, False if new data was created
            
        Raises:
            ValueError: If experiment not found
        """
        if result_data.get('time_post_reaction') is None:
            raise ValueError(
                f"time_post_reaction is required for ICP results (experiment '{experiment_id}')."
            )

        # Find experiment with normalization
        experiment = ICPService._find_experiment(db, experiment_id)
        if not experiment:
            # Keep behavior aligned with scalar uploads for treatment-variant IDs.
            from database.lineage_utils import auto_create_treatment_experiment
            experiment = auto_create_treatment_experiment(
                db=db,
                experiment_id=experiment_id,
                initial_note=result_data.get('description', 'Auto-created from ICP upload')
            )
            if not experiment:
                raise ValueError(f"Experiment with ID '{experiment_id}' not found and could not be auto-created.")
        
        # Find or create ExperimentalResults using unique result tracking improvements
        experimental_result = ICPService._find_or_create_experimental_result(
            db=db,
            experiment=experiment,
            time_post_reaction=result_data['time_post_reaction'],
            description=f"Day {result_data['time_post_reaction']} results"
        )
        
        # Separate fixed columns from all elemental data
        fixed_column_data = {}
        all_elements_data = {}
        
        # Extract fixed columns and prepare all elements JSON
        for key, value in result_data.items():
            if key in ICP_FIXED_ELEMENT_FIELDS and value is not None:
                fixed_column_data[key] = value
                all_elements_data[key] = value  # Also store in JSON for completeness
            elif key not in ICPService.NON_ELEMENT_FIELDS and value is not None:
                all_elements_data[key] = value  # Store additional elements in JSON only

        was_update = False
        if experimental_result.icp_data:
            # Update existing ICP record for this result row.
            # Only overwrite elements present in incoming CSV; preserve others.
            icp_data = experimental_result.icp_data

            # Snapshot old element values for audit trail
            old_fixed = {el: getattr(icp_data, el) for el in ICP_FIXED_ELEMENT_FIELDS}
            old_all = dict(icp_data.all_elements) if icp_data.all_elements else {}

            for element in ICP_FIXED_ELEMENT_FIELDS:
                if element in fixed_column_data:
                    setattr(icp_data, element, fixed_column_data[element])
            # Merge all_elements: incoming overrides, preserve existing for keys not in incoming
            existing = dict(icp_data.all_elements) if icp_data.all_elements else {}
            existing.update(all_elements_data)
            icp_data.all_elements = existing if existing else None
            icp_data.dilution_factor = result_data.get('dilution_factor')
            icp_data.raw_label = result_data.get('raw_label')
            if 'instrument_used' in result_data:
                icp_data.instrument_used = result_data.get('instrument_used')
            if 'detection_limits' in result_data:
                icp_data.detection_limits = result_data.get('detection_limits')
            if 'measurement_date' in result_data:
                icp_data.measurement_date = result_data.get('measurement_date')
            if 'sample_date' in result_data:
                icp_data.sample_date = result_data.get('sample_date')
            was_update = True

            # Audit trail: log changed element values
            changed_old: Dict[str, Any] = {}
            changed_new: Dict[str, Any] = {}
            for el in ICP_FIXED_ELEMENT_FIELDS:
                if el in fixed_column_data and old_fixed.get(el) != getattr(icp_data, el):
                    changed_old[el] = old_fixed.get(el)
                    changed_new[el] = getattr(icp_data, el)
            for el_key, el_val in all_elements_data.items():
                if old_all.get(el_key) != el_val:
                    changed_old[el_key] = old_all.get(el_key)
                    changed_new[el_key] = el_val
            if changed_old or changed_new:
                db.add(ModificationsLog(
                    experiment_id=experiment.experiment_id,
                    experiment_fk=experiment.id,
                    modification_type="update",
                    modified_table="icp_results",
                    old_values=changed_old or None,
                    new_values=changed_new or None,
                ))
        else:
            # Create ICP data with elemental concentrations
            icp_data = ICPResults(
                result_id=experimental_result.id,  # Link to ExperimentalResults
                # Fixed columns for Power BI efficiency
                fe=fixed_column_data.get('fe'),
                si=fixed_column_data.get('si'),
                ni=fixed_column_data.get('ni'),
                cu=fixed_column_data.get('cu'),
                mo=fixed_column_data.get('mo'),
                zn=fixed_column_data.get('zn'),
                mn=fixed_column_data.get('mn'),
                ca=fixed_column_data.get('ca'),
                cr=fixed_column_data.get('cr'),
                co=fixed_column_data.get('co'),
                mg=fixed_column_data.get('mg'),
                al=fixed_column_data.get('al'),
                sr=fixed_column_data.get('sr'),
                y=fixed_column_data.get('y'),
                nb=fixed_column_data.get('nb'),
                sb=fixed_column_data.get('sb'),
                cs=fixed_column_data.get('cs'),
                ba=fixed_column_data.get('ba'),
                nd=fixed_column_data.get('nd'),
                gd=fixed_column_data.get('gd'),
                pt=fixed_column_data.get('pt'),
                rh=fixed_column_data.get('rh'),
                ir=fixed_column_data.get('ir'),
                pd=fixed_column_data.get('pd'),
                ru=fixed_column_data.get('ru'),
                os=fixed_column_data.get('os'),
                tl=fixed_column_data.get('tl'),
                # JSON storage for all elements (including fixed ones)
                all_elements=all_elements_data if all_elements_data else None,
                # ICP metadata
                dilution_factor=result_data.get('dilution_factor'),
                raw_label=result_data.get('raw_label'),
                instrument_used=result_data.get('instrument_used'),
                detection_limits=result_data.get('detection_limits'),
                measurement_date=result_data.get('measurement_date'),
                sample_date=result_data.get('sample_date'),
                # Relationship
                result_entry=experimental_result
            )
            db.add(icp_data)

            # Audit trail for new ICP record
            if all_elements_data:
                db.add(ModificationsLog(
                    experiment_id=experiment.experiment_id,
                    experiment_fk=experiment.id,
                    modification_type="create",
                    modified_table="icp_results",
                    old_values=None,
                    new_values=all_elements_data,
                ))

        # Add to session (commit handled by caller)
        db.add(experimental_result)  # May be existing or new
        db.flush()  # Flush to get IDs assigned
        ensure_primary_result_for_timepoint(
            db=db,
            experiment_fk=experiment.id,
            time_post_reaction=result_data.get('time_post_reaction'),
        )

        # Recalculate cumulative times for the entire lineage chain
        update_cumulative_times_for_chain(db, experiment.id)
        
        return experimental_result, was_update
    
    @staticmethod
    def bulk_create_icp_results(db: Session, processed_data: List[Dict[str, Any]]) -> Tuple[List[ExperimentalResults], List[str]]:
        """
        Bulk create ICP results with validation and error collection.
        
        Args:
            db: Database session
            processed_data: List of processed ICP data dictionaries
            
        Returns:
            Tuple of (successful_results, error_messages)
        """
        results_to_add = []
        errors = []
        
        for idx, data in enumerate(processed_data):
            try:
                experiment_id = data.get('experiment_id')
                time_post_reaction = data.get('time_post_reaction')
                
                if not experiment_id:
                    errors.append(f"Sample {idx + 1}: Missing experiment_id.")
                    continue
                
                if time_post_reaction is None:
                    errors.append(f"Sample {idx + 1}: Missing time_post_reaction.")
                    continue
                
                # Create or update the ICP result
                result, was_update = ICPService.create_icp_result(
                    db=db,
                    experiment_id=experiment_id,
                    result_data=data
                )
                
                if result:
                    results_to_add.append(result)
                    
                    # Add informational message for overwrites
                    if was_update:
                        errors.append(
                            f"Sample {idx + 1}: Updated existing ICP-OES data for experiment '{experiment_id}' at time {time_post_reaction} days"
                        )
                    
            except ValueError as e:
                errors.append(f"Sample {idx + 1}: {str(e)}")
            except Exception as e:
                errors.append(f"Sample {idx + 1}: Unexpected error - {str(e)}")
        
        return results_to_add, errors
    
    @staticmethod
    def get_icp_results_for_experiment(db: Session, experiment_id: str) -> List[ICPResults]:
        """
        Retrieve all ICP results for an experiment.
        
        Args:
            db: Database session
            experiment_id: String experiment ID
            
        Returns:
            List of ICPResults objects
        """
        experiment = ICPService._find_experiment(db, experiment_id)
        if not experiment:
            return []
        return (db.query(ICPResults)
                .join(ExperimentalResults)
                .filter(ExperimentalResults.experiment_fk == experiment.id)
                .all())
    
    @staticmethod
    def update_icp_result(db: Session, result_id: int, update_data: Dict[str, Any]) -> Optional[ICPResults]:
        """
        Update an existing ICP result with new elemental data.
        
        Args:
            db: Database session
            result_id: ID of the ExperimentalResults entry
            update_data: Dictionary of fields to update
            
        Returns:
            Updated ICPResults object or None if not found
        """
        icp_result = db.query(ICPResults).filter(ICPResults.result_id == result_id).first()
        
        if not icp_result:
            raise ValueError(f"ICPResult with result_id {result_id} not found.")
        
        # Update fixed columns
        for element in ICP_FIXED_ELEMENT_FIELDS:
            if element in update_data:
                setattr(icp_result, element, update_data[element])
        
        # Update metadata fields
        metadata_fields = [
            'dilution_factor',
            'instrument_used',
            'detection_limits',
            'raw_label',
            'measurement_date',
            'sample_date',
        ]
        for field in metadata_fields:
            if field in update_data:
                setattr(icp_result, field, update_data[field])
        
        # Update JSON data if provided
        if 'all_elements' in update_data:
            icp_result.all_elements = update_data['all_elements']
        
        db.flush()
        return icp_result
    
    @staticmethod
    def _find_experiment(db: Session, experiment_id: str) -> Optional[Experiment]:
        """
        Find experiment by ID with normalization (case insensitive, ignore hyphens/underscores).
        
        Args:
            db: Database session
            experiment_id: String experiment ID to search for
            
        Returns:
            Experiment object or None if not found
        """
        # Normalize experiment_id: lower case and remove hyphens and underscores
        exp_id_normalized = experiment_id.lower().replace('-', '').replace('_', '')
        
        # Query by normalized experiment_id
        experiment = db.query(Experiment).filter(
            func.lower(func.replace(func.replace(Experiment.experiment_id, '-', ''), '_', '')) == exp_id_normalized
        ).first()
        
        if experiment:
             return experiment
             
        # Try to find a partial match if exact normalized match fails
        # This handles cases where user enters "AUTO_JW_013" but DB has "AUTO-JW-013"
        # The above query should handle this, but let's be robust
        
        # If still not found, check if this is a treatment variant that needs auto-creation?
        # For now, just return None if not found
        
        return None
    
    @staticmethod
    def _find_or_create_experimental_result(
        db: Session, 
        experiment: Experiment, 
        time_post_reaction: float = None, 
        description: str = None,
        incoming_data_type: str = "icp",
    ) -> ExperimentalResults:
        """
        Find existing ExperimentalResults or create new one.
        Attempts to reuse existing result for the same time point if it doesn't already have ICP data.
        
        Args:
            db: Database session
            experiment: Experiment object
            time_post_reaction: Time point in days (optional)
            description: Optional description
            
        Returns:
            ExperimentalResults object (new or existing)
        """
        candidates = find_timepoint_candidates(
            db=db,
            experiment_fk=experiment.id,
            time_post_reaction=time_post_reaction,
        )
        existing = choose_parent_candidate(candidates, incoming_data_type=incoming_data_type)
        if existing:
            # ICP metadata (raw_label) is stored on the ICP record itself;
            # don't pollute the parent description with auto-generated ICP text.
            return existing

        # Create new parent result row when no candidate exists for the time bucket.
        description_text = description
        if not description_text:
            if time_post_reaction is not None:
                description_text = f"Analysis results for Day {time_post_reaction}"
            else:
                description_text = "Analysis results"
        return create_experimental_result_row(
            db=db,
            experiment=experiment,
            time_post_reaction=time_post_reaction,
            description=description_text,
        )
    
    @staticmethod
    def validate_icp_data(processed_data: List[Dict[str, Any]]) -> List[str]:
        """
        Validate processed ICP data for common issues.
        
        Args:
            processed_data: List of processed data dictionaries
            
        Returns:
            List of validation error messages
        """
        errors = []
        
        if not processed_data:
            errors.append("No data to validate")
            return errors
        
        for idx, data in enumerate(processed_data):
            sample_id = f"Sample {idx + 1}"
            
            # Check required fields
            if not data.get('experiment_id'):
                errors.append(f"{sample_id}: Missing experiment_id")
            
            if data.get('time_post_reaction') is None:
                errors.append(f"{sample_id}: Missing time_post_reaction")
            
            if not data.get('dilution_factor'):
                errors.append(f"{sample_id}: Missing dilution_factor")
            
            # Check for elemental data
            elemental_keys = [k for k in data.keys() if k not in ['experiment_id', 'time_post_reaction', 'dilution_factor', 'raw_label']]
            if not elemental_keys:
                errors.append(f"{sample_id}: No elemental concentration data found")
        
        return errors
    
    @staticmethod
    def diagnose_csv_structure(file_content: bytes) -> Dict[str, Any]:
        """
        Diagnose CSV file structure to help with parsing issues.
        
        Args:
            file_content: Raw bytes content of the CSV file
            
        Returns:
            Dictionary with diagnostic information about the CSV structure
        """
        try:
            csv_string = file_content.decode('utf-8')
            lines = csv_string.split('\n')
            
            diagnosis = {
                'total_lines': len(lines),
                'line_analysis': [],
                'suggested_header_row': None
            }
            
            # Analyze first 20 lines
            for i, line in enumerate(lines[:20]):
                if line.strip():  # Skip empty lines
                    columns = line.split(',')
                    line_info = {
                        'line_number': i + 1,
                        'column_count': len(columns),
                        'has_icp_keywords': any(pattern in line.lower() for pattern in ['label', 'element', 'concentration', 'intensity', 'date time']),
                        'preview': line[:100] + '...' if len(line) > 100 else line
                    }
                    diagnosis['line_analysis'].append(line_info)
                    
                    # Suggest header row
                    if (line_info['has_icp_keywords'] and 
                        5 <= line_info['column_count'] <= 50 and 
                        diagnosis['suggested_header_row'] is None):
                        diagnosis['suggested_header_row'] = i
            
            return diagnosis
            
        except Exception as e:
            return {'error': f"Error diagnosing CSV structure: {str(e)}"}
    
    @staticmethod
    def parse_and_process_icp_file(file_content: bytes, manual_header_row: int = 0) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Complete workflow to parse and process ICP CSV file.
        
        This function orchestrates the entire ICP data processing pipeline:
        1. Parse CSV file (skip header rows 0-2)
        2. Filter out blank samples  
        3. Extract experiment info from sample labels
        4. Apply dilution corrections
        5. Select best lines for each element
        6. Convert from long to wide format
        7. Validate processed data
        
        Args:
            file_content: Raw bytes content of the CSV file
            
        Returns:
            Tuple of (processed_data_list, error_messages)
        """
        try:
            # Step 1: Parse CSV file (skip header rows)
            df = ICPService.parse_csv_file(file_content, manual_header_row)
            
            if df.empty:
                return [], ["Parsed CSV file is empty"]
            
            # Step 2: Process the DataFrame
            processed_data, processing_errors = ICPService.process_icp_dataframe(df)
            
            # Step 3: Validate the processed data
            validation_errors = ICPService.validate_icp_data(processed_data)
            
            # Combine all errors
            all_errors = processing_errors + validation_errors
            
            return processed_data, all_errors
            
        except Exception as e:
            return [], [f"Error in ICP file processing workflow: {str(e)}"]
