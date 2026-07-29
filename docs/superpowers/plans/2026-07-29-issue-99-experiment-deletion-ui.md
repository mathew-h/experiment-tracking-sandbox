# Experiment Deletion (Issue #99) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give researchers a self-serve, audited way to delete a single experiment from the app, with no orphan rows left behind and a restorable snapshot in `ModificationsLog`.

**Architecture:** A new service module `backend/services/experiment_deletion.py` owns both the read-only impact scan and the write path (decouple → snapshot → delete), so the router stays thin and the logic is testable without HTTP. A new `GET /api/experiments/{id}/delete-impact` powers the confirmation dialog; the existing `DELETE /api/experiments/{id}` is rewired to the service and changes from `204 No Content` to `200` with a body reporting what was actually decoupled. The frontend adds a `DeleteExperimentModal` with typed-ID confirmation, wired into `ExperimentDetail`'s quick-actions row (not the list row, so deletion stays deliberate).

**Tech Stack:** FastAPI + Pydantic v2 + SQLAlchemy 2.0 (`select()` style) + PostgreSQL; React 18 + TanStack Query v5 + Tailwind; pytest + vitest/@testing-library.

## Global Constraints

- **Locked decisions for this issue** (settled with the user on 2026-07-29, do not revisit):
  1. **Access:** any approved researcher. Do **not** wire the `role: admin` claim into `verify_firebase_token`. The controls are the `ModificationsLog` snapshot plus typed-ID confirmation.
  2. **Delete model:** hard delete. No `deleted_at` column, no view filtering. Freeing the `experiment_id` string for reuse is the actual requirement.
  3. **Scope:** single-experiment delete only. Bulk "Delete selected" is a follow-up issue, explicitly out of scope.
- **No schema change and no Alembic migration.** All orphan prevention happens in application code, which is correct whether or not the deployed DB carries the model-declared `ondelete` clauses (see "Verified DB facts" below). If you think you need a migration, stop and escalate per `.claude/CLAUDE.md` §7.
- **No new third-party packages** (frontend or backend). Adding one requires escalation, and `frontend/package.json` + `package-lock.json` must never be touched separately (`.claude/CLAUDE.md` §5).
- **Backend rules** (`backend/CLAUDE.md`): `structlog` only, never `print()`; SQLAlchemy 2.0 `select()` style matching the surrounding router; no business logic in `database/models/`.
- **Frontend rules** (`frontend/CLAUDE.md`): no hardcoded hex — Tailwind tokens only; no `console.log`; no `useEffect`+`useState` for fetching — TanStack Query only; ESLint zero warnings; `tsc --noEmit` must stay clean.
- **Never start, stop, or restart the uvicorn server or the Vite dev server.** Assume both are already running (ports 8000 / 5173). If unreachable, report it.
- **Commit format** (`.claude/CLAUDE.md` §8): `[#99] <imperative description under 50 chars>`, then `- Tests added: yes/no` and `- Docs updated: yes/no`.
- **Docs sync:** never write to `docs/project_context/` — the `PostToolUse` hook copies `docs/` writes there automatically.

---

## Verified DB facts (established 2026-07-29 — trust these over the issue text)

The issue body makes two claims that are wrong in detail. These were checked against the live dev DB; the plan below is built on the corrected picture.

**1. The FK constraints DO carry `ondelete` clauses in the dev DB.** From `pg_constraint` (`confdeltype`: `c`=CASCADE, `n`=SET NULL):

```
experiment_notes_experiment_fk_fkey          | experiment_notes        | c
experimental_conditions_experiment_fk_fkey   | experimental_conditions | c
experimental_results_experiment_fk_fkey      | experimental_results    | c
experiments_parent_experiment_fk_fkey        | experiments             | n
external_analyses_experiment_fk_fkey         | external_analyses       | c
modifications_log_experiment_fk_fkey         | modifications_log       | c
reactor_change_requests_experiment_id_fkey   | reactor_change_requests | n
scalar_results_background_experiment_fk_fkey | scalar_results          | n
xrd_phases_experiment_fk_fkey                | xrd_phases              | n
```

So the issue's predicted `IntegrityError` on `background_experiment_fk` will **not** happen here. But the dev and test DBs are built with `Base.metadata.create_all` (see `database/CLAUDE.md` and `tests/api/conftest.py:21`), while the lab PC came up through the Alembic chain — so parity with production is **not** guaranteed. Handle everything explicitly in app code; then behavior is identical either way.

**2. `background_experiment_fk` is dead; the *string* column is what's actually used.** Row counts from `scalar_results`:

```
total = 1056 | background_experiment_fk set = 0 | background_experiment_id set = 52
```

`backend/services/scalar_results_service.py:155` only ever writes the string. The FK has a DB-level `SET NULL` guard; **the string has no FK and therefore no protection at all.** Deleting an experiment today silently leaves dangling background references *by name* — that is the real bug, and it is the opposite of what the issue predicted. The decoupling logic must key on the string (and null the FK too, for completeness).

**Also important:** `background_experiment_id` is pure provenance — a label recording where the background number came from. The number itself lives in `scalar_results.background_ammonium_concentration_mM` and is what `backend/services/calculations/scalar_calcs.py:107,126` reads. **Nulling the provenance changes no derived value, so no `recalculate()` call is needed on the decoupling path.**

**3. `Experiment.xrd_phases` DOES exist** (`database/models/experiments.py:44`) — the issue says it doesn't. It has no `cascade=`, so on parent delete SQLAlchemy nullifies `experiment_fk` and leaves the row, with the stale `experiment_id` string still naming the deleted experiment. Net effect matches the issue's diagnosis: the `uq_xrd_phase_experiment_time_mineral` constraint on `(experiment_id, time_post_reaction_days, mineral_name)` then blocks re-creating that experiment's XRD data. Live exposure: **205 rows** currently have `experiment_fk` set, **0** are orphaned today.

**4. One reference the issue misses entirely:** `experiments_parent_experiment_fk_fkey` is also `SET NULL`. Deleting a group parent silently nulls its lettered replicates' `parent_experiment_fk`. This is **not** a data-loss bug — replicate groups are addressed by the `base_experiment_id` *string*, not by a row lookup (`.claude/rules/MODELS.md`, issue #87) — so the group page keeps working. But the researcher deserves to be told, so the impact response reports these children.

### Traps in the models — read before writing queries

- **`ChemicalAdditive.experiment_id` is an `Integer` FK to `experimental_conditions.id`** (`database/models/chemicals.py:59`), *not* the experiment's string ID and *not* `experiments.id`. Counting additives requires the conditions row's `id`.
- **`ExternalAnalysis` carries both `experiment_fk` (CASCADE) and a denormalized `experiment_id` string** (`database/models/analysis.py:26-27`). The CASCADE handles the rows; nothing extra needed.
- **`ReactorChangeRequest` has `UniqueConstraint("reactor_label", "experiment_id", "sync_date")`** (`database/models/notion_sync.py:33-36`). Nulling `experiment_id` on several rows sharing a `(reactor_label, sync_date)` pair is safe: PostgreSQL treats `NULL` as distinct in unique constraints, so no conflict.
- **`ModificationsLog.experiment_fk` is `ondelete="CASCADE"`** (`database/models/experiments.py:102`). The audit row **must** be written with `experiment_fk=None` or it deletes itself along with the experiment. `experiment_id` (the string) is a plain nullable `String` with no FK, so it survives.
- Scalar/ICP/file rows hang off `experimental_results.id` (`result_id`, all `ondelete="CASCADE"`), which itself cascades from `experiments.id`. They need counting for the dialog but no explicit deletion.

---

## File Structure

**Backend**
- Create `backend/services/experiment_deletion.py` — the whole deletion domain: a `DeleteImpact` dataclass, `collect_delete_impact()` (read-only scan), `serialize_experiment_snapshot()`, and `delete_experiment_cascade()` (decouple → log → delete). One responsibility: what deleting an experiment touches.
- Modify `backend/api/schemas/experiments.py` — append `DeleteImpactResponse` and `ExperimentDeletedResponse`.
- Modify `backend/api/routers/experiments.py` — add the `GET /{experiment_id}/delete-impact` route; rewrite the body of `delete_experiment` (currently lines 1271-1286) to call the service.

**Frontend**
- Modify `frontend/src/api/experiments.ts` — add `DeleteImpact` / `ExperimentDeleted` interfaces, add `getDeleteImpact()`, retype `delete()`.
- Create `frontend/src/components/experiments/DeleteExperimentModal.tsx` — the confirmation dialog, including the typed-ID gate. Kept out of `ExperimentDetail/index.tsx` because that file is already 440 lines and the modal is self-contained (same reasoning as the existing `CreateReplicatesModal`).
- Modify `frontend/src/pages/ExperimentDetail/index.tsx` — a "Delete Experiment" button in the existing quick-actions row plus the modal mount.

**Tests**
- Create `tests/services/test_experiment_deletion.py` — service-level, no HTTP.
- Modify `tests/api/test_experiments.py` — endpoint behavior; update the existing `test_delete_experiment` (line 74) for the 204→200 change.
- Create `frontend/src/components/experiments/DeleteExperimentModal.test.tsx`.
- Create `frontend/src/pages/ExperimentDetail/__tests__/DeleteExperiment.test.tsx`.

**Docs**
- Modify `.claude/rules/MODELS.md`, `docs/api/API_REFERENCE.md`, `docs/working/issue-log.md`, `docs/working/decisions.md`.

### Contract change to flag in review

`DELETE /api/experiments/{experiment_id}` goes from **`204 No Content`** to **`200`** with an `ExperimentDeletedResponse` body. Required by the acceptance criterion "reports the decoupled experiment" — a 204 cannot carry one, and the pre-flight `/delete-impact` is only an estimate that can go stale between dialog and confirm.

Known consumers, both checked:
- `tests/api/test_experiments.py:74` asserts `204` → **updated in Task 4**.
- `scripts/delete_experiments_via_api.ps1:161` uses `Invoke-RestMethod ... | Out-Null` — status-agnostic. **No change needed.**
- `frontend/src/api/experiments.ts:301` already does `.then((r) => r.data)` — a body is fine.

---

### Task 1: Impact scan service

Read-only. Counts every dependent record and resolves the two decoupling lists, so both the dialog and the delete path share one source of truth.

**Files:**
- Create: `backend/services/experiment_deletion.py`
- Test: `tests/services/test_experiment_deletion.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `@dataclass DeleteImpact` with fields `experiment_id: str`, `results: int`, `scalar_results: int`, `icp_results: int`, `result_files: int`, `notes: int`, `additives: int`, `external_analyses: int`, `xrd_phases: int`, `change_requests: int`, `background_for: list[str]`, `replicate_children: list[str]`, and a read-only `total` property.
  - `collect_delete_impact(db: Session, exp: Experiment) -> DeleteImpact`

`total` deliberately sums only the **counts**, not `background_for` / `replicate_children` — those are decoupled, not destroyed, and the UI uses `total > 0` to decide whether to demand a typed ID.

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_experiment_deletion.py`. Note the fixtures: this file needs its own DB session because `tests/services/` has no `client` fixture. Reuse the `tests/api/conftest.py` pattern.

```python
from __future__ import annotations
from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker, Session

from database import Base  # noqa: F401 — side-effect: registers all models
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.enums import AmountUnit, ExperimentStatus
from database.models.conditions import ExperimentalConditions
from database.models.chemicals import Compound, ChemicalAdditive
from database.models.results import ExperimentalResults, ScalarResults, ICPResults, ResultFiles
from database.models.analysis import ExternalAnalysis
from database.models.xrd import XRDPhase
from database.models.notion_sync import ReactorChangeRequest

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"
_engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(scope="module", autouse=True)
def _tables():
    Base.metadata.create_all(bind=_engine)
    yield


@pytest.fixture()
def db(_tables) -> Session:
    connection = _engine.connect()
    transaction = connection.begin()
    session = _SessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def _full_experiment(db: Session, experiment_id="DEL_FULL_001", number=7101) -> Experiment:
    """An experiment with one of every dependent record type."""
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=number,
        status=ExperimentStatus.ONGOING,
        researcher="Test Researcher",
    )
    db.add(exp)
    db.flush()

    cond = ExperimentalConditions(experiment_fk=exp.id, experiment_id=experiment_id, temperature_c=80.0)
    db.add(cond)
    db.flush()

    compound = Compound(name=f"Magnetite {number}", molecular_weight_g_mol=231.5)
    db.add(compound)
    db.flush()
    # ChemicalAdditive.experiment_id is the CONDITIONS row id (Integer FK), and
    # `unit` is Column(Enum(AmountUnit)) -- a bare "g" string will not bind.
    db.add(ChemicalAdditive(experiment_id=cond.id, compound_id=compound.id,
                            amount=5.0, unit=AmountUnit.GRAM))

    result = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=7.0,
        time_post_reaction_bucket_days=7.0,
        is_primary_timepoint_result=True,
        description="t7 sample",
    )
    db.add(result)
    db.flush()
    db.add(ScalarResults(result_id=result.id, final_ph=7.4))
    db.add(ICPResults(result_id=result.id, fe=980.0))
    db.add(ResultFiles(result_id=result.id, file_path="/tmp/x.csv", file_name="x.csv"))

    db.add(ExperimentNotes(experiment_id=experiment_id, experiment_fk=exp.id, note_text="a note"))
    db.add(ExternalAnalysis(experiment_fk=exp.id, experiment_id=experiment_id, analysis_type="XRD"))
    db.add(XRDPhase(experiment_fk=exp.id, experiment_id=experiment_id,
                    time_post_reaction_days=7, mineral_name="Magnetite", amount=12.0))
    db.add(ReactorChangeRequest(reactor_label="R01", experiment_id=experiment_id,
                                requested_change="swap", sync_date=date(2026, 7, 28)))
    db.commit()
    db.refresh(exp)
    return exp


def test_collect_impact_counts_every_dependent_record(db):
    from backend.services.experiment_deletion import collect_delete_impact

    exp = _full_experiment(db)
    impact = collect_delete_impact(db, exp)

    assert impact.experiment_id == "DEL_FULL_001"
    assert impact.results == 1
    assert impact.scalar_results == 1
    assert impact.icp_results == 1
    assert impact.result_files == 1
    assert impact.notes == 1
    assert impact.additives == 1
    assert impact.external_analyses == 1
    assert impact.xrd_phases == 1
    assert impact.change_requests == 1
    assert impact.total == 9


def test_collect_impact_is_zero_for_a_bare_experiment(db):
    from backend.services.experiment_deletion import collect_delete_impact

    exp = Experiment(experiment_id="DEL_BARE_001", experiment_number=7102,
                     status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.commit()
    db.refresh(exp)

    impact = collect_delete_impact(db, exp)
    assert impact.total == 0
    assert impact.background_for == []
    assert impact.replicate_children == []


def test_collect_impact_reports_background_dependents_by_string(db):
    """background_experiment_fk is unpopulated in practice (0/1056 rows) — the
    STRING column is the real reference and has no FK protecting it."""
    from backend.services.experiment_deletion import collect_delete_impact

    target = Experiment(experiment_id="DEL_BG_TARGET", experiment_number=7103,
                        status=ExperimentStatus.ONGOING)
    other = Experiment(experiment_id="DEL_BG_USER", experiment_number=7104,
                       status=ExperimentStatus.ONGOING)
    db.add_all([target, other])
    db.flush()

    result = ExperimentalResults(experiment_fk=other.id, time_post_reaction_days=0.0,
                                 is_primary_timepoint_result=True, description="t0")
    db.add(result)
    db.flush()
    db.add(ScalarResults(result_id=result.id, background_experiment_id="DEL_BG_TARGET"))
    db.commit()
    db.refresh(target)

    impact = collect_delete_impact(db, target)
    assert impact.background_for == ["DEL_BG_USER"]
    assert impact.total == 0  # decoupled, not destroyed


def test_collect_impact_reports_replicate_children(db):
    from backend.services.experiment_deletion import collect_delete_impact

    parent = Experiment(experiment_id="DEL_PARENT_001", experiment_number=7105,
                        status=ExperimentStatus.ONGOING)
    db.add(parent)
    db.flush()
    db.add(Experiment(experiment_id="DEL_PARENT_001a", experiment_number=7106,
                      status=ExperimentStatus.ONGOING, base_experiment_id="DEL_PARENT_001",
                      replicate_label="a", parent_experiment_fk=parent.id))
    db.commit()
    db.refresh(parent)

    impact = collect_delete_impact(db, parent)
    assert impact.replicate_children == ["DEL_PARENT_001a"]


def test_collect_impact_counts_xrd_phases_matched_by_string_only(db):
    """A phase row whose experiment_fk was already nulled by a previous delete
    still names the experiment by string and still blocks the unique constraint."""
    from backend.services.experiment_deletion import collect_delete_impact

    exp = Experiment(experiment_id="DEL_XRD_001", experiment_number=7107,
                     status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    db.add(XRDPhase(experiment_fk=exp.id, experiment_id="DEL_XRD_001",
                    time_post_reaction_days=0, mineral_name="Olivine", amount=5.0))
    db.add(XRDPhase(experiment_fk=None, experiment_id="DEL_XRD_001",
                    time_post_reaction_days=7, mineral_name="Olivine", amount=6.0))
    db.commit()
    db.refresh(exp)

    assert collect_delete_impact(db, exp).xrd_phases == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/services/test_experiment_deletion.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.experiment_deletion'`

- [ ] **Step 3: Write the implementation**

Create `backend/services/experiment_deletion.py`:

```python
"""Experiment deletion: impact scan and the orphan-safe delete path (issue #99).

Deletion is a HARD delete, available to any approved researcher. The controls
are the ModificationsLog snapshot written by delete_experiment_cascade() and
the typed-ID confirmation in the UI -- there is no role gate (locked decision,
2026-07-29).

Why this module exists rather than a bare db.delete(exp): three references to
an experiment are NOT covered by the cascade="all, delete-orphan" relationships
on Experiment (database/models/experiments.py:30-35), and one of them has no
DB-level protection at all:

  1. xrd_phases -- experiment_fk is ondelete="SET NULL" and the relationship
     (experiments.py:44) declares no cascade, so rows survive with a stale
     experiment_id string. The uq_xrd_phase_experiment_time_mineral constraint
     on (experiment_id, time_post_reaction_days, mineral_name) then blocks
     re-creating that experiment's XRD data. These rows are DELETED.
  2. scalar_results.background_experiment_id -- a plain String with NO foreign
     key. The parallel background_experiment_fk column is unpopulated in
     practice (0 of 1056 rows as of 2026-07-29; only the string is ever written,
     see backend/services/scalar_results_service.py:155), so the DB-level
     SET NULL on the FK protects nothing that matters. Both are NULLed out.
     This is provenance only -- the background NUMBER lives in
     background_ammonium_concentration_mM, so nulling it changes no derived
     value and needs no recalculate() call.
  3. reactor_change_requests.experiment_id -- ondelete="SET NULL"; nulled
     explicitly so behavior does not depend on deployed constraint parity.

Deployed constraints are not guaranteed to match the model declarations: the
dev and test DBs are built with Base.metadata.create_all (which honors the
ondelete clauses), while the lab PC came up through the Alembic chain, whose
initial migration declared none. Everything here is therefore explicit in
application code, so behavior is identical either way.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from database.models.analysis import ExternalAnalysis
from database.models.chemicals import ChemicalAdditive, Compound
from database.models.conditions import ExperimentalConditions
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.notion_sync import ReactorChangeRequest
from database.models.results import (
    ExperimentalResults, ICPResults, ResultFiles, ScalarResults,
)
from database.models.xrd import XRDPhase

log = structlog.get_logger(__name__)


@dataclass
class DeleteImpact:
    """What deleting one experiment destroys (counts) and decouples (lists)."""

    experiment_id: str
    results: int = 0
    scalar_results: int = 0
    icp_results: int = 0
    result_files: int = 0
    notes: int = 0
    additives: int = 0
    external_analyses: int = 0
    xrd_phases: int = 0
    change_requests: int = 0
    # Other experiments that name this one as their ammonium background.
    background_for: list[str] = field(default_factory=list)
    # Experiments whose parent_experiment_fk points at this one. Their
    # base_experiment_id STRING is untouched, so replicate groups -- addressed
    # by that string, not by a row lookup (MODELS.md, issue #87) -- keep
    # working. Reported so the researcher is told, not because data is lost.
    replicate_children: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Rows destroyed. Excludes background_for/replicate_children, which
        are decoupled and survive. The UI gates typed-ID confirmation on this.
        """
        return (
            self.results + self.scalar_results + self.icp_results
            + self.result_files + self.notes + self.additives
            + self.external_analyses + self.xrd_phases + self.change_requests
        )


def _count(db: Session, stmt) -> int:
    return db.execute(stmt).scalar_one() or 0


def collect_delete_impact(db: Session, exp: Experiment) -> DeleteImpact:
    """Count every dependent record and resolve both decoupling lists.

    Read-only -- safe to call from a GET. Shared by the delete-impact endpoint
    and by delete_experiment_cascade so the dialog and the audit log agree.
    """
    result_ids = db.execute(
        select(ExperimentalResults.id).where(ExperimentalResults.experiment_fk == exp.id)
    ).scalars().all()

    # ChemicalAdditive.experiment_id is an INTEGER FK to
    # experimental_conditions.id -- not the experiment string, not experiments.id.
    condition_ids = db.execute(
        select(ExperimentalConditions.id).where(ExperimentalConditions.experiment_fk == exp.id)
    ).scalars().all()

    impact = DeleteImpact(
        experiment_id=exp.experiment_id,
        results=len(result_ids),
        notes=_count(db, select(func.count()).select_from(ExperimentNotes)
                     .where(ExperimentNotes.experiment_fk == exp.id)),
        external_analyses=_count(db, select(func.count()).select_from(ExternalAnalysis)
                                 .where(ExternalAnalysis.experiment_fk == exp.id)),
        # Matched on fk OR string: a row whose fk was nulled by an earlier
        # delete still names this experiment and still holds the unique slot.
        xrd_phases=_count(db, select(func.count()).select_from(XRDPhase).where(
            or_(XRDPhase.experiment_fk == exp.id,
                XRDPhase.experiment_id == exp.experiment_id))),
        change_requests=_count(db, select(func.count()).select_from(ReactorChangeRequest)
                               .where(ReactorChangeRequest.experiment_id == exp.experiment_id)),
    )

    if result_ids:
        impact.scalar_results = _count(db, select(func.count()).select_from(ScalarResults)
                                       .where(ScalarResults.result_id.in_(result_ids)))
        impact.icp_results = _count(db, select(func.count()).select_from(ICPResults)
                                    .where(ICPResults.result_id.in_(result_ids)))
        impact.result_files = _count(db, select(func.count()).select_from(ResultFiles)
                                     .where(ResultFiles.result_id.in_(result_ids)))

    if condition_ids:
        impact.additives = _count(db, select(func.count()).select_from(ChemicalAdditive)
                                  .where(ChemicalAdditive.experiment_id.in_(condition_ids)))

    # Other experiments using this one as their ammonium background. Keyed on
    # the string (the FK is unpopulated in practice); self-references excluded.
    impact.background_for = sorted(set(db.execute(
        select(Experiment.experiment_id)
        .join(ExperimentalResults, ExperimentalResults.experiment_fk == Experiment.id)
        .join(ScalarResults, ScalarResults.result_id == ExperimentalResults.id)
        .where(
            or_(ScalarResults.background_experiment_id == exp.experiment_id,
                ScalarResults.background_experiment_fk == exp.id),
            Experiment.id != exp.id,
        )
    ).scalars().all()))

    impact.replicate_children = sorted(db.execute(
        select(Experiment.experiment_id).where(
            Experiment.parent_experiment_fk == exp.id,
            Experiment.id != exp.id,
        )
    ).scalars().all())

    return impact
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/services/test_experiment_deletion.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/experiment_deletion.py tests/services/test_experiment_deletion.py
git commit -m "[#99] Add experiment delete-impact scan

- Counts every dependent record; resolves background and replicate
  decoupling lists keyed on the string, not the unused FK
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Snapshot + orphan-safe delete

The audit trail plus the three explicit decouplings. This is the task that makes deletion acceptable — per the issue, it must land before any UI.

**Files:**
- Modify: `backend/services/experiment_deletion.py`
- Test: `tests/services/test_experiment_deletion.py`

**Interfaces:**
- Consumes: `DeleteImpact`, `collect_delete_impact` from Task 1.
- Produces:
  - `serialize_experiment_snapshot(db: Session, exp: Experiment) -> dict[str, Any]`
  - `delete_experiment_cascade(db: Session, exp: Experiment, modified_by: str | None) -> DeleteImpact` — commits, returns the impact measured **before** deletion.

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/test_experiment_deletion.py`:

```python
def test_snapshot_captures_experiment_conditions_and_additives(db):
    from backend.services.experiment_deletion import serialize_experiment_snapshot

    exp = _full_experiment(db, "DEL_SNAP_001", 7201)
    snap = serialize_experiment_snapshot(db, exp)

    assert snap["experiment"]["experiment_id"] == "DEL_SNAP_001"
    assert snap["experiment"]["experiment_number"] == 7201
    assert snap["experiment"]["researcher"] == "Test Researcher"
    assert snap["experiment"]["status"] == "ONGOING"
    assert snap["conditions"]["temperature_c"] == 80.0
    assert len(snap["additives"]) == 1
    assert snap["additives"][0]["compound_name"] == "Magnetite 7201"
    assert snap["additives"][0]["amount"] == 5.0
    assert snap["notes"] == ["a note"]


def test_snapshot_is_json_serializable(db):
    """old_values is a JSONB column -- datetimes and enums must already be
    primitives or the flush fails."""
    import json
    from datetime import datetime, timezone
    from backend.services.experiment_deletion import serialize_experiment_snapshot

    exp = _full_experiment(db, "DEL_JSON_001", 7202)
    exp.date = datetime(2026, 7, 20, tzinfo=timezone.utc)
    db.commit()

    json.dumps(serialize_experiment_snapshot(db, exp))  # must not raise


def test_delete_writes_a_log_row_that_survives_the_delete(db):
    from backend.services.experiment_deletion import delete_experiment_cascade

    exp = _full_experiment(db, "DEL_LOG_001", 7203)
    delete_experiment_cascade(db, exp, modified_by="tester@addisenergy.com")

    assert db.execute(
        select(Experiment).where(Experiment.experiment_id == "DEL_LOG_001")
    ).scalar_one_or_none() is None

    entry = db.execute(
        select(ModificationsLog).where(
            ModificationsLog.experiment_id == "DEL_LOG_001",
            ModificationsLog.modification_type == "delete",
        )
    ).scalar_one()
    # experiment_fk MUST be NULL: that FK is ondelete="CASCADE", so a populated
    # value would have deleted this very row along with the experiment.
    assert entry.experiment_fk is None
    assert entry.modified_table == "experiments"
    assert entry.modified_by == "tester@addisenergy.com"
    assert entry.old_values["experiment"]["experiment_number"] == 7203
    assert entry.old_values["conditions"]["temperature_c"] == 80.0
    assert entry.new_values["impact"]["results"] == 1


def test_delete_removes_xrd_phases_freeing_the_unique_slot(db):
    from backend.services.experiment_deletion import delete_experiment_cascade

    exp = _full_experiment(db, "DEL_XRD_FREE", 7204)
    delete_experiment_cascade(db, exp, modified_by="tester@addisenergy.com")

    assert db.execute(
        select(func.count()).select_from(XRDPhase)
        .where(XRDPhase.experiment_id == "DEL_XRD_FREE")
    ).scalar_one() == 0

    # The freed (experiment_id, time, mineral) slot is reusable.
    db.add(XRDPhase(experiment_fk=None, experiment_id="DEL_XRD_FREE",
                    time_post_reaction_days=7, mineral_name="Magnetite", amount=13.0))
    db.commit()  # must not raise on uq_xrd_phase_experiment_time_mineral


def test_delete_decouples_background_string_and_fk(db):
    from backend.services.experiment_deletion import delete_experiment_cascade

    target = Experiment(experiment_id="DEL_BG2_TARGET", experiment_number=7205,
                        status=ExperimentStatus.ONGOING)
    other = Experiment(experiment_id="DEL_BG2_USER", experiment_number=7206,
                       status=ExperimentStatus.ONGOING)
    db.add_all([target, other])
    db.flush()
    result = ExperimentalResults(experiment_fk=other.id, time_post_reaction_days=0.0,
                                 is_primary_timepoint_result=True, description="t0")
    db.add(result)
    db.flush()
    db.add(ScalarResults(result_id=result.id, background_experiment_id="DEL_BG2_TARGET",
                         background_experiment_fk=target.id,
                         background_ammonium_concentration_mM=0.2))
    db.commit()
    db.refresh(target)

    impact = delete_experiment_cascade(db, target, modified_by="tester@addisenergy.com")
    assert impact.background_for == ["DEL_BG2_USER"]

    scalar = db.execute(
        select(ScalarResults).where(ScalarResults.result_id == result.id)
    ).scalar_one()
    assert scalar.background_experiment_id is None
    assert scalar.background_experiment_fk is None
    # Provenance only -- the background NUMBER is untouched, so no derived
    # field changed and no recalculate() was needed.
    assert scalar.background_ammonium_concentration_mM == 0.2


def test_delete_nulls_change_request_references(db):
    from backend.services.experiment_deletion import delete_experiment_cascade

    exp = _full_experiment(db, "DEL_CR_001", 7207)
    delete_experiment_cascade(db, exp, modified_by="tester@addisenergy.com")

    rows = db.execute(
        select(ReactorChangeRequest).where(ReactorChangeRequest.reactor_label == "R01")
    ).scalars().all()
    assert rows, "the change request row itself must survive"
    assert all(r.experiment_id is None for r in rows)


def test_delete_leaves_no_orphan_rows_anywhere(db):
    """The headline acceptance criterion, checked table by table."""
    from backend.services.experiment_deletion import delete_experiment_cascade

    exp = _full_experiment(db, "DEL_ORPHAN_001", 7208)
    exp_pk = exp.id
    delete_experiment_cascade(db, exp, modified_by="tester@addisenergy.com")

    for model, clause in [
        (ExperimentalConditions, ExperimentalConditions.experiment_fk == exp_pk),
        (ExperimentNotes, ExperimentNotes.experiment_fk == exp_pk),
        (ExternalAnalysis, ExternalAnalysis.experiment_fk == exp_pk),
        (ExperimentalResults, ExperimentalResults.experiment_fk == exp_pk),
        (XRDPhase, XRDPhase.experiment_id == "DEL_ORPHAN_001"),
        (XRDPhase, XRDPhase.experiment_fk == exp_pk),
    ]:
        assert db.execute(
            select(func.count()).select_from(model).where(clause)
        ).scalar_one() == 0, f"orphan rows left in {model.__tablename__}"


def test_delete_nulls_replicate_children_parent_fk_but_keeps_the_group_string(db):
    from backend.services.experiment_deletion import delete_experiment_cascade

    parent = Experiment(experiment_id="DEL_GP_001", experiment_number=7209,
                        status=ExperimentStatus.ONGOING)
    db.add(parent)
    db.flush()
    db.add(Experiment(experiment_id="DEL_GP_001a", experiment_number=7210,
                      status=ExperimentStatus.ONGOING, base_experiment_id="DEL_GP_001",
                      replicate_label="a", parent_experiment_fk=parent.id))
    db.commit()
    db.refresh(parent)

    impact = delete_experiment_cascade(db, parent, modified_by="tester@addisenergy.com")
    assert impact.replicate_children == ["DEL_GP_001a"]

    child = db.execute(
        select(Experiment).where(Experiment.experiment_id == "DEL_GP_001a")
    ).scalar_one()
    assert child.parent_experiment_fk is None
    # base_experiment_id survives, so /experiments/groups/DEL_GP_001 still
    # resolves the group by string (MODELS.md, issue #87).
    assert child.base_experiment_id == "DEL_GP_001"
    assert child.replicate_label == "a"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/services/test_experiment_deletion.py -v`
Expected: the 8 new tests FAIL with `ImportError: cannot import name 'serialize_experiment_snapshot'` / `'delete_experiment_cascade'`; Task 1's 5 tests still pass.

- [ ] **Step 3: Write the implementation**

Append to `backend/services/experiment_deletion.py`:

```python
def _primitive(value: Any) -> Any:
    """Coerce a column value to something json/JSONB can hold."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "value"):  # enum member (e.g. ExperimentStatus)
        return value.value
    if hasattr(value, "isoformat"):  # date / datetime
        return value.isoformat()
    return str(value)


def _row_to_dict(instance: Any) -> dict[str, Any]:
    return {
        col.name: _primitive(getattr(instance, col.name))
        for col in instance.__table__.columns
    }


def serialize_experiment_snapshot(db: Session, exp: Experiment) -> dict[str, Any]:
    """A restorable snapshot of the experiment, its conditions, additives and notes.

    Every value is JSON-primitive because this lands in ModificationsLog.old_values
    (a JSONB column) -- enums and datetimes would otherwise fail the flush.
    Results/ICP are deliberately excluded: they are bulk-uploadable and would
    make the audit row unbounded. Their counts are recorded in new_values.
    """
    conditions = db.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
    ).scalar_one_or_none()

    additives: list[dict[str, Any]] = []
    if conditions is not None:
        rows = db.execute(
            select(ChemicalAdditive, Compound.name)
            .join(Compound, Compound.id == ChemicalAdditive.compound_id)
            .where(ChemicalAdditive.experiment_id == conditions.id)
        ).all()
        for additive, compound_name in rows:
            entry = _row_to_dict(additive)
            entry["compound_name"] = compound_name
            additives.append(entry)

    notes = db.execute(
        select(ExperimentNotes.note_text)
        .where(ExperimentNotes.experiment_fk == exp.id)
        .order_by(ExperimentNotes.created_at)
    ).scalars().all()

    return {
        "experiment": _row_to_dict(exp),
        "conditions": _row_to_dict(conditions) if conditions is not None else None,
        "additives": additives,
        "notes": [n for n in notes if n is not None],
    }


def delete_experiment_cascade(
    db: Session, exp: Experiment, modified_by: str | None
) -> DeleteImpact:
    """Decouple, audit, then hard-delete an experiment. Commits.

    Order matters: the impact scan and the snapshot both read rows that the
    delete destroys, so they run first. The ModificationsLog row is added with
    experiment_fk=None -- that FK is ondelete="CASCADE", so a populated value
    would take the audit row down with the experiment.
    """
    experiment_id = exp.experiment_id
    exp_pk = exp.id

    impact = collect_delete_impact(db, exp)
    snapshot = serialize_experiment_snapshot(db, exp)

    # 1. XRD phases: DELETE, not decouple. Matched on fk OR string so a row
    #    orphaned by an earlier delete cannot keep holding the unique slot on
    #    (experiment_id, time_post_reaction_days, mineral_name).
    db.query(XRDPhase).filter(
        or_(XRDPhase.experiment_fk == exp_pk, XRDPhase.experiment_id == experiment_id)
    ).delete(synchronize_session=False)

    # 2. Ammonium background provenance on OTHER experiments' scalar results.
    #    The string has no FK and is the column actually in use; the fk is
    #    nulled too so nothing depends on deployed constraint parity.
    db.execute(
        update(ScalarResults)
        .where(or_(ScalarResults.background_experiment_id == experiment_id,
                   ScalarResults.background_experiment_fk == exp_pk))
        .values(background_experiment_id=None, background_experiment_fk=None)
    )

    # 3. Reactor change requests keep their row, lose the reference. Safe
    #    against uq_change_request_reactor_experiment_date: PostgreSQL treats
    #    NULL as distinct in unique constraints.
    db.execute(
        update(ReactorChangeRequest)
        .where(ReactorChangeRequest.experiment_id == experiment_id)
        .values(experiment_id=None)
    )

    # 4. Replicate children: drop the parent pointer explicitly rather than
    #    relying on the DB SET NULL. base_experiment_id is untouched, so the
    #    group stays addressable by string (MODELS.md, issue #87).
    if impact.replicate_children:
        db.execute(
            update(Experiment)
            .where(Experiment.parent_experiment_fk == exp_pk, Experiment.id != exp_pk)
            .values(parent_experiment_fk=None)
        )

    # 5. The audit trail -- experiment_fk=None so it outlives the experiment.
    db.add(ModificationsLog(
        experiment_id=experiment_id,
        experiment_fk=None,
        sample_id=exp.sample_id,
        modified_by=modified_by,
        modification_type="delete",
        modified_table="experiments",
        old_values=snapshot,
        new_values={
            "impact": {
                "results": impact.results,
                "scalar_results": impact.scalar_results,
                "icp_results": impact.icp_results,
                "result_files": impact.result_files,
                "notes": impact.notes,
                "additives": impact.additives,
                "external_analyses": impact.external_analyses,
                "xrd_phases": impact.xrd_phases,
                "change_requests": impact.change_requests,
                "total": impact.total,
            },
            "decoupled_background_for": impact.background_for,
            "decoupled_replicate_children": impact.replicate_children,
        },
    ))
    db.flush()

    db.delete(exp)
    db.commit()

    log.info(
        "experiment_deleted",
        experiment_id=experiment_id,
        user=modified_by,
        rows_destroyed=impact.total,
        decoupled_background_for=impact.background_for,
        decoupled_replicate_children=impact.replicate_children,
    )
    return impact
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/services/test_experiment_deletion.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/experiment_deletion.py tests/services/test_experiment_deletion.py
git commit -m "[#99] Add audited orphan-safe experiment delete

- Snapshot to ModificationsLog with experiment_fk=NULL so it survives
- Deletes xrd_phases; nulls background provenance and change requests
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `GET /api/experiments/{experiment_id}/delete-impact`

**Files:**
- Modify: `backend/api/schemas/experiments.py` (append after `ReplicateCreateResponse`, currently ends line 209)
- Modify: `backend/api/routers/experiments.py` (add route immediately above `delete_experiment` at line 1271; extend the schema import block at lines 15-21)
- Test: `tests/api/test_experiments.py`

**Interfaces:**
- Consumes: `collect_delete_impact`, `DeleteImpact` (Task 1).
- Produces: `DeleteImpactResponse` and `ExperimentDeletedResponse` Pydantic models; `impact_to_response(impact: DeleteImpact) -> DeleteImpactResponse` lives in the router module as `_impact_to_response`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_experiments.py`:

```python
# --- Issue #99: delete impact and audited deletion ---

def _experiment_with_dependents(db, experiment_id="IMPACT_001", number=7301):
    """Experiment with results + scalar + note + XRD phase, for impact tests."""
    from database.models.results import ExperimentalResults, ScalarResults
    from database.models.experiments import ExperimentNotes
    from database.models.xrd import XRDPhase

    exp = Experiment(experiment_id=experiment_id, experiment_number=number,
                     status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    result = ExperimentalResults(experiment_fk=exp.id, time_post_reaction_days=7.0,
                                 time_post_reaction_bucket_days=7.0,
                                 is_primary_timepoint_result=True, description="t7")
    db.add(result)
    db.flush()
    db.add(ScalarResults(result_id=result.id, final_ph=7.2))
    db.add(ExperimentNotes(experiment_id=experiment_id, experiment_fk=exp.id, note_text="n"))
    db.add(XRDPhase(experiment_fk=exp.id, experiment_id=experiment_id,
                    time_post_reaction_days=7, mineral_name="Magnetite", amount=9.0))
    db.commit()
    db.refresh(exp)
    return exp


def test_delete_impact_returns_accurate_counts(client, db_session):
    _experiment_with_dependents(db_session)
    resp = client.get("/api/experiments/IMPACT_001/delete-impact")
    assert resp.status_code == 200
    body = resp.json()
    assert body["experiment_id"] == "IMPACT_001"
    assert body["results"] == 1
    assert body["scalar_results"] == 1
    assert body["notes"] == 1
    assert body["xrd_phases"] == 1
    assert body["icp_results"] == 0
    assert body["total"] == 4
    assert body["background_for"] == []
    assert body["replicate_children"] == []


def test_delete_impact_zero_for_bare_experiment(client, db_session):
    _make_experiment(db_session, "IMPACT_BARE_001", 7302)
    body = client.get("/api/experiments/IMPACT_BARE_001/delete-impact").json()
    assert body["total"] == 0


def test_delete_impact_404_for_unknown_experiment(client):
    assert client.get("/api/experiments/NOPE_999/delete-impact").status_code == 404


def test_delete_impact_lists_background_dependents(client, db_session):
    from database.models.results import ExperimentalResults, ScalarResults

    target = Experiment(experiment_id="IMPACT_BG_TARGET", experiment_number=7303,
                        status=ExperimentStatus.ONGOING)
    other = Experiment(experiment_id="IMPACT_BG_USER", experiment_number=7304,
                       status=ExperimentStatus.ONGOING)
    db_session.add_all([target, other])
    db_session.flush()
    result = ExperimentalResults(experiment_fk=other.id, time_post_reaction_days=0.0,
                                 is_primary_timepoint_result=True, description="t0")
    db_session.add(result)
    db_session.flush()
    db_session.add(ScalarResults(result_id=result.id,
                                 background_experiment_id="IMPACT_BG_TARGET"))
    db_session.commit()

    body = client.get("/api/experiments/IMPACT_BG_TARGET/delete-impact").json()
    assert body["background_for"] == ["IMPACT_BG_USER"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/api/test_experiments.py -k delete_impact -v`
Expected: FAIL — 404s from the SPA catch-all or `KeyError`, because the route does not exist yet.

> **Route-registration note:** per auto-memory `spa-catchall-blocks-404-tests`, a missing API route can be swallowed by the SPA catch-all and surface as HTML rather than a clean 404. If a failure looks like an HTML body, that confirms the route is simply not registered — not a bug to chase.

- [ ] **Step 3: Add the schemas**

Append to `backend/api/schemas/experiments.py`:

```python
class DeleteImpactResponse(BaseModel):
    """What deleting an experiment destroys and decouples (issue #99).

    `total` sums the counts only. `background_for` and `replicate_children`
    are decoupled -- those experiments survive -- so they are excluded from it.
    The UI demands a typed-ID confirmation when `total > 0`.
    """
    experiment_id: str
    results: int = 0
    scalar_results: int = 0
    icp_results: int = 0
    result_files: int = 0
    notes: int = 0
    additives: int = 0
    external_analyses: int = 0
    xrd_phases: int = 0
    change_requests: int = 0
    total: int = 0
    background_for: list[str] = []
    replicate_children: list[str] = []


class ExperimentDeletedResponse(BaseModel):
    """Body of DELETE /api/experiments/{experiment_id} (issue #99).

    This endpoint returns 200 with a body, NOT 204: the acceptance criteria
    require it to report which experiments were decoupled, which a 204 cannot
    carry. `impact` is measured immediately before the delete, so it reflects
    what actually happened rather than the pre-flight estimate.
    """
    experiment_id: str
    deleted: bool = True
    impact: DeleteImpactResponse
```

- [ ] **Step 4: Add the route**

In `backend/api/routers/experiments.py`, extend the schema import block (lines 15-21) with `DeleteImpactResponse, ExperimentDeletedResponse,` and add near the other service imports:

```python
from backend.services.experiment_deletion import (
    DeleteImpact, collect_delete_impact, delete_experiment_cascade,
)
```

Then insert immediately **above** `@router.delete("/{experiment_id}", status_code=204)` (line 1271):

```python
def _impact_to_response(impact: DeleteImpact) -> DeleteImpactResponse:
    return DeleteImpactResponse(
        experiment_id=impact.experiment_id,
        results=impact.results,
        scalar_results=impact.scalar_results,
        icp_results=impact.icp_results,
        result_files=impact.result_files,
        notes=impact.notes,
        additives=impact.additives,
        external_analyses=impact.external_analyses,
        xrd_phases=impact.xrd_phases,
        change_requests=impact.change_requests,
        total=impact.total,
        background_for=impact.background_for,
        replicate_children=impact.replicate_children,
    )


@router.get("/{experiment_id}/delete-impact", response_model=DeleteImpactResponse)
def get_experiment_delete_impact(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> DeleteImpactResponse:
    """Preview what deleting this experiment would destroy and decouple.

    Read-only; powers the confirmation dialog so it can show consequences
    instead of a generic warning. 404 if the experiment does not exist.
    """
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return _impact_to_response(collect_delete_impact(db, exp))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/api/test_experiments.py -k delete_impact -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add backend/api/schemas/experiments.py backend/api/routers/experiments.py tests/api/test_experiments.py
git commit -m "[#99] Add delete-impact preview endpoint

- GET /api/experiments/{id}/delete-impact with per-table counts
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Rewire `DELETE /api/experiments/{experiment_id}`

**Files:**
- Modify: `backend/api/routers/experiments.py:1271-1286` (the whole `delete_experiment` function)
- Test: `tests/api/test_experiments.py` (updates the existing `test_delete_experiment` at line 74)

**Interfaces:**
- Consumes: `delete_experiment_cascade` (Task 2), `_impact_to_response` and `ExperimentDeletedResponse` (Task 3).
- Produces: nothing new for later tasks beyond the changed response contract.

- [ ] **Step 1: Update the existing test and add new ones**

In `tests/api/test_experiments.py`, **replace** `test_delete_experiment` (line 74) with:

```python
def test_delete_experiment(client, db_session):
    """Issue #99: was 204 No Content; now 200 with an impact body so the
    caller learns what was decoupled."""
    _make_experiment(db_session, "DELETE_ME_001", 8005)
    resp = client.delete("/api/experiments/DELETE_ME_001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["experiment_id"] == "DELETE_ME_001"
    assert body["deleted"] is True
    assert body["impact"]["total"] == 0
    assert client.get("/api/experiments/DELETE_ME_001").status_code == 404


def test_delete_experiment_404_for_unknown(client):
    assert client.delete("/api/experiments/NOT_THERE_999").status_code == 404
```

And append:

```python
def test_delete_reports_impact_and_leaves_no_xrd_orphans(client, db_session):
    from database.models.xrd import XRDPhase
    from sqlalchemy import func, select as sa_select

    _experiment_with_dependents(db_session, "DELETE_DEEP_001", 7401)
    body = client.delete("/api/experiments/DELETE_DEEP_001").json()

    assert body["impact"]["results"] == 1
    assert body["impact"]["scalar_results"] == 1
    assert body["impact"]["xrd_phases"] == 1
    assert db_session.execute(
        sa_select(func.count()).select_from(XRDPhase)
        .where(XRDPhase.experiment_id == "DELETE_DEEP_001")
    ).scalar_one() == 0


def test_delete_succeeds_when_experiment_is_anothers_background(client, db_session):
    """Acceptance criterion: succeeds AND names the decoupled experiment."""
    from database.models.results import ExperimentalResults, ScalarResults

    target = Experiment(experiment_id="DELETE_BG_TARGET", experiment_number=7402,
                        status=ExperimentStatus.ONGOING)
    other = Experiment(experiment_id="DELETE_BG_USER", experiment_number=7403,
                       status=ExperimentStatus.ONGOING)
    db_session.add_all([target, other])
    db_session.flush()
    result = ExperimentalResults(experiment_fk=other.id, time_post_reaction_days=0.0,
                                 is_primary_timepoint_result=True, description="t0")
    db_session.add(result)
    db_session.flush()
    db_session.add(ScalarResults(result_id=result.id,
                                 background_experiment_id="DELETE_BG_TARGET",
                                 background_ammonium_concentration_mM=0.2))
    db_session.commit()

    resp = client.delete("/api/experiments/DELETE_BG_TARGET")
    assert resp.status_code == 200
    assert resp.json()["impact"]["background_for"] == ["DELETE_BG_USER"]

    from sqlalchemy import select as sa_select
    scalar = db_session.execute(
        sa_select(ScalarResults).where(ScalarResults.result_id == result.id)
    ).scalar_one()
    assert scalar.background_experiment_id is None
    assert scalar.background_ammonium_concentration_mM == 0.2  # number preserved
    assert client.get("/api/experiments/DELETE_BG_USER").status_code == 200


def test_delete_frees_the_experiment_id_for_reuse(client, db_session):
    """The actual need behind the SERUM_Catalyst incident."""
    _experiment_with_dependents(db_session, "REUSE_ME_001", 7404)
    assert client.delete("/api/experiments/REUSE_ME_001").status_code == 200
    resp = client.post("/api/experiments",
                       json={"experiment_id": "REUSE_ME_001", "experiment_number": 7405})
    assert resp.status_code == 201


def test_delete_audit_entry_survives_and_holds_a_snapshot(client, db_session):
    from database.models.experiments import ModificationsLog
    from sqlalchemy import select as sa_select

    _experiment_with_dependents(db_session, "AUDIT_ME_001", 7406)
    assert client.delete("/api/experiments/AUDIT_ME_001").status_code == 200

    entry = db_session.execute(
        sa_select(ModificationsLog).where(
            ModificationsLog.experiment_id == "AUDIT_ME_001",
            ModificationsLog.modification_type == "delete",
        )
    ).scalar_one()
    assert entry.experiment_fk is None
    assert entry.modified_by == "test@addisenergy.com"  # conftest _FAKE_USER
    assert entry.old_values["experiment"]["experiment_number"] == 7406
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/api/test_experiments.py -k "delete_experiment or delete_reports or delete_succeeds or frees_the_experiment or audit_entry" -v`
Expected: FAIL — `assert 204 == 200`, and `json.decoder.JSONDecodeError` on the empty 204 body.

- [ ] **Step 3: Rewrite the endpoint**

Replace `backend/api/routers/experiments.py:1271-1286` entirely with:

```python
@router.delete("/{experiment_id}", response_model=ExperimentDeletedResponse)
def delete_experiment(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentDeletedResponse:
    """Hard-delete an experiment, its dependents, and every reference to it.

    Returns 200 with the impact actually applied -- NOT 204 -- so the caller
    learns which other experiments were decoupled (issue #99). Available to any
    approved researcher; the controls are the ModificationsLog snapshot written
    here and the typed-ID confirmation in the UI. See
    backend/services/experiment_deletion.py for why a bare db.delete() is not
    sufficient.
    """
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    impact = delete_experiment_cascade(db, exp, modified_by=current_user.email)
    return ExperimentDeletedResponse(
        experiment_id=experiment_id,
        deleted=True,
        impact=_impact_to_response(impact),
    )
```

Note: the `log.info("experiment_deleted", ...)` call that was here moved into `delete_experiment_cascade` (Task 2) with richer fields — do not duplicate it.

- [ ] **Step 4: Run the full API + service suites**

Run: `.venv/Scripts/python -m pytest tests/api/test_experiments.py tests/services/test_experiment_deletion.py -v`
Expected: all pass, including the 13 service tests and every pre-existing `test_experiments.py` test.

Then confirm nothing else in the suite depended on the 204:

Run: `.venv/Scripts/python -m pytest tests/api tests/services tests/models tests/views -q`
Expected: all pass. If `tests/test_pg_backup_restore.py` appears and fails, that is the known pre-existing test-order issue (auto-memory `pg-backup-restore-test-order-fragility`) — do not chase it, and do not include that path in this run.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/experiments.py tests/api/test_experiments.py
git commit -m "[#99] Route DELETE through cascade service

- DELETE now 200 with impact body (was 204) to report decoupling
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Frontend API client

**Files:**
- Modify: `frontend/src/api/experiments.ts` (types near the other interfaces; methods in the `experimentsApi` object — `delete` is at line 301)
- Test: `frontend/src/api/__tests__/experiments.deleteExperiment.test.ts`

**Interfaces:**
- Consumes: the Task 3/4 response contract.
- Produces:
  - `interface DeleteImpact` (all 10 numeric fields plus `experiment_id`, `background_for`, `replicate_children`)
  - `interface ExperimentDeleted { experiment_id: string; deleted: boolean; impact: DeleteImpact }`
  - `experimentsApi.getDeleteImpact(experimentId: string): Promise<DeleteImpact>`
  - `experimentsApi.delete(experimentId: string): Promise<ExperimentDeleted>`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/__tests__/experiments.deleteExperiment.test.ts`. Mirror the existing `experiments.deleteNote.test.ts` harness.

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../client', () => ({
  apiClient: { get: vi.fn(), delete: vi.fn() },
}))

import { experimentsApi } from '../experiments'
import { apiClient } from '../client'

const IMPACT = {
  experiment_id: 'SERUM_001a',
  results: 2,
  scalar_results: 2,
  icp_results: 1,
  result_files: 0,
  notes: 1,
  additives: 3,
  external_analyses: 0,
  xrd_phases: 4,
  change_requests: 0,
  total: 13,
  background_for: ['SERUM_002a'],
  replicate_children: [],
}

beforeEach(() => vi.clearAllMocks())

describe('experimentsApi delete endpoints', () => {
  it('getDeleteImpact GETs the delete-impact path and unwraps data', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: IMPACT })
    const impact = await experimentsApi.getDeleteImpact('SERUM_001a')
    expect(apiClient.get).toHaveBeenCalledWith('/experiments/SERUM_001a/delete-impact')
    expect(impact.total).toBe(13)
    expect(impact.background_for).toEqual(['SERUM_002a'])
  })

  it('getDeleteImpact encodes ids with unsafe characters', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: IMPACT })
    await experimentsApi.getDeleteImpact('X Cation/001')
    expect(apiClient.get).toHaveBeenCalledWith(
      '/experiments/X%20Cation%2F001/delete-impact',
    )
  })

  it('delete returns the impact body', async () => {
    vi.mocked(apiClient.delete).mockResolvedValue({
      data: { experiment_id: 'SERUM_001a', deleted: true, impact: IMPACT },
    })
    const res = await experimentsApi.delete('SERUM_001a')
    expect(apiClient.delete).toHaveBeenCalledWith('/experiments/SERUM_001a')
    expect(res.deleted).toBe(true)
    expect(res.impact.xrd_phases).toBe(4)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/api/__tests__/experiments.deleteExperiment.test.ts`
Expected: FAIL — `experimentsApi.getDeleteImpact is not a function`

- [ ] **Step 3: Add the types and methods**

In `frontend/src/api/experiments.ts`, add after the `ExperimentDetail` interface (ends line 68):

```typescript
/** Issue #99: what deleting an experiment destroys (counts) and decouples (lists).
 *  `total` sums the counts only — the listed experiments survive. */
export interface DeleteImpact {
  experiment_id: string
  results: number
  scalar_results: number
  icp_results: number
  result_files: number
  notes: number
  additives: number
  external_analyses: number
  xrd_phases: number
  change_requests: number
  total: number
  /** Other experiments that named this one as their ammonium background. */
  background_for: string[]
  /** Replicates whose parent pointer is dropped; their group ID is unaffected. */
  replicate_children: string[]
}

export interface ExperimentDeleted {
  experiment_id: string
  deleted: boolean
  impact: DeleteImpact
}
```

Then **replace** the `delete` method (line 301-302) with:

```typescript
  getDeleteImpact: (experimentId: string) =>
    apiClient
      .get<DeleteImpact>(`/experiments/${encodeURIComponent(experimentId)}/delete-impact`)
      .then((r) => r.data),

  delete: (experimentId: string) =>
    apiClient
      .delete<ExperimentDeleted>(`/experiments/${encodeURIComponent(experimentId)}`)
      .then((r) => r.data),
```

- [ ] **Step 4: Run the test and the type check**

Run: `cd frontend && npx vitest run src/api/__tests__/experiments.deleteExperiment.test.ts && npx tsc --noEmit`
Expected: 3 passed; `tsc` clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/experiments.ts frontend/src/api/__tests__/experiments.deleteExperiment.test.ts
git commit -m "[#99] Add delete-impact to experiments API client

- getDeleteImpact + typed delete response
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `DeleteExperimentModal`

The confirmation dialog: fetches impact on open, itemizes consequences, and requires the exact `experiment_id` to be typed when `total > 0`.

**Files:**
- Create: `frontend/src/components/experiments/DeleteExperimentModal.tsx`
- Test: `frontend/src/components/experiments/DeleteExperimentModal.test.tsx`

**Interfaces:**
- Consumes: `experimentsApi.getDeleteImpact`, `experimentsApi.delete`, `DeleteImpact` (Task 5); `Modal`, `Button`, `Input`, `PageSpinner`, `useToast` from `@/components/ui`.
- Produces:
  ```typescript
  interface DeleteExperimentModalProps {
    open: boolean
    experimentId: string
    onClose: () => void
    onDeleted: (result: ExperimentDeleted) => void
  }
  export function DeleteExperimentModal(props: DeleteExperimentModalProps): JSX.Element | null
  ```
  `onDeleted` fires only after a successful delete; the parent owns navigation and cache invalidation (Task 7).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/experiments/DeleteExperimentModal.test.tsx`. Harness mirrors `CreateReplicatesModal.test.tsx` / `OutlierToggle.test.tsx`.

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'

vi.mock('@/api/experiments', () => ({
  experimentsApi: { getDeleteImpact: vi.fn(), delete: vi.fn() },
}))

import { DeleteExperimentModal } from './DeleteExperimentModal'
import { experimentsApi } from '@/api/experiments'
import type { DeleteImpact } from '@/api/experiments'

const EMPTY_IMPACT: DeleteImpact = {
  experiment_id: 'SERUM_001a',
  results: 0, scalar_results: 0, icp_results: 0, result_files: 0,
  notes: 0, additives: 0, external_analyses: 0, xrd_phases: 0,
  change_requests: 0, total: 0, background_for: [], replicate_children: [],
}

const HEAVY_IMPACT: DeleteImpact = {
  ...EMPTY_IMPACT,
  results: 3, scalar_results: 3, icp_results: 2, notes: 1, xrd_phases: 4,
  total: 13, background_for: ['SERUM_002a'], replicate_children: ['SERUM_001a-2'],
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
})

function renderModal(onDeleted = vi.fn(), onClose = vi.fn()) {
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <DeleteExperimentModal
          open
          experimentId="SERUM_001a"
          onClose={onClose}
          onDeleted={onDeleted}
        />
      </ToastProvider>
    </QueryClientProvider>,
  )
  return { onDeleted, onClose }
}

beforeEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
  vi.mocked(experimentsApi.delete).mockResolvedValue({
    experiment_id: 'SERUM_001a', deleted: true, impact: HEAVY_IMPACT,
  })
})

describe('DeleteExperimentModal', () => {
  it('itemizes the impact counts, hiding zero rows', async () => {
    vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue(HEAVY_IMPACT)
    renderModal()
    expect(await screen.findByText(/3 result timepoints/i)).toBeInTheDocument()
    expect(screen.getByText(/4 XRD phase rows/i)).toBeInTheDocument()
    expect(screen.queryByText(/result files/i)).not.toBeInTheDocument()
  })

  it('names the experiments that will be decoupled', async () => {
    vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue(HEAVY_IMPACT)
    renderModal()
    expect(await screen.findByText(/SERUM_002a/)).toBeInTheDocument()
    expect(screen.getByText(/SERUM_001a-2/)).toBeInTheDocument()
  })

  it('keeps Delete disabled until the exact id is typed when impact is non-zero', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue(HEAVY_IMPACT)
    renderModal()

    const confirmBtn = await screen.findByRole('button', { name: /^delete$/i })
    expect(confirmBtn).toBeDisabled()

    const input = screen.getByLabelText(/type the experiment id/i)
    await user.type(input, 'SERUM_001')
    expect(confirmBtn).toBeDisabled()

    await user.type(input, 'a')
    await waitFor(() => expect(confirmBtn).toBeEnabled())

    await user.click(confirmBtn)
    await waitFor(() => expect(experimentsApi.delete).toHaveBeenCalledWith('SERUM_001a'))
  })

  it('does not require a typed id when nothing depends on the experiment', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue(EMPTY_IMPACT)
    renderModal()

    expect(await screen.findByText(/no dependent records/i)).toBeInTheDocument()
    expect(screen.queryByLabelText(/type the experiment id/i)).not.toBeInTheDocument()

    const confirmBtn = screen.getByRole('button', { name: /^delete$/i })
    expect(confirmBtn).toBeEnabled()
    await user.click(confirmBtn)
    await waitFor(() => expect(experimentsApi.delete).toHaveBeenCalledWith('SERUM_001a'))
  })

  it('cancel is a no-op — closes without deleting', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue(HEAVY_IMPACT)
    const { onClose, onDeleted } = renderModal()

    await user.click(await screen.findByRole('button', { name: /cancel/i }))
    expect(onClose).toHaveBeenCalled()
    expect(experimentsApi.delete).not.toHaveBeenCalled()
    expect(onDeleted).not.toHaveBeenCalled()
  })

  it('calls onDeleted with the server response on success', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue(EMPTY_IMPACT)
    const { onDeleted } = renderModal()

    await user.click(await screen.findByRole('button', { name: /^delete$/i }))
    await waitFor(() =>
      expect(onDeleted).toHaveBeenCalledWith(
        expect.objectContaining({ experiment_id: 'SERUM_001a', deleted: true }),
      ),
    )
  })

  it('surfaces a server error and does not call onDeleted', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue(EMPTY_IMPACT)
    vi.mocked(experimentsApi.delete).mockRejectedValue({
      response: { data: { detail: 'Experiment not found' } },
    })
    const { onDeleted } = renderModal()

    await user.click(await screen.findByRole('button', { name: /^delete$/i }))
    expect(await screen.findByText(/experiment not found/i)).toBeInTheDocument()
    expect(onDeleted).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/experiments/DeleteExperimentModal.test.tsx`
Expected: FAIL — cannot resolve `./DeleteExperimentModal`

- [ ] **Step 3: Write the component**

Create `frontend/src/components/experiments/DeleteExperimentModal.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import type { DeleteImpact, ExperimentDeleted } from '@/api/experiments'
import { Modal, Button, Input, PageSpinner, useToast } from '@/components/ui'

interface DeleteExperimentModalProps {
  open: boolean
  experimentId: string
  onClose: () => void
  onDeleted: (result: ExperimentDeleted) => void
}

/** Human-readable label per impact field, in the order shown. */
const IMPACT_ROWS: Array<[keyof DeleteImpact, string]> = [
  ['results', 'result timepoints'],
  ['scalar_results', 'scalar measurement rows'],
  ['icp_results', 'ICP measurement rows'],
  ['result_files', 'result files'],
  ['notes', 'notes'],
  ['additives', 'chemical additives'],
  ['external_analyses', 'external analyses'],
  ['xrd_phases', 'XRD phase rows'],
  ['change_requests', 'reactor change requests'],
]

/**
 * Confirmation dialog for deleting a single experiment (issue #99).
 *
 * Deletion is a hard delete and is available to any approved researcher, so
 * the guard rails live here: the dialog itemizes exactly what will be
 * destroyed (from GET /delete-impact) and requires the user to type the
 * experiment ID whenever anything depends on it. The audit trail is written
 * server-side into ModificationsLog.
 */
export function DeleteExperimentModal({
  open, experimentId, onClose, onDeleted,
}: DeleteExperimentModalProps) {
  const { error: toastError } = useToast()
  const [typed, setTyped] = useState('')
  const [serverError, setServerError] = useState<string | null>(null)

  // Reset the gate whenever the dialog opens or retargets, so a previously
  // typed confirmation can never carry over to another experiment.
  useEffect(() => {
    if (open) {
      setTyped('')
      setServerError(null)
    }
  }, [open, experimentId])

  const { data: impact, isLoading } = useQuery({
    queryKey: ['delete-impact', experimentId],
    queryFn: () => experimentsApi.getDeleteImpact(experimentId),
    enabled: open && Boolean(experimentId),
  })

  const deleteMutation = useMutation({
    mutationFn: () => experimentsApi.delete(experimentId),
    onSuccess: (result) => onDeleted(result),
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      const msg = detail ?? 'Could not delete this experiment'
      setServerError(msg)
      toastError('Delete failed', msg)
    },
  })

  const needsTypedId = (impact?.total ?? 0) > 0
  const canDelete =
    Boolean(impact) && !deleteMutation.isPending &&
    (!needsTypedId || typed.trim() === experimentId)

  const rows = impact
    ? IMPACT_ROWS.filter(([key]) => (impact[key] as number) > 0)
    : []

  return (
    <Modal
      open={open}
      title="Delete Experiment"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            variant="danger"
            onClick={() => deleteMutation.mutate()}
            disabled={!canDelete}
          >
            Delete
          </Button>
        </>
      }
    >
      {isLoading && <PageSpinner />}

      {impact && (
        <div className="space-y-3 text-sm">
          <p className="text-ink-secondary">
            Permanently delete{' '}
            <span className="font-mono-data text-ink-primary">{experimentId}</span>?
            This cannot be undone from the app.
          </p>

          {rows.length > 0 ? (
            <div>
              <p className="text-ink-secondary">These records are deleted with it:</p>
              <ul className="mt-1 space-y-0.5 text-ink-muted">
                {rows.map(([key, label]) => (
                  <li key={key} className="tabular-nums">
                    {impact[key] as number} {label}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-ink-muted">No dependent records — nothing else is affected.</p>
          )}

          {impact.background_for.length > 0 && (
            <p className="text-ink-muted">
              Used as the ammonium background by{' '}
              <span className="font-mono-data">{impact.background_for.join(', ')}</span>.
              That reference is cleared; the stored background values are unchanged.
            </p>
          )}

          {impact.replicate_children.length > 0 && (
            <p className="text-ink-muted">
              Parent of{' '}
              <span className="font-mono-data">{impact.replicate_children.join(', ')}</span>.
              Those experiments survive and stay in their replicate group.
            </p>
          )}

          {needsTypedId && (
            <div>
              <label htmlFor="delete-confirm-id" className="block text-ink-secondary mb-1">
                Type the experiment ID to confirm
              </label>
              <Input
                id="delete-confirm-id"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                placeholder={experimentId}
                className="font-mono-data"
                autoFocus
              />
            </div>
          )}

          {serverError && <p className="text-red-400">{serverError}</p>}
        </div>
      )}
    </Modal>
  )
}
```

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/experiments/DeleteExperimentModal.test.tsx`
Expected: 7 passed

If `Input` does not forward `id`, check `frontend/src/components/ui/Input.tsx` — the label association is what `getByLabelText` relies on. If `id` is not in its props, thread it through (`id?: string` passed to the underlying `<input>`); that is a one-line additive change, not a redesign.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/experiments/DeleteExperimentModal.tsx frontend/src/components/experiments/DeleteExperimentModal.test.tsx
git commit -m "[#99] Add DeleteExperimentModal with typed-ID gate

- Itemizes impact from /delete-impact; names decoupled experiments
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Wire deletion into `ExperimentDetail`

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/index.tsx` (imports ~line 9; state ~line 33; quick-actions row lines 364-383; modal mount beside `CreateReplicatesModal` at lines 384-388)
- Test: `frontend/src/pages/ExperimentDetail/__tests__/DeleteExperiment.test.tsx`

**Interfaces:**
- Consumes: `DeleteExperimentModal` (Task 6).
- Produces: nothing for later tasks.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/ExperimentDetail/__tests__/DeleteExperiment.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '@/components/ui'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    get: vi.fn(),
    patch: vi.fn(),
    getReplicateGroup: vi.fn(),
    getResults: vi.fn(),
    getRollup: vi.fn(),
    getDeleteImpact: vi.fn(),
    delete: vi.fn(),
  },
}))
vi.mock('@/api/conditions', () => ({
  conditionsApi: { getByExperiment: vi.fn().mockRejectedValue(new Error('none')) },
}))

import { ExperimentDetailPage } from '../index'
import { experimentsApi } from '@/api/experiments'
import type { ExperimentDetail, DeleteImpact } from '@/api/experiments'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
})

const BASE_DETAIL: ExperimentDetail = {
  id: 5, experiment_id: 'SERUM_050', experiment_number: 150, status: 'ONGOING',
  researcher: null, date: null, sample_id: null, base_experiment_id: null,
  parent_experiment_fk: null, replicate_label: null, is_outlier: false,
  id_timepoint_days: null, created_at: '2026-07-01T00:00:00Z', updated_at: null,
  conditions: null, notes: [], modifications: [],
}

const EMPTY_IMPACT: DeleteImpact = {
  experiment_id: 'SERUM_050',
  results: 0, scalar_results: 0, icp_results: 0, result_files: 0, notes: 0,
  additives: 0, external_analyses: 0, xrd_phases: 0, change_requests: 0,
  total: 0, background_for: [], replicate_children: [],
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/experiments/SERUM_050']}>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <Routes>
            <Route path="/experiments/:id" element={<ExperimentDetailPage />} />
            <Route path="/experiments" element={<div>Experiments List</div>} />
          </Routes>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
  vi.mocked(experimentsApi.get).mockResolvedValue(BASE_DETAIL)
  vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
    base_experiment_id: 'SERUM_050', parent: null, members: [],
  })
  vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue(EMPTY_IMPACT)
  vi.mocked(experimentsApi.delete).mockResolvedValue({
    experiment_id: 'SERUM_050', deleted: true, impact: EMPTY_IMPACT,
  })
})

describe('experiment deletion from the detail page', () => {
  it('exposes a Delete Experiment action', async () => {
    renderPage()
    expect(
      await screen.findByRole('button', { name: /delete experiment/i }),
    ).toBeInTheDocument()
  })

  it('opens the confirmation dialog rather than deleting immediately', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /delete experiment/i }))
    expect(await screen.findByText(/permanently delete/i)).toBeInTheDocument()
    expect(experimentsApi.delete).not.toHaveBeenCalled()
  })

  it('deletes and navigates back to the list on success', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /delete experiment/i }))
    await user.click(await screen.findByRole('button', { name: /^delete$/i }))
    await waitFor(() => expect(experimentsApi.delete).toHaveBeenCalledWith('SERUM_050'))
    expect(await screen.findByText('Experiments List')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/ExperimentDetail/__tests__/DeleteExperiment.test.tsx`
Expected: FAIL — `Unable to find an accessible element with the role "button" and name /delete experiment/i`

- [ ] **Step 3: Wire it up**

In `frontend/src/pages/ExperimentDetail/index.tsx`:

Add after the `CreateReplicatesModal` import (line 9):

```tsx
import { DeleteExperimentModal } from '@/components/experiments/DeleteExperimentModal'
```

Add after the `replicatesOpen` state (line 33):

```tsx
  const [deleteOpen, setDeleteOpen] = useState(false)
```

Add a button at the end of the quick-actions `<div className="flex gap-2">` block (after the outlier toggle, before the closing `</div>` at line 383):

```tsx
        <Button variant="ghost" size="sm" onClick={() => setDeleteOpen(true)}>
          Delete Experiment
        </Button>
```

Add the modal immediately after `<CreateReplicatesModal ... />` (line 388):

```tsx
      <DeleteExperimentModal
        open={deleteOpen}
        experimentId={experiment.experiment_id}
        onClose={() => setDeleteOpen(false)}
        onDeleted={() => {
          setDeleteOpen(false)
          // Drop this experiment's own cached detail as well as the list and
          // group caches, so a freed experiment_id reused later does not read
          // back the deleted row.
          queryClient.removeQueries({ queryKey: ['experiment', experiment.experiment_id] })
          queryClient.invalidateQueries({ queryKey: ['experiments'] })
          queryClient.invalidateQueries({ queryKey: ['replicate-group'] })
          queryClient.invalidateQueries({ queryKey: ['rollup'] })
          success('Experiment deleted')
          navigate('/experiments', { replace: true })
        }}
      />
```

`success` and `navigate` are already in scope (lines 25 and 23).

- [ ] **Step 4: Run the tests, type check, and lint**

Run: `cd frontend && npx vitest run src/pages/ExperimentDetail/__tests__/DeleteExperiment.test.tsx && npx tsc --noEmit && npx eslint src --ext .ts,.tsx`
Expected: 3 passed; `tsc` clean; eslint zero warnings.

Then the whole frontend suite, to catch any snapshot/count assertions broken by the new button:

Run: `cd frontend && npx vitest run`
Expected: all files pass (was 133 passing across 23 files before this branch; expect 133 + the 13 added in Tasks 5-7).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/index.tsx frontend/src/pages/ExperimentDetail/__tests__/DeleteExperiment.test.tsx
git commit -m "[#99] Add delete action to experiment detail page

- Quick-action button, modal mount, cache eviction, redirect to list
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Documentation

**Files:**
- Modify: `.claude/rules/MODELS.md` (`Experiment` section, after the `is_outlier` bullet)
- Modify: `docs/api/API_REFERENCE.md` (Experiments section — insert before `### PATCH /api/experiments/{experiment_id}` at line 261)
- Modify: `docs/working/issue-log.md` (append)
- Modify: `docs/working/decisions.md` (append)

Do **not** edit `docs/project_context/` — the `PostToolUse` hook syncs it. `.claude/rules/MODELS.md` is outside `docs/` and is not synced; leave it at its real path.

**Interfaces:** none.

- [ ] **Step 1: Document the deletion path in MODELS.md**

Add to the `Experiment` bullet list in `.claude/rules/MODELS.md`, after the `is_outlier` entry:

```markdown
- **Deletion path (issue #99):** `DELETE /api/experiments/{experiment_id}` is a
  **hard** delete available to any approved researcher (no role gate) and returns
  **200 with a body** reporting what was decoupled — not 204. All orphan
  prevention lives in `backend/services/experiment_deletion.py`, not in the
  relationship cascades, because three references are not covered by
  `cascade="all, delete-orphan"`:
  - `xrd_phases` rows are **deleted**, matched on `experiment_fk` **or** the
    `experiment_id` string. Nulling the FK alone would leave rows whose stale
    string still holds the `uq_xrd_phase_experiment_time_mineral` slot on
    `(experiment_id, time_post_reaction_days, mineral_name)`, blocking
    re-creation of that experiment's XRD data.
  - `scalar_results.background_experiment_id` / `background_experiment_fk` on
    **other** experiments are NULLed. The string is the column actually in use
    (`background_experiment_fk` was set on 0 of 1056 rows as of 2026-07-29) and
    it has **no FK**, so nothing at the DB level protects it. This is provenance
    only — `background_ammonium_concentration_mM` holds the number the
    calculation engine reads, so no derived field changes and no
    `recalculate()` is needed.
  - `reactor_change_requests.experiment_id` is NULLed; the request row survives.
    Safe against `uq_change_request_reactor_experiment_date` because PostgreSQL
    treats `NULL` as distinct in unique constraints.

  Replicate children keep their `base_experiment_id` and `replicate_label`; only
  `parent_experiment_fk` is dropped. Groups are addressed by the base-ID
  *string* (issue #87), so the group page and `v_results_scalar_rollup` are
  unaffected — the affected IDs are reported in the response so the researcher
  is told.

  Every delete writes a `ModificationsLog` row with `modification_type='delete'`,
  `modified_table='experiments'`, `old_values` holding a snapshot of the
  experiment plus its conditions, additives and notes, and `new_values` holding
  the impact counts. **The row must be written with `experiment_fk = NULL`** —
  that FK is `ondelete="CASCADE"`, so a populated value would delete the audit
  row along with the experiment. Results and ICP data are deliberately excluded
  from the snapshot (bulk-uploadable, unbounded); only their counts are kept.

  **Constraint-parity caveat:** the dev and test DBs are built with
  `Base.metadata.create_all`, which honors the model `ondelete` clauses; the lab
  PC came up through the Alembic chain, whose initial migration declared none.
  The deletion service therefore never relies on DB-level behavior — every
  decoupling is explicit in application code.
```

- [ ] **Step 2: Document the endpoints in API_REFERENCE.md**

Insert before `### PATCH /api/experiments/{experiment_id}` in `docs/api/API_REFERENCE.md`:

```markdown
### GET /api/experiments/{experiment_id}/delete-impact

Preview what deleting an experiment would destroy and decouple. Read-only;
powers the delete confirmation dialog. `404` if the experiment does not exist.

```json
{
  "experiment_id": "SERUM_001a",
  "results": 3,
  "scalar_results": 3,
  "icp_results": 2,
  "result_files": 0,
  "notes": 1,
  "additives": 2,
  "external_analyses": 0,
  "xrd_phases": 4,
  "change_requests": 0,
  "total": 15,
  "background_for": ["SERUM_002a"],
  "replicate_children": []
}
```

`total` sums the counts only. `background_for` (experiments naming this one as
their ammonium background) and `replicate_children` (experiments whose
`parent_experiment_fk` points here) are **decoupled, not deleted** — those
experiments survive — so they are excluded from `total`. The UI requires the
user to type the experiment ID whenever `total > 0`.

### DELETE /api/experiments/{experiment_id}

Hard-deletes the experiment, its dependent records, and every reference to it.
Available to any approved researcher. `404` if the experiment does not exist.

**Returns `200` with a body, not `204`** — the caller needs to know what was
decoupled:

```json
{
  "experiment_id": "SERUM_001a",
  "deleted": true,
  "impact": { "...": "same shape as GET /delete-impact" }
}
```

`impact` is measured immediately before the delete, so it reports what actually
happened rather than the pre-flight estimate. Every call writes a
`ModificationsLog` entry with a restorable snapshot; see the deletion-path notes
in `.claude/rules/MODELS.md` for the orphan-prevention details and the
`experiment_fk = NULL` requirement on that log row.
```

- [ ] **Step 3: Append the issue-log entry**

Append to `docs/working/issue-log.md`, following the format of the `issue #98` entry above it: date `2026-07-29`, mode `issue #99`, the files changed, the three locked decisions, the corrections to the issue's premises (FK constraints do exist in dev; `background_experiment_fk` is unpopulated so the *string* is the real hazard; `Experiment.xrd_phases` does exist but has no cascade; `parent_experiment_fk` SET NULL was unmentioned in the issue), the `204 → 200` contract change with its two checked consumers, `Tests added: yes` with actual counts from the final runs, and the explicitly deferred bulk-delete follow-up.

- [ ] **Step 4: Append the decisions entry**

Append to `docs/working/decisions.md`: the three locked decisions with their rationale (any approved researcher — the issue exists to remove the Mat bottleneck, and the audit log plus typed-ID confirmation are the controls; hard delete — soft delete would not free the `experiment_id` string, which was the actual need in the SERUM_Catalyst incident, and would require filtering every `v_*` view; single delete only — bulk delete deferred until single delete is proven), plus the decision to hold all orphan prevention in app code rather than adding a migration to normalize FK constraints, because dev/prod constraint parity is unverified and app-level handling is correct either way.

- [ ] **Step 5: Run the full verification pass**

```bash
.venv/Scripts/python -m pytest tests/api tests/services tests/models tests/views -q
cd frontend && npx vitest run && npx tsc --noEmit && npx eslint src --ext .ts,.tsx
```

Record the actual pass counts in the issue-log entry. Do not claim completion until every command above has been run and its output confirmed (`superpowers:verification-before-completion`). If `tests/test_pg_backup_restore.py` is picked up and fails, that is the known pre-existing test-order issue — note it, do not fix it here.

- [ ] **Step 6: Commit**

```bash
git add .claude/rules/MODELS.md docs/api/API_REFERENCE.md docs/working/issue-log.md docs/working/decisions.md docs/project_context/
git commit -m "[#99] Document experiment deletion path

- MODELS.md orphan-prevention notes; API_REFERENCE delete endpoints
- Tests added: no
- Docs updated: yes

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Manual verification before merge

Automated tests do not exercise the real app. Before `/complete-task`, walk this in the running app (uvicorn on 8000, Vite on 5173 — both already running; do not restart them):

1. Open an experiment that has results, ICP, additives and XRD phases. Click **Delete Experiment**. Confirm the dialog itemizes real counts, not zeros.
2. Type a wrong ID → **Delete** stays disabled. Click **Cancel** → nothing happens, the experiment still exists.
3. Re-open, type the exact ID, delete. Confirm the redirect to `/experiments` and that the row is gone from the list.
4. Confirm in psql that no `xrd_phases` rows remain for that `experiment_id`, and that the `modifications_log` delete row exists with `experiment_fk IS NULL`:
   ```sql
   SELECT count(*) FROM xrd_phases WHERE experiment_id = '<deleted_id>';
   SELECT experiment_fk, modification_type, old_values->'experiment'->>'experiment_number'
   FROM modifications_log WHERE experiment_id = '<deleted_id>';
   ```
5. Re-create an experiment with the same `experiment_id` — it must succeed. This is the SERUM_Catalyst requirement.
6. Delete an experiment that is another experiment's ammonium background. Confirm the dialog names the dependent, the delete succeeds, and the dependent's `background_ammonium_concentration_mM` is unchanged while its `background_experiment_id` is now NULL.

## Deferred to a follow-up issue

- **Bulk "Delete selected"** reusing the existing selection `Set` in `ExperimentList.tsx:224`, with typed-ID confirmation per batch. This is what would have handled the 69-row SERUM_Catalyst incident directly. Open it once single delete is proven in the lab.
- **Normalizing FK `ondelete` clauses across dev and the lab PC** via a migration, so deployed constraints provably match the model declarations. Not needed for correctness here (everything is explicit in app code) but the unverified parity is a latent hazard for any future code that does rely on DB-level behavior.
