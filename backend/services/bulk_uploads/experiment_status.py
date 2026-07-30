from __future__ import annotations

import io
from datetime import datetime, date
from typing import List, Tuple, Dict, Any
from dataclasses import dataclass

import pandas as pd
from sqlalchemy.orm import Session

from database import Experiment
from database.models import ExperimentalConditions
from database.models.enums import ExperimentStatus
from database.reactor_slot import derive_reactor_slot


_VALID_STATUSES = {s.value for s in ExperimentStatus}
_UNSET = object()


def _occupant_is_older(occupant_date: date | None, incoming_date: date | None) -> bool:
    """True only when both dates are present and the occupant started strictly earlier."""
    if occupant_date is None or incoming_date is None:
        return False
    return occupant_date < incoming_date


def _demoted_message(reactor_slot: str, demoted_id: str, new_id: str) -> str:
    return (
        f"Reactor {reactor_slot}: Marked experiment '{demoted_id}' "
        f"as COMPLETED (replaced by '{new_id}')"
    )


def _not_demoted_message(reactor_slot: str, occupant_id: str, new_id: str) -> str:
    return (
        f"Reactor {reactor_slot}: '{occupant_id}' was NOT completed — its start date "
        f"is not older than '{new_id}''s (or a start date is missing on one of them). "
        f"Manual review needed."
    )


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
    reactor_slot: str
    triggering_experiment_id: str


@dataclass
class StatusChangePreview:
    """Preview of per-row status changes and reactor demotions to be applied."""
    changes: List[PlannedChange]
    demotions: List[PlannedDemotion]
    missing_ids: List[str]
    errors: List[str]
    warnings: List[str]


@dataclass
class ApplyResult:
    """Outcome of applying a StatusChangePreview."""
    status_changes_applied: int
    demotions_applied: int
    reactor_updates: int
    date_updates: int
    warnings: List[str]
    errors: List[str]


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
        # Keyed on the canonical slot label, not the bare integer: an HPHT into
        # R01 and a Core Flood into CF01 in one file are two different vessels
        # and must not collide (issue #97, Defect 2).
        reactor_targets: Dict[str, str] = {}
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

            incoming_slot = derive_reactor_slot(r["reactor_number"], exp_type)
            if (
                r["status"] == ExperimentStatus.ONGOING.value
                and incoming_slot is not None
            ):
                existing = reactor_targets.get(incoming_slot)
                if existing is not None:
                    conflict_errors.append(
                        f"Reactor {incoming_slot} is targeted by multiple rows in "
                        f"this file: '{existing}' and '{exp.experiment_id}'"
                    )
                else:
                    reactor_targets[incoming_slot] = exp.experiment_id

        if conflict_errors:
            return StatusChangePreview([], [], missing_ids, conflict_errors, [])

        demotions: List[PlannedDemotion] = []
        warnings: List[str] = []

        for r in parsed_rows:
            exp = exp_by_id.get(r["experiment_id"])
            if exp is None or r["status"] != ExperimentStatus.ONGOING.value:
                continue
            exp_type = exp.conditions.experiment_type if exp.conditions else None
            incoming_slot = derive_reactor_slot(r["reactor_number"], exp_type)
            if incoming_slot is None:
                continue

            # Scoped on reactor_slot, so an occupant is only found in the SAME
            # physical vessel. Filtering on reactor_number alone made a Core
            # Flood going ONGOING find the HPHT in R01 (issue #97, Defect 1).
            occupants = db.query(Experiment).join(
                ExperimentalConditions,
                Experiment.id == ExperimentalConditions.experiment_fk,
            ).filter(
                Experiment.id != exp.id,
                Experiment.status == ExperimentStatus.ONGOING,
                ExperimentalConditions.reactor_slot == incoming_slot,
            ).all()

            incoming_date = r["date"].date() if r["date"] is not None else None

            for occ in occupants:
                occ_date = occ.date.date() if occ.date else None
                if _occupant_is_older(occ_date, incoming_date):
                    demotions.append(PlannedDemotion(
                        experiment_id=occ.experiment_id,
                        experiment_pk=occ.id,
                        reactor_number=r["reactor_number"],
                        reactor_slot=incoming_slot,
                        triggering_experiment_id=exp.experiment_id,
                    ))
                    warnings.append(_demoted_message(incoming_slot, occ.experiment_id, exp.experiment_id))
                else:
                    warnings.append(_not_demoted_message(incoming_slot, occ.experiment_id, exp.experiment_id))

        return StatusChangePreview(changes, demotions, missing_ids, [], warnings)
    
    @staticmethod
    def apply_status_changes(
        db: Session,
        preview: StatusChangePreview,
    ) -> ApplyResult:
        """
        Apply a StatusChangePreview: set each row's status/date/reactor_number,
        then run reactor-occupancy demotion for eligible ONGOING rows.

        Args:
            db: Database session
            preview: The StatusChangePreview returned by preview_status_changes_from_excel

        Returns:
            ApplyResult with counts and any warnings/errors encountered.
        """
        errors: List[str] = []
        warnings: List[str] = []
        status_changes = 0
        date_updates = 0
        reactor_updates = 0
        demotions_applied = 0

        try:
            exp_ids = [c.experiment_id for c in preview.changes]
            exps = db.query(Experiment).outerjoin(
                ExperimentalConditions,
                Experiment.id == ExperimentalConditions.experiment_fk,
            ).filter(Experiment.experiment_id.in_(exp_ids)).all() if exp_ids else []
            exp_by_id = {e.experiment_id: e for e in exps}

            for change in preview.changes:
                exp = exp_by_id.get(change.experiment_id)
                if exp is None:
                    continue

                exp.status = ExperimentStatus(change.new_status)
                status_changes += 1

                if change.new_date is not None:
                    exp.date = change.new_date.to_pydatetime()
                    date_updates += 1

                if change.new_reactor_number is not None and exp.conditions:
                    if exp.conditions.reactor_number != change.new_reactor_number:
                        exp.conditions.reactor_number = change.new_reactor_number
                        reactor_updates += 1

                # Derived here rather than read off exp.conditions.reactor_slot:
                # the assignment above has just changed reactor_number in-session
                # and the before_flush listener has not run yet (issue #97
                # pre-flush rule).
                incoming_slot = derive_reactor_slot(
                    change.new_reactor_number, change.experiment_type
                )
                if change.new_status == ExperimentStatus.ONGOING.value and incoming_slot is not None:
                    newer_than = change.new_date.to_pydatetime() if change.new_date is not None else None
                    marked, occ_warnings = ExperimentStatusService.manage_reactor_occupancy(
                        db, exp, change.new_reactor_number, commit=False,
                        newer_than=newer_than, reactor_slot=incoming_slot,
                    )
                    demotions_applied += marked
                    warnings.extend(occ_warnings)

            db.flush()

        except Exception as e:
            errors.append(f"Error applying status changes: {e}")

        return ApplyResult(
            status_changes_applied=status_changes,
            demotions_applied=demotions_applied,
            reactor_updates=reactor_updates,
            date_updates=date_updates,
            warnings=warnings,
            errors=errors,
        )
    
    @staticmethod
    def manage_reactor_occupancy(
        db: Session,
        new_experiment: Experiment,
        reactor_number: int,
        commit: bool = True,
        newer_than: datetime | None = _UNSET,
        reactor_slot: str | None = None,
    ) -> Tuple[int, List[str]]:
        """
        Ensure only one experiment is ONGOING per physical reactor slot at a time.

        Occupancy is keyed on `reactor_slot` (e.g. 'R01', 'CF01'), not on the bare
        `reactor_number` — R01 and CF01 are different vessels that share the number
        1, and keying on the integer let a Core Flood auto-complete a running HPHT
        (issue #97, Defect 1).

        If `newer_than` is explicitly passed (even as None), a start-date guard is
        active: an occupant is only demoted if its `date` is strictly older (by
        calendar date) than `newer_than`; occupants with a missing date, or a date
        that is newer-or-equal, are left ONGOING with a warning instead. Omitting
        `newer_than` entirely preserves the original unconditional behavior relied
        on by `backend/services/bulk_uploads/new_experiments.py` (both its create
        and auto-copy-conditions call sites omit `newer_than` and depend on
        unconditional demotion — this is a live bulk-upload path, not just the
        legacy Streamlit create screen) and by the legacy Streamlit create path.

        Args:
            db: Database session
            new_experiment: The experiment being created/updated
            reactor_number: The reactor number being assigned
            commit: Whether to commit changes (default True)
            newer_than: Optional start-date guard (see above)
            reactor_slot: The canonical slot the incoming experiment is claiming.
                Callers that have just assigned a new reactor_number in-session
                must pass this, because the derived column is only written at
                flush time. When omitted it is derived from `new_experiment`'s
                own conditions — which is what keeps the legacy Streamlit caller
                correct without changing it.

        Returns:
            Tuple of (marked_completed_count, warnings). Returns (0, []) when the
            incoming experiment holds no slot at all: a non-occupancy type, a
            missing reactor_number, or reactor_number <= 0.
        """
        warnings: List[str] = []
        marked_completed = 0
        guard_active = newer_than is not _UNSET

        try:
            if new_experiment.status != ExperimentStatus.ONGOING:
                return 0, []

            slot = reactor_slot
            if slot is None:
                conditions = getattr(new_experiment, "conditions", None)
                slot = derive_reactor_slot(
                    reactor_number,
                    conditions.experiment_type if conditions is not None else None,
                )
            if slot is None:
                # No physical slot to contest — nothing to demote, and nothing
                # worth warning about.
                return 0, []

            conflicting_experiments = db.query(Experiment).join(
                ExperimentalConditions,
                Experiment.id == ExperimentalConditions.experiment_fk
            ).filter(
                Experiment.id != new_experiment.id,
                Experiment.status == ExperimentStatus.ONGOING,
                ExperimentalConditions.reactor_slot == slot
            ).all()

            for exp in conflicting_experiments:
                if guard_active:
                    occ_date = exp.date.date() if exp.date else None
                    incoming_date = newer_than.date() if newer_than else None
                    if incoming_date is None or occ_date is None or occ_date >= incoming_date:
                        warnings.append(
                            _not_demoted_message(slot, exp.experiment_id, new_experiment.experiment_id)
                        )
                        continue

                exp.status = ExperimentStatus.COMPLETED
                marked_completed += 1
                warnings.append(
                    _demoted_message(slot, exp.experiment_id, new_experiment.experiment_id)
                )

            if commit:
                db.commit()

        except Exception as e:
            warnings.append(f"Error managing reactor occupancy: {e}")
            if commit:
                db.rollback()

        return marked_completed, warnings

