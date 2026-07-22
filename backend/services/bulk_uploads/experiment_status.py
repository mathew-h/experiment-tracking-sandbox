from __future__ import annotations

import io
from typing import List, Tuple, Dict, Any
from dataclasses import dataclass

import pandas as pd
from sqlalchemy.orm import Session

from database import Experiment
from database.models import ExperimentalConditions
from database.models.enums import ExperimentStatus


_VALID_STATUSES = {s.value for s in ExperimentStatus}
_OCCUPANCY_TYPES = {"hpht", "core flood"}


def _normalize_type(experiment_type: str | None) -> str:
    """Lowercase + collapse whitespace so 'HPHT ', 'Core  Flood', etc. compare cleanly."""
    return " ".join((experiment_type or "").strip().lower().split())


def _is_eligible_for_occupancy(experiment_type: str | None) -> bool:
    """True for HPHT / Core Flood — the types with physical reactor occupancy."""
    return _normalize_type(experiment_type) in _OCCUPANCY_TYPES


@dataclass
class PlannedChange:
    """One row's planned effect on an Experiment."""
    experiment_id: str
    experiment_pk: int
    current_status: str
    new_status: str
    experiment_type: str | None
    reactor_number: int | None       # current ExperimentalConditions.reactor_number
    new_reactor_number: int | None   # value from the row, if provided
    new_date: pd.Timestamp | None    # value from the row, if provided


@dataclass
class PlannedDemotion:
    """One reactor occupant that will be completed when its row's demotion is applied."""
    experiment_id: str
    experiment_pk: int
    reactor_number: int
    triggering_experiment_id: str


@dataclass
class StatusChangePreview:
    """Preview of per-row status changes and reactor demotions to be applied."""
    changes: List[PlannedChange]
    demotions: List[PlannedDemotion]
    missing_ids: List[str]
    errors: List[str]
    warnings: List[str]


class ExperimentStatusService:
    """Service for bulk updating experiment statuses"""

    @staticmethod
    def preview_status_changes_from_excel(
        db: Session,
        file_bytes: bytes,
    ) -> StatusChangePreview:
        """
        Preview per-row status/date/reactor changes from an Excel file.

        Args:
            db: Database session
            file_bytes: Excel file bytes with 'experiment_id' (required), 'status'
                       (required), 'reactor_number' (optional), 'date' (optional) columns

        Returns:
            StatusChangePreview with planned per-row changes, planned reactor
            demotions, missing experiment IDs, row/column-level errors, and warnings.
        """
        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception as e:
            return StatusChangePreview([], [], [], [f"Failed to read Excel: {e}"], [])

        col_map = {str(c).lower().strip(): str(c) for c in df.columns}

        if "experiment_id" not in col_map:
            return StatusChangePreview([], [], [], ["Missing required column: 'experiment_id'"], [])
        if "status" not in col_map:
            return StatusChangePreview([], [], [], ["Missing required column: 'status'"], [])

        rename_map = {col_map["experiment_id"]: "experiment_id", col_map["status"]: "status"}
        if "reactor_number" in col_map:
            rename_map[col_map["reactor_number"]] = "reactor_number"
        if "date" in col_map:
            rename_map[col_map["date"]] = "date"
        df = df.rename(columns=rename_map)

        errors: List[str] = []
        parsed_rows: List[Dict[str, Any]] = []
        seen_ids: set = set()

        for _, row in df.iterrows():
            exp_id = str(row.get("experiment_id") or "").strip()
            if not exp_id or exp_id in seen_ids:
                continue
            seen_ids.add(exp_id)

            row_errors: List[str] = []

            raw_status = row.get("status")
            status_str = str(raw_status).strip().upper() if pd.notna(raw_status) else ""
            if status_str not in _VALID_STATUSES:
                row_errors.append(f"Invalid status for {exp_id}: {raw_status!r}")

            reactor_number = None
            if "reactor_number" in df.columns:
                reactor_val = row.get("reactor_number")
                if pd.notna(reactor_val):
                    try:
                        reactor_number = int(reactor_val)
                    except (ValueError, TypeError):
                        row_errors.append(f"Invalid reactor_number for {exp_id}: {reactor_val}")

            new_date = None
            if "date" in df.columns:
                date_val = row.get("date")
                if pd.notna(date_val):
                    try:
                        new_date = pd.Timestamp(date_val)
                    except (ValueError, TypeError):
                        row_errors.append(f"Invalid date for {exp_id}: {date_val}")

            if row_errors:
                errors.extend(row_errors)
                continue

            parsed_rows.append({
                "experiment_id": exp_id,
                "status": status_str,
                "reactor_number": reactor_number,
                "date": new_date,
            })

        if not parsed_rows and not errors:
            return StatusChangePreview([], [], [], ["No valid experiment IDs found in file"], [])
        if errors:
            return StatusChangePreview([], [], [], errors, [])

        listed_ids = [r["experiment_id"] for r in parsed_rows]
        exps = db.query(Experiment).outerjoin(
            ExperimentalConditions,
            Experiment.id == ExperimentalConditions.experiment_fk,
        ).filter(Experiment.experiment_id.in_(listed_ids)).all()
        exp_by_id = {e.experiment_id: e for e in exps}
        found_ids = set(exp_by_id.keys())
        missing_ids = [eid for eid in listed_ids if eid not in found_ids]

        changes: List[PlannedChange] = []
        reactor_targets: Dict[int, str] = {}
        conflict_errors: List[str] = []

        for r in parsed_rows:
            exp = exp_by_id.get(r["experiment_id"])
            if exp is None:
                continue

            exp_type = exp.conditions.experiment_type if exp.conditions else None
            changes.append(PlannedChange(
                experiment_id=exp.experiment_id,
                experiment_pk=exp.id,
                current_status=exp.status.value if exp.status else "None",
                new_status=r["status"],
                experiment_type=exp_type,
                reactor_number=exp.conditions.reactor_number if exp.conditions else None,
                new_reactor_number=r["reactor_number"],
                new_date=r["date"],
            ))

            if (
                r["status"] == ExperimentStatus.ONGOING.value
                and r["reactor_number"] is not None
                and _is_eligible_for_occupancy(exp_type)
            ):
                existing = reactor_targets.get(r["reactor_number"])
                if existing is not None:
                    conflict_errors.append(
                        f"Reactor {r['reactor_number']} is targeted by multiple rows in "
                        f"this file: '{existing}' and '{exp.experiment_id}'"
                    )
                else:
                    reactor_targets[r["reactor_number"]] = exp.experiment_id

        if conflict_errors:
            return StatusChangePreview([], [], missing_ids, conflict_errors, [])

        return StatusChangePreview(changes, [], missing_ids, [], [])
    
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
