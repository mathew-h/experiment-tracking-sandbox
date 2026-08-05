# Bulk-Rename Denormalized `experiment_id` Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the bulk-upload rename path sync every denormalized copy of `experiments.experiment_id` — including `experimental_conditions.experiment_id`, the column that produced all 187 stale strings — so migration 018's backfill stops decaying with every rename workbook.

**Architecture:** Five tables carry a denormalized `experiment_id` string next to an authoritative `experiment_fk`: `experimental_conditions`, `experiment_notes`, `modifications_log`, `external_analyses`, `xrd_phases`. Today two rename paths each hand-roll a *different subset* of the fan-out (`PATCH /api/experiments/{id}` does four tables, the bulk parser does two, and no path does all five). This plan extracts one shared helper, `backend/services/denormalized_ids.py::sync_denormalized_experiment_id`, and has both paths call it — so the fan-out has exactly one definition and adding a sixth table later is a one-file change. The locked bulk parser's diff shrinks to deleting two loops and adding one call.

**Tech Stack:** Python 3.11, SQLAlchemy 2.x ORM (`update()` Core statements + ORM attribute assignment), FastAPI, PostgreSQL, pytest, structlog.

## Global Constraints

- **Locked files touched — user sign-off obtained 2026-08-05.** `backend/services/bulk_uploads/new_experiments.py` (Task 3) and `database/models/conditions.py` (Task 4, comment only) are locked per `.claude/CLAUDE.md` §5. Do not touch any other file under `backend/services/bulk_uploads/` or `database/models/`.
- **`database/models/` is storage-only.** No logic, no properties, no cascade changes there. Task 4's edit to `conditions.py` is a comment and nothing else.
- **No new third-party packages.** Everything needed is already imported somewhere in the repo.
- **Never run two pytest processes at once.** `experiments_test` is a single shared PostgreSQL schema; concurrent runs corrupt it and an interrupted run leaves a stale schema that `create_all` cannot repair.
- **Test-suite baseline:** `tests/test_pg_backup_restore.py` has **3 pre-existing failures** on `develop` (unrelated: `drop_all()` wiping `experiments_test`). Full-suite expectation is `3 failed, 1332 passed, 4 skipped`. Three failures = clean. Any fourth is yours.
- **Commands use the venv prefix:** `.venv/Scripts/python`, `.venv/Scripts/pytest`, `.venv/Scripts/alembic`. Bare `pytest`/`alembic` are not on PATH.
- **Branch:** `fix/issue-109-bulk-rename-id-sync`, cut from `develop`. PRs always `gh pr create --base develop`.
- **Commit format:** `[#109] <imperative, <50 chars, no trailing period>` then a body with `- Tests added: yes/no` and `- Docs updated: yes/no`.
- **No migration in this plan.** Zero schema change — the columns and the `uq_conditions_experiment_fk` constraint already exist (Alembic `00063a5dd6a8`).
- **Do not run `database/data_migrations/dedupe_conditions_and_backfill_ids_018.py --apply`.** That script has not been applied to any database including dev, and its deploy sequence is owned by the issue doc, not by this plan.

---

## Background an implementer needs

**The bug in one sentence:** `backend/services/bulk_uploads/new_experiments.py:543-575` renames an experiment and then updates the denormalized string on `experiment_notes` and `modifications_log` — but not on `experimental_conditions`, `external_analyses`, or `xrd_phases`.

**Why `experimental_conditions` is the one that mattered.** Every consumer of that string was fixed in the previous fix wave to resolve through `experiment_fk` instead, so a stale string is now cosmetic rather than load-bearing. But `database/data_migrations/dedupe_conditions_and_backfill_ids_018.py` is about to backfill all 187 stale rows on the lab PC, and every future rename workbook re-creates the debris it just cleaned.

**Why `xrd_phases` is worse than cosmetic.** `uq_xrd_phase_experiment_time_mineral` is `UNIQUE (experiment_id, time_post_reaction_days, mineral_name)` — on the *string*. A stale string holds that slot under the old name, and `backend/services/experiment_deletion.py` deletes XRD rows matched on `experiment_fk` **or** the string precisely because of this. Syncing the string is the right fix, but it can *collide* with a row that already holds the target slot — which is why the helper skips-and-reports rather than blowing up a rename (Task 1, Step 5).

**How the existing conditions block interacts.** At `new_experiments.py:759-774` the conditions sheet resolves its row by `ExperimentalConditions.experiment_fk` and never reassigns `experiment_id` on an existing row; a brand-new row gets the correct string at construction. So the conditions sheet neither fixes nor worsens the staleness — the rename block is the only place to fix it.

**Where the truth is currently mis-stated (Task 4).** Four places still claim no rename path syncs the string:
`database/models/conditions.py:9-14`, `backend/api/routers/conditions.py:48-61`, `.claude/rules/MODELS.md:~194`, `docs/api/API_REFERENCE.md:394`. Plus `docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md`'s "Follow-up" section, which this plan closes.

---

### Task 1: The shared sync helper

**Files:**
- Create: `backend/services/denormalized_ids.py`
- Test: `tests/services/test_denormalized_ids.py`

**Interfaces:**
- Consumes: nothing from earlier tasks. Model classes come from the `database` package root (`from database import ...`) — that package re-exports all five, verified.
- Produces — Tasks 2 and 3 both call exactly this:
  ```python
  @dataclass
  class DenormalizedIdSync:
      conditions: int = 0
      notes: int = 0
      modifications: int = 0
      external_analyses: int = 0
      xrd_phases: int = 0
      xrd_phases_skipped: list[int] = field(default_factory=list)

  def sync_denormalized_experiment_id(
      db: Session, experiment_fk: int, new_id: str
  ) -> DenormalizedIdSync: ...
  ```

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_denormalized_ids.py`. `db_session` is re-exported by `tests/services/conftest.py` from `tests/api/conftest.py`; it is a transaction-wrapped session that rolls back after each test, so seeded rows never persist.

```python
"""Unit tests for the single definition of the rename fan-out (issue #109 follow-up)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import (
    Experiment,
    ExperimentNotes,
    ExperimentalConditions,
    ExternalAnalysis,
    ModificationsLog,
    XRDPhase,
)
from database.models.enums import ExperimentStatus
from backend.services.denormalized_ids import sync_denormalized_experiment_id


def _seed(db: Session, exp_id: str, number: int) -> Experiment:
    """Create an experiment with one row in each of the five denormalized tables."""
    exp = Experiment(
        experiment_id=exp_id,
        experiment_number=number,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.flush()
    db.add_all([
        ExperimentalConditions(experiment_id=exp_id, experiment_fk=exp.id, temperature_c=250.0),
        ExperimentNotes(experiment_id=exp_id, experiment_fk=exp.id, note_text="seed note"),
        ModificationsLog(
            experiment_id=exp_id, experiment_fk=exp.id,
            modified_by="test", modification_type="create", modified_table="experiments",
        ),
        ExternalAnalysis(experiment_id=exp_id, experiment_fk=exp.id, analysis_type="XRD"),
        XRDPhase(
            experiment_id=exp_id, experiment_fk=exp.id,
            mineral_name="Magnetite", amount=12.5, time_post_reaction_days=7.0,
        ),
    ])
    db.flush()
    return exp


def test_syncs_all_five_tables(db_session: Session):
    """Every denormalized copy follows the new id, and each is counted."""
    exp = _seed(db_session, "SYNC_TEST_001", 8801001)
    exp.experiment_id = "SYNC_TEST_001a-t7"
    db_session.flush()

    result = sync_denormalized_experiment_id(db_session, exp.id, "SYNC_TEST_001a-t7")
    db_session.flush()

    assert result.conditions == 1
    assert result.notes == 1
    assert result.modifications == 1
    assert result.external_analyses == 1
    assert result.xrd_phases == 1
    assert result.xrd_phases_skipped == []

    for model in (ExperimentalConditions, ExperimentNotes, ModificationsLog,
                  ExternalAnalysis, XRDPhase):
        rows = db_session.query(model).filter(model.experiment_fk == exp.id).all()
        assert rows, f"{model.__name__} row vanished"
        for row in rows:
            assert row.experiment_id == "SYNC_TEST_001a-t7", (
                f"{model.__name__}.experiment_id still stale: {row.experiment_id!r}"
            )


def test_conditions_string_is_the_regression_target(db_session: Session):
    """The column that produced all 187 stale strings, asserted on its own."""
    exp = _seed(db_session, "SYNC_TEST_002", 8801002)
    exp.experiment_id = "SYNC_TEST_002b-t3"
    db_session.flush()

    sync_denormalized_experiment_id(db_session, exp.id, "SYNC_TEST_002b-t3")
    db_session.flush()

    cond = (
        db_session.query(ExperimentalConditions)
        .filter(ExperimentalConditions.experiment_fk == exp.id)
        .one()
    )
    assert cond.experiment_id == "SYNC_TEST_002b-t3"


def test_in_session_objects_see_the_new_string(db_session: Session):
    """An already-loaded ORM object must not keep serving the stale string.

    The bulk parser processes its conditions sheet AFTER the rename block and
    resolves the row by experiment_fk into the same session, so a Core UPDATE
    that left the identity map stale would hand it the old value.
    """
    exp = _seed(db_session, "SYNC_TEST_003", 8801003)
    note = (
        db_session.query(ExperimentNotes)
        .filter(ExperimentNotes.experiment_fk == exp.id)
        .one()
    )
    assert note.experiment_id == "SYNC_TEST_003"  # loaded into the identity map

    exp.experiment_id = "SYNC_TEST_003c"
    db_session.flush()
    sync_denormalized_experiment_id(db_session, exp.id, "SYNC_TEST_003c")

    assert note.experiment_id == "SYNC_TEST_003c", "identity map left stale"


def test_no_rows_is_not_an_error(db_session: Session):
    """An experiment with no children syncs to all-zero counts, no exception."""
    exp = Experiment(
        experiment_id="SYNC_TEST_004",
        experiment_number=8801004,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(exp)
    db_session.flush()

    result = sync_denormalized_experiment_id(db_session, exp.id, "SYNC_TEST_004a")

    assert (result.conditions, result.notes, result.modifications,
            result.external_analyses, result.xrd_phases) == (0, 0, 0, 0, 0)


def test_other_experiments_are_untouched(db_session: Session):
    """The fan-out is scoped to one experiment_fk and never reaches a sibling."""
    keep = _seed(db_session, "SYNC_TEST_005", 8801005)
    other = _seed(db_session, "SYNC_TEST_006", 8801006)

    keep.experiment_id = "SYNC_TEST_005a"
    db_session.flush()
    sync_denormalized_experiment_id(db_session, keep.id, "SYNC_TEST_005a")
    db_session.flush()

    other_cond = (
        db_session.query(ExperimentalConditions)
        .filter(ExperimentalConditions.experiment_fk == other.id)
        .one()
    )
    assert other_cond.experiment_id == "SYNC_TEST_006"


def test_xrd_slot_collision_is_skipped_not_raised(db_session: Session):
    """uq_xrd_phase_experiment_time_mineral is on the STRING. When another row
    already holds (new_id, time, mineral), renaming into it would raise an
    IntegrityError and abort the whole rename — so that row is left alone and
    reported instead."""
    victim = _seed(db_session, "SYNC_TEST_007", 8801007)
    # Debris already parked on the target slot, owned by a different experiment.
    blocker_owner = Experiment(
        experiment_id="SYNC_TEST_008",
        experiment_number=8801008,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(blocker_owner)
    db_session.flush()
    db_session.add(XRDPhase(
        experiment_id="SYNC_TEST_007a",     # the id `victim` is about to take
        experiment_fk=blocker_owner.id,
        mineral_name="Magnetite", amount=9.0, time_post_reaction_days=7.0,
    ))
    db_session.flush()

    victim.experiment_id = "SYNC_TEST_007a"
    db_session.flush()

    result = sync_denormalized_experiment_id(db_session, victim.id, "SYNC_TEST_007a")
    db_session.flush()  # must NOT raise IntegrityError

    victim_phase = (
        db_session.query(XRDPhase)
        .filter(XRDPhase.experiment_fk == victim.id)
        .one()
    )
    assert result.xrd_phases == 0
    assert result.xrd_phases_skipped == [victim_phase.id]
    assert victim_phase.experiment_id == "SYNC_TEST_007"  # left stale on purpose
    # Everything else still synced.
    assert result.conditions == 1
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/Scripts/pytest tests/services/test_denormalized_ids.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'backend.services.denormalized_ids'`.

- [ ] **Step 3: Write the implementation**

Create `backend/services/denormalized_ids.py`:

```python
"""Single definition of the denormalized-`experiment_id` fan-out on a rename.

Five tables carry a copy of `experiments.experiment_id` next to the
authoritative `experiment_fk`. Renaming an experiment without updating all five
leaves debris: 187 of 1013 `experimental_conditions` rows were stale as of
2026-08-05, all of it produced by the bulk-upload rename path, which synced two
of the five. `PATCH /api/experiments/{id}` synced four. This module is the one
place that knows the whole list, so a sixth table is a one-file change.

`experiment_fk` remains the only authoritative link on every one of these
tables — nothing here makes the string resolvable-by. It is kept correct so
reporting columns, the Power BI views and the XRD uniqueness slot read the
current name.

reactor_slot is NOT affected. Per `.claude/rules/MODELS.md`, a Core `UPDATE`
does not fire the `set_reactor_slot` mapper listener — but `reactor_slot`
derives from `(reactor_number, experiment_type)`, and nothing here touches
either, so no recompute is needed. Same argument as
`database/data_migrations/dedupe_conditions_and_backfill_ids_018.py`.

See docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md
"""
from __future__ import annotations

from dataclasses import dataclass, field

import structlog
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from database import (
    ExperimentNotes,
    ExperimentalConditions,
    ExternalAnalysis,
    ModificationsLog,
    XRDPhase,
)

log = structlog.get_logger(__name__)


@dataclass
class DenormalizedIdSync:
    """Rows updated per table, plus XRD rows deliberately left stale."""

    conditions: int = 0
    notes: int = 0
    modifications: int = 0
    external_analyses: int = 0
    xrd_phases: int = 0
    xrd_phases_skipped: list[int] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            self.conditions + self.notes + self.modifications
            + self.external_analyses + self.xrd_phases
        )


def sync_denormalized_experiment_id(
    db: Session, experiment_fk: int, new_id: str
) -> DenormalizedIdSync:
    """Point every denormalized `experiment_id` copy for one experiment at `new_id`.

    Call this AFTER the rename itself has been flushed. Flushes nothing and
    commits nothing — the caller owns the transaction boundary.

    `xrd_phases` rows that would collide with an existing holder of
    `uq_xrd_phase_experiment_time_mineral` (`experiment_id`,
    `time_post_reaction_days`, `mineral_name`) are left stale and returned in
    `xrd_phases_skipped`; renaming into an occupied slot would raise
    `IntegrityError` at flush and take the whole rename down with it.
    """
    result = DenormalizedIdSync()

    # Conditions: ORM assignment, not a Core UPDATE. UNIQUE (experiment_fk)
    # makes this at most one row going forward, but a database that predates
    # `uq_conditions_experiment_fk` can still hold several — update all of them
    # rather than picking one.
    conditions = db.execute(
        select(ExperimentalConditions)
        .where(ExperimentalConditions.experiment_fk == experiment_fk)
        .order_by(ExperimentalConditions.id)
    ).scalars().all()
    for cond in conditions:
        cond.experiment_id = new_id
    result.conditions = len(conditions)

    # Notes / audit log / external analyses: unbounded row counts, so Core
    # UPDATE. `synchronize_session` is left at its default ("auto"), which
    # expires matching in-session objects — the bulk parser processes its
    # conditions sheet after this call using the same session.
    for model, attr in (
        (ExperimentNotes, "notes"),
        (ModificationsLog, "modifications"),
        (ExternalAnalysis, "external_analyses"),
    ):
        res = db.execute(
            update(model)
            .where(model.experiment_fk == experiment_fk)
            .values(experiment_id=new_id)
        )
        setattr(result, attr, res.rowcount or 0)

    # XRD phases: row-by-row, because of the string-keyed unique slot.
    phases = db.execute(
        select(XRDPhase)
        .where(XRDPhase.experiment_fk == experiment_fk)
        .order_by(XRDPhase.id)
    ).scalars().all()
    for phase in phases:
        if phase.experiment_id == new_id:
            result.xrd_phases += 1
            continue
        blocker = db.execute(
            select(XRDPhase.id)
            .where(
                XRDPhase.experiment_id == new_id,
                XRDPhase.time_post_reaction_days == phase.time_post_reaction_days,
                XRDPhase.mineral_name == phase.mineral_name,
                XRDPhase.id != phase.id,
            )
        ).scalars().first()
        if blocker is not None:
            result.xrd_phases_skipped.append(phase.id)
            continue
        phase.experiment_id = new_id
        result.xrd_phases += 1

    if result.xrd_phases_skipped:
        log.warning(
            "denormalized_id_sync_xrd_slot_conflict",
            experiment_fk=experiment_fk,
            new_id=new_id,
            skipped_phase_ids=result.xrd_phases_skipped,
        )
    log.info(
        "denormalized_id_synced",
        experiment_fk=experiment_fk,
        new_id=new_id,
        conditions=result.conditions,
        notes=result.notes,
        modifications=result.modifications,
        external_analyses=result.external_analyses,
        xrd_phases=result.xrd_phases,
    )
    return result
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/Scripts/pytest tests/services/test_denormalized_ids.py -v
```

Expected: 6 passed.

If `test_in_session_objects_see_the_new_string` fails, the default `synchronize_session` did not expire the loaded object. Fix by appending `.execution_options(synchronize_session="fetch")` to each of the three `update()` statements — do **not** "fix" it by changing the test.

- [ ] **Step 5: Commit**

```bash
git add backend/services/denormalized_ids.py tests/services/test_denormalized_ids.py
git commit -m "$(cat <<'EOF'
[#109] Add shared denormalized experiment_id sync

- One definition of the five-table rename fan-out
- xrd_phases slot collisions are skipped and reported, never raised
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Adopt the helper in `PATCH /api/experiments/{id}`

**Files:**
- Modify: `backend/api/routers/experiments.py:1291-1315` (the four hand-rolled updates inside the rename branch)
- Test: `tests/api/test_experiments_rename_sync.py` (create)

**Interfaces:**
- Consumes: `sync_denormalized_experiment_id`, `DenormalizedIdSync` from Task 1.
- Produces: nothing new. This is the *unlocked* proving ground — land it before touching the locked parser in Task 3, so any surprise surfaces in a file you are free to iterate on.

**Behavior change to be aware of:** this path currently does **not** update pre-existing `modifications_log.experiment_id` rows (it only appends a new one). After this task it does — matching the bulk path, which has always synced them. That is the intended convergence: an audit row stays findable by the experiment's current name, and its `experiment_fk` link is unchanged either way. Delete-snapshot rows (written with `experiment_fk = NULL` per `.claude/rules/MODELS.md`) are never matched by the `experiment_fk ==` filter, so history for deleted experiments is untouched.

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_experiments_rename_sync.py`. Follow the surrounding `tests/api/` convention: seed via the session fixture, drive the endpoint via the `client` fixture. Check `tests/api/conftest.py` for the exact fixture names (`client`, `db_session`) and the auth override before writing — the suite stubs `verify_firebase_token`, so no real token is needed.

```python
"""PATCH /api/experiments/{id} must sync every denormalized experiment_id copy."""
from __future__ import annotations

from database import (
    Experiment,
    ExperimentNotes,
    ExperimentalConditions,
    ExternalAnalysis,
    ModificationsLog,
    XRDPhase,
)
from database.models.enums import ExperimentStatus


def test_patch_rename_syncs_all_denormalized_ids(client, db_session):
    exp = Experiment(
        experiment_id="RENAME_API_001",
        experiment_number=8802001,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(exp)
    db_session.flush()
    db_session.add_all([
        ExperimentalConditions(
            experiment_id="RENAME_API_001", experiment_fk=exp.id, temperature_c=200.0
        ),
        ExperimentNotes(
            experiment_id="RENAME_API_001", experiment_fk=exp.id, note_text="n"
        ),
        ModificationsLog(
            experiment_id="RENAME_API_001", experiment_fk=exp.id,
            modified_by="t", modification_type="create", modified_table="experiments",
        ),
        ExternalAnalysis(
            experiment_id="RENAME_API_001", experiment_fk=exp.id, analysis_type="XRD"
        ),
        XRDPhase(
            experiment_id="RENAME_API_001", experiment_fk=exp.id,
            mineral_name="Olivine", amount=4.0, time_post_reaction_days=1.0,
        ),
    ])
    db_session.commit()
    exp_pk = exp.id

    resp = client.patch(
        f"/api/experiments/{exp_pk}",
        json={"experiment_id": "RENAME_API_001a-t1"},
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    for model in (ExperimentalConditions, ExperimentNotes, ExternalAnalysis, XRDPhase):
        for row in db_session.query(model).filter(model.experiment_fk == exp_pk).all():
            assert row.experiment_id == "RENAME_API_001a-t1", (
                f"{model.__name__} not synced: {row.experiment_id!r}"
            )
    # Every modifications_log row for this experiment now names the new id,
    # including the pre-existing one and the row the rename itself wrote.
    mods = db_session.query(ModificationsLog).filter(
        ModificationsLog.experiment_fk == exp_pk
    ).all()
    assert mods
    assert {m.experiment_id for m in mods} == {"RENAME_API_001a-t1"}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/Scripts/pytest tests/api/test_experiments_rename_sync.py -v
```

Expected: FAIL on the `modifications_log` assertion — the pre-existing row still reads `"RENAME_API_001"`. (The other four already pass; that is the point of asserting all five.)

- [ ] **Step 3: Replace the hand-rolled fan-out**

In `backend/api/routers/experiments.py`, add the import next to the other `backend.services` imports (around line 42):

```python
from backend.services.denormalized_ids import sync_denormalized_experiment_id
```

Then replace lines 1291-1315 — from the `# Keep denormalized string in conditions in sync...` comment through the closing paren of the `XRDPhase` update, stopping **immediately before** `db.add(ModificationsLog(` — with:

```python
            # Point every denormalized experiment_id copy at the new name. One
            # definition of the fan-out lives in backend/services/denormalized_ids.py
            # so this path and the bulk-upload rename path cannot drift apart again
            # (issue #109 follow-up). experiment_fk stays the only authoritative link.
            id_sync = sync_denormalized_experiment_id(db, exp.id, new_id)
            if id_sync.xrd_phases_skipped:
                log.warning(
                    "experiment_rename_xrd_slot_conflict",
                    experiment_id=new_id,
                    skipped_phase_ids=id_sync.xrd_phases_skipped,
                    user=current_user.uid,
                )
```

Read the file first and match the existing block exactly — it is indented 12 spaces inside the rename branch. After the edit, check whether `ExternalAnalysis`, `XRDPhase`, `ExperimentNotes` and `update` are still used elsewhere in `experiments.py`:

```bash
grep -n "ExternalAnalysis\|XRDPhase\|ExperimentNotes\|update(" backend/api/routers/experiments.py | head -30
```

Leave every import that still has a use. Only remove one if the grep shows zero remaining references.

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/Scripts/pytest tests/api/test_experiments_rename_sync.py -v
.venv/Scripts/pytest tests/api/test_experiments.py tests/services/test_denormalized_ids.py -q
```

Expected: the new test passes; the existing experiments API suite is unchanged (no new failures).

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/experiments.py tests/api/test_experiments_rename_sync.py
git commit -m "$(cat <<'EOF'
[#109] Route PATCH rename through the shared sync

- Adds modifications_log to what PATCH syncs, matching the bulk path
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Adopt the helper in the bulk-upload rename path (LOCKED FILE)

**Files:**
- Modify: `backend/services/bulk_uploads/new_experiments.py:543-575` (rename branch) and its import block at line 11-20
- Test: `tests/services/bulk_uploads/test_new_experiments_rename_denormalized_ids.py` (create)

**Interfaces:**
- Consumes: `sync_denormalized_experiment_id` from Task 1.
- Produces: nothing. This is the last code change.

**This file is locked.** The user signed off on 2026-08-05 for exactly this edit. Keep the diff to: one import line added, one import name removed, two loops replaced by one call. Do not reformat, do not fix unrelated style, do not touch the conditions or additives sheet blocks.

**Why the test file uses its own `autoflush=False` session.** `tests/services/bulk_uploads/conftest.py`'s `db_session` runs `autoflush=True`, but production `database.database.SessionLocal` runs `autoflush=False`. `test_new_experiments_rename_lineage.py` already builds a production-faithful `pg_session` fixture for exactly this reason (issue #86 defect A was masked by autoflush). Copy that fixture — the rename block flushes explicitly before the sync call, and the test must prove that works without autoflush's help.

- [ ] **Step 1: Write the failing test**

Create `tests/services/bulk_uploads/test_new_experiments_rename_denormalized_ids.py`:

```python
"""Issue #109 follow-up: the bulk rename path must sync every denormalized
experiment_id copy, not just notes and modifications_log.

This is the mechanism that produced all 187 stale experimental_conditions
strings (of 1013 rows) measured against the 2026-08-05 production dump. With
the string unsynced, migration 018's backfill decays with every rename
workbook.

Uses an autoflush=False session, mirroring production SessionLocal — the same
reason test_new_experiments_rename_lineage.py does.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from database import (
    Experiment,
    ExperimentNotes,
    ExperimentalConditions,
    ExternalAnalysis,
    ModificationsLog,
    XRDPhase,
)
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads.new_experiments import NewExperimentsUploadService

from .excel_helpers import make_excel

_TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"
_engine = create_engine(_TEST_DB_URL, pool_pre_ping=True)
_SessionAutoflushOff = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

_EXP_HEADERS = [
    "experiment_id",
    "old_experiment_id",
    "sample_id",
    "researcher",
    "date",
    "status",
    "initial_note",
    "overwrite",
]


@pytest.fixture()
def pg_session(create_test_tables) -> Session:
    """Per-test autoflush=False session, wrapped in a transaction that rolls back."""
    connection = _engine.connect()
    transaction = connection.begin()
    session = _SessionAutoflushOff(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def _seed_with_children(db: Session, exp_id: str, number: int) -> Experiment:
    exp = Experiment(
        experiment_id=exp_id,
        experiment_number=number,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.flush()
    db.add_all([
        ExperimentalConditions(experiment_id=exp_id, experiment_fk=exp.id, temperature_c=250.0),
        ExperimentNotes(experiment_id=exp_id, experiment_fk=exp.id, note_text="seed"),
        ModificationsLog(
            experiment_id=exp_id, experiment_fk=exp.id,
            modified_by="t", modification_type="create", modified_table="experiments",
        ),
        ExternalAnalysis(experiment_id=exp_id, experiment_fk=exp.id, analysis_type="XRD"),
        XRDPhase(
            experiment_id=exp_id, experiment_fk=exp.id,
            mineral_name="Magnetite", amount=11.0, time_post_reaction_days=7.0,
        ),
    ])
    db.flush()
    return exp


def test_bulk_rename_syncs_conditions_string(pg_session: Session):
    """The regression this task exists for."""
    exp = _seed_with_children(pg_session, "BULKSYNC_001", 8803001)
    exp_pk = exp.id

    xlsx = make_excel(
        _EXP_HEADERS,
        [["BULKSYNC_001a-t7", "BULKSYNC_001", None, None, None, None, None, True]],
        sheet_name="experiments",
    )
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(pg_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert updated == 1

    cond = (
        pg_session.query(ExperimentalConditions)
        .filter(ExperimentalConditions.experiment_fk == exp_pk)
        .one()
    )
    assert cond.experiment_id == "BULKSYNC_001a-t7", (
        "conditions string still stale — this is the 187-row mechanism"
    )


def test_bulk_rename_syncs_all_five_tables(pg_session: Session):
    """Full parity with PATCH /api/experiments/{id}."""
    exp = _seed_with_children(pg_session, "BULKSYNC_002", 8803002)
    exp_pk = exp.id

    xlsx = make_excel(
        _EXP_HEADERS,
        [["BULKSYNC_002b-t3", "BULKSYNC_002", None, None, None, None, None, True]],
        sheet_name="experiments",
    )
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(pg_session, xlsx)
    )
    assert errors == [], f"Unexpected errors: {errors}"

    for model in (ExperimentalConditions, ExperimentNotes, ModificationsLog,
                  ExternalAnalysis, XRDPhase):
        rows = pg_session.query(model).filter(model.experiment_fk == exp_pk).all()
        assert rows, f"{model.__name__} row vanished"
        for row in rows:
            assert row.experiment_id == "BULKSYNC_002b-t3", (
                f"{model.__name__} not synced: {row.experiment_id!r}"
            )


def test_conditions_sheet_after_rename_sees_new_string(pg_session: Session):
    """The conditions sheet is processed after the rename block and resolves its
    row by experiment_fk into the same session. A sync that left the identity
    map stale would hand it the old string."""
    exp = _seed_with_children(pg_session, "BULKSYNC_003", 8803003)
    exp_pk = exp.id

    import io
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "experiments"
    ws.append(_EXP_HEADERS)
    ws.append(["BULKSYNC_003c", "BULKSYNC_003", None, None, None, None, None, True])
    ws2 = wb.create_sheet("conditions")
    ws2.append(["experiment_id", "temperature_c"])
    ws2.append(["BULKSYNC_003c", 275.0])
    buf = io.BytesIO()
    wb.save(buf)

    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(pg_session, buf.getvalue())
    )
    assert errors == [], f"Unexpected errors: {errors}"

    cond = (
        pg_session.query(ExperimentalConditions)
        .filter(ExperimentalConditions.experiment_fk == exp_pk)
        .one()
    )
    assert cond.experiment_id == "BULKSYNC_003c"
    assert cond.temperature_c == 275.0, "conditions sheet did not apply"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_new_experiments_rename_denormalized_ids.py -v
```

Expected: `test_bulk_rename_syncs_conditions_string` and `test_bulk_rename_syncs_all_five_tables` FAIL with the conditions string still `"BULKSYNC_001"` / `"BULKSYNC_002"`. `test_conditions_sheet_after_rename_sees_new_string` may pass already — it is the guard for the fix, not proof of the bug.

- [ ] **Step 3: Edit the locked parser**

Read `backend/services/bulk_uploads/new_experiments.py:543-580` first — the block is indented 32 spaces and **some of the blank lines carry trailing whitespace**, so an exact-match edit needs the file's real bytes, not this plan's rendering.

3a. Add the import after `from database.lineage_utils import update_experiment_lineage` (line 27):

```python
from backend.services.denormalized_ids import sync_denormalized_experiment_id
```

3b. Replace the two loops — from the comment `# Update denormalized experiment_id in related ExperimentNotes records` through `mod.experiment_id = exp_id` (lines 559-571) — with:

```python
                                # Point every denormalized experiment_id copy at the new
                                # name. Before this, only notes and modifications_log were
                                # synced, so every rename workbook left a stale
                                # experimental_conditions.experiment_id behind -- the
                                # mechanism behind 187 of 1013 stale rows measured
                                # 2026-08-05, and the reason migration 018's backfill was
                                # going to decay. The fan-out has one definition in
                                # backend/services/denormalized_ids.py, shared with
                                # PATCH /api/experiments/{id} (issue #109 follow-up).
                                id_sync = sync_denormalized_experiment_id(
                                    db, experiment.id, exp_id
                                )
                                if id_sync.xrd_phases_skipped:
                                    warnings.append(
                                        f"[experiments] Row {idx+2}: renamed "
                                        f"'{old_experiment_id}' -> '{exp_id}', but "
                                        f"{len(id_sync.xrd_phases_skipped)} XRD phase row(s) "
                                        f"kept the old ID string because another row already "
                                        f"holds that (experiment_id, timepoint, mineral) slot."
                                    )
```

3c. `ModificationsLog` is now referenced nowhere else in the file. Confirm and remove it from the `from database import (...)` block at line 14:

```bash
grep -n "ModificationsLog" backend/services/bulk_uploads/new_experiments.py
```

If the only hit is the import line, delete that line. If there are others, leave the import alone. `ExperimentNotes` has 8 uses — keep it.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_new_experiments_rename_denormalized_ids.py -v
.venv/Scripts/pytest tests/services/bulk_uploads/ -q
```

Expected: 3 passed in the new file; the whole locked-parser suite green (this is the suite the lock exists to protect — `test_new_experiments.py`, `test_new_experiments_additives.py`, `test_new_experiments_plan.py`, `test_new_experiments_rename_lineage.py` in particular).

If anything in `tests/services/bulk_uploads/` fails, **stop and report** rather than adjusting the parser further — per `.claude/CLAUDE.md` §7, two failed fix attempts on a locked component escalates to the user.

- [ ] **Step 5: Run the full backend suite**

```bash
.venv/Scripts/pytest -q
```

Expected: `3 failed, <N> passed, 4 skipped` where the 3 are `tests/test_pg_backup_restore.py`. Any other failure is a regression from this task. One process only — never run a second pytest concurrently against `experiments_test`.

- [ ] **Step 6: Commit**

```bash
git add backend/services/bulk_uploads/new_experiments.py tests/services/bulk_uploads/test_new_experiments_rename_denormalized_ids.py
git commit -m "$(cat <<'EOF'
[#109] Sync conditions string on bulk rename

- Bulk rename now syncs all five denormalized experiment_id copies
- Closes the mechanism behind 187 stale conditions rows
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Correct every stale comment and doc

**Files:**
- Modify: `database/models/conditions.py:9-14` (LOCKED — comment text only)
- Modify: `backend/api/routers/conditions.py:48-61` (docstring)
- Modify: `.claude/rules/MODELS.md` (the `ExperimentalConditions` "Identity (issue #109 follow-up)" bullet, ~line 194)
- Modify: `docs/api/API_REFERENCE.md:394`
- Modify: `docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md` ("Follow-up" section)

**Interfaces:**
- Consumes: the behavior shipped in Tasks 1-3.
- Produces: nothing. Documentation only — no test.

The `PostToolUse` hook in `.claude/settings.json` copies anything written under `docs/` into `docs/project_context/` automatically. **Do not write to `docs/project_context/` yourself**; it will show up in `git status` on its own and must be committed alongside.

- [ ] **Step 1: Fix the locked model comment**

In `database/models/conditions.py`, replace lines 9-14 with:

```python
    # ExperimentalConditions is 1:1 with Experiment, and experiment_fk is the
    # only authoritative link. The experiment_id String below is a denormalized
    # convenience copy -- never resolve a conditions row by it. Both rename
    # paths now keep it in sync (PATCH /api/experiments/{id} and the bulk
    # upload parser, via backend/services/denormalized_ids.py), but 187 of 1013
    # production rows were stale as of 2026-08-05 and are only corrected by
    # running database/data_migrations/dedupe_conditions_and_backfill_ids_018.py.
    # See docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md
```

Nothing else in this file changes. It is locked and models are storage-only.

- [ ] **Step 2: Fix the router docstring**

In `backend/api/routers/conditions.py`, replace the second paragraph of `get_conditions_by_experiment`'s docstring (lines 50-56, beginning `Resolved through experiment_fk, never through the denormalized`) with:

```
    Resolved through experiment_fk, never through the denormalized
    ExperimentalConditions.experiment_id string. Both rename paths now sync that
    string (backend/services/denormalized_ids.py), but 187 of 1013 production
    rows are stale until dedupe_conditions_and_backfill_ids_018.py runs, and the
    FK is authoritative regardless. A string-keyed lookup both missed rows that
    exist and matched rows belonging to another experiment; the resulting 404 is
    what made the detail page offer "Add Details" and create a duplicate
    conditions row -- see
    docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md
```

Leave the `.first()` paragraph below it unchanged — it is still accurate.

- [ ] **Step 3: Fix `.claude/rules/MODELS.md`**

Find the `**Identity (issue #109 follow-up):**` bullet under `ExperimentalConditions` and replace the sentence beginning "The single-experiment rename path ... does keep it in sync; the **bulk** rename path ... does not" with:

```markdown
  Both rename paths keep it in sync as of 2026-08-05: `PATCH /api/experiments/{id}`
  and the bulk parser (`backend/services/bulk_uploads/new_experiments.py`) both
  call `backend/services/denormalized_ids.py::sync_denormalized_experiment_id`,
  which is the **single definition** of the five-table fan-out
  (`experimental_conditions`, `experiment_notes`, `modifications_log`,
  `external_analyses`, `xrd_phases`). Add a sixth table there, not at a call site.
  `xrd_phases` rows whose new `(experiment_id, time_post_reaction_days,
  mineral_name)` slot is already taken are **left stale and reported** rather
  than renamed — renaming into an occupied `uq_xrd_phase_experiment_time_mineral`
  slot would abort the whole rename with an `IntegrityError`.
  187 of 1013 rows were stale as of 2026-08-05 from the pre-fix bulk path and
  are corrected only by running
  `database/data_migrations/dedupe_conditions_and_backfill_ids_018.py`.
  Never resolve a conditions row by this string — resolve through `experiment_fk`.
```

- [ ] **Step 4: Fix `docs/api/API_REFERENCE.md`**

At line 394, change the parenthetical `(issue #109 follow-up — that string is denormalized and not kept in sync by rename paths; 187 of 1013 rows were stale as of 2026-08-05)` to:

```
(issue #109 follow-up — that string is denormalized; both rename paths now sync it via `backend/services/denormalized_ids.py`, but 187 of 1013 rows stay stale until `dedupe_conditions_and_backfill_ids_018.py` runs, and `experiment_fk` is authoritative regardless)
```

- [ ] **Step 5: Close the Follow-up section in the issue doc**

In `docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md`, replace the whole `## Follow-up` section with:

```markdown
## Follow-up — CLOSED 2026-08-05

**The bulk rename leak is fixed, so 018's backfill no longer decays.** The
fan-out now has a single definition,
`backend/services/denormalized_ids.py::sync_denormalized_experiment_id`, called
by both rename paths: `PATCH /api/experiments/{id}` and
`backend/services/bulk_uploads/new_experiments.py` (locked file, edited with
user sign-off 2026-08-05). It covers all five tables that carry a denormalized
`experiment_id` — `experimental_conditions`, `experiment_notes`,
`modifications_log`, `external_analyses`, `xrd_phases` — where the bulk path
previously did two and PATCH did four.

Two behavioral notes:

- **`PATCH` now also updates pre-existing `modifications_log.experiment_id`
  rows**, which it did not before; the bulk path always did. Delete-snapshot
  rows (`experiment_fk = NULL`) are never matched, so history for deleted
  experiments is untouched.
- **XRD slot collisions are skipped, not raised.**
  `uq_xrd_phase_experiment_time_mineral` is keyed on the *string*. If another
  row already holds `(new_id, time_post_reaction_days, mineral_name)`, the
  phase row keeps its old string and is reported — in the upload `warnings`
  for the bulk path, and via structlog for PATCH. Renaming into an occupied
  slot would raise `IntegrityError` and take the whole rename down.

`database/data_migrations/dedupe_conditions_and_backfill_ids_018.py` is still
required to correct the 187 rows already stale; nothing new accumulates behind
it. Deploy sequence unchanged — see "Deploy to the lab PC" above.
```

Also update the two earlier claims in the same file that the bulk path does not sync: the last sentence of **Root cause** (lines ~16-21) and the parenthetical in the 018 script's own description. Change them to point at this closed Follow-up section rather than describing the leak as open.

- [ ] **Step 6: Verify the hook synced project_context**

```bash
git status --short docs/project_context/
```

Expected: `docs/project_context/API_REFERENCE.md` and the issue doc's copy appear as modified. If they did not, the hook did not fire — re-run the `Edit` on the `docs/` file rather than writing into `project_context/` by hand.

- [ ] **Step 7: Commit**

```bash
git add database/models/conditions.py backend/api/routers/conditions.py .claude/rules/MODELS.md docs/api/API_REFERENCE.md docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md docs/project_context/
git commit -m "$(cat <<'EOF'
[#109] Correct rename-sync claims in comments and docs

- Four sites said no rename path synced the conditions string
- Issue #109 follow-up section closed
- Tests added: no
- Docs updated: yes

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Definition of done

- [ ] `.venv/Scripts/pytest -q` → `3 failed` and they are all `tests/test_pg_backup_restore.py`
- [ ] `.venv/Scripts/pytest tests/services/bulk_uploads/ -q` → fully green
- [ ] A bulk rename workbook leaves zero stale `experimental_conditions.experiment_id` rows
- [ ] `backend/services/denormalized_ids.py` is the only place listing the five tables — `grep -rn "experiment_id=new_id\|\.experiment_id = new_id" backend/` shows no other fan-out
- [ ] No file under `backend/services/bulk_uploads/` other than `new_experiments.py` changed; no file under `database/models/` changed except the `conditions.py` comment
- [ ] Follow `docs/GIT_WORKFLOW.md`, then `/complete-task`. PR with `gh pr create --base develop`
