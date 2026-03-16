from __future__ import annotations

import io
from typing import Dict, List, Tuple, Optional, Any

import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import (
    Experiment,
    ExperimentNotes,
    ModificationsLog,
    ExperimentalConditions,
    ChemicalAdditive,
    Compound,
    ExperimentStatus,
    AmountUnit,
)
from backend.services.bulk_uploads.chemical_inventory import ChemicalInventoryService
from backend.services.bulk_uploads.experiment_status import ExperimentStatusService
from backend.services.experiment_validation import parse_experiment_id as parse_exp_id_validation, validate_experiment_id, extract_lineage_info
from database.lineage_utils import update_experiment_lineage


def find_parent_for_copy(db: Session, experiment_id: str) -> Optional[Experiment]:
    """
    Find the most appropriate parent experiment to copy conditions/additives from.
    
    Logic:
    - For Serum_MH_101-2: finds Serum_MH_101 (base)
    - For Serum_MH_101_Desorption: finds Serum_MH_101 (base)
    - For Serum_MH_101-3_Desorption: finds Serum_MH_101-3 (immediate parent with sequential)
    
    Args:
        db: Database session
        experiment_id: The experiment ID to find parent for
        
    Returns:
        Parent Experiment object if found, None otherwise
    """
    base_id, sequential_num, treatment_variant = extract_lineage_info(experiment_id)
    
    # No sequential or treatment? Not a derived experiment
    if sequential_num is None and treatment_variant is None:
        return None
    
    # Determine which parent to look for
    parent_id_to_find = None
    
    if sequential_num and treatment_variant:
        # Combined: Serum_MH_101-3_Desorption -> find Serum_MH_101-3
        parent_id_to_find = f"{base_id}-{sequential_num}"
    elif sequential_num:
        # Sequential only: Serum_MH_101-2 -> find Serum_MH_101
        parent_id_to_find = base_id
    elif treatment_variant:
        # Treatment only: Serum_MH_101_Desorption -> find Serum_MH_101
        parent_id_to_find = base_id
    
    if not parent_id_to_find:
        return None
    
    # Find parent using normalized matching (case-insensitive, ignore delimiters)
    parent_id_norm = ''.join(ch for ch in parent_id_to_find.lower() if ch not in ['-', '_', ' '])
    parent = db.query(Experiment).filter(
        func.lower(
            func.replace(
                func.replace(
                    func.replace(Experiment.experiment_id, '-', ''),
                    '_', ''
                ),
                ' ', ''
            )
        ) == parent_id_norm
    ).first()
    
    return parent


class NewExperimentsUploadService:
    @staticmethod
    def bulk_upsert_from_excel(db: Session, file_bytes: bytes) -> Tuple[int, int, int, List[str], List[str], List[str]]:
        """
        Create or update Experiments, ExperimentalConditions, and ChemicalAdditives from a
        multi-sheet Excel workbook.

        Sheets (case-insensitive names):
          - experiments: experiment_id*, old_experiment_id (optional, for renames), sample_id, date, status, initial_note, overwrite
            (researcher is optional and auto-populated from experiment_id if not provided)
            (old_experiment_id: when provided with overwrite=True, finds experiment by old ID and renames to new experiment_id)
          - conditions: experiment_id*, columns matching ExperimentalConditions fields
            (experiment_type is auto-populated from experiment_id)
          - additives: experiment_id*, compound*, amount*, unit*, order, method
          
        Experiment ID format: Supports two formats:
        - ExperimentType_ResearcherInitials_Index (3-part, e.g., Serum_MH_101)
        - ExperimentType_Index (2-part, e.g., HPHT_001)
        Both formats support:
        - Sequential: add -NUMBER (e.g., Serum_MH_101-2 or HPHT_001-2)
        - Treatment: add _TEXT (e.g., Serum_MH_101_Desorption or HPHT_001_Desorption)

        Auto-copy behavior (overwrite=False):
          - Sequential/treatment experiments automatically copy CONDITIONS from parent
          - Chemical additives are NEVER auto-copied - must be explicitly provided
          - User-provided values override copied condition values
          - Missing parent creates warning but still creates experiment

        Overwrite behavior per experiment row:
          - overwrite=False and experiment exists: skip with error
          - overwrite=True and experiment exists: update provided fields; if additives sheet has
            rows for that experiment, REPLACE all existing additives with the provided set.

        Returns (created_experiments, updated_experiments, skipped_rows, errors, warnings, info_messages)
        """
        created_exp = updated_exp = skipped = 0
        errors: List[str] = []
        warnings: List[str] = []
        info_messages: List[str] = []

        try:
            sheets: Dict[str, pd.DataFrame] = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None)
        except Exception as e:
            return 0, 0, 0, [f"Failed to read Excel: {e}"], [], []

        # Normalize sheet keys
        normalized: Dict[str, pd.DataFrame] = {str(k).strip().lower(): v for k, v in (sheets or {}).items()}

        # Compounds sheet is no longer supported in this uploader; compounds can be bulked via the separate Chemical Inventory upload.

        # Helper: map enum for ExperimentStatus (accept name or value, case-insensitive)
        def parse_status(val: Any) -> Optional[ExperimentStatus]:
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return None
            text = str(val).strip()
            for s in ExperimentStatus:
                if text.lower() == s.name.lower() or text.lower() == str(s.value).lower():
                    return s
            return None

        # Helper: parse boolean-ish overwrite flag
        def parse_bool(val: Any) -> bool:
            if isinstance(val, bool):
                return val
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return False
            return str(val).strip().lower() in {"1", "true", "yes", "y"}

        # Preload experiment map and compute next experiment_number for new experiments
        # Note: SQLite ignores FOR UPDATE; we mirror existing pattern from UI creation flow
        last = db.query(Experiment).order_by(Experiment.experiment_number.desc()).first()
        next_experiment_number = 1 if last is None else int(last.experiment_number or 0) + 1

        # Track overwrite preference per experiment_id
        overwrite_by_exp_id: Dict[str, bool] = {}
        
        # Track parent experiments for auto-copy (experiment_id -> parent Experiment object)
        parent_for_copy: Dict[str, Experiment] = {}
        
        # Track which experiments were successfully processed in experiments sheet
        processed_experiment_ids: set = set()
        failed_experiment_ids: set = set()
        renamed_experiment_ids: set = set()

        # === Process experiments sheet ===
        if 'experiments' in normalized:
            df_exp = normalized['experiments'].copy()
            # Strip any display asterisks and parenthetical hints from headers and normalize to lowercase
            # Example: "experiment_id* (TYPE_INITIALS_INDEX)" -> "experiment_id"
            def normalize_column(col_name: str) -> str:
                col_str = str(col_name).replace('*', '').strip()
                # Remove parenthetical hints (e.g., "(TYPE_INITIALS_INDEX)" or "(optional, for renames)")
                if '(' in col_str:
                    col_str = col_str.split('(')[0].strip()
                return col_str.lower()
            
            df_exp.columns = [normalize_column(c) for c in df_exp.columns]

            for idx, row in df_exp.iterrows():
                try:
                    exp_id = str(row.get('experiment_id') or '').strip()
                    if not exp_id:
                        skipped += 1
                        continue
                    
                    # Validate experiment ID and collect warnings
                    try:
                        validation_result = validate_experiment_id(exp_id)
                        if not isinstance(validation_result, tuple) or len(validation_result) != 2:
                            warnings.append(f"[experiments] Row {idx+2}: Unexpected validation result format for '{exp_id}'")
                            continue
                        is_valid, id_warnings = validation_result
                    except ValueError as ve:
                        warnings.append(f"[experiments] Row {idx+2}: Error unpacking validation result for '{exp_id}': {ve}")
                        continue
                    
                    if id_warnings:
                        for warning in id_warnings:
                            warnings.append(f"[experiments] Row {idx+2} ({exp_id}): {warning}")
                    
                    # Parse experiment_id to extract components (use validation function for dataclass)
                    current_step = "parsing experiment_id components"
                    parsed = parse_exp_id_validation(exp_id)

                    current_step = "parsing overwrite flag"
                    overwrite_flag = parse_bool(row.get('overwrite'))
                    overwrite_by_exp_id[exp_id] = overwrite_flag

                    # Check for old_experiment_id column (for renaming experiments)
                    old_experiment_id = None
                    if 'old_experiment_id' in df_exp.columns:
                        old_id_raw = row.get('old_experiment_id')
                        # Check for NaN first, then check if non-empty string
                        if not pd.isna(old_id_raw) and str(old_id_raw).strip() != '':
                            old_experiment_id = str(old_id_raw).strip()
                            
                    # Resolve existing experiment
                    current_step = "normalizing experiment_id and querying database"
                    experiment = None
                    
                    if old_experiment_id and overwrite_flag:
                        # Use old_experiment_id for matching when provided (for renames)
                        old_exp_id_norm = ''.join(ch for ch in old_experiment_id.lower() if ch not in ['-', '_', ' '])
                        
                        experiment = db.query(Experiment).filter(
                            func.lower(
                                func.replace(
                                    func.replace(
                                        func.replace(Experiment.experiment_id, '-', ''),
                                        '_', ''
                                    ),
                                    ' ', ''
                                )
                            ) == old_exp_id_norm
                        ).first()
                        
                        if experiment:
                            # Check if target experiment_id already exists (potential ordering issue)
                            target_exp_id_norm = ''.join(ch for ch in exp_id.lower() if ch not in ['-', '_', ' '])
                            existing_target = db.query(Experiment).filter(
                                func.lower(
                                    func.replace(
                                        func.replace(
                                            func.replace(Experiment.experiment_id, '-', ''),
                                            '_', ''
                                        ),
                                        ' ', ''
                                    )
                                ) == target_exp_id_norm
                            ).first()
                            
                            if existing_target and existing_target.id != experiment.id:
                                # Target ID exists and is a different experiment - chain rename conflict!
                                warnings.append(
                                    f"[experiments] Row {idx+2}: ⚠️ CHAIN RENAME CONFLICT: Cannot rename '{old_experiment_id}' "
                                    f"to '{exp_id}' because '{exp_id}' already exists as a separate experiment. "
                                    f"If you're renaming '{exp_id}' to something else in a later row, process that row FIRST. "
                                    f"Correct order: rename experiments AWAY from conflicting names before renaming INTO them."
                                )
                                failed_experiment_ids.add(target_exp_id_norm)
                                continue  # Skip this row
                            
                            info_messages.append(f"Rename: '{old_experiment_id}' -> '{exp_id}'")
                        else:
                            warnings.append(f"[experiments] Row {idx+2}: Old experiment_id='{old_experiment_id}' NOT FOUND")
                    else:
                        # Standard normalized matching (backward compatible)
                        exp_id_norm = ''.join(ch for ch in exp_id.lower() if ch not in ['-', '_', ' '])
                        experiment = db.query(Experiment).filter(
                            func.lower(
                                func.replace(
                                    func.replace(
                                        func.replace(Experiment.experiment_id, '-', ''),
                                        '_', ''
                                    ),
                                    ' ', ''
                                )
                            ) == exp_id_norm
                        ).first()
                    
                    # Calculate normalized ID for tracking (use new ID after potential rename)
                    exp_id_norm = ''.join(ch for ch in exp_id.lower() if ch not in ['-', '_', ' '])

                    # Parse fields
                    current_step = "parsing sample_id field"
                    sample_id = str(row.get('sample_id').strip()) if isinstance(row.get('sample_id'), str) and row.get('sample_id').strip() != '' else None
                    
                    current_step = "parsing researcher field"
                    # Auto-populate researcher from experiment_id if not provided (only for 3-part format)
                    researcher = str(row.get('researcher').strip()) if isinstance(row.get('researcher'), str) and row.get('researcher').strip() != '' else None
                    if not researcher and parsed.researcher_initials:
                        # Only set researcher from parsed initials if they exist (3-part format)
                        researcher = parsed.researcher_initials
                    
                    current_step = "parsing status field"
                    status_val = parse_status(row.get('status'))
                    
                    current_step = "parsing date field"
                    # date can be Excel serial, ISO, or empty
                    date_val: Optional[pd.Timestamp]
                    try:
                        date_raw = row.get('date')
                        if pd.isna(date_raw):
                            date_val = None
                        else:
                            date_val = pd.to_datetime(date_raw, errors='coerce')
                    except Exception:
                        date_val = None
                    
                    current_step = "parsing initial_note field"
                    initial_note = str(row.get('initial_note')).strip() if row.get('initial_note') is not None and str(row.get('initial_note')).strip() != '' else None

                    current_step = "checking experiment existence and overwrite rules"
                    if experiment is None and overwrite_flag:
                        # Overwrite requested but experiment does not exist
                        if old_experiment_id:
                            warnings.append(f"[experiments] Row {idx+2}: overwrite=True but old_experiment_id '{old_experiment_id}' not found")
                            old_exp_id_norm = ''.join(ch for ch in old_experiment_id.lower() if ch not in ['-', '_', ' '])
                            failed_experiment_ids.add(old_exp_id_norm)
                        else:
                            warnings.append(f"[experiments] Row {idx+2}: overwrite=True but experiment_id '{exp_id}' does not exist")
                            failed_experiment_ids.add(exp_id_norm)  # Use normalized ID for tracking
                        continue

                    if experiment is not None and not overwrite_flag:
                        warnings.append(f"[experiments] Row {idx+2}: experiment_id '{exp_id}' already exists; set overwrite=True to update")
                        failed_experiment_ids.add(exp_id_norm)  # Use normalized ID for tracking
                        continue

                    if experiment is None:
                        current_step = "finding parent experiment for copying"
                        # Check if this is a sequential/treatment experiment that should copy from parent
                        parent = find_parent_for_copy(db, exp_id)
                        
                        # Auto-populate sample_id from parent if not provided (per requirement 6a)
                        if parent and not sample_id:
                            sample_id = parent.sample_id
                        
                        # Create new experiment - prepare each field separately for debugging
                        current_step = "creating new experiment object - preparing fields"
                        exp_number = next_experiment_number
                        exp_id_field = exp_id
                        sample_id_field = sample_id
                        researcher_field = researcher
                        status_field = status_val if status_val is not None else ExperimentStatus.ONGOING
                        
                        current_step = "creating new experiment object - converting date"
                        date_field = None if date_val is None else date_val.to_pydatetime()
                        
                        current_step = "creating new experiment object - calling Experiment()"
                        experiment = Experiment(
                            experiment_number=exp_number,
                            experiment_id=exp_id_field,
                            sample_id=sample_id_field,
                            researcher=researcher_field,
                            status=status_field,
                            date=date_field,
                        )
                        
                        current_step = "creating new experiment object - db.add()"
                        db.add(experiment)
                        
                        current_step = "creating new experiment object - db.flush()"
                        db.flush()
                        next_experiment_number += 1
                        created_exp += 1
                        processed_experiment_ids.add(exp_id_norm)  # Use normalized ID for tracking
                        
                        # Track parent for later condition/additive copying
                        if parent:
                            parent_for_copy[exp_id] = parent
                            info_messages.append(f"Experiment {exp_id}: Will copy from parent {parent.experiment_id}")
                        elif parsed.sequential_number or parsed.treatment_variant:
                            # Sequential/treatment but no parent found
                            warnings.append(
                                f"Experiment {exp_id}: Sequential/treatment experiment created without parent "
                                f"(expected parent not found). Suggest providing complete conditions in upload."
                            )
                    else:
                        current_step = "updating existing experiment"
                        # Update provided fields only
                        # IMPORTANT: Update experiment_id FIRST if it's a rename (old_experiment_id provided)
                        
                        if old_experiment_id and experiment.experiment_id != exp_id:
                            try:
                                experiment.experiment_id = exp_id
                                info_messages.append(f"Renamed experiment: '{old_experiment_id}' -> '{exp_id}'")
                                renamed_experiment_ids.add(exp_id)
                                
                                # Recalculate lineage fields based on new experiment_id
                                update_experiment_lineage(db, experiment)
                                
                                # Update denormalized experiment_id in related ExperimentNotes records
                                notes_to_update = db.query(ExperimentNotes).filter(
                                    ExperimentNotes.experiment_fk == experiment.id
                                ).all()
                                for note in notes_to_update:
                                    note.experiment_id = exp_id
                                
                                # Update denormalized experiment_id in related ModificationsLog records
                                mods_to_update = db.query(ModificationsLog).filter(
                                    ModificationsLog.experiment_fk == experiment.id
                                ).all()
                                for mod in mods_to_update:
                                    mod.experiment_id = exp_id
                                
                                # Flush rename changes so subsequent queries see the new ID
                                db.flush()
                            except Exception as rename_error:
                                # Check if this is a UNIQUE constraint error (chain rename ordering issue)
                                error_str = str(rename_error).lower()
                                if 'unique constraint' in error_str and 'experiment_id' in error_str:
                                    # This is likely a chain rename ordering problem
                                    warnings.append(
                                        f"[experiments] Row {idx+2}: Cannot rename '{old_experiment_id}' to '{exp_id}' - "
                                        f"experiment_id '{exp_id}' already exists. "
                                        f"⚠️ CHAIN RENAME ORDERING ISSUE: If you're renaming multiple experiments where "
                                        f"new IDs overlap with old IDs, process rows so experiments rename AWAY from "
                                        f"conflicting names before renaming INTO them. "
                                        f"See docs/EXPERIMENT_RENAME_GUIDE.md for details."
                                    )
                                    failed_experiment_ids.add(exp_id_norm)
                                    # Re-raise to trigger transaction rollback
                                    raise
                                else:
                                    # Some other error - re-raise with context
                                    raise
                        
                        # Clear existing notes when overwrite=True (full data replacement)
                        current_step = "clearing existing notes for overwrite"
                        db.query(ExperimentNotes).filter(
                            ExperimentNotes.experiment_fk == experiment.id
                        ).delete(synchronize_session=False)
                        
                        if sample_id is not None:
                            experiment.sample_id = sample_id
                        if researcher is not None:
                            experiment.researcher = researcher
                        if status_val is not None:
                            experiment.status = status_val
                        if date_val is not None:
                            experiment.date = date_val.to_pydatetime()
                        updated_exp += 1
                        processed_experiment_ids.add(exp_id_norm)  # Use normalized ID for tracking (new ID after rename)

                    current_step = "adding initial note"
                    # Handle initial note: create new ExperimentNotes entry
                    # NOTE: When overwrite=True, all existing notes are cleared first (see above)
                    # NOTE: initial_note is NEVER copied from parent - only user-provided notes are created
                    # This ensures user's description always takes precedence (per requirement)
                    if initial_note:
                        note = ExperimentNotes(
                            experiment_fk=experiment.id,
                            experiment_id=experiment.experiment_id,
                            note_text=initial_note,
                        )
                        db.add(note)

                except Exception as e:
                    # Add more detailed error info including which step failed
                    error_detail = f"{type(e).__name__}: {str(e)}"
                    step_info = f" (during: {current_step})" if 'current_step' in locals() else ""
                    warnings.append(f"[experiments] Row {idx+2}: {error_detail}{step_info}")
                    # Try to track which experiment_id failed, if we got that far
                    try:
                        if 'exp_id_norm' in locals() and exp_id_norm:
                            failed_experiment_ids.add(exp_id_norm)  # Use normalized ID for tracking
                        elif 'exp_id' in locals() and exp_id:
                            warnings.append(f"[experiments] Row {idx+2}: Failed processing experiment_id '{exp_id}'")
                    except:
                        pass
        else:
            errors.append("Missing required 'experiments' sheet")

        # Expire session cache to ensure conditions/additives sheets see renamed experiments
        db.expire_all()

        # === Process conditions sheet (optional but recommended) ===
        if 'conditions' in normalized:
            df_cond = normalized['conditions'].copy()
            # Strip any display asterisks and parenthetical hints from headers and normalize
            def normalize_column(col_name: str) -> str:
                col_str = str(col_name).replace('*', '').strip()
                if '(' in col_str:
                    col_str = col_str.split('(')[0].strip()
                return col_str.lower()
            
            df_cond.columns = [normalize_column(c) for c in df_cond.columns]
            if 'experiment_id' not in df_cond.columns:
                errors.append("[conditions] Missing required column 'experiment_id'")
            else:
                # Build set of updatable attribute names from the model (avoid PK/FKs and internals)
                reserved = {'id', 'experiment_id', 'experiment_fk', 'created_at', 'updated_at'}
                blacklist = {
                    'catalyst', 'catalyst_mass',
                    'buffer_system', 'buffer_concentration',
                    'surfactant_type', 'surfactant_concentration',
                    'catalyst_percentage', 'catalyst_ppm',
                    'water_to_rock_ratio', 'nitrate_concentration', 'dissolved_oxygen',
                    'ammonium_chloride_concentration'   # Calculated field
                }
                updatable_attrs = {
                    col.name for col in ExperimentalConditions.__table__.columns
                    if col.name not in reserved and col.name not in blacklist
                }
                # Map lowercased column names to actual model column names
                # (Excel headers are normalized to lowercase, but model columns may have mixed case like water_volume_mL)
                lower_to_actual = {name.lower(): name for name in updatable_attrs}
                for idx, row in df_cond.iterrows():
                    try:
                        exp_id = str(row.get('experiment_id') or '').strip()
                        if not exp_id:
                            skipped += 1
                            continue
                        exp_id_norm = ''.join(ch for ch in exp_id.lower() if ch not in ['-', '_', ' '])
                        experiment = db.query(Experiment).filter(
                            func.lower(
                                func.replace(
                                    func.replace(
                                        func.replace(Experiment.experiment_id, '-', ''),
                                        '_', ''
                                    ),
                                    ' ', ''
                                )
                            ) == exp_id_norm
                        ).first()
                        if not experiment:
                            # Provide helpful diagnostic about why experiment wasn't found (use normalized ID for tracking checks)
                            if exp_id_norm in failed_experiment_ids:
                                warnings.append(f"[conditions] Row {idx+2}: experiment_id '{exp_id}' not found - experiment creation/update failed in experiments sheet (check errors above)")
                            elif exp_id_norm in processed_experiment_ids:
                                warnings.append(f"[conditions] Row {idx+2}: experiment_id '{exp_id}' was processed but not found in database - possible transaction issue or session cache problem")
                            else:
                                warnings.append(
                                    f"[conditions] Row {idx+2}: experiment_id '{exp_id}' not found. "
                                    f"If you renamed this experiment in the experiments sheet, ensure you're using the NEW experiment_id here "
                                    f"(not the old_experiment_id). The conditions/additives sheets should always use the NEW experiment_id."
                                )
                            continue
                        # Resolve or create conditions
                        conditions = (
                            db.query(ExperimentalConditions)
                            .filter(ExperimentalConditions.experiment_fk == experiment.id)
                            .first()
                        )
                        if not conditions:
                            conditions = ExperimentalConditions(
                                experiment_id=experiment.experiment_id,
                                experiment_fk=experiment.id,
                            )
                            db.add(conditions)
                            db.flush()

                        # Auto-copy from parent if experiment is flagged for copying
                        parent = parent_for_copy.get(exp_id)
                        if parent and parent.conditions:
                            # Copy all condition fields from parent first (requirement 2a: merge)
                            for attr in updatable_attrs:
                                parent_value = getattr(parent.conditions, attr, None)
                                if parent_value is not None:
                                    setattr(conditions, attr, parent_value)
                            info_messages.append(f"Experiment {exp_id}: Copied conditions from parent {parent.experiment_id}")

                        # Then override with user-provided values from Excel row (requirement 2a)
                        updated_fields = []
                        for col_name, val in row.items():
                            actual_attr = lower_to_actual.get(col_name)
                            if actual_attr:
                                # Convert empty strings to None
                                if isinstance(val, str) and val.strip() == '':
                                    setattr(conditions, actual_attr, None)
                                elif not pd.isna(val):  # Only override if value is not NaN/blank
                                    try:
                                        setattr(conditions, actual_attr, val)
                                        updated_fields.append(f"{actual_attr}={val}")
                                    except Exception as set_error:
                                        warnings.append(f"[conditions] Row {idx+2}: Failed to set {actual_attr}={val}: {set_error}")
                        # Persist updated fields so later phases see the changed values
                        if updated_fields:
                            db.flush()
                        
                        # Debug logging for renamed experiments
                        if exp_id in renamed_experiment_ids:
                            if updated_fields:
                                info_messages.append(f"[conditions] Updated fields for renamed experiment '{exp_id}': {', '.join(updated_fields[:5])}")
                            else:
                                warnings.append(f"[conditions] Row {idx+2}: No fields updated for '{exp_id}' - check column names match model")
                        
                        # Auto-populate experiment_type from experiment_id if not already set
                        if not conditions.experiment_type or conditions.experiment_type == '':
                            parsed = parse_exp_id_validation(exp_id)
                            if parsed.experiment_type:
                                conditions.experiment_type = parsed.experiment_type.value
                        
                        # Recalculate derived fields
                        conditions.calculate_derived_conditions()
                        
                        # Manage reactor occupancy: if experiment is ONGOING and has reactor_number, 
                        # mark other ONGOING experiments in same reactor as COMPLETED
                        if conditions.reactor_number and experiment.status == ExperimentStatus.ONGOING:
                            marked, reactor_warnings = ExperimentStatusService.manage_reactor_occupancy(
                                db, experiment, conditions.reactor_number, commit=False
                            )
                            warnings.extend(reactor_warnings)
                            if marked > 0:
                                info_messages.append(
                                    f"Reactor {conditions.reactor_number}: Auto-completed {marked} "
                                    f"conflicting experiment(s) for '{exp_id}'"
                                )
                    except Exception as e:
                        warnings.append(f"[conditions] Row {idx+2}: {e}")
        
        # === Auto-copy conditions for experiments with parents but no conditions sheet entry ===
        # (Requirement: edge case 8 - no conditions sheet means copy parent's conditions entirely)
        for exp_id, parent in parent_for_copy.items():
            if not parent or not parent.conditions:
                continue
            
            # Check if this experiment already has conditions (either from sheet or created earlier)
            exp_id_norm = ''.join(ch for ch in exp_id.lower() if ch not in ['-', '_', ' '])
            experiment = db.query(Experiment).filter(
                func.lower(
                    func.replace(
                        func.replace(
                            func.replace(Experiment.experiment_id, '-', ''),
                            '_', ''
                        ),
                        ' ', ''
                    )
                ) == exp_id_norm
            ).first()
            
            if not experiment:
                continue
            
            conditions = db.query(ExperimentalConditions).filter(
                ExperimentalConditions.experiment_fk == experiment.id
            ).first()
            
            # If conditions don't exist yet (no row in conditions sheet), create and copy
            if not conditions:
                conditions = ExperimentalConditions(
                    experiment_id=experiment.experiment_id,
                    experiment_fk=experiment.id,
                )
                db.add(conditions)
                db.flush()
                
                # Copy all fields from parent
                reserved = {'id', 'experiment_id', 'experiment_fk', 'created_at', 'updated_at'}
                blacklist = {
                    'catalyst', 'catalyst_mass',
                    'buffer_system', 'buffer_concentration',
                    'surfactant_type', 'surfactant_concentration',
                    'catalyst_percentage', 'catalyst_ppm',
                    'water_to_rock_ratio', 'nitrate_concentration', 'dissolved_oxygen',
                    'ammonium_chloride_concentration'
                }
                updatable_attrs = {
                    col.name for col in ExperimentalConditions.__table__.columns
                    if col.name not in reserved and col.name not in blacklist
                }
                
                for attr in updatable_attrs:
                    parent_value = getattr(parent.conditions, attr, None)
                    if parent_value is not None:
                        setattr(conditions, attr, parent_value)
                
                info_messages.append(f"Experiment {exp_id}: Copied all conditions from parent {parent.experiment_id} (no conditions sheet row provided)")
                conditions.calculate_derived_conditions()
                
                # Manage reactor occupancy for auto-copied conditions
                if conditions.reactor_number and experiment.status == ExperimentStatus.ONGOING:
                    marked, reactor_warnings = ExperimentStatusService.manage_reactor_occupancy(
                        db, experiment, conditions.reactor_number, commit=False
                    )
                    warnings.extend(reactor_warnings)
                    if marked > 0:
                        info_messages.append(
                            f"Reactor {conditions.reactor_number}: Auto-completed {marked} "
                            f"conflicting experiment(s) for '{exp_id}'"
                        )

        # === Process additives sheet ===
        if 'additives' in normalized:
            df_add = normalized['additives'].copy()
            # Strip any display asterisks and parenthetical hints from headers and normalize
            def normalize_column(col_name: str) -> str:
                col_str = str(col_name).replace('*', '').strip()
                if '(' in col_str:
                    col_str = col_str.split('(')[0].strip()
                return col_str.lower()
            
            df_add.columns = [normalize_column(c) for c in df_add.columns]
            required_cols = {'experiment_id', 'compound', 'amount', 'unit'}
            if not required_cols.issubset(set(df_add.columns)):
                missing = ', '.join(sorted(required_cols - set(df_add.columns)))
                warnings.append(f"[additives] Missing required column(s): {missing}")
            else:
                # Preload compounds into map; refresh as we auto-create
                all_compounds = db.query(Compound).all()
                name_to_compound: Dict[str, Compound] = {c.name.lower(): c for c in all_compounds}

                # Group rows by experiment_id for replace semantics
                grouped = df_add.groupby(df_add['experiment_id'].map(lambda x: str(x).strip()))
                for exp_id, group in grouped:
                    if not exp_id:
                        continue
                    exp_id_norm = ''.join(ch for ch in exp_id.lower() if ch not in ['-', '_', ' '])
                    experiment = db.query(Experiment).filter(
                        func.lower(
                            func.replace(
                                func.replace(
                                    func.replace(Experiment.experiment_id, '-', ''),
                                    '_', ''
                                ),
                                ' ', ''
                            )
                        ) == exp_id_norm
                    ).first()
                    if not experiment:
                        # Provide helpful diagnostic about why experiment wasn't found (use normalized ID for tracking checks)
                        if exp_id_norm in failed_experiment_ids:
                            warnings.append(f"[additives] experiment_id '{exp_id}' not found - experiment creation/update failed in experiments sheet (check errors above)")
                        elif exp_id_norm in processed_experiment_ids:
                            warnings.append(f"[additives] experiment_id '{exp_id}' was processed but not found in database - possible transaction issue or session cache problem")
                        else:
                            warnings.append(
                                f"[additives] experiment_id '{exp_id}' not found. "
                                f"If you renamed this experiment in the experiments sheet, ensure you're using the NEW experiment_id here "
                                f"(not the old_experiment_id). The conditions/additives sheets should always use the NEW experiment_id."
                            )
                        continue

                    # Resolve or create conditions row
                    conditions = (
                        db.query(ExperimentalConditions)
                        .filter(ExperimentalConditions.experiment_fk == experiment.id)
                        .first()
                    )
                    if not conditions:
                        conditions = ExperimentalConditions(
                            experiment_id=experiment.experiment_id,
                            experiment_fk=experiment.id,
                        )
                        db.add(conditions)
                        db.flush()

                    replace_all = bool(overwrite_by_exp_id.get(exp_id, False))
                    if replace_all:
                        # Delete all existing additives for this experiment's conditions
                        db.query(ChemicalAdditive).filter(
                            ChemicalAdditive.experiment_id == conditions.id
                        ).delete(synchronize_session=False)
                    
                    # NOTE: Chemical additives are NEVER auto-copied from parent
                    # Users must explicitly provide all additives for each experiment
                    
                    for ridx, row in group.iterrows():
                        try:
                            comp_name = str(row.get('compound') or '').strip()
                            if not comp_name:
                                skipped += 1
                                continue

                            # amount
                            try:
                                amount_val = float(row.get('amount'))
                            except Exception:
                                warnings.append(f"[additives] Row {int(ridx)+2}: invalid amount '{row.get('amount')}'")
                                continue
                            if amount_val <= 0:
                                warnings.append(f"[additives] Row {int(ridx)+2}: amount must be > 0")
                                continue

                            # unit
                            unit_text = str(row.get('unit') or '').strip()
                            unit_enum: Optional[AmountUnit] = None
                            for u in AmountUnit:
                                if unit_text == u.value:
                                    unit_enum = u
                                    break
                            if unit_enum is None:
                                warnings.append(f"[additives] Row {int(ridx)+2}: invalid unit '{unit_text}'")
                                continue

                            # Resolve or auto-create compound by name
                            comp = name_to_compound.get(comp_name.lower())
                            if not comp:
                                comp = Compound(name=comp_name)
                                db.add(comp)
                                db.flush()
                                name_to_compound[comp_name.lower()] = comp

                            # order and method
                            order_val = row.get('order') if 'order' in df_add.columns else None
                            try:
                                order_int = int(order_val) if order_val is not None and str(order_val).strip() != '' else None
                            except Exception:
                                order_int = None
                            method_text = str(row.get('method')).strip() if 'method' in df_add.columns and row.get('method') is not None and str(row.get('method')).strip() != '' else None

                            if replace_all:
                                # Always insert fresh records
                                new_add = ChemicalAdditive(
                                    experiment_id=conditions.id,
                                    compound_id=comp.id,
                                    amount=amount_val,
                                    unit=unit_enum,
                                    addition_order=order_int,
                                    addition_method=method_text,
                                )
                                # Derived fields auto via event listeners; call explicitly for safety
                                new_add.calculate_derived_values()
                                db.add(new_add)
                            else:
                                # Upsert per-compound
                                existing_add = db.query(ChemicalAdditive).filter(
                                    ChemicalAdditive.experiment_id == conditions.id,
                                    ChemicalAdditive.compound_id == comp.id,
                                ).first()
                                if existing_add:
                                    # Update existing (could be from parent copy or previous upload)
                                    existing_add.amount = amount_val
                                    existing_add.unit = unit_enum
                                    existing_add.addition_order = order_int
                                    existing_add.addition_method = method_text
                                    existing_add.calculate_derived_values()
                                else:
                                    # New additive from user sheet
                                    new_add = ChemicalAdditive(
                                        experiment_id=conditions.id,
                                        compound_id=comp.id,
                                        amount=amount_val,
                                        unit=unit_enum,
                                        addition_order=order_int,
                                        addition_method=method_text,
                                    )
                                    new_add.calculate_derived_values()
                                    db.add(new_add)
                        except Exception as e:
                            warnings.append(f"[additives] Row {int(ridx)+2}: {e}")

        return created_exp, updated_exp, skipped, errors, warnings, info_messages


