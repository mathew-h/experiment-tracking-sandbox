from __future__ import annotations

import io
from dataclasses import dataclass, field
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
from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH
from database.reactor_slot import derive_reactor_slot
from backend.services.bulk_uploads.chemical_inventory import ChemicalInventoryService
from backend.services.bulk_uploads.experiment_status import ExperimentStatusService
from backend.services.experiment_validation import parse_experiment_id as parse_exp_id_validation, validate_experiment_id, extract_lineage_info
from backend.services.calculations.registry import recalculate
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
    base_id, sequential_num, treatment_variant, _replicate_label = extract_lineage_info(experiment_id)
    
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


@dataclass
class PlanCreate:
    """A row that will create a brand-new Experiment (issue #100 item 2)."""
    row: int
    experiment_id: str
    parent_id: Optional[str] = None
    copied_from: Optional[str] = None


@dataclass
class PlanRename:
    """A row that renames an existing Experiment via old_experiment_id + overwrite=TRUE."""
    row: int
    from_id: str
    to_id: str


@dataclass
class FieldChange:
    field: str
    old: Any
    new: Any


@dataclass
class PlanOverwrite:
    """An existing Experiment updated in place (not a rename). One entry per
    experiment_id, merging field changes discovered across the experiments and
    conditions sheets — the same experiment can be touched by both."""
    row: int
    experiment_id: str
    fields_changed: List[FieldChange] = field(default_factory=list)


@dataclass
class PlanSkip:
    row: int
    experiment_id: Optional[str]
    reason: str


@dataclass
class PlanConflict:
    row: int
    kind: str
    detail: str


@dataclass
class UploadPlan:
    """Structured create/rename/overwrite/skip/conflict summary for a New Experiments
    upload (issue #100 item 2). Only bulk_upsert_from_excel_ex populates this —
    bulk_upsert_from_excel keeps its original 6-tuple return untouched so none of
    its existing callers need to change."""
    creates: List[PlanCreate] = field(default_factory=list)
    renames: List[PlanRename] = field(default_factory=list)
    overwrites: List[PlanOverwrite] = field(default_factory=list)
    skips: List[PlanSkip] = field(default_factory=list)
    conflicts: List[PlanConflict] = field(default_factory=list)

    @property
    def counts(self) -> Dict[str, int]:
        return {
            "creates": len(self.creates),
            "renames": len(self.renames),
            "overwrites": len(self.overwrites),
            "skips": len(self.skips),
            "conflicts": len(self.conflicts),
        }


class NewExperimentsUploadService:
    @staticmethod
    def bulk_upsert_from_excel(db: Session, file_bytes: bytes) -> Tuple[int, int, int, List[str], List[str], List[str]]:
        """Create or update Experiments/ExperimentalConditions/ChemicalAdditives from a
        multi-sheet Excel workbook. See _bulk_upsert_from_excel_impl for full behavior.

        Kept as a thin wrapper with its original 6-value return so none of its many
        existing callers need to change (issue #100 item 2). Use bulk_upsert_from_excel_ex
        for the same behavior plus a structured UploadPlan.
        """
        created, updated, skipped, errors, warnings, info, _plan = (
            NewExperimentsUploadService._bulk_upsert_from_excel_impl(db, file_bytes)
        )
        return created, updated, skipped, errors, warnings, info

    @staticmethod
    def bulk_upsert_from_excel_ex(
        db: Session, file_bytes: bytes
    ) -> Tuple[int, int, int, List[str], List[str], List[str], "UploadPlan"]:
        """Same as bulk_upsert_from_excel, plus a structured UploadPlan (issue #100 item 2)."""
        return NewExperimentsUploadService._bulk_upsert_from_excel_impl(db, file_bytes)

    @staticmethod
    def _bulk_upsert_from_excel_impl(
        db: Session, file_bytes: bytes
    ) -> Tuple[int, int, int, List[str], List[str], List[str], "UploadPlan"]:
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
          - old_experiment_id provided but overwrite is not TRUE: rejected as a conflict and
            skipped (never falls through to create a duplicate under the new experiment_id).

        Returns (created_experiments, updated_experiments, skipped_rows, errors, warnings,
        info_messages, plan) — plan is a structured UploadPlan (issue #100 item 2).
        """
        created_exp = updated_exp = skipped = 0
        errors: List[str] = []
        warnings: List[str] = []
        info_messages: List[str] = []
        plan = UploadPlan()
        # Keyed by (current) experiment_id — merges field changes discovered across the
        # experiments sheet and the conditions sheet into one PlanOverwrite per experiment.
        overwrite_plan_by_exp_id: Dict[str, PlanOverwrite] = {}

        try:
            sheets: Dict[str, pd.DataFrame] = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None)
        except Exception as e:
            return 0, 0, 0, [f"Failed to read Excel: {e}"], [], [], UploadPlan()

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
                # Per-row savepoint isolation (issue #86, Defect B): a failed flush
                # anywhere in this row's processing is confined to its own SAVEPOINT
                # and rolled back, leaving the session usable for the remaining rows.
                # Without this, one bad row poisoned the whole batch with cascading
                # PendingRollbackError and buried the real cause. row_ok stays False
                # for any early `continue` (all of which are pre-write skips) and for
                # any exception, so the finally rolls those back; it is set True only
                # when the row's body runs to completion.
                savepoint = db.begin_nested()
                row_ok = False
                try:
                    exp_id = str(row.get('experiment_id') or '').strip()
                    if not exp_id:
                        skipped += 1
                        plan.skips.append(PlanSkip(row=idx + 2, experiment_id=None, reason="empty experiment_id"))
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
                                chain_conflict_detail = (
                                    f"Cannot rename '{old_experiment_id}' to '{exp_id}' because '{exp_id}' already "
                                    f"exists as a separate experiment. If you're renaming '{exp_id}' to something "
                                    f"else in a later row, process that row FIRST. Correct order: rename experiments "
                                    f"AWAY from conflicting names before renaming INTO them."
                                )
                                warnings.append(
                                    f"[experiments] Row {idx+2}: ⚠️ CHAIN RENAME CONFLICT: {chain_conflict_detail}"
                                )
                                plan.conflicts.append(PlanConflict(
                                    row=idx + 2, kind="chain_rename_conflict", detail=chain_conflict_detail,
                                ))
                                failed_experiment_ids.add(target_exp_id_norm)
                                continue  # Skip this row
                            
                            info_messages.append(f"Rename: '{old_experiment_id}' -> '{exp_id}'")
                        else:
                            warnings.append(f"[experiments] Row {idx+2}: Old experiment_id='{old_experiment_id}' NOT FOUND")
                    elif old_experiment_id and not overwrite_flag:
                        # old_experiment_id supplied but overwrite is falsy: this used to fall
                        # through to standard matching on the NEW id below, which normally finds
                        # nothing and silently CREATES a duplicate instead of renaming
                        # 'old_experiment_id' (issue #100 — the 2026-07-28 SERUM_Catalyst incident:
                        # two intended-rename workbooks with overwrite blank produced 80 creates
                        # alongside the 80 originals). Block the row instead of guessing.
                        rename_conflict_detail = (
                            f"old_experiment_id='{old_experiment_id}' provided but overwrite is not TRUE. "
                            f"This row would CREATE '{exp_id}' rather than rename '{old_experiment_id}'. "
                            f"Set overwrite=TRUE to rename."
                        )
                        warnings.append(f"[experiments] Row {idx+2}: {rename_conflict_detail}")
                        plan.conflicts.append(PlanConflict(
                            row=idx + 2, kind="rename_without_overwrite", detail=rename_conflict_detail,
                        ))
                        exp_id_norm = ''.join(ch for ch in exp_id.lower() if ch not in ['-', '_', ' '])
                        failed_experiment_ids.add(exp_id_norm)
                        continue
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
                            plan.conflicts.append(PlanConflict(
                                row=idx + 2, kind="overwrite_old_id_not_found",
                                detail=f"overwrite=True but old_experiment_id '{old_experiment_id}' not found",
                            ))
                            old_exp_id_norm = ''.join(ch for ch in old_experiment_id.lower() if ch not in ['-', '_', ' '])
                            failed_experiment_ids.add(old_exp_id_norm)
                        else:
                            warnings.append(f"[experiments] Row {idx+2}: overwrite=True but experiment_id '{exp_id}' does not exist")
                            plan.conflicts.append(PlanConflict(
                                row=idx + 2, kind="overwrite_nonexistent",
                                detail=f"overwrite=True but experiment_id '{exp_id}' does not exist",
                            ))
                            failed_experiment_ids.add(exp_id_norm)  # Use normalized ID for tracking
                        continue

                    if experiment is not None and not overwrite_flag:
                        warnings.append(f"[experiments] Row {idx+2}: experiment_id '{exp_id}' already exists; set overwrite=True to update")
                        plan.conflicts.append(PlanConflict(
                            row=idx + 2, kind="already_exists",
                            detail=f"experiment_id '{exp_id}' already exists; set overwrite=True to update",
                        ))
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
                        plan.creates.append(PlanCreate(
                            row=idx + 2, experiment_id=exp_id,
                            parent_id=parent.experiment_id if parent else None,
                            copied_from=parent.experiment_id if parent else None,
                        ))
                    else:
                        current_step = "updating existing experiment"
                        # Update provided fields only
                        # IMPORTANT: Update experiment_id FIRST if it's a rename (old_experiment_id provided)
                        rename_occurred = False

                        if old_experiment_id and experiment.experiment_id != exp_id:
                            try:
                                experiment.experiment_id = exp_id
                                # Persist the rename BEFORE recomputing lineage (issue #86, Defect A1).
                                # autoflush is off on the production session, so update_experiment_lineage's
                                # group-parent SELECT would otherwise run against the row's OLD id and could
                                # match the row against itself (self-parent -> CircularDependencyError). Flush
                                # first so the lookup resolves against the NEW id. UNIQUE-constraint violations
                                # now surface here and are still caught by the handler below.
                                db.flush()
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
                                rename_occurred = True
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
                        
                        if rename_occurred:
                            plan.renames.append(PlanRename(row=idx + 2, from_id=old_experiment_id, to_id=exp_id))
                        else:
                            # Diff old vs new BEFORE the assignments below overwrite them — this is
                            # the fields_changed the issue calls "the highest-value part" (issue #100
                            # item 2). Renames are reported separately (from_id/to_id only, no diff).
                            _fields_changed: List[FieldChange] = []
                            if sample_id is not None and sample_id != experiment.sample_id:
                                _fields_changed.append(
                                    FieldChange(field="sample_id", old=experiment.sample_id, new=sample_id)
                                )
                            if researcher is not None and researcher != experiment.researcher:
                                _fields_changed.append(
                                    FieldChange(field="researcher", old=experiment.researcher, new=researcher)
                                )
                            if status_val is not None and status_val != experiment.status:
                                _fields_changed.append(FieldChange(
                                    field="status",
                                    old=experiment.status.value if experiment.status else None,
                                    new=status_val.value,
                                ))
                            _new_date = None if date_val is None else date_val.to_pydatetime()
                            if date_val is not None and _new_date != experiment.date:
                                _fields_changed.append(FieldChange(
                                    field="date",
                                    old=experiment.date.isoformat() if experiment.date else None,
                                    new=_new_date.isoformat() if _new_date else None,
                                ))
                            if _fields_changed:
                                overwrite_plan_by_exp_id.setdefault(
                                    exp_id, PlanOverwrite(row=idx + 2, experiment_id=exp_id)
                                ).fields_changed.extend(_fields_changed)

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

                    # Row body completed without exception or early `continue`.
                    row_ok = True

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
                        # A row discarded by savepoint rollback must not leave its new
                        # ID behind in the renamed-tracking set (issue #86, Defect B).
                        if 'exp_id' in locals() and exp_id:
                            renamed_experiment_ids.discard(exp_id)
                    except:
                        pass
                finally:
                    # Commit the row's savepoint on success; otherwise roll it back so
                    # the session is usable for the next row. rollback() is also the
                    # required recovery after a failed flush inside the savepoint, and
                    # is a harmless no-op for the pre-write `continue` skip paths.
                    if row_ok:
                        savepoint.commit()
                    else:
                        savepoint.rollback()
        else:
            errors.append("Missing required 'experiments' sheet")

        # Flush pending experiments-sheet field updates (status/sample_id/researcher/date,
        # renames) before expiring the session, so expire_all() reloads the NEW values
        # instead of discarding them. See issue #68.
        db.flush()
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
                        # A brand-new conditions row has no prior value to diff against — only a
                        # pre-existing row's changes count as an overwrite (issue #100 item 2).
                        conditions_was_new = conditions is None
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
                        _cond_fields_changed: List[FieldChange] = []
                        for col_name, val in row.items():
                            actual_attr = lower_to_actual.get(col_name)
                            if actual_attr:
                                _old_val = getattr(conditions, actual_attr, None)
                                # Convert empty strings to None
                                if isinstance(val, str) and val.strip() == '':
                                    setattr(conditions, actual_attr, None)
                                    if not conditions_was_new and _old_val is not None:
                                        _cond_fields_changed.append(
                                            FieldChange(field=actual_attr, old=_old_val, new=None)
                                        )
                                elif not pd.isna(val):  # Only override if value is not NaN/blank
                                    try:
                                        setattr(conditions, actual_attr, val)
                                        updated_fields.append(f"{actual_attr}={val}")
                                        if not conditions_was_new and _old_val != val:
                                            _cond_fields_changed.append(
                                                FieldChange(field=actual_attr, old=_old_val, new=val)
                                            )
                                    except Exception as set_error:
                                        warnings.append(f"[conditions] Row {idx+2}: Failed to set {actual_attr}={val}: {set_error}")
                        if _cond_fields_changed:
                            overwrite_plan_by_exp_id.setdefault(
                                exp_id, PlanOverwrite(row=idx + 2, experiment_id=exp_id)
                            ).fields_changed.extend(_cond_fields_changed)
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
                        
                        # Manage reactor occupancy: only one ONGOING experiment per
                        # physical slot. Keyed on the derived reactor_slot, which is
                        # None for a non-occupancy type (Serum / Autoclave / Other)
                        # and for reactor_number <= 0 — so this path can no longer
                        # complete an HPHT because a Serum row carried a stray
                        # reactor number, and `is not None` no longer skips rows
                        # whose reactor number is 0 (issue #97, Defect 3).
                        #
                        # `newer_than` is still deliberately NOT passed, so the
                        # start-date guard stays inactive and demotion here remains
                        # unconditional. Issue #97 §3 asks for it, but its stated
                        # rationale is "let the trigger be the backstop" — and the
                        # one-ONGOING-per-slot trigger is not in this pass. Failing
                        # open with no backstop would leave real double-bookings in
                        # the DB behind nothing but a warning. Pass newer_than in the
                        # same change that adds the trigger, not before. Tracked in
                        # docs/issues/issue-reactor-occupancy-uniqueness-trigger.md.
                        incoming_slot = derive_reactor_slot(
                            conditions.reactor_number, conditions.experiment_type
                        )
                        if incoming_slot is not None and experiment.status == ExperimentStatus.ONGOING:
                            marked, reactor_warnings = ExperimentStatusService.manage_reactor_occupancy(
                                db, experiment, conditions.reactor_number, commit=False,
                                reactor_slot=incoming_slot,
                            )
                            warnings.extend(reactor_warnings)
                            if marked > 0:
                                info_messages.append(
                                    f"Reactor {incoming_slot}: Auto-completed {marked} "
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

                # Manage reactor occupancy for auto-copied conditions.
                # Same gates as the conditions-sheet path above (issue #97, Defect 3):
                # slot-scoped, non-occupancy types excluded, zero excluded. `newer_than`
                # is omitted here for the same reason — see the comment on that path.
                incoming_slot = derive_reactor_slot(
                    conditions.reactor_number, conditions.experiment_type
                )
                if incoming_slot is not None and experiment.status == ExperimentStatus.ONGOING:
                    marked, reactor_warnings = ExperimentStatusService.manage_reactor_occupancy(
                        db, experiment, conditions.reactor_number, commit=False,
                        reactor_slot=incoming_slot,
                    )
                    warnings.extend(reactor_warnings)
                    if marked > 0:
                        info_messages.append(
                            f"Reactor {incoming_slot}: Auto-completed {marked} "
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
                    _prior_additives_summary = None
                    if replace_all:
                        # Snapshot before delete — this is the "old" side of the additives
                        # fields_changed summary (issue #100 item 2). Per-compound diffing was
                        # scoped out for this pass; a full replace is reported as one line.
                        _prior_count = db.query(ChemicalAdditive).filter(
                            ChemicalAdditive.experiment_id == conditions.id
                        ).count()
                        _prior_additives_summary = f"{_prior_count} additive(s)" if _prior_count else "no additives"
                        # Delete all existing additives for this experiment's conditions
                        db.query(ChemicalAdditive).filter(
                            ChemicalAdditive.experiment_id == conditions.id
                        ).delete(synchronize_session=False)
                    
                    # NOTE: Chemical additives are NEVER auto-copied from parent
                    # Users must explicitly provide all additives for each experiment
                    
                    for ridx, row in group.iterrows():
                        # Per-row savepoint isolation (issue #96 Defect B, mirrors issue #86's
                        # experiments-sheet loop): a failed flush anywhere in this row's processing
                        # is confined to its own SAVEPOINT and rolled back, leaving the session
                        # usable for the remaining additive rows.
                        savepoint = db.begin_nested()
                        row_ok = False
                        # Tracks the name_to_compound cache key ONLY if this row is the one that
                        # auto-created a brand-new Compound (issue #96 review finding). If the row
                        # then fails and its savepoint is rolled back, the new Compound INSERT is
                        # undone too, but the dict would otherwise keep a reference to that now-
                        # invalid ORM object — poisoning any later row in the same upload that
                        # references the same (still-novel) compound name. Cleared in `finally`.
                        new_compound_key: Optional[str] = None
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
                                new_compound_key = comp_name.lower()

                            # order and method
                            order_val = row.get('order') if 'order' in df_add.columns else None
                            try:
                                order_int = int(order_val) if order_val is not None and str(order_val).strip() != '' else None
                            except Exception:
                                order_int = None
                            method_text = str(row.get('method')).strip() if 'method' in df_add.columns and row.get('method') is not None and str(row.get('method')).strip() != '' else None
                            if method_text and len(method_text) > ADDITION_METHOD_MAX_LENGTH:
                                warnings.append(
                                    f"[additives] Row {int(ridx)+2}: method truncated to {ADDITION_METHOD_MAX_LENGTH} "
                                    f"characters (was {len(method_text)})"
                                )
                                method_text = method_text[:ADDITION_METHOD_MAX_LENGTH]

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
                                db.add(new_add)
                                db.flush()
                                recalculate(new_add, db)
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
                                    db.flush()
                                    recalculate(existing_add, db)
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
                                    db.add(new_add)
                                    db.flush()
                                    recalculate(new_add, db)

                            # Row body completed without exception or early `continue`.
                            row_ok = True
                        except Exception as e:
                            warnings.append(f"[additives] Row {int(ridx)+2}: {e}")
                        finally:
                            # savepoint.commit() (RELEASE SAVEPOINT) flushes the session first,
                            # so a dirty instance left over by recalculate() can still fail here
                            # even though row_ok is True. If that commit itself raises, it must
                            # not escape this `finally` uncaught (issue #96 review finding) --
                            # an uncaught raise here would unwind the whole additives phase for
                            # this experiment group, reproducing the original all-or-nothing
                            # failure mode from a different trigger point. Roll back and record
                            # a row-scoped warning instead, exactly like an in-body failure.
                            commit_failed = False
                            if row_ok:
                                try:
                                    savepoint.commit()
                                except Exception as commit_error:
                                    savepoint.rollback()
                                    commit_failed = True
                                    warnings.append(f"[additives] Row {int(ridx)+2}: {commit_error}")
                            else:
                                savepoint.rollback()

                            if not row_ok or commit_failed:
                                # This row's savepoint rollback undid the new Compound INSERT
                                # (if any) — evict it from the cache so a later row referencing
                                # the same name re-queries/re-creates a fresh Compound instead of
                                # reusing the now-rolled-back ORM object.
                                if new_compound_key is not None and name_to_compound.get(new_compound_key) is comp:
                                    del name_to_compound[new_compound_key]

                    if replace_all:
                        _new_additives_summary = f"{len(group)} additive(s) provided"
                        overwrite_plan_by_exp_id.setdefault(
                            exp_id, PlanOverwrite(row=int(group.index[0]) + 2, experiment_id=exp_id)
                        ).fields_changed.append(FieldChange(
                            field="additives", old=_prior_additives_summary, new=_new_additives_summary,
                        ))

        # Merge all overwrite entries discovered across the experiments/conditions/additives
        # sheets into the plan (issue #100 item 2) — one entry per experiment_id.
        plan.overwrites.extend(overwrite_plan_by_exp_id.values())

        return created_exp, updated_exp, skipped, errors, warnings, info_messages, plan


