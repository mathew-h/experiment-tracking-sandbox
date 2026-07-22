# Issue #66 — Experiment Status Bulk Upload: Per-Row Status, Start Date, Reactor-Scoped Date-Aware Demotion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the Experiment Status Update bulk upload from a whole-world "snapshot" model (forces every listed experiment to ONGOING, blanket-completes every unlisted ongoing HPHT experiment) into an explicit per-row model: each row carries its own `status`, and reactor demotion is scoped to the physical reactor and gated on start date, for HPHT and Core Flood experiments.

**Architecture:** `ExperimentStatusService` (`backend/services/bulk_uploads/experiment_status.py`) gets a rewritten `preview_status_changes_from_excel` (per-row parse/validate → `StatusChangePreview` with planned changes + planned demotions) and `apply_status_changes` (consumes a `StatusChangePreview`, writes status/date/reactor_number, then reuses `manage_reactor_occupancy` — now with an optional start-date guard — to execute demotions). The FastAPI router wraps these two calls unchanged in shape (preview → apply → commit/rollback), the Excel template gets four columns + an INSTRUCTIONS sheet, and the frontend tile copy is updated. No database migration — every field involved already exists.

**Tech Stack:** FastAPI, SQLAlchemy 2.x ORM, pandas (Excel parsing), openpyxl (Excel template generation), pytest (backend tests).

## Global Constraints

- No database migration — `Experiment.status`, `Experiment.date`, `ExperimentalConditions.experiment_type`, `ExperimentalConditions.reactor_number` already exist.
- `backend/services/bulk_uploads/` is a locked component (`docs/LOCKED_COMPONENTS.md`) — this issue is the explicit user instruction authorizing modification of `experiment_status.py` only. Do not touch other files in that directory.
- `manage_reactor_occupancy`'s existing callers (`backend/services/bulk_uploads/new_experiments.py` lines ~599, ~671, and the legacy Streamlit create path) must behave **exactly as before** — they never pass the new guard parameter.
- Keep the existing all-or-nothing transaction behavior: commit only if there are no hard errors, otherwise roll back.
- Confirmed decisions on the issue's four open items (user sign-off obtained 2026-07-22):
  1. **Missing start dates:** if either the incoming row's date or the occupant's date is missing, do not demote — warn instead.
  2. **`status` column:** required. A missing `status` (or `experiment_id`) column hard-errors the whole upload with no changes applied.
  3. **Multiple rows targeting the same reactor:** detected in preview and rejected as a hard error (whole upload fails, nothing applied).
  4. **Same-day start dates:** "newer-or-equal → warn" — a same-day swap warns rather than auto-demoting.
- Status values are case-insensitive on input, normalized to the `ExperimentStatus` enum's upper-case values (`ONGOING`, `COMPLETED`, `CANCELLED`, `QUEUED`).
- `experiment_type` is a free string column — normalize case/whitespace defensively when comparing against `"HPHT"` / `"Core Flood"` rather than assuming exact casing.
- The reactor occupancy/demotion gate is about the **physical reactor**: an occupant of *any* experiment type in that reactor is a demotion candidate. The HPHT/Core-Flood restriction applies only to which **incoming** rows trigger a check.
- `UploadResponse` (`backend/api/schemas/bulk_upload.py`) already has a `warnings: list[str] = []` field — no schema change needed there.

---

## File Structure

| File | Change |
|------|--------|
| `backend/services/bulk_uploads/experiment_status.py` | Rewrite `StatusChangePreview` (+ new `PlannedChange`, `PlannedDemotion`, `ApplyResult` dataclasses), rewrite `preview_status_changes_from_excel`, rewrite `apply_status_changes`, add a start-date guard to `manage_reactor_occupancy`. |
| `backend/api/routers/bulk_uploads.py` | Rewrite `upload_experiment_status` (~line 580) to the new preview/apply shapes; rewrite the `"experiment-status"` branch of `_get_template_bytes` (~line 988) to 4 columns + INSTRUCTIONS sheet. |
| `frontend/src/pages/BulkUploads.tsx` | Update the Experiment Status Update tile's `description` and `helpText` (~line 335). |
| `tests/services/bulk_uploads/test_experiment_status.py` | Full rewrite to match the new per-row contract. |
| `tests/api/test_bulk_uploads.py` | Update the `experiment-status` router-level mock test (~line 315) to the new preview/apply shapes; add a template-content test. |
| `docs/api/API_REFERENCE.md` | Update the `experiment-status` endpoint/template row descriptions. |
| `docs/user_guide/BULK_UPLOADS.md` | Rewrite section "11 — Experiment Status Update". |

---

### Task 1: Preview — parsing, validation, missing IDs, same-reactor-in-file conflict

**Files:**
- Modify: `backend/services/bulk_uploads/experiment_status.py` (full rewrite via Write — old `apply_status_changes` and `manage_reactor_occupancy` are carried over unchanged for now; Tasks 3–4 rewrite them)
- Test: `tests/services/bulk_uploads/test_experiment_status.py` (rewrite preview-section tests)

**Interfaces:**
- Produces: `PlannedChange` dataclass (`experiment_id: str`, `experiment_pk: int`, `current_status: str`, `new_status: str`, `experiment_type: str | None`, `reactor_number: int | None`, `new_reactor_number: int | None`, `new_date: pd.Timestamp | None`), `PlannedDemotion` dataclass (`experiment_id: str`, `experiment_pk: int`, `reactor_number: int`, `triggering_experiment_id: str`), `StatusChangePreview` dataclass (`changes: List[PlannedChange]`, `demotions: List[PlannedDemotion]`, `missing_ids: List[str]`, `errors: List[str]`, `warnings: List[str]`), module-level `_normalize_type(experiment_type: str | None) -> str` and `_is_eligible_for_occupancy(experiment_type: str | None) -> bool`, and `ExperimentStatusService.preview_status_changes_from_excel(db, file_bytes) -> StatusChangePreview` (demotions/warnings always `[]` until Task 2).
- Consumes: nothing new (uses existing `Experiment`, `ExperimentalConditions`, `ExperimentStatus`).

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `tests/services/bulk_uploads/test_experiment_status.py` with:

```python
"""Tests for ExperimentStatusService.

Per-row model:
- Each row sets its own `status` (ONGOING / COMPLETED / CANCELLED / QUEUED).
- `reactor_number` and `date` are optional; `date` is the experiment start date.
- Setting an HPHT or Core Flood row to ONGOING with a reactor_number schedules
  demotion of an older ONGOING occupant in the same reactor (see Task 2 tests).
- A missing `experiment_id` or `status` column hard-errors the whole upload.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from database import Experiment
from database.models import ExperimentalConditions
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads.experiment_status import ExperimentStatusService

from .excel_helpers import make_excel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_experiment(
    db: Session,
    experiment_id: str,
    exp_num: int,
    status: ExperimentStatus = ExperimentStatus.ONGOING,
    experiment_type: str | None = None,
    reactor_number: int | None = None,
    date=None,
) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=exp_num,
        status=status,
        date=date,
    )
    db.add(exp)
    db.flush()

    if experiment_type is not None or reactor_number is not None:
        cond = ExperimentalConditions(
            experiment_fk=exp.id,
            experiment_id=experiment_id,
            experiment_type=experiment_type,
            reactor_number=reactor_number,
        )
        db.add(cond)
        db.flush()

    return exp


# ---------------------------------------------------------------------------
# Column / row validation
# ---------------------------------------------------------------------------

def test_preview_missing_experiment_id_column_returns_error(db_session: Session):
    xlsx = make_excel(["status", "reactor_number"], [["ONGOING", 3]])
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert len(preview.errors) == 1
    assert "experiment_id" in preview.errors[0]
    assert preview.changes == []


def test_preview_missing_status_column_returns_error(db_session: Session):
    xlsx = make_excel(["experiment_id", "reactor_number"], [["HPHT_ST001", 3]])
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert len(preview.errors) == 1
    assert "status" in preview.errors[0]
    assert preview.changes == []


def test_preview_builds_planned_change_per_row(db_session: Session):
    """A valid row produces one PlannedChange with the parsed status/reactor/date."""
    _seed_experiment(db_session, "HPHT_ST001", 6601, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_ST001", "ongoing", 3, "2026-07-15"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.errors == []
    assert len(preview.changes) == 1
    change = preview.changes[0]
    assert change.experiment_id == "HPHT_ST001"
    assert change.new_status == "ONGOING"
    assert change.new_reactor_number == 3
    assert change.new_date is not None
    assert change.new_date.date().isoformat() == "2026-07-15"


def test_preview_records_missing_experiment_ids(db_session: Session):
    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number"],
        [["NONEXISTENT_ST", "ONGOING", 2]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert "NONEXISTENT_ST" in preview.missing_ids
    assert preview.changes == []
    assert preview.errors == []


def test_preview_invalid_status_produces_row_error(db_session: Session):
    _seed_experiment(db_session, "HPHT_ST002", 6602, ExperimentStatus.ONGOING, "HPHT")
    xlsx = make_excel(
        ["experiment_id", "status"],
        [["HPHT_ST002", "IN_PROGRESS"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert len(preview.errors) == 1
    assert "Invalid status" in preview.errors[0]


def test_preview_invalid_reactor_number_produces_row_error(db_session: Session):
    _seed_experiment(db_session, "HPHT_ST003", 6603, ExperimentStatus.ONGOING, "HPHT")
    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number"],
        [["HPHT_ST003", "ONGOING", "not-a-number"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert len(preview.errors) == 1
    assert "Invalid reactor_number" in preview.errors[0]


def test_preview_invalid_date_produces_row_error(db_session: Session):
    _seed_experiment(db_session, "HPHT_ST004", 6604, ExperimentStatus.ONGOING, "HPHT")
    xlsx = make_excel(
        ["experiment_id", "status", "date"],
        [["HPHT_ST004", "ONGOING", "not-a-date"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert len(preview.errors) == 1
    assert "Invalid date" in preview.errors[0]


# ---------------------------------------------------------------------------
# Same-reactor-in-file conflict (Open Item #3: error, don't let apply order decide)
# ---------------------------------------------------------------------------

def test_preview_same_reactor_multiple_rows_errors(db_session: Session):
    _seed_experiment(db_session, "HPHT_ST005", 6605, ExperimentStatus.COMPLETED, "HPHT")
    _seed_experiment(db_session, "HPHT_ST006", 6606, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number"],
        [["HPHT_ST005", "ONGOING", 4], ["HPHT_ST006", "ONGOING", 4]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert len(preview.errors) == 1
    assert "Reactor 4" in preview.errors[0]
    assert "HPHT_ST005" in preview.errors[0]
    assert "HPHT_ST006" in preview.errors[0]
    assert preview.changes == []


def test_preview_serum_rows_same_reactor_do_not_conflict(db_session: Session):
    """The same-reactor conflict check only applies to HPHT/Core Flood rows."""
    _seed_experiment(db_session, "Serum_ST001", 6607, ExperimentStatus.COMPLETED, "Serum")
    _seed_experiment(db_session, "Serum_ST002", 6608, ExperimentStatus.COMPLETED, "Serum")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number"],
        [["Serum_ST001", "ONGOING", 4], ["Serum_ST002", "ONGOING", 4]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.errors == []
    assert len(preview.changes) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/services/bulk_uploads/test_experiment_status.py -v`
Expected: FAIL — `AttributeError: 'StatusChangePreview' object has no attribute 'changes'` (or similar), since the current dataclass only has `to_ongoing`/`to_completed`.

- [ ] **Step 3: Rewrite `backend/services/bulk_uploads/experiment_status.py`**

Write the full file (this keeps the current `apply_status_changes` and `manage_reactor_occupancy` methods byte-for-byte identical to today — Tasks 3–4 rewrite them):

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/services/bulk_uploads/test_experiment_status.py -v`
Expected: All tests in the file PASS (the preview-section tests written in Step 1; `apply_status_changes` still uses the old signature so no other test file references it yet).

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/experiment_status.py tests/services/bulk_uploads/test_experiment_status.py
git commit -m "$(cat <<'EOF'
[#66] Rework status preview to per-row model

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 2: Preview — reactor demotion planning (read-only)

**Files:**
- Modify: `backend/services/bulk_uploads/experiment_status.py` (extend `preview_status_changes_from_excel`, add 3 module-level helpers)
- Test: `tests/services/bulk_uploads/test_experiment_status.py` (append demotion-planning tests)

**Interfaces:**
- Consumes: `PlannedChange`, `PlannedDemotion`, `StatusChangePreview`, `_is_eligible_for_occupancy` from Task 1.
- Produces: module-level `_occupant_is_older(occupant_date: date | None, incoming_date: date | None) -> bool`, `_demoted_message(reactor_number: int, demoted_id: str, new_id: str) -> str`, `_not_demoted_message(reactor_number: int, occupant_id: str, new_id: str) -> str`. `preview_status_changes_from_excel` now populates `demotions` and `warnings` on the returned `StatusChangePreview` (previously always `[]`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/bulk_uploads/test_experiment_status.py`:

```python
# ---------------------------------------------------------------------------
# Reactor demotion planning (read-only — preview does not mutate the DB)
# ---------------------------------------------------------------------------

def test_preview_demotes_older_hpht_occupant_in_same_reactor(db_session: Session):
    from datetime import datetime

    _seed_experiment(
        db_session, "HPHT_ST010", 6610, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=5, date=datetime(2026, 1, 1),
    )
    _seed_experiment(db_session, "HPHT_ST011", 6611, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_ST011", "ONGOING", 5, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.errors == []
    assert len(preview.demotions) == 1
    assert preview.demotions[0].experiment_id == "HPHT_ST010"
    assert preview.demotions[0].triggering_experiment_id == "HPHT_ST011"
    assert any("HPHT_ST010" in w and "COMPLETED" in w for w in preview.warnings)


def test_preview_demotes_older_core_flood_occupant_in_same_reactor(db_session: Session):
    from datetime import datetime

    _seed_experiment(
        db_session, "CF_ST001", 6612, ExperimentStatus.ONGOING, "Core Flood",
        reactor_number=1, date=datetime(2026, 1, 1),
    )
    _seed_experiment(db_session, "CF_ST002", 6613, ExperimentStatus.COMPLETED, "Core Flood")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["CF_ST002", "ONGOING", 1, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.errors == []
    demoted_ids = [d.experiment_id for d in preview.demotions]
    assert "CF_ST001" in demoted_ids


def test_preview_warns_no_demote_when_occupant_newer(db_session: Session):
    from datetime import datetime

    _seed_experiment(
        db_session, "HPHT_ST012", 6614, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=6, date=datetime(2026, 6, 1),
    )
    _seed_experiment(db_session, "HPHT_ST013", 6615, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_ST013", "ONGOING", 6, "2026-01-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.errors == []
    assert preview.demotions == []
    assert any("HPHT_ST012" in w for w in preview.warnings)


def test_preview_warns_no_demote_when_occupant_equal_date(db_session: Session):
    """Open Item #4: same-day → warn, do not demote."""
    from datetime import datetime

    _seed_experiment(
        db_session, "HPHT_ST014", 6616, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=7, date=datetime(2026, 6, 1),
    )
    _seed_experiment(db_session, "HPHT_ST015", 6617, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_ST015", "ONGOING", 7, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.demotions == []
    assert any("HPHT_ST014" in w for w in preview.warnings)


def test_preview_warns_no_demote_when_incoming_date_missing(db_session: Session):
    """Open Item #1: missing incoming date → don't demote, warn."""
    from datetime import datetime

    _seed_experiment(
        db_session, "HPHT_ST016", 6618, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=8, date=datetime(2026, 1, 1),
    )
    _seed_experiment(db_session, "HPHT_ST017", 6619, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number"],
        [["HPHT_ST017", "ONGOING", 8]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.demotions == []
    assert any("HPHT_ST016" in w for w in preview.warnings)


def test_preview_warns_no_demote_when_occupant_date_missing(db_session: Session):
    """Open Item #1: missing occupant date → don't demote, warn."""
    _seed_experiment(
        db_session, "HPHT_ST018", 6620, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=9, date=None,
    )
    _seed_experiment(db_session, "HPHT_ST019", 6621, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_ST019", "ONGOING", 9, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.demotions == []
    assert any("HPHT_ST018" in w for w in preview.warnings)


def test_preview_serum_ongoing_with_reactor_no_demotion(db_session: Session):
    """Non-occupancy types never trigger demotion, even if ONGOING with a reactor_number."""
    from datetime import datetime

    _seed_experiment(
        db_session, "Serum_ST003", 6622, ExperimentStatus.ONGOING, "Serum",
        reactor_number=10, date=datetime(2026, 1, 1),
    )
    _seed_experiment(db_session, "Serum_ST004", 6623, ExperimentStatus.COMPLETED, "Serum")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["Serum_ST004", "ONGOING", 10, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.demotions == []
    assert preview.warnings == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/services/bulk_uploads/test_experiment_status.py -v -k demote or -k occupant or -k missing_date`
Expected: FAIL — `preview.demotions` is always `[]` and `preview.warnings` is always `[]` (demotion planning not implemented yet).

- [ ] **Step 3: Add the demotion-planning helpers and extend `preview_status_changes_from_excel`**

Add these three module-level functions to `backend/services/bulk_uploads/experiment_status.py`, directly below `_is_eligible_for_occupancy`:

```python
def _occupant_is_older(occupant_date, incoming_date) -> bool:
    """True only when both dates are present and the occupant started strictly earlier."""
    if occupant_date is None or incoming_date is None:
        return False
    return occupant_date < incoming_date


def _demoted_message(reactor_number: int, demoted_id: str, new_id: str) -> str:
    return (
        f"Reactor {reactor_number}: Marked experiment '{demoted_id}' "
        f"as COMPLETED (replaced by '{new_id}')"
    )


def _not_demoted_message(reactor_number: int, occupant_id: str, new_id: str) -> str:
    return (
        f"Reactor {reactor_number}: '{occupant_id}' was NOT completed — its start date "
        f"is not older than '{new_id}''s (or a start date is missing on one of them). "
        f"Manual review needed."
    )
```

In `preview_status_changes_from_excel`, replace the final line:

```python
        return StatusChangePreview(changes, [], missing_ids, [], [])
```

with:

```python
        demotions: List[PlannedDemotion] = []
        warnings: List[str] = []

        for r in parsed_rows:
            exp = exp_by_id.get(r["experiment_id"])
            if exp is None or r["status"] != ExperimentStatus.ONGOING.value or r["reactor_number"] is None:
                continue
            exp_type = exp.conditions.experiment_type if exp.conditions else None
            if not _is_eligible_for_occupancy(exp_type):
                continue

            occupants = db.query(Experiment).join(
                ExperimentalConditions,
                Experiment.id == ExperimentalConditions.experiment_fk,
            ).filter(
                Experiment.id != exp.id,
                Experiment.status == ExperimentStatus.ONGOING,
                ExperimentalConditions.reactor_number == r["reactor_number"],
            ).all()

            incoming_date = r["date"].date() if r["date"] is not None else None

            for occ in occupants:
                occ_date = occ.date.date() if occ.date else None
                if _occupant_is_older(occ_date, incoming_date):
                    demotions.append(PlannedDemotion(
                        experiment_id=occ.experiment_id,
                        experiment_pk=occ.id,
                        reactor_number=r["reactor_number"],
                        triggering_experiment_id=exp.experiment_id,
                    ))
                    warnings.append(_demoted_message(r["reactor_number"], occ.experiment_id, exp.experiment_id))
                else:
                    warnings.append(_not_demoted_message(r["reactor_number"], occ.experiment_id, exp.experiment_id))

        return StatusChangePreview(changes, demotions, missing_ids, [], warnings)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/services/bulk_uploads/test_experiment_status.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/experiment_status.py tests/services/bulk_uploads/test_experiment_status.py
git commit -m "$(cat <<'EOF'
[#66] Plan reactor demotions in status preview

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 3: `manage_reactor_occupancy` — optional start-date guard

**Files:**
- Modify: `backend/services/bulk_uploads/experiment_status.py` (add `_UNSET` sentinel, extend `manage_reactor_occupancy`)
- Test: `tests/services/bulk_uploads/test_experiment_status.py` (append `manage_reactor_occupancy`-focused tests)

**Interfaces:**
- Consumes: `_demoted_message`, `_not_demoted_message` from Task 2.
- Produces: `ExperimentStatusService.manage_reactor_occupancy(db, new_experiment, reactor_number, commit=True, newer_than=_UNSET) -> Tuple[int, List[str]]`. Callers that omit `newer_than` get byte-identical behavior to today (unconditional demotion of every ONGOING occupant in the reactor). Callers that pass `newer_than` (a `datetime` or `None`) activate the date guard: an occupant is demoted only if its `date` is strictly older (by calendar date) than `newer_than`; a missing occupant date, a missing `newer_than`, or a newer-or-equal occupant date produces a warning instead.

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/bulk_uploads/test_experiment_status.py`:

```python
# ---------------------------------------------------------------------------
# manage_reactor_occupancy — start-date guard
# ---------------------------------------------------------------------------

def test_manage_reactor_occupancy_legacy_call_still_demotes_unconditionally(db_session: Session):
    """Regression: callers that don't pass newer_than (new_experiments.py, legacy create)
    keep demoting regardless of start dates."""
    from datetime import datetime

    occupant = _seed_experiment(
        db_session, "HPHT_ST020", 6624, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=11, date=datetime(2026, 12, 31),  # newer than the incoming experiment
    )
    new_exp = _seed_experiment(
        db_session, "HPHT_ST021", 6625, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=11, date=datetime(2026, 1, 1),
    )

    marked, warnings = ExperimentStatusService.manage_reactor_occupancy(
        db_session, new_exp, 11, commit=False,
    )

    assert marked == 1
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.COMPLETED
    assert any("COMPLETED" in w for w in warnings)


def test_manage_reactor_occupancy_guard_demotes_older_occupant(db_session: Session):
    from datetime import datetime

    occupant = _seed_experiment(
        db_session, "HPHT_ST022", 6626, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=12, date=datetime(2026, 1, 1),
    )
    new_exp = _seed_experiment(
        db_session, "HPHT_ST023", 6627, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=12, date=datetime(2026, 6, 1),
    )

    marked, warnings = ExperimentStatusService.manage_reactor_occupancy(
        db_session, new_exp, 12, commit=False, newer_than=datetime(2026, 6, 1),
    )

    assert marked == 1
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.COMPLETED


def test_manage_reactor_occupancy_guard_warns_on_newer_or_equal_occupant(db_session: Session):
    from datetime import datetime

    occupant = _seed_experiment(
        db_session, "HPHT_ST024", 6628, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=13, date=datetime(2026, 6, 1),
    )
    new_exp = _seed_experiment(
        db_session, "HPHT_ST025", 6629, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=13, date=datetime(2026, 1, 1),
    )

    marked, warnings = ExperimentStatusService.manage_reactor_occupancy(
        db_session, new_exp, 13, commit=False, newer_than=datetime(2026, 1, 1),
    )

    assert marked == 0
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.ONGOING
    assert any("HPHT_ST024" in w and "HPHT_ST025" in w for w in warnings)


def test_manage_reactor_occupancy_guard_warns_when_newer_than_is_none(db_session: Session):
    occupant = _seed_experiment(
        db_session, "HPHT_ST026", 6630, ExperimentStatus.ONGOING, "HPHT", reactor_number=14,
    )
    new_exp = _seed_experiment(
        db_session, "HPHT_ST027", 6631, ExperimentStatus.ONGOING, "HPHT", reactor_number=14,
    )

    marked, warnings = ExperimentStatusService.manage_reactor_occupancy(
        db_session, new_exp, 14, commit=False, newer_than=None,
    )

    assert marked == 0
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.ONGOING
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/services/bulk_uploads/test_experiment_status.py -v -k manage_reactor_occupancy`
Expected: FAIL — `TypeError: manage_reactor_occupancy() got an unexpected keyword argument 'newer_than'`.

- [ ] **Step 3: Add the guard**

Add the `_UNSET` sentinel directly below the `_OCCUPANCY_TYPES` constant:

```python
_UNSET = object()
```

Add `from datetime import datetime` to the top-of-file imports (alongside the existing `import io` line).

Replace the `manage_reactor_occupancy` method with:

```python
    @staticmethod
    def manage_reactor_occupancy(
        db: Session,
        new_experiment: Experiment,
        reactor_number: int,
        commit: bool = True,
        newer_than: datetime | None = _UNSET,
    ) -> Tuple[int, List[str]]:
        """
        Ensure only one experiment is ONGOING per reactor at a time.

        When a new experiment is set to ONGOING with a reactor number, this function
        marks other ONGOING experiments in the same reactor as COMPLETED.

        If `newer_than` is explicitly passed (even as None), a start-date guard is
        active: an occupant is only demoted if its `date` is strictly older (by
        calendar date) than `newer_than`; occupants with a missing date, or a date
        that is newer-or-equal, are left ONGOING with a warning instead. Omitting
        `newer_than` entirely preserves the original unconditional behavior relied
        on by `new_experiments.py` and the legacy create path.

        Args:
            db: Database session
            new_experiment: The experiment being created/updated
            reactor_number: The reactor number being assigned
            commit: Whether to commit changes (default True)
            newer_than: Optional start-date guard (see above)

        Returns:
            Tuple of (marked_completed_count, warnings)
        """
        warnings: List[str] = []
        marked_completed = 0
        guard_active = newer_than is not _UNSET

        try:
            if new_experiment.status != ExperimentStatus.ONGOING:
                return 0, []

            conflicting_experiments = db.query(Experiment).join(
                ExperimentalConditions,
                Experiment.id == ExperimentalConditions.experiment_fk
            ).filter(
                Experiment.id != new_experiment.id,
                Experiment.status == ExperimentStatus.ONGOING,
                ExperimentalConditions.reactor_number == reactor_number
            ).all()

            for exp in conflicting_experiments:
                if guard_active:
                    occ_date = exp.date.date() if exp.date else None
                    incoming_date = newer_than.date() if newer_than else None
                    if incoming_date is None or occ_date is None or occ_date >= incoming_date:
                        warnings.append(
                            _not_demoted_message(reactor_number, exp.experiment_id, new_experiment.experiment_id)
                        )
                        continue

                exp.status = ExperimentStatus.COMPLETED
                marked_completed += 1
                warnings.append(
                    _demoted_message(reactor_number, exp.experiment_id, new_experiment.experiment_id)
                )

            if commit:
                db.commit()

        except Exception as e:
            warnings.append(f"Error managing reactor occupancy: {e}")
            if commit:
                db.rollback()

        return marked_completed, warnings
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/services/bulk_uploads/test_experiment_status.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run the full bulk_uploads service suite to confirm `new_experiments.py`'s callers are unaffected**

Run: `pytest tests/services/bulk_uploads/ -v`
Expected: All tests PASS, including `tests/services/bulk_uploads/test_new_experiments.py` (uses `manage_reactor_occupancy` without `newer_than`).

- [ ] **Step 6: Commit**

```bash
git add backend/services/bulk_uploads/experiment_status.py tests/services/bulk_uploads/test_experiment_status.py
git commit -m "$(cat <<'EOF'
[#66] Add optional start-date guard to reactor occupancy

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 4: Apply — per-row writes + demotion execution

**Files:**
- Modify: `backend/services/bulk_uploads/experiment_status.py` (add `ApplyResult` dataclass, rewrite `apply_status_changes`)
- Test: `tests/services/bulk_uploads/test_experiment_status.py` (append apply-section tests)

**Interfaces:**
- Consumes: `StatusChangePreview`, `PlannedChange`, `_is_eligible_for_occupancy` from Task 1; `manage_reactor_occupancy(..., newer_than=...)` from Task 3.
- Produces: `ApplyResult` dataclass (`status_changes_applied: int`, `demotions_applied: int`, `reactor_updates: int`, `date_updates: int`, `warnings: List[str]`, `errors: List[str]`), `ExperimentStatusService.apply_status_changes(db: Session, preview: StatusChangePreview) -> ApplyResult`. This **replaces** the old `(db, experiment_ids_to_ongoing, reactor_number_map) -> Tuple[int, int, int, List[str]]` signature — Task 5 updates the router call site.

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/bulk_uploads/test_experiment_status.py`:

```python
# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "status,exp_num",
    [("ONGOING", 6700), ("COMPLETED", 6701), ("CANCELLED", 6702), ("QUEUED", 6703)],
)
def test_apply_sets_each_status_value(db_session: Session, status: str, exp_num: int):
    exp = _seed_experiment(db_session, f"HPHT_ST_{status}", exp_num, ExperimentStatus.ONGOING, "HPHT")

    xlsx = make_excel(["experiment_id", "status"], [[exp.experiment_id, status]])
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert preview.errors == []

    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.errors == []
    assert result.status_changes_applied == 1
    db_session.refresh(exp)
    assert exp.status == ExperimentStatus(status)


def test_apply_writes_date_when_provided(db_session: Session):
    exp = _seed_experiment(db_session, "HPHT_ST030", 6640, ExperimentStatus.ONGOING, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "date"],
        [["HPHT_ST030", "ONGOING", "2026-03-15"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.date_updates == 1
    db_session.refresh(exp)
    assert exp.date.date().isoformat() == "2026-03-15"


def test_apply_leaves_date_untouched_when_absent(db_session: Session):
    from datetime import datetime

    exp = _seed_experiment(
        db_session, "HPHT_ST031", 6641, ExperimentStatus.ONGOING, "HPHT", date=datetime(2026, 1, 1),
    )

    xlsx = make_excel(["experiment_id", "status"], [["HPHT_ST031", "COMPLETED"]])
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.date_updates == 0
    db_session.refresh(exp)
    assert exp.date == datetime(2026, 1, 1)


def test_apply_updates_reactor_number_when_provided(db_session: Session):
    exp = _seed_experiment(
        db_session, "HPHT_ST032", 6642, ExperimentStatus.ONGOING, "HPHT", reactor_number=1,
    )

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number"],
        [["HPHT_ST032", "ONGOING", 9]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.reactor_updates == 1
    db_session.refresh(exp)
    assert exp.conditions.reactor_number == 9


def test_apply_triggers_demotion_for_ongoing_hpht_with_older_occupant(db_session: Session):
    from datetime import datetime

    occupant = _seed_experiment(
        db_session, "HPHT_ST033", 6643, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=15, date=datetime(2026, 1, 1),
    )
    new_exp = _seed_experiment(db_session, "HPHT_ST034", 6644, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_ST034", "ONGOING", 15, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.demotions_applied == 1
    db_session.refresh(occupant)
    db_session.refresh(new_exp)
    assert occupant.status == ExperimentStatus.COMPLETED
    assert new_exp.status == ExperimentStatus.ONGOING


def test_apply_no_demotion_for_serum_type_even_with_reactor_number(db_session: Session):
    from datetime import datetime

    occupant = _seed_experiment(
        db_session, "Serum_ST005", 6645, ExperimentStatus.ONGOING, "Serum",
        reactor_number=16, date=datetime(2026, 1, 1),
    )
    new_exp = _seed_experiment(db_session, "Serum_ST006", 6646, ExperimentStatus.COMPLETED, "Serum")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["Serum_ST006", "ONGOING", 16, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.demotions_applied == 0
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.ONGOING


def test_apply_does_not_touch_unlisted_ongoing_experiment(db_session: Session):
    """The retired 'complete every unlisted ongoing HPHT' behavior must not fire."""
    unlisted = _seed_experiment(db_session, "HPHT_ST035", 6647, ExperimentStatus.ONGOING, "HPHT")
    listed = _seed_experiment(db_session, "HPHT_ST036", 6648, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(["experiment_id", "status"], [["HPHT_ST036", "ONGOING"]])
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    ExperimentStatusService.apply_status_changes(db_session, preview)

    db_session.refresh(unlisted)
    assert unlisted.status == ExperimentStatus.ONGOING


def test_full_round_trip_file_to_db_state(db_session: Session):
    """Full round-trip: file → preview → apply → DB state correct, including a demotion."""
    from datetime import datetime

    occupant = _seed_experiment(
        db_session, "HPHT_ST037", 6649, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=5, date=datetime(2026, 1, 1),
    )
    new_exp = _seed_experiment(db_session, "HPHT_ST038", 6650, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_ST038", "ONGOING", 5, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert preview.errors == []

    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.errors == []
    assert result.status_changes_applied == 1
    assert result.demotions_applied == 1
    db_session.refresh(new_exp)
    db_session.refresh(occupant)
    assert new_exp.status == ExperimentStatus.ONGOING
    assert new_exp.date.date().isoformat() == "2026-06-01"
    assert occupant.status == ExperimentStatus.COMPLETED
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/services/bulk_uploads/test_experiment_status.py -v -k apply or round_trip`
Expected: FAIL — `apply_status_changes()` still expects `(db, experiment_ids_to_ongoing, reactor_number_map)`, not a `StatusChangePreview`.

- [ ] **Step 3: Replace `apply_status_changes` and add `ApplyResult`**

Add the `ApplyResult` dataclass directly below `StatusChangePreview`:

```python
@dataclass
class ApplyResult:
    """Outcome of applying a StatusChangePreview."""
    status_changes_applied: int
    demotions_applied: int
    reactor_updates: int
    date_updates: int
    warnings: List[str]
    errors: List[str]
```

Replace the entire `apply_status_changes` method with:

```python
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

                if (
                    change.new_status == ExperimentStatus.ONGOING.value
                    and change.new_reactor_number is not None
                    and _is_eligible_for_occupancy(change.experiment_type)
                ):
                    newer_than = change.new_date.to_pydatetime() if change.new_date is not None else None
                    marked, occ_warnings = ExperimentStatusService.manage_reactor_occupancy(
                        db, exp, change.new_reactor_number, commit=False, newer_than=newer_than,
                    )
                    demotions_applied += marked
                    warnings.extend(occ_warnings)

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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/services/bulk_uploads/test_experiment_status.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/experiment_status.py tests/services/bulk_uploads/test_experiment_status.py
git commit -m "$(cat <<'EOF'
[#66] Apply per-row status changes and reactor demotions

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 5: Router — wire the new preview/apply shapes

**Files:**
- Modify: `backend/api/routers/bulk_uploads.py:580-626` (`upload_experiment_status`)
- Test: `tests/api/test_bulk_uploads.py:315-336` (`test_experiment_status_returns_upload_response_shape`)

**Interfaces:**
- Consumes: `ExperimentStatusService.preview_status_changes_from_excel`, `ExperimentStatusService.apply_status_changes` (Tasks 1–4), `UploadResponse` (`backend/api/schemas/bulk_upload.py` — unchanged, already has `warnings: list[str] = []`).

- [ ] **Step 1: Update the failing router test**

In `tests/api/test_bulk_uploads.py`, replace `test_experiment_status_returns_upload_response_shape` (currently ~line 315) with:

```python
def test_experiment_status_returns_upload_response_shape(client):
    mock_preview = MagicMock()
    mock_preview.errors = []
    mock_preview.missing_ids = []

    mock_result = MagicMock()
    mock_result.status_changes_applied = 0
    mock_result.demotions_applied = 0
    mock_result.reactor_updates = 0
    mock_result.date_updates = 0
    mock_result.warnings = []
    mock_result.errors = []

    mock_svc = MagicMock()
    mock_svc.preview_status_changes_from_excel.return_value = mock_preview
    mock_svc.apply_status_changes.return_value = mock_result
    fake_mod = MagicMock()
    fake_mod.ExperimentStatusService = mock_svc

    with patch.dict(sys.modules, {
        "backend.services.bulk_uploads.experiment_status": fake_mod,
    }):
        resp = client.post(
            "/api/bulk-uploads/experiment-status",
            files={"file": ("status.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
        )
    assert resp.status_code == 200
    _assert_upload_shape(resp.json())
```

Run: `pytest tests/api/test_bulk_uploads.py -v -k experiment_status`
Expected: FAIL — router still calls `apply_status_changes(db, to_ongoing_ids, reactor_map)` with the old 3-arg signature and reads `preview.to_ongoing`, which the mock no longer provides.

- [ ] **Step 2: Rewrite the router endpoint**

In `backend/api/routers/bulk_uploads.py`, replace the entire `upload_experiment_status` function (currently lines 580–626) with:

```python
@router.post("/experiment-status", response_model=UploadResponse)
async def upload_experiment_status(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload an Experiment Status Excel file (per-row status/date/reactor updates)."""
    from backend.services.bulk_uploads.experiment_status import ExperimentStatusService  # noqa: PLC0415
    file_bytes = await file.read()
    try:
        preview = ExperimentStatusService.preview_status_changes_from_excel(db, file_bytes)
        if preview.errors:
            return UploadResponse(
                created=0, updated=0, skipped=len(preview.missing_ids),
                errors=preview.errors,
                message="Validation failed — no changes applied",
            )
        result = ExperimentStatusService.apply_status_changes(db, preview)
        if not result.errors:
            db.commit()
        else:
            db.rollback()
    except Exception as exc:
        db.rollback()
        log.error("experiment_status_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(
        created=0,
        updated=result.status_changes_applied,
        skipped=len(preview.missing_ids),
        errors=result.errors,
        warnings=result.warnings,
        feedbacks=[{
            "status_changes": result.status_changes_applied,
            "demotions": result.demotions_applied,
            "reactor_updates": result.reactor_updates,
            "date_updates": result.date_updates,
        }],
        message=(
            f"Status update: {result.status_changes_applied} row(s) applied, "
            f"{result.demotions_applied} reactor demotion(s), "
            f"{len(preview.missing_ids)} not found"
        ),
    )
```

- [ ] **Step 3: Run the tests to verify they pass**

Run: `pytest tests/api/test_bulk_uploads.py -v`
Expected: All tests PASS (this includes the parametrized auth/file-required tests at lines ~356 and ~391, which already reference `/api/bulk-uploads/experiment-status` and are unaffected by the body rewrite).

- [ ] **Step 4: Commit**

```bash
git add backend/api/routers/bulk_uploads.py tests/api/test_bulk_uploads.py
git commit -m "$(cat <<'EOF'
[#66] Wire per-row status endpoint to new service shapes

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 6: Template — 4 columns + INSTRUCTIONS sheet

**Files:**
- Modify: `backend/api/routers/bulk_uploads.py:988-993` (`_get_template_bytes`, `"experiment-status"` branch)
- Test: `tests/api/test_bulk_uploads.py` (append a template-content test)

**Interfaces:**
- Consumes: nothing new — `_get_template_bytes(upload_type, mode=None) -> bytes` keeps its existing signature; only the `"experiment-status"` branch's body changes.

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_bulk_uploads.py` (near the other template tests, after `test_template_download_returns_xlsx`):

```python
def test_experiment_status_template_has_four_columns_and_instructions(client):
    import openpyxl

    resp = client.get("/api/bulk-uploads/templates/experiment-status")
    assert resp.status_code == 200

    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    ws = wb["Template"]
    headers = [c.value for c in ws[1]]
    assert headers == ["experiment_id", "status", "reactor_number", "date"]
    assert ws.cell(row=2, column=1).value == "HPHT_072"
    assert ws.cell(row=2, column=2).value == "ONGOING"

    assert "INSTRUCTIONS" in wb.sheetnames
    inst_col_a = [c.value for c in wb["INSTRUCTIONS"]["A"] if c.value]
    assert "status" in inst_col_a
    assert "date" in inst_col_a
```

Run: `pytest tests/api/test_bulk_uploads.py -v -k experiment_status_template`
Expected: FAIL — `KeyError: 'INSTRUCTIONS'` (current template is a 2-column `_simple_template` call with no INSTRUCTIONS sheet).

- [ ] **Step 2: Rewrite the template branch**

In `backend/api/routers/bulk_uploads.py`, replace:

```python
    if upload_type == "experiment-status":
        return _simple_template(
            headers=["experiment_id", "reactor_number"],
            required={"experiment_id"},
            example_row=["HPHT_072", 3],
        )
```

with:

```python
    if upload_type == "experiment-status":
        import openpyxl  # noqa: PLC0415
        from openpyxl.styles import PatternFill, Font, Alignment  # noqa: PLC0415

        headers = ["experiment_id", "status", "reactor_number", "date"]
        required = {"experiment_id", "status"}
        example_row = ["HPHT_072", "ONGOING", 3, "2026-07-15"]
        req_fill = PatternFill(start_color="FFD700", end_color="FFD700", fill_type="solid")
        opt_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Template"
        for col, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.font = Font(bold=True)
            cell.fill = req_fill if h in required else opt_fill
            cell.alignment = Alignment(horizontal="center")
            ws.column_dimensions[cell.column_letter].width = max(len(h) + 4, 18)
        for col, val in enumerate(example_row, start=1):
            ws.cell(row=2, column=col, value=val)

        ws_inst = wb.create_sheet("INSTRUCTIONS")
        ws_inst.column_dimensions["A"].width = 30
        ws_inst.column_dimensions["B"].width = 80
        instructions = [
            ("Column", "Notes"),
            ("experiment_id", "REQUIRED. Must match an existing experiment_id."),
            ("status", "REQUIRED. One of ONGOING, COMPLETED, CANCELLED, QUEUED (case-insensitive)."),
            ("reactor_number", "Integer. Only meaningful for HPHT / Core Flood experiments."),
            (
                "date",
                "Experiment start date (YYYY-MM-DD or Excel date). Used both to set the "
                "experiment's start date and to decide reactor demotion order.",
            ),
            (
                "Demotion rule",
                "Setting an HPHT or Core Flood experiment to ONGOING with a reactor_number "
                "completes an older experiment currently ongoing in the same reactor. If the "
                "reactor is held by a newer-or-equal-dated experiment (or either start date "
                "is missing), nothing is demoted and a warning is returned.",
            ),
        ]
        for r_idx, (col_name, note) in enumerate(instructions, start=1):
            name_cell = ws_inst.cell(row=r_idx, column=1, value=col_name)
            note_cell = ws_inst.cell(row=r_idx, column=2, value=note)
            if r_idx == 1:
                name_cell.font = Font(bold=True)
                note_cell.font = Font(bold=True)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
```

- [ ] **Step 3: Run the tests to verify they pass**

Run: `pytest tests/api/test_bulk_uploads.py -v`
Expected: All tests PASS, including the pre-existing `test_template_download_returns_xlsx[experiment-status]` parametrization.

- [ ] **Step 4: Commit**

```bash
git add backend/api/routers/bulk_uploads.py tests/api/test_bulk_uploads.py
git commit -m "$(cat <<'EOF'
[#66] Regenerate experiment-status template with 4 columns

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 7: Frontend — tile copy update

**Files:**
- Modify: `frontend/src/pages/BulkUploads.tsx:335-346`

**Interfaces:**
- Consumes: nothing (copy-only change). The tile already renders `result.warnings` generically via `frontend/src/pages/BulkUploadRow.tsx` (confirmed present at lines ~224 and ~253–268) — no component change needed there.

- [ ] **Step 1: Update the tile copy**

In `frontend/src/pages/BulkUploads.tsx`, replace:

```tsx
        {/* 11 — Experiment Status Update */}
        <UploadRow
          id="experiment-status"
          title="Experiment Status Update"
          description="Bulk-set ONGOING / COMPLETED statuses"
          helpText="Required column: experiment_id. Listed experiments are set to ONGOING; other HPHT experiments currently ONGOING are set to COMPLETED. Optional: reactor_number column."
          accept=".xlsx,.xls,.csv"
          uploadFn={(file) => bulkUploadsApi.uploadExperimentStatus(file)}
          templateType="experiment-status"
          isOpen={isOpen('experiment-status')}
          onToggle={() => toggle('experiment-status')}
        />
```

with:

```tsx
        {/* 11 — Experiment Status Update */}
        <UploadRow
          id="experiment-status"
          title="Experiment Status Update"
          description="Bulk-set experiment status (ONGOING / COMPLETED / QUEUED / CANCELLED)"
          helpText="Required columns: experiment_id, status. Optional: reactor_number, date (start date). Setting an HPHT or Core Flood experiment to ONGOING with a reactor_number auto-completes an older experiment in the same reactor; a newer-or-equal-dated occupant triggers a warning instead of a completion."
          accept=".xlsx,.xls,.csv"
          uploadFn={(file) => bulkUploadsApi.uploadExperimentStatus(file)}
          templateType="experiment-status"
          isOpen={isOpen('experiment-status')}
          onToggle={() => toggle('experiment-status')}
        />
```

- [ ] **Step 2: Verify no frontend unit test targets this copy**

Run: `cd frontend && npx vitest run src -t "experiment"`
Expected: PASS or no matching tests found (no existing test asserts on this tile's copy strings — confirmed via `grep -r "Bulk-set ONGOING" frontend/src` returning no test-file matches).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/BulkUploads.tsx
git commit -m "$(cat <<'EOF'
[#66] Update Experiment Status tile copy for per-row model

- Tests added: no
- Docs updated: no
EOF
)"
```

---

### Task 8: Documentation + final verification

**Files:**
- Modify: `docs/api/API_REFERENCE.md:280-282` (endpoint row + template row)
- Modify: `docs/user_guide/BULK_UPLOADS.md:269-290` (section "11 — Experiment Status Update")

**Interfaces:** none (documentation only). The `PostToolUse` hook auto-copies both files into `docs/project_context/` after each `Write`/`Edit` — do not write to `docs/project_context/` directly.

- [ ] **Step 1: Update `docs/api/API_REFERENCE.md`**

Replace the line (currently ~280):

```
| POST | `/api/bulk-uploads/experiment-status` | Preview + apply bulk ONGOING/COMPLETED transitions. |
```

with:

```
| POST | `/api/bulk-uploads/experiment-status` | Per-row status/date/reactor update. HPHT/Core Flood rows set to ONGOING with a reactor_number auto-complete an older occupant in the same reactor (date-gated); no blanket "complete unlisted HPHT" behavior. |
```

- [ ] **Step 2: Rewrite `docs/user_guide/BULK_UPLOADS.md` section 11**

Replace the entire section (currently lines 269–290, from `## 11 — Experiment Status Update` through the line before `## 12 — pXRF Readings`):

```markdown
## 11 — Experiment Status Update

**Endpoint:** `POST /api/bulk-uploads/experiment-status`
**Template:** available

Set each experiment's status explicitly, per row. Applies to experiments of any
type — Serum, Autoclave, HPHT, Core Flood.

Logic:
- Each row sets its own `status` (`ONGOING`, `COMPLETED`, `CANCELLED`, or `QUEUED`; case-insensitive).
- If `date` is provided, it updates the experiment's start date (`Experiment.date`).
- If `reactor_number` is provided, it updates `ExperimentalConditions.reactor_number`.
- Setting an **HPHT or Core Flood** row to `ONGOING` with a `reactor_number` completes
  an experiment already `ONGOING` in that same reactor, **only if** the occupant's
  start date is older than the incoming row's start date.
- If the reactor is held by a newer-or-equal-dated experiment (or either date is
  missing), nothing is demoted and a warning names both experiments and the reactor.
- Experiment IDs not found in the database are reported as `missing_ids`.
- There is no blanket "complete every unlisted ongoing HPHT" behavior — an
  experiment not referenced in the file is never touched.
- Invalid `status`/`reactor_number`/`date` values, or two rows targeting the same
  `reactor_number`, hard-fail the whole upload with no changes applied. A missing
  `experiment_id` or `status` column does the same.

The endpoint runs preview validation and apply in one request (no separate
confirm step): upload the file and the response reports what was applied.

| Column | Required | Notes |
|--------|----------|-------|
| experiment_id | ✓ | |
| status | ✓ | ONGOING, COMPLETED, CANCELLED, or QUEUED (case-insensitive) |
| reactor_number | | Optional; only meaningful for HPHT / Core Flood experiments |
| date | | Optional; experiment start date (YYYY-MM-DD or Excel date) |

---
```

- [ ] **Step 3: Run the full backend and frontend test suites**

Run: `pytest tests/ -v --ignore=tests/test_pg_backup_restore.py`
Expected: All PASS (the ignored file requires a live `experiments_restore_test` Postgres instance — a pre-existing, unrelated infra dependency per `docs/working/plan.md`'s M8 notes).

Run: `cd frontend && npx vitest run src`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/api/API_REFERENCE.md docs/user_guide/BULK_UPLOADS.md docs/project_context/API_REFERENCE.md docs/project_context/BULK_UPLOADS.md
git commit -m "$(cat <<'EOF'
[#66] Document per-row experiment status upload

- Tests added: no
- Docs updated: yes
EOF
)"
```

---

## Self-Review Notes

- **Spec coverage:** Template (Task 6), per-row parse/validate (Task 1), demotion planning + execution (Tasks 2–4), reactor helper guard + backward compatibility (Task 3), router (Task 5), frontend copy (Task 7), all four confirmed open items (Global Constraints + Tasks 1–4 tests), all Testing-section bullet points (per-row status × 4 values, date write/untouched, HPHT + Core Flood demotion, newer/equal/missing-date warnings, unlisted-never-touched, invalid-row errors, missing-column hard errors, same-reactor-two-rows, `manage_reactor_occupancy` regression), docs (Task 8).
- **Out of scope, confirmed not touched:** `new_experiments.py` logic itself (only its dependency, `manage_reactor_occupancy`, gains a parameter it never passes), reactor-number validation against a canonical registry, legacy Streamlit create path, `experiment_type` enum migration.
- **Type consistency check:** `PlannedChange.experiment_type` (Task 1) is read by `_is_eligible_for_occupancy` in both preview (Task 2) and apply (Task 4) — same function, same input type (`str | None`). `ApplyResult` fields (Task 4) match exactly what the router (Task 5) reads: `status_changes_applied`, `demotions_applied`, `reactor_updates`, `date_updates`, `warnings`, `errors`. `StatusChangePreview.errors`/`.missing_ids` (Task 1) are what the router checks before calling apply — unchanged shape through all tasks.
