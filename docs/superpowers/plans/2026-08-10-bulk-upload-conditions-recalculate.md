# Bulk Upload Conditions Recalculation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the New Experiments bulk upload compute the stored derived fields on every `ExperimentalConditions` row it touches, and backfill the rows already in the database, so `ferrous_iron_yield_h2_pct` stops coming back NULL for bulk-created experiments.

**Architecture:** `water_to_rock_ratio` and `total_ferrous_iron_g` are *stored* derived fields written by `recalculate_conditions()` in the calculation registry. Every write path in the codebase calls `recalculate()` after mutating a conditions row — except `backend/services/bulk_uploads/new_experiments.py`, which creates or modifies conditions rows in three places and only ever recalculates `ChemicalAdditive`. The fix records the primary key of every conditions row the upload touches and runs one recalculation pass at the end of the parse, after all three sheets have finished mutating them. The data side runs the existing purpose-built migration `backfill_total_ferrous_iron_017.py` plus the existing scalar-only pass from `recalculate_all_registry_012.py`; no new migration file is needed.

**Tech Stack:** Python 3.11, SQLAlchemy 2.x, pandas, openpyxl, FastAPI, PostgreSQL, pytest.

## Global Constraints

- Task mode is **`inline`**. Commit prefix is `[fix]`; description imperative, under 50 characters, no trailing period.
- Branch from `develop`: `git checkout -b fix/bulk-upload-conditions-recalc develop`. Never commit directly to `develop` or `main`. PRs use `--base develop`.
- `backend/services/bulk_uploads/` is a **locked component** (CLAUDE.md §5, `backend/CLAUDE.md`). This plan carries the user's explicit instruction to modify `new_experiments.py`; that authorisation covers **only** the helper added in Task 1 and the five insertions in Task 2 (accumulator declaration, three `touched_conditions_ids.add(...)` lines, recalculation pass). Do not refactor, reformat, or otherwise touch anything else in that file — including nearby code that looks improvable.
- `database/models/` is locked and models are storage-only. **No model changes in this plan** — no new columns, no migration, no `schema-checklist.md` run.
- Multi-line commit messages: write the message to a file under the session scratchpad and use `git commit -F <path>`. PowerShell here-strings break on embedded double quotes and git then reports it as a bad pathspec. Each task below names its message file as `<scratchpad>/msg-taskN.txt`; `<scratchpad>` is the session scratchpad directory given in your environment prompt.
- Never start, stop, or restart the uvicorn server. Assume port 8000 is already running.
- Run pytest **one process at a time** — the test DB (`experiments_test`) is shared and two concurrent runs corrupt its schema.
- `pytest -q` on the full suite has 3 pre-existing failures in `tests/test_pg_backup_restore.py` caused by `drop_all()` wiping `experiments_test`. Confirm they also fail on `develop` before attributing them to this work.
- Use `.venv/Scripts/python` and `.venv/Scripts/pytest` — bare `python`/`pytest` may not resolve.
- Anything written under `docs/` is auto-copied to `docs/project_context/` by a `PostToolUse` hook. Never write to `docs/project_context/` directly.

---

## Background: the defect this fixes

Verified against the production backup `docs/sample_data/experiments_20260810_010002.sql` (2026-08-10 01:00).

`SERUM_Catalyst_001a-t3` has a complete H2 chain and a NULL iron conversion:

```
h2_concentration = 353.88 ppm   gas_sampling_volume_ml = 30   gas_sampling_pressure_MPa = 0.101353
h2_micromoles    = 0.4415       h2_grams_per_ton_yield  = 0.8899
ferrous_iron_yield_h2_pct = NULL
```

`calculate_ferrous_iron_yield_h2` (`backend/services/calculations/scalar_calcs.py:24`) returns `None` when `total_ferrous_iron_g` is None, and that experiment's conditions row has it NULL — alongside a NULL `water_to_rock_ratio` on a row with `rock_mass_g = 1` and `water_volume_mL = 20`, where the ratio is plainly computable. Both derived fields empty on one row is the proof that `recalculate()` never ran on it. Running `recalculate` on that row produces `total_ferrous_iron_g = 0.0738 g`, `water_to_rock_ratio = 20.0`, and `Fe²⁺ %H₂ = 0.100%`.

This is **not** specific to GC direct injection. `SERUM_Cation_001a-t5` is a DI row with the same 30 mL / 14.7 psi geometry and the same sample `20250616_7`, and it *has* `ferrous_iron_yield_h2_pct = 0.0159%` — because a later elemental upload recalculated its conditions via `recalculate_conditions_for_samples` (`backend/services/elemental_composition_service.py:34`). The SERUM_Catalyst_001 vials were created 2026-07-24, after the last FeO upload for that sample, so nothing ever touched them.

Production scope — of 577 scalar rows with a computed `h2_micromoles`, 249 have no Fe²⁺ %H₂:

| Cause | Rows | Fixed by |
|---|---|---|
| `total_ferrous_iron_g` NULL, sample **has** FeO on record | 157 (144 experiments) | Task 4 (migration 017) |
| `total_ferrous_iron_g` NULL, sample has no FeO on record | 77 | Nothing — needs rock characterization first |
| `total_ferrous_iron_g` populated, scalar row stale | 15 | Task 4 (scalar pass) |

Separately, 185 conditions rows have **both** derived fields NULL with positive rock mass and water volume — the same signature, also affecting `water_to_rock_ratio` in Power BI.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/services/bulk_uploads/new_experiments.py` (modify) | Add module-level `_recalculate_touched_conditions`; record touched conditions PKs at the three write sites; run the pass before returning. |
| `tests/services/bulk_uploads/test_new_experiments_conditions_recalc.py` (create) | Unit tests for the helper; integration tests driving all three write paths through `bulk_upsert_from_excel`; one end-to-end test reproducing `SERUM_Catalyst_001a-t3`. |
| `docs/issues/issue-bulk-upload-never-recalculates-conditions.md` (create) | Incident record: root cause, production measurements, acceptance criteria, backfill outcome. |
| `docs/CALCULATIONS.md` (modify) | Record that the New Experiments upload now recalculates conditions derived fields, and which paths are covered. |
| `.claude/rules/MODELS.md` (modify) | One line on the `total_ferrous_iron_g` entry noting the bulk path recalculates and that 2026-07/08 rows needed a backfill. |

No new files in `backend/` and no new data-migration file: `backfill_total_ferrous_iron_017.py` and `recalculate_all_registry_012.py::_backfill_scalars` already do exactly what Task 4 needs.

---

## Task 1: `_recalculate_touched_conditions` helper

Add the helper and prove it in isolation. No wiring yet — Task 1 leaves the uploader's behaviour unchanged, so a reviewer can accept the helper's contract and error handling on its own.

**Files:**
- Modify: `backend/services/bulk_uploads/new_experiments.py` (insert after `find_parent_for_copy`, which ends at line 82, before the `@dataclass class FieldChange` at line 102)
- Test: `tests/services/bulk_uploads/test_new_experiments_conditions_recalc.py` (create)

**Interfaces:**
- Consumes: `recalculate` (already imported at `new_experiments.py:25`), `ExperimentalConditions` (already imported at line 14), `Session`, `Tuple`, `List` (already imported).
- Produces: `_recalculate_touched_conditions(db: Session, conditions_ids: set[int]) -> Tuple[int, List[str]]`, returning `(rows_recalculated, warnings)`. Task 2 calls this exact signature.

- [ ] **Step 1: Write the failing tests**

Create `tests/services/bulk_uploads/test_new_experiments_conditions_recalc.py`:

```python
# tests/services/bulk_uploads/test_new_experiments_conditions_recalc.py
"""Tests: the New Experiments bulk upload recalculates stored derived fields on
every ExperimentalConditions row it touches.

water_to_rock_ratio and total_ferrous_iron_g are written by recalculate_conditions()
in the calculation registry. This uploader never called it, so bulk-created
experiments landed with both NULL — which made ferrous_iron_yield_h2_pct and
ferrous_iron_yield_nh3_pct NULL on all of their scalar results, because
calculate_ferrous_iron_yield_h2() returns None when total_ferrous_iron_g is None.

Motivating production case: SERUM_Catalyst_001a-t3 (353.88 ppm H2, 30 mL, 14.7 psi)
had h2_micromoles = 0.4415 and h2_grams_per_ton_yield = 0.8899 but no Fe2+ %H2.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

import backend.services.calculations  # noqa: F401 — registers all calculators

from database import Analyte, ElementalAnalysis, Experiment, ExperimentalConditions, SampleInfo
from database.models.analysis import ExternalAnalysis
from backend.services.bulk_uploads.new_experiments import (
    NewExperimentsUploadService,
    _recalculate_touched_conditions,
)
from backend.services.elemental_composition_service import FE_IN_FEO_FRACTION

from .excel_helpers import make_excel, make_excel_multisheet

_EXP_HEADERS = [
    "experiment_id", "old_experiment_id", "sample_id", "researcher",
    "date", "status", "initial_note", "overwrite",
]


def _seed_sample_with_feo(db: Session, sample_id: str, feo_wt_pct: float) -> SampleInfo:
    """SampleInfo + Elemental ExternalAnalysis + FeO Analyte + ElementalAnalysis."""
    sample = SampleInfo(sample_id=sample_id)
    db.add(sample)
    db.flush()

    ext = ExternalAnalysis(sample_id=sample_id, analysis_type="Elemental")
    db.add(ext)
    db.flush()

    analyte = db.query(Analyte).filter_by(analyte_symbol="FeO").first()
    if not analyte:
        analyte = Analyte(analyte_symbol="FeO", unit="%")
        db.add(analyte)
        db.flush()

    db.add(ElementalAnalysis(
        external_analysis_id=ext.id,
        sample_id=sample_id,
        analyte_id=analyte.id,
        analyte_composition=feo_wt_pct,
    ))
    db.flush()
    return sample


def test_helper_sets_both_derived_fields(db_session: Session):
    """The helper writes water_to_rock_ratio and total_ferrous_iron_g, and counts the row."""
    _seed_sample_with_feo(db_session, "ROCK-RC-001", 9.5)
    exp = Experiment(experiment_id="SERUM_RC_001", experiment_number=990001,
                     sample_id="ROCK-RC-001")
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_id="SERUM_RC_001", experiment_fk=exp.id,
        rock_mass_g=1.0, water_volume_mL=20.0,
    )
    db_session.add(cond)
    db_session.flush()
    cond.total_ferrous_iron_g = None
    cond.water_to_rock_ratio = None
    db_session.flush()

    recalculated, warnings = _recalculate_touched_conditions(db_session, {cond.id})

    assert recalculated == 1
    assert warnings == []
    db_session.refresh(cond)
    assert cond.water_to_rock_ratio == pytest.approx(20.0)
    assert cond.total_ferrous_iron_g == pytest.approx(
        (9.5 / 100.0) * FE_IN_FEO_FRACTION * 1.0, rel=1e-4
    )


def test_helper_skips_unknown_id_without_warning(db_session: Session):
    """An id whose row is gone (rolled-back savepoint) is skipped, not warned about."""
    recalculated, warnings = _recalculate_touched_conditions(db_session, {987654321})

    assert recalculated == 0
    assert warnings == []


def test_helper_recalculates_remaining_rows_after_one_failure(db_session: Session, monkeypatch):
    """One unusable row must not cost the other rows their derived fields."""
    _seed_sample_with_feo(db_session, "ROCK-RC-002", 8.0)
    ids = []
    for n in (1, 2):
        exp = Experiment(experiment_id=f"SERUM_RC_01{n}", experiment_number=990010 + n,
                         sample_id="ROCK-RC-002")
        db_session.add(exp)
        db_session.flush()
        cond = ExperimentalConditions(
            experiment_id=f"SERUM_RC_01{n}", experiment_fk=exp.id,
            rock_mass_g=2.0, water_volume_mL=40.0,
        )
        db_session.add(cond)
        db_session.flush()
        cond.total_ferrous_iron_g = None
        cond.water_to_rock_ratio = None
        ids.append(cond.id)
    db_session.flush()

    # Fail on the lowest id only; the helper iterates sorted(conditions_ids).
    import backend.services.bulk_uploads.new_experiments as mod
    real = mod.recalculate
    first = min(ids)

    def flaky(instance, session):
        if getattr(instance, "id", None) == first:
            raise RuntimeError("boom")
        return real(instance, session)

    monkeypatch.setattr(mod, "recalculate", flaky)

    recalculated, warnings = _recalculate_touched_conditions(db_session, set(ids))

    assert recalculated == 1
    assert len(warnings) == 1
    assert "boom" in warnings[0]
    survivor = db_session.get(ExperimentalConditions, max(ids))
    assert survivor.water_to_rock_ratio == pytest.approx(20.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest tests/services/bulk_uploads/test_new_experiments_conditions_recalc.py -v`

Expected: collection error — `ImportError: cannot import name '_recalculate_touched_conditions' from 'backend.services.bulk_uploads.new_experiments'`.

- [ ] **Step 3: Add the helper**

In `backend/services/bulk_uploads/new_experiments.py`, insert between line 82 (`    return parent`, the end of `find_parent_for_copy`) and line 102 (`@dataclass`):

```python
def _recalculate_touched_conditions(
    db: Session, conditions_ids: set[int]
) -> Tuple[int, List[str]]:
    """Recompute stored derived fields on every conditions row this upload touched.

    `water_to_rock_ratio` and `total_ferrous_iron_g` are STORED derived fields,
    written by `recalculate_conditions()` in the calculation registry. Every other
    write path calls `recalculate()` itself — `backend/api/routers/conditions.py:103`
    and `:125`, `backend/api/routers/experiments.py:1329`,
    `database/lineage_utils.py:603`. This uploader never did, so bulk-created
    experiments landed with both fields NULL. That in turn made
    `ferrous_iron_yield_h2_pct` and `ferrous_iron_yield_nh3_pct` NULL on every one of
    their scalar results, because `calculate_ferrous_iron_yield_h2()` returns None
    when `total_ferrous_iron_g` is None — 157 production scalar rows as of
    2026-08-10, `SERUM_Catalyst_001a-t3` among them.

    Deliberately keyed on primary keys rather than ORM instances: `db.expire_all()`
    runs after the experiments-sheet loop (issue #68) and a per-row savepoint can be
    rolled back after a row is recorded, so an int is the only handle that stays
    valid. A row whose id no longer resolves is skipped silently — its savepoint was
    rolled back and there is nothing left to recalculate.

    One try/except per row, mirroring `recalculate_conditions_for_samples()`
    (`backend/services/elemental_composition_service.py:56-73`): one unusable row
    must not cost the rest of the upload its derived fields. No flush — the caller
    commits, as at every other `recalculate()` site in this module.

    Returns (rows_recalculated, warnings).
    """
    recalculated = 0
    warnings: List[str] = []
    for conditions_id in sorted(conditions_ids):
        conditions = db.get(ExperimentalConditions, conditions_id)
        if conditions is None:
            continue
        try:
            recalculate(conditions, db)
            recalculated += 1
        except Exception as e:
            warnings.append(
                f"[conditions] Could not recalculate derived fields for "
                f"'{conditions.experiment_id}': {e}"
            )
    return recalculated, warnings


```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/services/bulk_uploads/test_new_experiments_conditions_recalc.py -v`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/new_experiments.py tests/services/bulk_uploads/test_new_experiments_conditions_recalc.py
git commit -F <scratchpad>/msg-task1.txt
```

Message body for `msg-task1.txt`:

```
[fix] Add conditions recalculation helper

- New _recalculate_touched_conditions in new_experiments.py
- Not wired into the uploader yet (Task 2)
- Tests added: yes
- Docs updated: no
```

---

## Task 2: Wire the helper into all three conditions write paths

`new_experiments.py` creates or modifies an `ExperimentalConditions` row in three distinct places. Each records its row's primary key; one pass at the end recalculates them all, after every sheet has finished mutating them.

**Files:**
- Modify: `backend/services/bulk_uploads/new_experiments.py` — declaration after line 226; record sites after lines 781, 912, 1018; pass before line 1187
- Test: `tests/services/bulk_uploads/test_new_experiments_conditions_recalc.py` (append)

**Interfaces:**
- Consumes: `_recalculate_touched_conditions(db, conditions_ids) -> Tuple[int, List[str]]` from Task 1.
- Produces: no new public names. `bulk_upsert_from_excel` keeps its 6-value return and `_bulk_upsert_from_excel_impl` its 7-value return; the recalculation count is reported through the existing `info_messages` list, and failures through the existing `warnings` list.

**Behaviour note for the reviewer:** `recalculate_conditions()` cascades to every linked `ScalarResults` row (`backend/services/calculations/conditions_calcs.py:51-57`). For a brand-new experiment that is free — there are no results yet. For an `overwrite=TRUE` upload against an experiment that already has results, this now recalculates those scalar rows as well. That is the intended propagation (it is why the cascade exists), and it is what makes an `overwrite` that corrects `rock_mass_g` fix the stored yields instead of leaving them describing the old mass. It does mean an overwrite upload touching many-result experiments does more write work than before; the per-row `try`/`except` keeps one bad row from taking the batch down.

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/bulk_uploads/test_new_experiments_conditions_recalc.py`:

```python
# ---------------------------------------------------------------------------
# Integration: all three conditions write paths in bulk_upsert_from_excel
# ---------------------------------------------------------------------------

def test_conditions_sheet_path_recalculates(db_session: Session):
    """A conditions sheet row gets both derived fields computed by the upload."""
    _seed_sample_with_feo(db_session, "ROCK-RC-010", 9.5)

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["SERUM_RC_100", None, "ROCK-RC-010", "MH", "2026-08-03", "ONGOING", None, None]],
        ),
        "conditions": (
            ["experiment_id", "rock_mass_g", "water_volume_mL"],
            [["SERUM_RC_100", 1.0, 20.0]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    exp = db_session.query(Experiment).filter_by(experiment_id="SERUM_RC_100").one()
    cond = db_session.query(ExperimentalConditions).filter_by(experiment_fk=exp.id).one()
    assert cond.water_to_rock_ratio == pytest.approx(20.0)
    assert cond.total_ferrous_iron_g == pytest.approx(
        (9.5 / 100.0) * FE_IN_FEO_FRACTION * 1.0, rel=1e-4
    ), "conditions-sheet path did not recalculate total_ferrous_iron_g"
    assert any("Recalculated derived fields" in m for m in info)


def test_conditions_sheet_overwrite_of_existing_row_recalculates(db_session: Session):
    """An overwrite that changes rock_mass_g must recompute, not keep the old value."""
    _seed_sample_with_feo(db_session, "ROCK-RC-011", 10.0)
    exp = Experiment(experiment_id="SERUM_RC_110", experiment_number=990110,
                     sample_id="ROCK-RC-011")
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_id="SERUM_RC_110", experiment_fk=exp.id,
        rock_mass_g=1.0, water_volume_mL=20.0,
        total_ferrous_iron_g=(10.0 / 100.0) * FE_IN_FEO_FRACTION * 1.0,
        water_to_rock_ratio=20.0,
    )
    db_session.add(cond)
    db_session.flush()

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["SERUM_RC_110", None, None, None, None, None, None, True]],
        ),
        "conditions": (
            ["experiment_id", "rock_mass_g"],
            [["SERUM_RC_110", 4.0]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    db_session.refresh(cond)
    assert cond.water_to_rock_ratio == pytest.approx(5.0), "stale ratio after overwrite"
    assert cond.total_ferrous_iron_g == pytest.approx(
        (10.0 / 100.0) * FE_IN_FEO_FRACTION * 4.0, rel=1e-4
    ), "stale total_ferrous_iron_g after overwrite"


def test_parent_autocopy_path_recalculates(db_session: Session):
    """A sequential re-run with no conditions sheet row copies the parent's conditions
    and must still get its own derived fields computed."""
    _seed_sample_with_feo(db_session, "ROCK-RC-012", 9.5)
    parent = Experiment(experiment_id="SERUM_RC_120", experiment_number=990120,
                        sample_id="ROCK-RC-012")
    db_session.add(parent)
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_id="SERUM_RC_120", experiment_fk=parent.id,
        rock_mass_g=2.0, water_volume_mL=20.0, experiment_type="Serum",
    ))
    db_session.flush()

    # No conditions sheet at all -> the auto-copy pass creates the child's row.
    xlsx = make_excel(
        _EXP_HEADERS,
        [["SERUM_RC_120-2", None, "ROCK-RC-012", "MH", None, "ONGOING", None, None]],
        sheet_name="experiments",
    )
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    child = db_session.query(Experiment).filter_by(experiment_id="SERUM_RC_120-2").one()
    cond = db_session.query(ExperimentalConditions).filter_by(experiment_fk=child.id).one()
    assert cond.rock_mass_g == pytest.approx(2.0), "parent conditions were not copied"
    assert cond.water_to_rock_ratio == pytest.approx(10.0)
    assert cond.total_ferrous_iron_g == pytest.approx(
        (9.5 / 100.0) * FE_IN_FEO_FRACTION * 2.0, rel=1e-4
    ), "auto-copy path did not recalculate total_ferrous_iron_g"


def test_additives_only_path_recalculates(db_session: Session):
    """An experiment reaching conditions creation only through the additives sheet
    gets its derived fields computed (NULL here — that row carries no rock mass)."""
    _seed_sample_with_feo(db_session, "ROCK-RC-013", 9.5)

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["SERUM_RC_130", None, "ROCK-RC-013", "MH", None, "ONGOING", None, None]],
        ),
        "additives": (
            ["experiment_id", "compound", "amount", "unit"],
            [["SERUM_RC_130", "NiCl2", 5.0, "mg"]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    exp = db_session.query(Experiment).filter_by(experiment_id="SERUM_RC_130").one()
    cond = db_session.query(ExperimentalConditions).filter_by(experiment_fk=exp.id).one()
    # No rock_mass_g on this row, so both stay None — but explicitly computed as
    # None rather than left uncomputed, matching backfill_total_ferrous_iron_017's
    # stated philosophy.
    assert cond.total_ferrous_iron_g is None
    assert cond.water_to_rock_ratio is None
    assert any("Recalculated derived fields" in m for m in info)


# ---------------------------------------------------------------------------
# End-to-end: the production case that motivated this work
# ---------------------------------------------------------------------------

def test_bulk_created_experiment_gets_fe_yield_h2_on_scalar_result(db_session: Session):
    """Reproduces SERUM_Catalyst_001a-t3: a bulk-created vial with a DI H2 reading
    must end up with a non-NULL ferrous_iron_yield_h2_pct."""
    from backend.services.scalar_results_service import ScalarResultsService

    _seed_sample_with_feo(db_session, "20250616_RC", 9.5)

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["SERUM_RCat_001a-t3", None, "20250616_RC", "MH", "2026-08-03",
              "ONGOING", None, None]],
        ),
        "conditions": (
            ["experiment_id", "rock_mass_g", "water_volume_mL"],
            [["SERUM_RCat_001a-t3", 1.0, 20.0]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )
    assert errors == [], f"Unexpected errors: {errors}"

    # The real row's numbers: 353.88 ppm through a 30 mL / 14.7 psi DI injection.
    upsert = ScalarResultsService.create_scalar_result_ex(
        db_session, "SERUM_RCat_001a-t3",
        {
            "time_post_reaction": 3.0,
            "description": "DI, GC-A",
            "h2_concentration": 353.8808110781404,
            "gas_sampling_volume_ml": 30.0,
            "gas_sampling_pressure_MPa": 0.10135297199999999,
        },
    )
    scalar = upsert.experimental_result.scalar_data

    assert scalar.h2_micromoles == pytest.approx(0.4414611531787, rel=1e-6)
    assert scalar.ferrous_iron_yield_h2_pct is not None, (
        "Fe2+ %H2 is still NULL — total_ferrous_iron_g was not computed by the upload"
    )
    assert scalar.ferrous_iron_yield_h2_pct == pytest.approx(0.10015684764938, rel=1e-4)
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.venv/Scripts/pytest tests/services/bulk_uploads/test_new_experiments_conditions_recalc.py -v`

Expected: the 3 Task 1 tests pass; the 5 new tests fail on their `total_ferrous_iron_g` / `water_to_rock_ratio` / `ferrous_iron_yield_h2_pct` assertions (`assert None == approx(...)`), and the two `info` assertions fail because no `"Recalculated derived fields"` message exists yet.

- [ ] **Step 3: Declare the accumulator**

In `_bulk_upsert_from_excel_impl`, after line 226 (`overwrite_plan_by_exp_id: Dict[str, PlanOverwrite] = {}`), insert at 8-space indentation:

```python
        # Primary keys of every ExperimentalConditions row this upload creates or
        # modifies. Recalculated in one pass just before returning, after all three
        # sheets have finished mutating them — see _recalculate_touched_conditions.
        touched_conditions_ids: set[int] = set()
```

- [ ] **Step 4: Record at write site 1 (conditions sheet)**

In the conditions-sheet loop, between line 781 (`                            db.flush()`) and line 783 (`                        # Auto-copy from parent if experiment is flagged for copying`), insert at **24-space** indentation — outside the `if not conditions:` block, so a pre-existing row being overwritten is recorded too:

```python
                        touched_conditions_ids.add(conditions.id)
```

- [ ] **Step 5: Record at write site 2 (parent auto-copy)**

In the `for exp_id, parent in parent_for_copy.items():` loop, immediately after line 912 (`                db.flush()`), insert at **16-space** indentation:

```python
                touched_conditions_ids.add(conditions.id)
```

- [ ] **Step 6: Record at write site 3 (additives sheet)**

In the additives loop, immediately after line 1018 (`                        db.flush()`), insert at **24-space** indentation:

```python
                        touched_conditions_ids.add(conditions.id)
```

- [ ] **Step 7: Run the recalculation pass before returning**

Immediately before line 1187 (`        return created_exp, updated_exp, skipped, errors, warnings, info_messages, plan`), insert at 8-space indentation:

```python
        # One pass over every conditions row this upload touched, now that all three
        # sheets have finished mutating them. Deferred rather than inline at each
        # write site so a row reached by both the conditions and additives sheets is
        # recalculated once, from its final state.
        _cond_recalculated, _cond_recalc_warnings = _recalculate_touched_conditions(
            db, touched_conditions_ids
        )
        warnings.extend(_cond_recalc_warnings)
        if _cond_recalculated:
            info_messages.append(
                f"Recalculated derived fields (water_to_rock_ratio, "
                f"total_ferrous_iron_g) on {_cond_recalculated} conditions row(s)"
            )

```

- [ ] **Step 8: Run the new tests to verify they pass**

Run: `.venv/Scripts/pytest tests/services/bulk_uploads/test_new_experiments_conditions_recalc.py -v`

Expected: 8 passed.

- [ ] **Step 9: Run the full bulk-upload and calculation suites for regressions**

Run: `.venv/Scripts/pytest tests/services/bulk_uploads/ tests/services/calculations/ tests/api/test_results.py -q`

Expected: all pass. If a pre-existing test now fails, read it before changing anything — the likely cause is a test asserting `total_ferrous_iron_g is None` or a `water_to_rock_ratio` of None on a bulk-created row, which this change intentionally makes non-None. Update the assertion only when the new value is provably correct for that fixture's rock mass and FeO; otherwise stop and report.

- [ ] **Step 10: Commit**

```bash
git add backend/services/bulk_uploads/new_experiments.py tests/services/bulk_uploads/test_new_experiments_conditions_recalc.py
git commit -F <scratchpad>/msg-task2.txt
```

Message body for `msg-task2.txt`:

```
[fix] Recalculate conditions on bulk upload

- Record touched conditions PKs at all three write sites
- One recalculation pass before returning; count in info_messages
- Restores Fe2+ %H2 and %NH3 on bulk-created experiments
- Tests added: yes
- Docs updated: no
```

---

## Task 3: Documentation and incident record

**Files:**
- Create: `docs/issues/issue-bulk-upload-never-recalculates-conditions.md`
- Modify: `docs/CALCULATIONS.md`
- Modify: `.claude/rules/MODELS.md`

**Interfaces:**
- Consumes: the production measurements in this plan's Background section and the `info_messages` string added in Task 2.
- Produces: nothing consumed by later tasks. Task 4 appends its backfill counts to the issue document created here.

- [ ] **Step 1: Write the issue record**

Create `docs/issues/issue-bulk-upload-never-recalculates-conditions.md`:

```markdown
# New Experiments bulk upload never recalculated conditions derived fields

**Found:** 2026-08-10, investigating a missing Fe²⁺ %H₂ on `SERUM_Catalyst_001a-t3`.
**Status:** code fixed (`fix/bulk-upload-conditions-recalc`); data backfill see below.

## Symptom

`SERUM_Catalyst_001a-t3` had a complete H2 chain and no iron conversion:

```
h2_concentration = 353.88 ppm   gas_sampling_volume_ml = 30   gas_sampling_pressure_MPa = 0.101353
h2_micromoles    = 0.4415       h2_grams_per_ton_yield  = 0.8899
ferrous_iron_yield_h2_pct = NULL
```

Reported as a direct-injection problem, because the affected vials were all DI runs.

## Root cause

`water_to_rock_ratio` and `total_ferrous_iron_g` are stored derived fields written by
`recalculate_conditions()`. Every write path called `recalculate()` after mutating a
conditions row — `backend/api/routers/conditions.py:103` and `:125`,
`backend/api/routers/experiments.py:1329`, `database/lineage_utils.py:603` — except
`backend/services/bulk_uploads/new_experiments.py`, which creates or modifies
conditions rows in three places and only recalculated `ChemicalAdditive`.

`calculate_ferrous_iron_yield_h2` (`backend/services/calculations/scalar_calcs.py:24`)
returns None when `total_ferrous_iron_g` is None, so every scalar result under a
bulk-created experiment lost both Fe²⁺ yield percentages.

The tell was `water_to_rock_ratio` being NULL on the same row, with
`rock_mass_g = 1` and `water_volume_mL = 20`. Two computable derived fields both
empty means `recalculate()` never ran, not that an input was missing.

## Not a DI problem

`SERUM_Cation_001a-t5` is a DI row with the same 30 mL / 14.7 psi geometry and the
same sample `20250616_7`, and it *has* `ferrous_iron_yield_h2_pct = 0.0159%` — its
conditions row was recalculated by a later elemental upload via
`recalculate_conditions_for_samples`. The SERUM_Catalyst_001 vials were created
2026-07-24, after the last FeO upload for that sample, so nothing ever touched them.
The DI correlation is that the DI-era runs were all bulk-created.

## Production measurements (backup 2026-08-10 01:00)

Of 577 scalar rows with a computed `h2_micromoles`, 249 had no Fe²⁺ %H₂:

| Cause | Rows |
|---|---|
| `total_ferrous_iron_g` NULL, sample has FeO on record | 157 (144 experiments) |
| `total_ferrous_iron_g` NULL, sample has no FeO on record | 77 |
| `total_ferrous_iron_g` populated, scalar row stale | 15 |

845 of 1125 conditions rows had `total_ferrous_iron_g` NULL; 185 of those had **both**
derived fields NULL with positive rock mass and water volume.

## Fix

`_recalculate_touched_conditions(db, conditions_ids)` in `new_experiments.py` records
the primary key of every conditions row the upload touches — at all three write sites
— and recalculates them in one pass before returning, after every sheet has finished
mutating them. Keyed on primary keys because `db.expire_all()` runs after the
experiments-sheet loop and per-row savepoints can be rolled back after recording.
One try/except per row, so an unusable row does not cost the rest of the upload its
derived fields. The count appears in the upload's `info_messages`.

## Acceptance criteria

- [ ] A conditions-sheet row gets both derived fields computed by the upload.
- [ ] An `overwrite=TRUE` row that changes `rock_mass_g` recomputes both fields rather than keeping the stale values.
- [ ] A parent auto-copy row (no conditions sheet entry) gets its own derived fields.
- [ ] An experiment reaching conditions creation only via the additives sheet is recalculated.
- [ ] A bulk-created vial with a DI H2 reading ends up with a non-NULL `ferrous_iron_yield_h2_pct`.
- [ ] The 157 recoverable production rows have Fe²⁺ %H₂ after the backfill.
- [~] The 77 rows whose sample has no FeO on record cannot be fixed here — they need rock characterization uploaded first, which then triggers `recalculate_conditions_for_samples` automatically.

## Backfill

Filled in by Task 4.
```

- [ ] **Step 2: Update `docs/CALCULATIONS.md`**

`docs/CALCULATIONS.md:254` currently under-reports the trigger list — it names only two of the six paths, which is what made this defect invisible for so long. Replace that single line:

```markdown
**Trigger:** Fires via `registry.recalculate()` on `POST /conditions` and `PATCH /conditions`.
```

with:

```markdown
**Trigger:** Fires via `registry.recalculate()`. This field is **stored, not computed on
read**, so a conditions row is only correct if `recalculate()` ran after its last
mutation — and `calculate_ferrous_iron_yield_h2` returns NULL whenever this is NULL,
taking `ferrous_iron_yield_h2_pct` and `ferrous_iron_yield_nh3_pct` down with it. Every
path that recalculates:

- `POST /api/conditions`, `PUT /api/conditions/{id}` — `backend/api/routers/conditions.py:103`, `:125`
- `PATCH /api/experiments/{id}` — `backend/api/routers/experiments.py:1329`
- Replicate creation — `database/lineage_utils.py:603`
- Any elemental upload, via `recalculate_conditions_for_samples()` (`backend/services/elemental_composition_service.py:34`) — this is what covers experiments created *before* their rock's FeO data arrived
- The New Experiments bulk upload, as of 2026-08-10 — records every conditions row it touches and recalculates them in one pass before returning, reporting the count in `info_messages`

Before 2026-08-10 the bulk uploader recalculated only `ChemicalAdditive`, so
bulk-created experiments landed with `total_ferrous_iron_g` **and**
`water_to_rock_ratio` NULL and therefore no Fe²⁺ yield percentages on any of their
scalar results — 845 of 1125 production conditions rows and 157 scalar rows. A NULL
`water_to_rock_ratio` on a row with positive rock mass and water volume is the
diagnostic for "recalculate never ran here". See
`docs/issues/issue-bulk-upload-never-recalculates-conditions.md`.
```

- [ ] **Step 3: Update `.claude/rules/MODELS.md`**

In the `ExperimentalConditions` → **Derived Fields** list, replace the `total_ferrous_iron_g` bullet:

```markdown
  - `total_ferrous_iron_g` (Float, nullable): mass of ferrous iron (Fe²⁺) in grams, derived from rock characterization FeO wt% × `FE_IN_FEO_FRACTION` × `rock_mass_g`; see `docs/CALCULATIONS.md` for full formula.
```

with:

```markdown
  - `total_ferrous_iron_g` (Float, nullable): mass of ferrous iron (Fe²⁺) in grams, derived from rock characterization FeO wt% × `FE_IN_FEO_FRACTION` × `rock_mass_g`; see `docs/CALCULATIONS.md` for full formula. **Stored, so it is only correct if `recalculate()` ran after the row's last mutation** — and `calculate_ferrous_iron_yield_h2` returns NULL whenever it is NULL, taking `ferrous_iron_yield_h2_pct` and `ferrous_iron_yield_nh3_pct` down with it. The New Experiments bulk upload did not recalculate conditions until 2026-08-10, so 845 of 1125 production conditions rows held NULL and 157 scalar rows had no Fe²⁺ %H₂ despite a computed `h2_micromoles`; both are fixed by `database/data_migrations/backfill_total_ferrous_iron_017.py`. A NULL `water_to_rock_ratio` on a row with positive rock mass and water volume is the diagnostic for "recalculate never ran here". See `docs/issues/issue-bulk-upload-never-recalculates-conditions.md`.
```

- [ ] **Step 4: Verify the docs hook synced**

Run: `git status --short docs/project_context/`

Expected: `docs/project_context/CALCULATIONS.md` and `docs/project_context/issue-bulk-upload-never-recalculates-conditions.md` appear as modified/untracked. `.claude/rules/MODELS.md` is outside `docs/` and is not synced — that is correct.

- [ ] **Step 5: Commit**

```bash
git add docs/issues/issue-bulk-upload-never-recalculates-conditions.md docs/CALCULATIONS.md docs/project_context/ .claude/rules/MODELS.md
git commit -F <scratchpad>/msg-task3.txt
```

Message body for `msg-task3.txt`:

```
[fix] Document conditions recalculation contract

- Issue record with production measurements and root cause
- CALCULATIONS.md: every write path that recalculates
- MODELS.md: stored-field caveat on total_ferrous_iron_g
- Tests added: no
- Docs updated: yes
```

---

## Task 4: Backfill the existing rows

Two passes. `backfill_total_ferrous_iron_017.py` targets conditions rows where `total_ferrous_iron_g IS NULL` and cascades to their scalar results — that is the 157-row bucket. It does **not** reach the 15 rows whose conditions already had a value but whose scalar row is stale, so `recalculate_all_registry_012.py::_backfill_scalars` runs after it. No new migration file: both already exist and both support `dry_run`.

**Files:**
- Run: `database/data_migrations/backfill_total_ferrous_iron_017.py`
- Run: `database/data_migrations/recalculate_all_registry_012.py::_backfill_scalars`
- Modify: `docs/issues/issue-bulk-upload-never-recalculates-conditions.md` (fill in the Backfill section)

**Interfaces:**
- Consumes: the issue document from Task 3, and the merged code from Task 2 (so the dev DB stops regressing on the next upload).
- Produces: measured before/after counts recorded in the issue document, and a lab-PC runbook.

- [ ] **Step 1: Measure the dev DB before touching it**

Run:

```bash
.venv/Scripts/python -c "
from database.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
q = lambda s: db.execute(text(s)).scalar()
print('conditions rows                        :', q('SELECT count(*) FROM experimental_conditions'))
print('  total_ferrous_iron_g NULL            :', q('SELECT count(*) FROM experimental_conditions WHERE total_ferrous_iron_g IS NULL'))
print('  both derived NULL, inputs present    :', q('SELECT count(*) FROM experimental_conditions WHERE total_ferrous_iron_g IS NULL AND water_to_rock_ratio IS NULL AND rock_mass_g > 0 AND \"water_volume_mL\" > 0'))
print('scalar rows with h2_micromoles         :', q('SELECT count(*) FROM scalar_results WHERE h2_micromoles IS NOT NULL'))
print('  ...missing ferrous_iron_yield_h2_pct :', q('SELECT count(*) FROM scalar_results WHERE h2_micromoles IS NOT NULL AND ferrous_iron_yield_h2_pct IS NULL'))
db.close()
"
```

Expected on the current dev DB: roughly 1009 conditions rows, ~732 with NULL `total_ferrous_iron_g`, and 158 scalar rows with a computed `h2_micromoles` but no Fe²⁺ %H₂. Record the actual numbers — they are the "before" side of Step 6.

- [ ] **Step 2: Dry-run migration 017**

Run: `.venv/Scripts/python database/data_migrations/backfill_total_ferrous_iron_017.py --dry-run`

Expected: prints `Found N conditions rows with NULL total_ferrous_iron_g`, one `total_ferrous_iron_g = X.XXXX g` line per row it would update, then `=== DRY RUN: Rolling back changes ===` and a summary with `Errors: 0`. Stop and report if `Errors` is non-zero.

- [ ] **Step 3: Apply migration 017 to the dev DB**

Run: `.venv/Scripts/python database/data_migrations/backfill_total_ferrous_iron_017.py`

Expected: same per-row output, then `=== Changes committed ===`. Record `conditions_updated` and `scalar_cascades`.

- [ ] **Step 4: Dry-run then apply the scalar-only pass**

Run:

```bash
.venv/Scripts/python -c "
from database import SessionLocal
from database.data_migrations.recalculate_all_registry_012 import _backfill_scalars
db = SessionLocal()
_backfill_scalars(db, dry_run=True)
db.close()
"
```

Expected: `[INFO] _backfill_scalars complete — ok=N err=0 (DRY RUN — nothing committed)`. Stop and report if `err` is non-zero.

Then apply:

```bash
.venv/Scripts/python -c "
from database import SessionLocal
from database.data_migrations.recalculate_all_registry_012 import _backfill_scalars
db = SessionLocal()
_backfill_scalars(db, dry_run=False)
db.close()
"
```

- [ ] **Step 5: Recreate the reporting views**

`v_results_scalar` and `v_results_scalar_rollup` read the columns just backfilled. Recreate them so Power BI sees a definition matching the current schema:

Run: `.venv/Scripts/python -c "from database.event_listeners import create_reporting_views; create_reporting_views()"`

Expected: no output and no exception.

- [ ] **Step 6: Verify the dev DB after**

Re-run the Step 1 command. Expected: `total_ferrous_iron_g NULL` drops by the `conditions_updated` count from Step 3; `both derived NULL, inputs present` drops to 0; the `missing ferrous_iron_yield_h2_pct` count drops to only those rows whose sample has no FeO on record.

Then confirm the specific vial that started this, which will still be resultless in dev but must now carry the conditions inputs:

```bash
.venv/Scripts/python -c "
from database.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
for r in db.execute(text('''
SELECT e.experiment_id, ec.rock_mass_g, ec.water_to_rock_ratio, ec.total_ferrous_iron_g
FROM experiments e JOIN experimental_conditions ec ON ec.experiment_fk = e.id
WHERE e.experiment_id LIKE 'SERUM/_Catalyst/_001%' ESCAPE '/'
ORDER BY e.experiment_id
''')).all():
    print(r)
db.close()
"
```

Expected: every row shows `water_to_rock_ratio = 20.0` and `total_ferrous_iron_g ≈ 0.0738`.

- [ ] **Step 7: Record the outcome in the issue document**

Replace the `## Backfill` section of `docs/issues/issue-bulk-upload-never-recalculates-conditions.md` with the measured numbers, using this shape and substituting the real values from Steps 1, 3, 4 and 6:

```markdown
## Backfill

Dev DB, <date>:

| Measure | Before | After |
|---|---|---|
| conditions rows with `total_ferrous_iron_g` NULL | <n> | <n> |
| conditions rows with both derived fields NULL and inputs present | <n> | 0 |
| scalar rows with `h2_micromoles` but no Fe²⁺ %H₂ | <n> | <n> |

`backfill_total_ferrous_iron_017.py` updated <n> conditions rows and cascaded to
<n> scalar rows; `recalculate_all_registry_012.py::_backfill_scalars` then
recalculated <n> scalar rows, catching the ones whose conditions already had a
value. Reporting views recreated afterwards via `create_reporting_views()`.

### Lab PC runbook

Run **after** deploying this branch, from the repo root on the lab PC, in this order:

1. `.venv/Scripts/python database/data_migrations/backfill_total_ferrous_iron_017.py --dry-run` — confirm `Errors: 0`
2. `.venv/Scripts/python database/data_migrations/backfill_total_ferrous_iron_017.py`
3. `.venv/Scripts/python -c "from database import SessionLocal; from database.data_migrations.recalculate_all_registry_012 import _backfill_scalars; db = SessionLocal(); _backfill_scalars(db, dry_run=False); db.close()"`
4. `.venv/Scripts/python -c "from database.event_listeners import create_reporting_views; create_reporting_views()"`
5. Refresh the Power BI dataset.

The 77 rows whose sample has no FeO on record stay NULL. They resolve on their own
once that rock's elemental data is uploaded — `recalculate_conditions_for_samples`
fires on every elemental upload and covers experiments created before the rock data
arrived.
```

- [ ] **Step 8: Commit**

```bash
git add docs/issues/issue-bulk-upload-never-recalculates-conditions.md docs/project_context/
git commit -F <scratchpad>/msg-task4.txt
```

Message body for `msg-task4.txt`:

```
[fix] Record conditions backfill results

- Ran migration 017 and the scalar-only pass on the dev DB
- Recreated reporting views
- Lab PC runbook added to the issue doc
- Tests added: no
- Docs updated: yes
```

- [ ] **Step 9: Commit this plan document**

`docs/superpowers/plans/` is tracked by convention — leaving the plan untracked dangles every cross-reference to it.

```bash
git add docs/superpowers/plans/2026-08-10-bulk-upload-conditions-recalculate.md
git commit -m "[fix] Add conditions recalculation plan"
```

---

## Out of scope

- **The 77 rows with no FeO on record.** Nothing in this plan can fix them; they need rock characterization uploaded, which then recalculates them automatically.
- **`gas_sampling_volume_ml = 1` on `SERUM_Catalyst_001a-t7` and `001b-t3`.** The current v3 Dashboard says 30 mL for both, so their `h2_grams_per_ton_yield` is ~30× low (0.029 vs ~0.78 for near-identical ppm). Probably an earlier workbook revision was uploaded. Separate investigation — do not fold it in here.
- **Persisting GC source provenance** (`h2_source` / `h2_di_superseded` are computed per row and rendered nowhere). Would be an additive `ScalarResults` column and a schema-checklist run; tracked under issue #111 follow-ups.
- **Making `POST /api/conditions` recalculate on a path it currently misses.** Audited during this investigation and found correct — `conditions.py:103` and `:125` both call `recalculate`.
