from __future__ import annotations

import io
from typing import List, Tuple, Dict, Any
from dataclasses import dataclass

import pandas as pd
from sqlalchemy.orm import Session

from database import Experiment
from database.models import ExperimentalConditions
from database.models.enums import ExperimentStatus


@dataclass
class StatusChangePreview:
    """Preview of status changes to be applied"""
    to_ongoing: List[Dict[str, Any]]  # List of {experiment_id, current_status, reactor_number, new_reactor_number}
    to_completed: List[Dict[str, Any]]  # List of {experiment_id, current_status, reactor_number}
    missing_ids: List[str]  # Experiment IDs not found in database
    errors: List[str]  # Validation errors


class ExperimentStatusService:
    """Service for bulk updating experiment statuses"""
    
    @staticmethod
    def preview_status_changes_from_excel(
        db: Session, 
        file_bytes: bytes
    ) -> StatusChangePreview:
        """
        Preview status changes from an Excel file.
        
        Args:
            db: Database session
            file_bytes: Excel file bytes with 'experiment_id' (required) and 
                       'reactor_number' (optional) columns
            
        Returns:
            StatusChangePreview with lists of changes to be made, including 
            reactor_number_map attribute for applying reactor number updates
        """
        errors: List[str] = []
        missing_ids: List[str] = []
        
        # Read Excel file
        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception as e:
            return StatusChangePreview(
                to_ongoing=[],
                to_completed=[],
                missing_ids=[],
                errors=[f"Failed to read Excel: {e}"]
            )
        
        # Normalize column names (case-insensitive)
        col_map = {str(c).lower().strip(): str(c) for c in df.columns}
        
        # Check for required column
        if "experiment_id" not in col_map:
            return StatusChangePreview(
                to_ongoing=[],
                to_completed=[],
                missing_ids=[],
                errors=["Missing required column: 'experiment_id'"]
            )
        
        # Rename to standard column names
        rename_map = {col_map["experiment_id"]: "experiment_id"}
        if "reactor_number" in col_map:
            rename_map[col_map["reactor_number"]] = "reactor_number"
        df = df.rename(columns=rename_map)
        
        # Extract experiment IDs and reactor numbers (remove blanks and duplicates)
        listed_exp_ids = []
        reactor_number_map = {}  # Maps experiment_id to reactor_number
        for idx, row in df.iterrows():
            exp_id = str(row.get("experiment_id") or "").strip()
            if exp_id and exp_id not in listed_exp_ids:
                listed_exp_ids.append(exp_id)
                # Store reactor_number if provided and valid
                if "reactor_number" in df.columns:
                    reactor_val = row.get("reactor_number")
                    if pd.notna(reactor_val):
                        try:
                            reactor_number_map[exp_id] = int(reactor_val)
                        except (ValueError, TypeError):
                            errors.append(f"Invalid reactor_number for {exp_id}: {reactor_val}")
        
        if not listed_exp_ids:
            return StatusChangePreview(
                to_ongoing=[],
                to_completed=[],
                missing_ids=[],
                errors=["No valid experiment IDs found in file"]
            )
        
        # Find experiments to set ONGOING (must exist in DB) with their conditions
        to_ongoing_exps = db.query(Experiment).outerjoin(
            ExperimentalConditions,
            Experiment.id == ExperimentalConditions.experiment_fk
        ).filter(
            Experiment.experiment_id.in_(listed_exp_ids)
        ).all()
        
        # Track which IDs were found
        found_ids = {exp.experiment_id for exp in to_ongoing_exps}
        missing_ids = [exp_id for exp_id in listed_exp_ids if exp_id not in found_ids]
        
        # Find experiments to set COMPLETED (currently ONGOING, not in list, and HPHT type)
        to_completed_exps = db.query(Experiment).join(
            ExperimentalConditions,
            Experiment.id == ExperimentalConditions.experiment_fk
        ).filter(
            Experiment.status == ExperimentStatus.ONGOING,
            ~Experiment.experiment_id.in_(listed_exp_ids),
            ExperimentalConditions.experiment_type == "HPHT"
        ).all()
        
        # Build preview data
        to_ongoing = []
        for exp in to_ongoing_exps:
            preview_item = {
                "experiment_id": exp.experiment_id,
                "current_status": exp.status.value if exp.status else "None",
                "current_reactor_number": exp.conditions.reactor_number if exp.conditions else None,
                "new_reactor_number": reactor_number_map.get(exp.experiment_id)
            }
            to_ongoing.append(preview_item)
        
        to_completed = []
        for exp in to_completed_exps:
            preview_item = {
                "experiment_id": exp.experiment_id,
                "current_status": exp.status.value,
                "current_reactor_number": exp.conditions.reactor_number if exp.conditions else None
            }
            to_completed.append(preview_item)
        
        preview = StatusChangePreview(
            to_ongoing=to_ongoing,
            to_completed=to_completed,
            missing_ids=missing_ids,
            errors=errors
        )
        # Store reactor_number_map for later use in apply
        preview.reactor_number_map = reactor_number_map  # type: ignore
        return preview
    
    @staticmethod
    def apply_status_changes(
        db: Session,
        experiment_ids_to_ongoing: List[str],
        reactor_number_map: Dict[str, int] = None
    ) -> Tuple[int, int, int, List[str]]:
        """
        Apply status changes: set listed experiments to ONGOING, others to COMPLETED.
        Optionally update reactor numbers.
        
        Args:
            db: Database session
            experiment_ids_to_ongoing: List of experiment IDs to mark as ONGOING
            reactor_number_map: Optional dict mapping experiment_id to reactor_number
            
        Returns:
            Tuple of (marked_ongoing_count, marked_completed_count, reactor_updates_count, errors)
        """
        errors: List[str] = []
        marked_ongoing = 0
        marked_completed = 0
        reactor_updates = 0
        reactor_number_map = reactor_number_map or {}
        
        try:
            # Update experiments to ONGOING and update reactor numbers
            if experiment_ids_to_ongoing:
                to_ongoing_exps = db.query(Experiment).outerjoin(
                    ExperimentalConditions,
                    Experiment.id == ExperimentalConditions.experiment_fk
                ).filter(
                    Experiment.experiment_id.in_(experiment_ids_to_ongoing)
                ).all()
                
                for exp in to_ongoing_exps:
                    exp.status = ExperimentStatus.ONGOING
                    marked_ongoing += 1
                    
                    # Update reactor_number if provided
                    if exp.experiment_id in reactor_number_map and exp.conditions:
                        new_reactor_number = reactor_number_map[exp.experiment_id]
                        if exp.conditions.reactor_number != new_reactor_number:
                            exp.conditions.reactor_number = new_reactor_number
                            reactor_updates += 1
            
            # Update other ONGOING HPHT experiments to COMPLETED
            to_completed_exps = db.query(Experiment).join(
                ExperimentalConditions,
                Experiment.id == ExperimentalConditions.experiment_fk
            ).filter(
                Experiment.status == ExperimentStatus.ONGOING,
                ExperimentalConditions.experiment_type == "HPHT",
                ~Experiment.experiment_id.in_(experiment_ids_to_ongoing) if experiment_ids_to_ongoing else True
            ).all()
            
            for exp in to_completed_exps:
                exp.status = ExperimentStatus.COMPLETED
                marked_completed += 1
            
        except Exception as e:
            errors.append(f"Error applying status changes: {e}")
        
        return marked_ongoing, marked_completed, reactor_updates, errors
    
    @staticmethod
    def manage_reactor_occupancy(
        db: Session,
        new_experiment: Experiment,
        reactor_number: int,
        commit: bool = True
    ) -> Tuple[int, List[str]]:
        """
        Ensure only one experiment is ONGOING per reactor at a time.
        
        When a new experiment is set to ONGOING with a reactor number, this function
        automatically marks any other ONGOING experiments in the same reactor as COMPLETED.
        
        Args:
            db: Database session
            new_experiment: The experiment being created/updated
            reactor_number: The reactor number being assigned
            commit: Whether to commit changes (default True)
            
        Returns:
            Tuple of (marked_completed_count, warnings)
            
        Example:
            >>> marked, warnings = ExperimentStatusService.manage_reactor_occupancy(
            ...     db, new_exp, reactor_number=3
            ... )
            >>> print(f"Marked {marked} experiments as completed")
        """
        warnings: List[str] = []
        marked_completed = 0
        
        try:
            # Only manage occupancy if the new experiment is ONGOING
            if new_experiment.status != ExperimentStatus.ONGOING:
                return 0, []
            
            # Find other ONGOING experiments in the same reactor
            conflicting_experiments = db.query(Experiment).join(
                ExperimentalConditions,
                Experiment.id == ExperimentalConditions.experiment_fk
            ).filter(
                Experiment.id != new_experiment.id,  # Exclude the current experiment
                Experiment.status == ExperimentStatus.ONGOING,
                ExperimentalConditions.reactor_number == reactor_number
            ).all()
            
            # Mark conflicting experiments as COMPLETED
            for exp in conflicting_experiments:
                exp.status = ExperimentStatus.COMPLETED
                marked_completed += 1
                warnings.append(
                    f"Reactor {reactor_number}: Marked experiment '{exp.experiment_id}' "
                    f"as COMPLETED (replaced by '{new_experiment.experiment_id}')"
                )
            
            if commit:
                db.commit()
                
        except Exception as e:
            warnings.append(f"Error managing reactor occupancy: {e}")
            if commit:
                db.rollback()
        
        return marked_completed, warnings

