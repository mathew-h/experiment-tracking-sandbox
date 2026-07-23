# Issue #68 — Fix db.expire_all() Discarding Unflushed Overwrite Writes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `overwrite=True` on the New Experiments bulk upload actually persist `status`, `sample_id`, `researcher`, and `date` changes to existing experiments, instead of having them silently reverted by `db.expire_all()`.

**Architecture:** `NewExperimentsUploadService.bulk_upsert_from_excel` (`backend/services/bulk_uploads/new_experiments.py`) sets the four fields directly on the ORM-mapped `Experiment` object in its update branch (lines 436–443) but never flushes before calling `db.expire_all()` at line 477. `Session.expire_all()` discards uncommitted attribute changes and forces a reload from the database on next access, so the writes vanish. Fix: add one `db.flush()` immediately before that `db.expire_all()` call so pending writes are persisted to the transaction (not lost) before the session is expired. TDD: write failing tests that reproduce every acceptance-criteria scenario against the current code, confirm they fail, then add the one-line fix and confirm they pass alongside the full existing bulk-upload test suite.

**Tech Stack:** Python, SQLAlchemy 2.x ORM, pytest, PostgreSQL (`experiments_test` DB via `tests/services/bulk_uploads/conftest.py`).

## Global Constraints

- `backend/services/bulk_uploads/` is a locked component (`.claude/CLAUDE.md` §5, `docs/LOCKED_COMPONENTS.md`) — this plan modifies it under explicit user instruction obtained during `/start-task` scope confirmation for issue #68. Do not touch any other bulk upload parser file.
- No schema/migration changes — this is a pure application-logic fix.
- Bug fix commit message format (per `.claude/CLAUDE.md` §8): `[#68] <imperative description>` with `- Tests added: yes` / `- Docs updated: yes|no`.
- Test DB: `experiments_test` (PostgreSQL) via the `db_session` fixture in `tests/services/bulk_uploads/conftest.py` — per-test transaction, rolled back after each test. Do not commit inside tests.
- Follow existing test file conventions in `tests/services/bulk_uploads/` (see `test_master_bulk_upload.py`, `excel_helpers.py`) rather than the standalone in-memory-SQLite pattern used by the older `tests/test_experiment_rename.py`.

---

### Task 1: Write failing regression tests reproducing the bug

**Files:**
- Create: `tests/services/bulk_uploads/test_new_experiments.py`
- Test: same file (this task *is* the test file)

**Interfaces:**
- Consumes: `NewExperimentsUploadService.bulk_upsert_from_excel(db, file_bytes) -> Tuple[int, int, int, List[str], List[str], List[str]]` (created, updated, skipped, errors, warnings, info_messages) — signature unchanged, defined in `backend/services/bulk_uploads/new_experiments.py:84`.
- Consumes: `make_excel(headers, rows, sheet_name)` and `make_excel_multisheet(sheets)` from `tests/services/bulk_uploads/excel_helpers.py`.
- Consumes: `db_session` fixture from `tests/services/bulk_uploads/conftest.py` (PostgreSQL, per-test rollback).
- Produces: nothing consumed by later tasks — Task 2 only needs this file to exist and its tests to currently fail.

- [ ] **Step 1: Write the failing tests**

Create `tests/services/bulk_uploads/test_new_experiments.py`:

```python
"""Tests for NewExperimentsUploadService.bulk_upsert_from_excel overwrite behavior.

Regression coverage for issue #68: db.expire_all() (called after the experiments-sheet
loop) was discarding unflushed status/sample_id/researcher/date writes made in the
update-existing-experiment branch before they were ever persisted.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import Experiment, ExperimentalConditions, SampleInfo
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads.new_experiments import NewExperimentsUploadService

from .excel_helpers import make_excel, make_excel_multisheet

_EXP_HEADERS = [
    "experiment_id", "old_experiment_id", "sample_id", "researcher",
    "date", "status", "initial_note", "overwrite",
]


def _seed_experiment(
    db: Session,
    experiment_id: str,
    exp_num: int,
    status: ExperimentStatus = ExperimentStatus.ONGOING,
    sample_id: str | None = None,
    researcher: str | None = None,
) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=exp_num,
        status=status,
        sample_id=sample_id,
        researcher=researcher,
    )
    db.add(exp)
    db.flush()
    return exp


def _seed_sample(db: Session, sample_id: str) -> SampleInfo:
    sample = SampleInfo(sample_id=sample_id)
    db.add(sample)
    db.flush()
    return sample


def _experiments_excel(rows: list[list]) -> bytes:
    return make_excel(_EXP_HEADERS, rows, sheet_name="experiments")


def test_overwrite_persists_status_sample_researcher_date(db_session: Session):
    """overwrite=True on an existing experiment must persist status/sample_id/researcher/date."""
    _seed_experiment(db_session, "HPHT_I68_001", 68001, status=ExperimentStatus.ONGOING)
    _seed_sample(db_session, "SAMPLE-I68-001")

    xlsx = _experiments_excel([
        ["HPHT_I68_001", None, "SAMPLE-I68-001", "JD", "2026-02-01", "QUEUED", None, True],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert updated == 1
    assert created == 0

    exp = db_session.query(Experiment).filter_by(experiment_id="HPHT_I68_001").first()
    assert exp.status == ExperimentStatus.QUEUED, "status overwrite was silently discarded"
    assert exp.sample_id == "SAMPLE-I68-001", "sample_id overwrite was silently discarded"
    assert exp.researcher == "JD", "researcher overwrite was silently discarded"
    assert exp.date is not None and exp.date.date().isoformat() == "2026-02-01", (
        "date overwrite was silently discarded"
    )


def test_reactivation_via_overwrite_demotes_prior_reactor_occupant(db_session: Session):
    """Setting an existing experiment back to ONGOING in an occupied reactor (via overwrite)
    must trigger manage_reactor_occupancy and demote the current occupant."""
    occupant = _seed_experiment(db_session, "HPHT_I68_010", 68010, status=ExperimentStatus.ONGOING)
    occupant_conditions = ExperimentalConditions(
        experiment_id=occupant.experiment_id,
        experiment_fk=occupant.id,
        reactor_number=7,
        experiment_type="HPHT",
    )
    db_session.add(occupant_conditions)
    _seed_experiment(db_session, "HPHT_I68_011", 68011, status=ExperimentStatus.COMPLETED)
    db_session.flush()

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["HPHT_I68_011", None, None, None, None, "ONGOING", None, True]],
        ),
        "conditions": (
            ["experiment_id", "reactor_number"],
            [["HPHT_I68_011", 7]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"

    reactivated = db_session.query(Experiment).filter_by(experiment_id="HPHT_I68_011").first()
    demoted = db_session.query(Experiment).filter_by(experiment_id="HPHT_I68_010").first()
    assert reactivated.status == ExperimentStatus.ONGOING
    assert demoted.status == ExperimentStatus.COMPLETED, (
        "reactor occupancy check saw the stale (pre-overwrite) status and never fired"
    )
    assert any("Auto-completed" in m for m in info), (
        f"expected an auto-completion info message, got: {info}"
    )


def test_rename_with_status_change_persists_both(db_session: Session):
    """old_experiment_id rename combined with a status change in the same row must
    persist both the rename and the status change."""
    _seed_experiment(db_session, "HPHT_I68_020", 68020, status=ExperimentStatus.ONGOING)

    xlsx = _experiments_excel([
        ["HPHT_I68_020_Renamed", "HPHT_I68_020", None, None, None, "QUEUED", None, True],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert updated == 1

    renamed = db_session.query(Experiment).filter_by(experiment_id="HPHT_I68_020_Renamed").first()
    assert renamed is not None, "rename was not persisted"
    assert renamed.status == ExperimentStatus.QUEUED, "status change alongside rename was discarded"


def test_new_experiment_creation_path_unaffected(db_session: Session):
    """New-experiment creation (flushed immediately, before expire_all runs) must be unaffected."""
    xlsx = _experiments_excel([
        ["HPHT_I68_030", None, None, "AB", "2026-01-10", "ONGOING", "Created via test", False],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1
    assert updated == 0

    exp = db_session.query(Experiment).filter_by(experiment_id="HPHT_I68_030").first()
    assert exp is not None
    assert exp.status == ExperimentStatus.ONGOING
    assert exp.researcher == "AB"
```

- [ ] **Step 2: Run the tests to verify they fail against current (buggy) code**

Run: `pytest tests/services/bulk_uploads/test_new_experiments.py -v`

Expected: `test_overwrite_persists_status_sample_researcher_date`, `test_reactivation_via_overwrite_demotes_prior_reactor_occupant`, and `test_rename_with_status_change_persists_both` all **FAIL** (assertion errors showing the stale/pre-overwrite values). `test_new_experiment_creation_path_unaffected` should **PASS** already (creation path is unaffected by the bug).

Note: an earlier draft of this plan included a fifth test, `test_overwrite_dirty_state_is_flushed_before_expire`, asserting `not db_session.dirty` after the call. It was dropped after Task 1 review: `Session.expire_all()` unconditionally clears an object's dirty/modified flag as part of expiring it, regardless of whether a flush happened first — so that assertion is true both before and after the Task 2 fix and can never fail. It provided no regression coverage beyond what `test_overwrite_persists_status_sample_researcher_date` already verifies.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/services/bulk_uploads/test_new_experiments.py
git commit -m "$(cat <<'EOF'
[#68] Add failing tests for overwrite expire_all bug

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 2: Fix `db.expire_all()` discarding unflushed writes

**Files:**
- Modify: `backend/services/bulk_uploads/new_experiments.py:476-477`
- Test: `tests/services/bulk_uploads/test_new_experiments.py` (from Task 1, no changes)

**Interfaces:**
- Consumes: nothing new — this task only edits the internals of `bulk_upsert_from_excel`; its public signature and return tuple are unchanged.
- Produces: nothing new — no other file depends on this change beyond the tests already written.

- [ ] **Step 1: Read the current code at the fix site**

`backend/services/bulk_uploads/new_experiments.py` currently reads (lines 473–477):

```python
        else:
            errors.append("Missing required 'experiments' sheet")

        # Expire session cache to ensure conditions/additives sheets see renamed experiments
        db.expire_all()
```

- [ ] **Step 2: Apply the fix**

Change lines 476–477 to flush pending writes before expiring:

```python
        else:
            errors.append("Missing required 'experiments' sheet")

        # Flush pending experiments-sheet field updates (status/sample_id/researcher/date,
        # renames) before expiring the session, so expire_all() reloads the NEW values
        # instead of discarding them. See issue #68.
        db.flush()
        db.expire_all()
```

- [ ] **Step 3: Run the new tests to verify they now pass**

Run: `pytest tests/services/bulk_uploads/test_new_experiments.py -v`

Expected: all 4 tests **PASS**.

- [ ] **Step 4: Run the full bulk-upload and rename regression suites**

Run: `pytest tests/services/bulk_uploads/ tests/test_experiment_rename.py tests/api/test_bulk_uploads.py -v`

Expected: all tests **PASS**, no regressions introduced by moving the flush earlier (e.g. no new constraint-violation errors surfacing sooner than before).

- [ ] **Step 5: Run the full test suite as a final check**

Run: `pytest tests/ -v`

Expected: all tests **PASS** (same total count as before this change, plus the 4 new tests from Task 1).

- [ ] **Step 6: Commit the fix**

```bash
git add backend/services/bulk_uploads/new_experiments.py
git commit -m "$(cat <<'EOF'
[#68] Flush before expire_all in new experiments upload

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

## Self-Review Notes

- **Spec coverage:** All acceptance criteria from issue #68 map to tests: status/sample_id/researcher/date persistence → `test_overwrite_persists_status_sample_researcher_date`; reactor auto-demotion on reactivation → `test_reactivation_via_overwrite_demotes_prior_reactor_occupant`; rename + field update in the same row → `test_rename_with_status_change_persists_both`; new-experiment creation regression → `test_new_experiment_creation_path_unaffected`. The issue's suggested `db.dirty` regression guard was evaluated and dropped (see Task 1 Step 2 note) — `Session.expire_all()` clears the dirty flag unconditionally, so that specific check can never fail regardless of whether the fix is present.
- **Locked component:** modification confirmed with user during `/start-task` scope confirmation before this plan was written.
- **No schema changes, no new dependencies, no docs updates needed** — this is a pure bug-fix inside existing service logic with no API contract or model change.
