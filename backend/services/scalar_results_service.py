from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from database import Experiment, ExperimentalResults, ScalarResults, ModificationsLog
from backend.services.result_merge_utils import (
    create_experimental_result_row,
    ensure_primary_result_for_timepoint,
    find_timepoint_candidates,
    choose_parent_candidate,
    update_cumulative_times_for_chain,
)

# All updatable scalar fields -- shared by create and audit-trail logic.
SCALAR_UPDATABLE_FIELDS = [
    'ferrous_iron_yield', 'gross_ammonium_concentration_mM', 'background_ammonium_concentration_mM',
    'background_experiment_id',
    'h2_concentration', 'h2_concentration_unit', 'gas_sampling_volume_ml', 'gas_sampling_pressure_MPa',
    'final_ph', 'final_nitrate_concentration_mM', 'final_dissolved_oxygen_mg_L', 'co2_partial_pressure_MPa',
    'final_conductivity_mS_cm', 'final_alkalinity_mg_L', 'sampling_volume_mL', 'measurement_date',
]


class ScalarUpsertResult:
    """Structured result from a single scalar upsert operation."""

    __slots__ = (
        "experimental_result", "action", "fields_updated",
        "fields_preserved", "old_values", "new_values",
    )

    def __init__(self, experimental_result: ExperimentalResults, action: str):
        self.experimental_result = experimental_result
        self.action: str = action  # "created" | "updated"
        self.fields_updated: List[str] = []
        self.fields_preserved: List[str] = []
        self.old_values: Dict[str, Any] = {}
        self.new_values: Dict[str, Any] = {}


class ScalarResultsService:
    """Service for handling scalar results (solution chemistry) operations."""
    
    @staticmethod
    def create_scalar_result(db: Session, experiment_id: str, result_data: Dict[str, Any]) -> Optional[ExperimentalResults]:
        """
        Create or upsert an experimental result with scalar chemistry data.
        If an ExperimentalResults entry already exists for the experiment and time point,
        this method will update (merge) the existing ScalarResults record instead of erroring.
        
        Args:
            db: Database session
            experiment_id: String experiment ID
            result_data: Dictionary containing result data fields
                        Special key '_overwrite' (bool) determines update behavior:
                        - False (default): only update provided fields, keep existing values
                        - True: replace all fields with provided values, set missing fields to None
            
        Returns:
            ExperimentalResults object (existing or new) with scalar data attached
            
        Raises:
            ValueError: If experiment not found or scalar data already exists for this time point
        """
        upsert = ScalarResultsService.create_scalar_result_ex(db, experiment_id, result_data)
        return upsert.experimental_result if upsert else None

    @staticmethod
    def create_scalar_result_ex(
        db: Session, experiment_id: str, result_data: Dict[str, Any],
    ) -> ScalarUpsertResult:
        """
        Extended version of ``create_scalar_result`` that returns a
        ``ScalarUpsertResult`` with field-level change tracking.
        """
        # Extract overwrite flag (default False)
        overwrite = result_data.pop('_overwrite', False)
        
        # Ensure h2_concentration_unit defaults to ppm if concentration is present
        if result_data.get('h2_concentration') is not None:
            if not result_data.get('h2_concentration_unit'):
                result_data['h2_concentration_unit'] = 'ppm'

        # Find experiment with normalization
        experiment = ScalarResultsService._find_experiment(db, experiment_id)
        if not experiment:
            # Try to auto-create if this is a treatment variant with existing parent
            from database.lineage_utils import auto_create_treatment_experiment
            experiment = auto_create_treatment_experiment(
                db=db,
                experiment_id=experiment_id,
                initial_note=result_data.get('description', 'Auto-created from scalar results upload')
            )
            if not experiment:
                raise ValueError(f"Experiment with ID '{experiment_id}' not found and could not be auto-created.")
        
        # Validate time_post_reaction is provided (required for proper merge with ICP data)
        time_post_reaction = result_data.get('time_post_reaction')
        if time_post_reaction is None:
            raise ValueError(
                "time_post_reaction (Time (days)) is required for scalar results. "
                "Use 0 for pre-reaction baselines."
            )

        # Find or create ExperimentalResults with deterministic timepoint merge rules.
        experimental_result = ScalarResultsService._find_or_create_experimental_result(
            db=db,
            experiment=experiment,
            time_post_reaction=time_post_reaction,
            description=result_data.get('description'),
            incoming_data_type="scalar",
        )
        
        # Upsert ScalarResults: update if exists; otherwise create new
        if experimental_result.scalar_data:
            scalar_data = experimental_result.scalar_data

            # Snapshot old values before modification
            old_snapshot = {
                f: getattr(scalar_data, f) for f in SCALAR_UPDATABLE_FIELDS
            }

            if overwrite:
                for field in SCALAR_UPDATABLE_FIELDS:
                    setattr(scalar_data, field, result_data.get(field))
            else:
                for field in SCALAR_UPDATABLE_FIELDS:
                    if field in result_data:
                        setattr(scalar_data, field, result_data.get(field))

            # Build change tracking
            upsert = ScalarUpsertResult(experimental_result, action="updated")
            for field in SCALAR_UPDATABLE_FIELDS:
                old_val = old_snapshot[field]
                new_val = getattr(scalar_data, field)
                if old_val != new_val:
                    upsert.fields_updated.append(field)
                    upsert.old_values[field] = old_val
                    upsert.new_values[field] = new_val
                elif old_val is not None:
                    upsert.fields_preserved.append(field)
        else:
            # Create scalar data with chemistry measurements
            scalar_data = ScalarResults(
                result_id=experimental_result.id,
                ferrous_iron_yield=result_data.get('ferrous_iron_yield'),
                gross_ammonium_concentration_mM=result_data.get('gross_ammonium_concentration_mM'),
                background_ammonium_concentration_mM=result_data.get('background_ammonium_concentration_mM'),
                background_experiment_id=result_data.get('background_experiment_id'),
                h2_concentration=result_data.get('h2_concentration'),
                h2_concentration_unit=result_data.get('h2_concentration_unit'),
                gas_sampling_volume_ml=result_data.get('gas_sampling_volume_ml'),
                gas_sampling_pressure_MPa=result_data.get('gas_sampling_pressure_MPa'),
                final_ph=result_data.get('final_ph'),
                final_nitrate_concentration_mM=result_data.get('final_nitrate_concentration_mM'),
                final_dissolved_oxygen_mg_L=result_data.get('final_dissolved_oxygen_mg_L'),
                co2_partial_pressure_MPa=result_data.get('co2_partial_pressure_MPa'),
                final_conductivity_mS_cm=result_data.get('final_conductivity_mS_cm'),
                final_alkalinity_mg_L=result_data.get('final_alkalinity_mg_L'),
                sampling_volume_mL=result_data.get('sampling_volume_mL'),
                measurement_date=result_data.get('measurement_date'),
                result_entry=experimental_result,
            )
            db.add(scalar_data)

            upsert = ScalarUpsertResult(experimental_result, action="created")
            upsert.fields_updated = [
                f for f in SCALAR_UPDATABLE_FIELDS if result_data.get(f) is not None
            ]
            upsert.new_values = {
                f: result_data[f] for f in upsert.fields_updated
            }

        # Calculate derived values (yields, conversions, etc.)
        scalar_data.calculate_yields()

        # Audit trail: log changes via ModificationsLog
        if upsert.fields_updated:
            # Serialize values to JSON-safe types (datetimes -> isoformat strings)
            def _serialize(val: Any) -> Any:
                if hasattr(val, 'isoformat'):
                    return val.isoformat()
                return val

            log_entry = ModificationsLog(
                experiment_id=experiment.experiment_id,
                experiment_fk=experiment.id,
                modification_type=upsert.action,
                modified_table="scalar_results",
                old_values={k: _serialize(v) for k, v in upsert.old_values.items()} or None,
                new_values={k: _serialize(v) for k, v in upsert.new_values.items()} or None,
            )
            db.add(log_entry)

        # Touch parent entry and flush IDs if needed
        db.add(experimental_result)
        db.flush()
        ensure_primary_result_for_timepoint(
            db=db,
            experiment_fk=experiment.id,
            time_post_reaction=result_data.get('time_post_reaction'),
        )

        # Recalculate cumulative times for the entire lineage chain
        update_cumulative_times_for_chain(db, experiment.id)

        return upsert
    
    @staticmethod
    def bulk_create_scalar_results(
        db: Session,
        results_data: List[Dict[str, Any]],
    ) -> Tuple[List[ExperimentalResults], List[str]]:
        """
        Bulk create scalar results with validation and error collection.

        Returns:
            Tuple of (successful_results, error_messages)
        """
        results, errors, _feedbacks = ScalarResultsService.bulk_create_scalar_results_ex(
            db, results_data,
        )
        return results, errors

    @staticmethod
    def bulk_create_scalar_results_ex(
        db: Session,
        results_data: List[Dict[str, Any]],
    ) -> Tuple[List[ExperimentalResults], List[str], List[Dict[str, Any]]]:
        """
        Extended bulk create that also returns per-row structured feedback.

        Returns:
            ``(successful_results, error_messages, row_feedbacks)``
            Each feedback dict has keys: row, experiment_id, time_post_reaction,
            status, fields_updated, fields_preserved, old_values, new_values,
            warnings, errors.
        """
        results_to_add: List[ExperimentalResults] = []
        errors: List[str] = []
        feedbacks: List[Dict[str, Any]] = []

        for index, row_data in enumerate(results_data):
            row_num = index + 2  # Excel row (1-indexed header + 1)
            fb: Dict[str, Any] = {
                "row": row_num,
                "experiment_id": str(row_data.get("experiment_id", "")),
                "time_post_reaction": row_data.get("time_post_reaction"),
                "status": "pending",
                "fields_updated": [],
                "fields_preserved": [],
                "old_values": {},
                "new_values": {},
                "warnings": [],
                "errors": [],
            }
            try:
                exp_id_raw = row_data.get('experiment_id')
                if not exp_id_raw:
                    fb["status"] = "error"
                    fb["errors"].append("Missing experiment_id.")
                    errors.append(f"Row {row_num}: Missing experiment_id.")
                    feedbacks.append(fb)
                    continue

                # Auto-generate description when not provided
                if not row_data.get('description'):
                    time_val = row_data.get('time_post_reaction')
                    if time_val is not None:
                        row_data['description'] = f"Day {time_val} results"
                    else:
                        row_data['description'] = "Analysis results"

                # Use a savepoint so a failed row doesn't poison the session
                savepoint = db.begin_nested()
                try:
                    upsert = ScalarResultsService.create_scalar_result_ex(
                        db=db,
                        experiment_id=exp_id_raw,
                        result_data=row_data,
                    )

                    if upsert and upsert.experimental_result:
                        results_to_add.append(upsert.experimental_result)
                        fb["status"] = upsert.action
                        fb["fields_updated"] = list(upsert.fields_updated)
                        fb["fields_preserved"] = list(upsert.fields_preserved)
                        fb["old_values"] = dict(upsert.old_values)
                        fb["new_values"] = dict(upsert.new_values)
                    else:
                        fb["status"] = "skipped"
                        savepoint.rollback()

                    # Commit the savepoint on success (no-op if already committed)
                    if savepoint.is_active:
                        savepoint.commit()

                except ValueError as e:
                    savepoint.rollback()
                    fb["status"] = "error"
                    fb["errors"].append(str(e))
                    errors.append(f"Row {row_num}: {str(e)}")
                except Exception as e:
                    savepoint.rollback()
                    fb["status"] = "error"
                    fb["errors"].append(f"Unexpected error - {str(e)}")
                    errors.append(f"Row {row_num}: Unexpected error - {str(e)}")

            except Exception as e:
                fb["status"] = "error"
                fb["errors"].append(f"Unexpected error - {str(e)}")
                errors.append(f"Row {row_num}: Unexpected error - {str(e)}")

            feedbacks.append(fb)

        return results_to_add, errors, feedbacks
    
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
        ).options(joinedload(Experiment.conditions)).first()
        
        return experiment
    
    @staticmethod
    def _find_or_create_experimental_result(
        db: Session, 
        experiment: Experiment, 
        time_post_reaction: float = None, 
        description: str = None,
        incoming_data_type: str = "scalar",
    ) -> ExperimentalResults:
        """
        Find existing ExperimentalResults or create new one.
        Reuses any existing result for the same time point (Scalar service handles updates/merges).
        
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
            # User-provided scalar descriptions take priority over auto-generated ones
            if description:
                existing.description = description
            return existing

        # Fallback: match a NULL-time row for the same experiment by description.
        # This handles re-uploads that restore missing time values.
        if time_post_reaction is not None and description:
            from backend.services.result_merge_utils import normalize_timepoint as _norm_tp
            null_time_match = (
                db.query(ExperimentalResults)
                .options(
                    joinedload(ExperimentalResults.scalar_data),
                    joinedload(ExperimentalResults.icp_data),
                )
                .filter(
                    ExperimentalResults.experiment_fk == experiment.id,
                    ExperimentalResults.time_post_reaction_days.is_(None),
                    ExperimentalResults.description == description,
                )
                .first()
            )
            if null_time_match:
                null_time_match.time_post_reaction_days = time_post_reaction
                null_time_match.time_post_reaction_bucket_days = _norm_tp(time_post_reaction)
                if description:
                    null_time_match.description = description
                return null_time_match

        # Create new parent result row when no timepoint candidate exists.
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
    def get_scalar_results_for_experiment(db: Session, experiment_id: str) -> List[ScalarResults]:
        """
        Retrieve all scalar results for an experiment.
        
        Args:
            db: Database session
            experiment_id: String experiment ID
            
        Returns:
            List of ScalarResults objects
        """
        experiment = ScalarResultsService._find_experiment(db, experiment_id)
        if not experiment:
            return []
        return (
            db.query(ScalarResults)
            .join(ExperimentalResults)
            .filter(ExperimentalResults.experiment_fk == experiment.id)
            .all()
        )
    
    @staticmethod
    def update_scalar_result(db: Session, result_id: int, update_data: Dict[str, Any]) -> Optional[ScalarResults]:
        """
        Update an existing scalar result and recalculate derived values.
        
        Args:
            db: Database session
            result_id: ID of the ExperimentalResults entry
            update_data: Dictionary of fields to update
            
        Returns:
            Updated ScalarResults object or None if not found
        """
        scalar_result = db.query(ScalarResults).filter(ScalarResults.result_id == result_id).first()
        
        if not scalar_result:
            raise ValueError(f"ScalarResult with result_id {result_id} not found.")
        
        # Update fields from update_data
        for field, value in update_data.items():
            if hasattr(scalar_result, field):
                setattr(scalar_result, field, value)
        
        # Recalculate derived values
        scalar_result.calculate_yields()
        
        db.flush()
        return scalar_result
    
    @staticmethod
    def validate_required_fields(data: Dict[str, Any], required_fields: set) -> List[str]:
        """
        Validate that required fields are present in data.
        
        Args:
            data: Dictionary to validate
            required_fields: Set of required field names
            
        Returns:
            List of error messages for missing fields
        """
        errors = []
        missing_fields = required_fields - set(data.keys())
        
        if missing_fields:
            errors.append(f"Missing required fields: {', '.join(missing_fields)}")
        
        return errors
