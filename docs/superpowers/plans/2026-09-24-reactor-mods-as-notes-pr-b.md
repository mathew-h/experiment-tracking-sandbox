# Reactor Modifications Become Dated Notes (issue #122, PR-B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A reactor modification is a `modification` note anchored to a result OR a calendar date, not a separate Notion-era object. The dashboard card writes and reads such notes, the Reactor Modifications tab disappears, and the 333 existing `reactor_change_requests` rows are converted by an audited, idempotent backfill whose dry run Mat audits before it is applied.

**Architecture:** `experiment_notes` gains `event_date DATE NULL` and `ck_note_scope` relaxes so `modification ⇒ (result_id IS NOT NULL OR event_date IS NOT NULL)`; the API's `POST`/`PATCH` notes routes and `backend/services/notes.py::add_note` carry the field; `v_notes` exposes it. `database/data_migrations/migrate_reactor_change_requests_021.py` converts each change-request row into one dated note plus one `ModificationsLog` snapshot (dry run by default, `--apply` only on Mat's approval). After approval, `dashboard.py` reads today's and the latest modification from notes in one batched query, `ReactorGrid.tsx` saves through `POST notes`, the detail page loses its tab, `DeleteImpact` drops `change_requests`, and the three `/change-requests` routes are marked deprecated (removed by PR-E).

**Tech Stack:** FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic (PostgreSQL 18); React 18 + TypeScript + TanStack Query v5 (frontend); pytest against `experiments_test`; vitest + Testing Library.

**Spec:** `docs/working/issues/07-notes-overhaul-phase-2.md` — §4 "PR-B: reactor modifications become dated modification notes", §2 pre-authorization 1 (the `event_date` column and the `ck_note_scope` drop-and-recreate), §3 decisions 1, 2, 9, 10, 11, 12. (The spec file lands on `develop` with PR #123; on this branch read it via `git show feat/notes-review-queue:docs/working/issues/07-notes-overhaul-phase-2.md`.)

**Gap decisions made in-session (2026-09-24), binding on every task:**
1. The spec's "26 rows whose experiment does not exist" are 26 rows with `experiment_id IS NULL`: the column is an FK to `experiments.experiment_id` with `ON DELETE SET NULL`, so a non-NULL string always resolves exactly. The script treats NULL as "orphaned" and reports those rows by id, reactor label and date.
2. `NoteUpdate.event_date` distinguishes "omitted" from "set to NULL" with `model_fields_set`; the PATCH scope check evaluates the note's state AFTER the patch.
3. `_check_bulk_retype` lives only on PR #123's branch and is not touched here; PR body flags the mirror for whichever branch merges second.
4. The TS `ExperimentNote.event_date` is optional (`event_date?: string | null`) so PR #123's fixtures need no change when the branches meet.
5. The dashboard N+1 test asserts "at most two statements touch `experiment_notes`" (the card query's description subquery plus the one batched modification query), not "exactly one".
6. Decision 2's label-prefix question is asked once in the dry-run report; the script has no prefix option until Mat answers.
7. Alembic revision id for this PR: `e5b2d9c7a1f4`, parent `c4d8f1a2b6e7`.

## Global Constraints

- Branch `feat/reactor-mods-as-notes` off `develop` (`db85cf4`); PR base `develop`. Not stacked on PR #123 or #124.
- Commit format `[#122] <imperative, <50 chars, no trailing period>` with `- Tests added: yes/no` / `- Docs updated: yes/no` lines and a final `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Multi-line messages via `git commit -F <scratchpad file>`.
- **Locked files:** `database/models/experiments.py` may change ONLY as pre-authorization 1 allows: the `event_date` column, the `CheckConstraint` text, and docstrings. No file under `backend/services/bulk_uploads/`. Never delete a file under `alembic/versions/`. `database/models/notion_sync.py` and the `reactor_change_requests` table stay (E2 is NOT authorized).
- `alembic heads` must print exactly `e5b2d9c7a1f4 (head)` before the Task 1 commit; before that it prints `c4d8f1a2b6e7 (head)`.
- The `experiments_test` database is the only disposable Postgres DB. After Task 1's model change: `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` on `experiments_test` before the first pytest run, because `create_all` never alters an existing table. **One pytest process at a time.** Never include root-level `tests/test_*.py` in an invocation with `tests/services`.
- Python via `.venv/Scripts/python.exe` / `.venv/Scripts/pytest.exe` / `.venv/Scripts/alembic.exe`, run from the repo root with `PYTHONPATH=.` where a script imports `database`. The default `DATABASE_URL` (`.env`) is the dev mirror `experiments`; point at `experiments_test` explicitly for rehearsals: `DATABASE_URL=postgresql://experiments_user:password@localhost:5432/experiments_test`.
- **Hard gate:** `migrate_reactor_change_requests_021.py --apply` is never run by an agent. Dry run only; Task 4 stops the plan until Mat's audit.
- Backend: `structlog` only, no `print` outside data-migration scripts; Pydantic v2 (`model_config = ConfigDict(from_attributes=True)`); FastAPI 422 text for the new rule is exactly: `A 'modification' note must be scoped to a result or carry an event_date.`
- Frontend rules: functional components, React Query for server state, Tailwind classes only, no hex literals, no `console.log`. `frontend/package.json`/`package-lock.json` untouched. Known baseline: 5 eslint problems, 3 tsc errors in `ResultsTab.columns.test.tsx`; neither may grow.
- Docs edited with the Edit tool so the PostToolUse hook copies them to `docs/project_context/`; `docs/working/` is excluded by design.
- Suite for every backend task: `.venv/Scripts/pytest.exe tests/models tests/views tests/api tests/test_icp_handling.py tests/services tests/regression tests/data_migrations -q` (develop baseline 1,369 passed, 0 failed, on a fresh `experiments_test`).

## Review Focus

Inputs the spec implies but names no test for; each is pinned in the owning task.

1. **A `modification` PATCHed to `event_date: null` when it has no `result_id`** — must be a 422 with the exact text, not an `IntegrityError` 500. Pinned in Task 2.
2. **Two change-request rows for the same experiment and date with different reactor labels but identical text** — collapse to one note under the idempotency key and are counted as collapsed, never silently dropped or doubled. Pinned in Task 3.
3. **A result-anchored `modification` note with no `event_date`** — counted for `latest_modification` by `created_at::date` but never as "today's" (spec: today's = `event_date = today`). Pinned in Task 5.
4. **Several modifications saved for today on one card** — joined with `'; '` in id order, not the last one only. Pinned in Task 5.
5. **Dashboard save with a blank textarea** — the Save button is disabled, and the trimmed text is what is posted; the server's `add_note` receives no blank text. Pinned in Task 6.

---

# PHASE 1 — schema, API, backfill script, dry run (Tasks 1–4)

### Task 1: `event_date` column, relaxed CHECK, `v_notes`, migration, model tests, rehearsal

**Files:**
- Modify: `database/models/experiments.py` (class `ExperimentNotes`: docstring, `__table_args__` `CheckConstraint`, new column after `result_id`)
- Modify: `database/event_listeners.py` (the `v_notes` entry in `_VIEWS`, ~line 695)
- Create: `alembic/versions/e5b2d9c7a1f4_note_event_date.py`
- Create: `tests/models/test_note_event_date_scope.py`
- Modify: `tests/views/test_typed_notes_views.py` (append one test)

**Interfaces:**
- Produces: `ExperimentNotes.event_date: Column(Date, nullable=True, index=True)`; index `ix_experiment_notes_event_date`; CHECK `ck_note_scope` = `(note_type = 'description' AND result_id IS NULL) OR (note_type = 'modification' AND (result_id IS NOT NULL OR event_date IS NOT NULL)) OR (note_type = 'result_note' AND result_id IS NOT NULL) OR (note_type = 'observation')`; `v_notes.event_date`. Tasks 2, 3 and 5 rely on the column name and the CHECK.

- [ ] **Step 1: Write the failing model tests**

Create `tests/models/test_note_event_date_scope.py`:

```python
"""ck_note_scope after issue #122 PR-B: a 'modification' note is anchored to a
result OR an event_date (design decision 1). Every (note_type, result_id,
event_date) combination the spec names is pinned here against PostgreSQL --
the test DB is built with create_all, so the model's CheckConstraint must carry
the new rule; if a row here goes red the migration e5b2d9c7a1f4 has drifted too.
"""
import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from database import Experiment, ExperimentNotes, ExperimentalResults
from database.models.enums import ExperimentStatus, NoteType

DAY = datetime.date(2026, 9, 24)


def _exp(db, exp_id, number):
    exp = Experiment(experiment_id=exp_id, experiment_number=number, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _result(db, exp, day=7.0):
    r = ExperimentalResults(experiment_fk=exp.id, time_post_reaction_days=day,
                            time_post_reaction_bucket_days=day, description="seed")
    db.add(r)
    db.flush()
    return r


def _note(db, exp, **kw):
    n = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text="t", **kw)
    db.add(n)
    db.flush()
    return n


def test_event_date_column_round_trips_and_is_nullable(db_session):
    exp = _exp(db_session, "EVD_001", 91001)
    dated = _note(db_session, exp, note_type=NoteType.observation, event_date=DAY)
    undated = _note(db_session, exp, note_type=NoteType.observation)
    db_session.refresh(dated)
    assert dated.event_date == DAY
    assert undated.event_date is None


# --- the nine combinations the spec names -----------------------------------

def test_description_without_result_is_valid(db_session):
    exp = _exp(db_session, "EVD_002", 91002)
    _note(db_session, exp, note_type=NoteType.description)


def test_description_with_result_is_rejected(db_session):
    exp = _exp(db_session, "EVD_003", 91003)
    r = _result(db_session, exp)
    with pytest.raises(IntegrityError, match="ck_note_scope"):
        _note(db_session, exp, note_type=NoteType.description, result_id=r.id)


def test_modification_with_result_only_is_valid(db_session):
    exp = _exp(db_session, "EVD_004", 91004)
    r = _result(db_session, exp)
    _note(db_session, exp, note_type=NoteType.modification, result_id=r.id)


def test_modification_with_date_only_is_valid(db_session):
    exp = _exp(db_session, "EVD_005", 91005)
    _note(db_session, exp, note_type=NoteType.modification, event_date=DAY)


def test_modification_with_result_and_date_is_valid(db_session):
    exp = _exp(db_session, "EVD_006", 91006)
    r = _result(db_session, exp)
    _note(db_session, exp, note_type=NoteType.modification, result_id=r.id, event_date=DAY)


def test_modification_with_neither_anchor_is_rejected(db_session):
    exp = _exp(db_session, "EVD_007", 91007)
    with pytest.raises(IntegrityError, match="ck_note_scope"):
        _note(db_session, exp, note_type=NoteType.modification)


def test_result_note_with_result_is_valid(db_session):
    exp = _exp(db_session, "EVD_008", 91008)
    r = _result(db_session, exp)
    _note(db_session, exp, note_type=NoteType.result_note, result_id=r.id)


def test_result_note_with_date_only_is_rejected(db_session):
    # A date does not anchor a result_note; only a result does.
    exp = _exp(db_session, "EVD_009", 91009)
    with pytest.raises(IntegrityError, match="ck_note_scope"):
        _note(db_session, exp, note_type=NoteType.result_note, event_date=DAY)


def test_observation_with_date_only_is_valid(db_session):
    exp = _exp(db_session, "EVD_010", 91010)
    _note(db_session, exp, note_type=NoteType.observation, event_date=DAY)
```

Append to `tests/views/test_typed_notes_views.py` (uses that file's existing `view_db`, `_exp` fixtures/helpers; add `import datetime` at the top only if the file lacks it — it already imports `datetime`):

```python
def test_v_notes_exposes_event_date(view_db):
    exp = _exp(view_db, "VNOTE_EVD_001", 93001)
    dated = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text="swapped brine",
                            note_type=NoteType.modification, event_date=datetime.date(2026, 9, 24))
    undated = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text="looks fine",
                              note_type=NoteType.observation)
    view_db.add_all([dated, undated])
    view_db.flush()
    rows = {r.note_id: r for r in view_db.execute(
        text("SELECT note_id, event_date, note_type FROM v_notes WHERE experiment_id = :e"),
        {"e": exp.experiment_id},
    ).all()}
    assert rows[dated.id].event_date == datetime.date(2026, 9, 24)
    assert rows[dated.id].note_type == "modification"
    assert rows[undated.id].event_date is None
```

- [ ] **Step 2: Reset `experiments_test` and run the new tests to see them fail**

```
psql -U postgres -d experiments_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
.venv/Scripts/pytest.exe tests/models/test_note_event_date_scope.py tests/views/test_typed_notes_views.py -q
```
(`psql` is `C:\Program Files\PostgreSQL\18\bin\psql.exe`, password `password`.)
Expected: the round-trip test and every `event_date=` test FAIL with `TypeError: 'event_date' is an invalid keyword argument for ExperimentNotes`; `test_modification_with_neither_anchor_is_rejected` PASSES already (the old CHECK rejects it too); the view test FAILS (`event_date` column missing).

- [ ] **Step 3: Model change (locked file — pre-authorization 1 only)**

In `database/models/experiments.py`, class `ExperimentNotes`:

(a) Ensure `Date` is imported from `sqlalchemy` alongside the existing column types (add it to the existing `from sqlalchemy import ...` line if absent).

(b) Replace the `CheckConstraint` in `__table_args__`:
```python
        CheckConstraint(
            "(note_type = 'description' AND result_id IS NULL) OR "
            "(note_type = 'modification' AND (result_id IS NOT NULL OR event_date IS NOT NULL)) OR "
            "(note_type = 'result_note' AND result_id IS NOT NULL) OR "
            "(note_type = 'observation')",
            name="ck_note_scope",
        ),
```

(c) Add the column directly after `result_id`:
```python
    # Issue #122 PR-B: a calendar-date anchor for a 'modification' note that is
    # not tied to a result row (the dashboard's reactor-modification form, and the
    # 021 backfill of reactor_change_requests). Either anchor satisfies
    # ck_note_scope for 'modification'; 'result_note' still requires a result.
    event_date = Column(Date, nullable=True, index=True)
```

(d) In the class docstring, replace the `ck_note_scope` bullet with:
```
      * ck_note_scope -- 'description' is never result-scoped; 'modification'
        is anchored to a result OR an event_date (issue #122 PR-B); 'result_note'
        always to a result; 'observation' may be anything.
```

- [ ] **Step 4: `v_notes` in `database/event_listeners.py`**

In the `v_notes` SQL, insert `n.event_date,` on its own line directly after `n.result_id,`, and add `event_date` to the comment above it: after the line `# One row per experiment note, typed and optionally scoped to a result.` add `# event_date (issue #122 PR-B) anchors a dated reactor modification.`

- [ ] **Step 5: Migration**

Create `alembic/versions/e5b2d9c7a1f4_note_event_date.py`:

```python
"""experiment_notes.event_date and a relaxed ck_note_scope (issue #122, PR-B).

A reactor modification is a 'modification' note anchored to a result OR to a
calendar date (design decision 1 of the phase-2 spec). Until now ck_note_scope
required every 'modification' to carry a result_id, which cannot represent the
dashboard's "what was done to this reactor on <date>" entries -- those lived in
the Notion-era reactor_change_requests table, which PR-B retires.

* ADD COLUMN event_date DATE NULL + ix_experiment_notes_event_date.
* ck_note_scope becomes:
    description  => result_id IS NULL
    modification => result_id IS NOT NULL OR event_date IS NOT NULL
    result_note  => result_id IS NOT NULL
    observation  => anything
* v_notes gains event_date (recreated here AND in database/event_listeners.py,
  house pattern from c4d8f1a2b6e7, so Power BI is right after the nightly
  `alembic upgrade head` even before the API restarts).

Downgrade restores the old CHECK and drops the column, but REFUSES (RuntimeError
naming the count) while any 'modification' row is anchored by event_date alone:
such rows would violate the old CHECK and the alternative -- deleting them --
is data loss a downgrade must not decide on its own (house pattern from
00063a5dd6a8).

Revision ID: e5b2d9c7a1f4
Revises: c4d8f1a2b6e7
Create Date: 2026-09-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5b2d9c7a1f4"
down_revision: Union[str, None] = "c4d8f1a2b6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCOPE_CHECK_OLD = (
    "(note_type = 'description' AND result_id IS NULL) OR "
    "(note_type IN ('modification', 'result_note') AND result_id IS NOT NULL) OR "
    "(note_type = 'observation')"
)
_SCOPE_CHECK_NEW = (
    "(note_type = 'description' AND result_id IS NULL) OR "
    "(note_type = 'modification' AND (result_id IS NOT NULL OR event_date IS NOT NULL)) OR "
    "(note_type = 'result_note' AND result_id IS NOT NULL) OR "
    "(note_type = 'observation')"
)

_V_NOTES_OLD = """
    CREATE VIEW v_notes AS
    SELECT
        n.id                 AS note_id,
        e.experiment_id,
        n.result_id,
        n.note_type::text    AS note_type,
        n.note_text,
        n.created_at,
        n.created_by,
        n.needs_review
    FROM experiment_notes n
    JOIN experiments e ON e.id = n.experiment_fk
"""
_V_NOTES_NEW = """
    CREATE VIEW v_notes AS
    SELECT
        n.id                 AS note_id,
        e.experiment_id,
        n.result_id,
        n.event_date,
        n.note_type::text    AS note_type,
        n.note_text,
        n.created_at,
        n.created_by,
        n.needs_review
    FROM experiment_notes n
    JOIN experiments e ON e.id = n.experiment_fk
"""


def upgrade() -> None:
    op.add_column("experiment_notes", sa.Column("event_date", sa.Date(), nullable=True))
    op.create_index("ix_experiment_notes_event_date", "experiment_notes", ["event_date"])
    op.drop_constraint("ck_note_scope", "experiment_notes", type_="check")
    op.create_check_constraint("ck_note_scope", "experiment_notes", _SCOPE_CHECK_NEW)
    op.execute("DROP VIEW IF EXISTS v_notes CASCADE")
    op.execute(_V_NOTES_NEW)


def downgrade() -> None:
    conn = op.get_bind()
    dated_only = conn.execute(sa.text(
        "SELECT count(*) FROM experiment_notes "
        "WHERE note_type = 'modification' AND result_id IS NULL AND event_date IS NOT NULL"
    )).scalar_one()
    if dated_only:
        raise RuntimeError(
            f"Cannot downgrade e5b2d9c7a1f4: {dated_only} 'modification' note(s) are anchored "
            "only by event_date and would violate the pre-PR-B ck_note_scope. Retype or "
            "delete them first: SELECT id FROM experiment_notes WHERE note_type = 'modification' "
            "AND result_id IS NULL AND event_date IS NOT NULL"
        )
    op.execute("DROP VIEW IF EXISTS v_notes CASCADE")
    op.execute(_V_NOTES_OLD)
    op.drop_constraint("ck_note_scope", "experiment_notes", type_="check")
    op.create_check_constraint("ck_note_scope", "experiment_notes", _SCOPE_CHECK_OLD)
    op.drop_index("ix_experiment_notes_event_date", table_name="experiment_notes")
    op.drop_column("experiment_notes", "event_date")
```

- [ ] **Step 6: Reset `experiments_test` again (the model changed) and run the tests to see them pass**

```
psql -U postgres -d experiments_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
.venv/Scripts/pytest.exe tests/models/test_note_event_date_scope.py tests/views/test_typed_notes_views.py tests/models/test_typed_notes_columns.py -q
```
Expected: all pass (10 new model tests + 10 views tests + the 15 existing typed-notes model tests).

- [ ] **Step 7: Rehearse the migration on `experiments_test` (memory `migration-rehearsal-on-experiments-test`)**

Write `<scratchpad>/rehearse_event_date_migration.py` and run it with `PYTHONPATH=. DATABASE_URL=postgresql://experiments_user:password@localhost:5432/experiments_test .venv/Scripts/python.exe <scratchpad>/rehearse_event_date_migration.py` from the repo root. Never point this at `experiments`.

```python
"""Rehearse e5b2d9c7a1f4 on experiments_test: build the PRE-change schema, stamp
the parent, upgrade, prove the refusal path, downgrade, upgrade again, clean up."""
import os, subprocess, sys
from sqlalchemy import create_engine, text

URL = os.environ["DATABASE_URL"]
assert URL.endswith("/experiments_test"), "refusing to run against anything but experiments_test"
ALEMBIC = os.path.join(".venv", "Scripts", "alembic.exe")

def alembic(*args, expect_fail=False):
    r = subprocess.run([ALEMBIC, *args], capture_output=True, text=True, env=os.environ)
    ok = r.returncode == 0
    print(f"$ alembic {' '.join(args)} -> {'ok' if ok else 'FAILED'}")
    if ok == expect_fail:
        print(r.stdout[-2000:], r.stderr[-2000:])
        sys.exit(f"unexpected result for alembic {' '.join(args)}")
    return r

from database import Base  # noqa: E402  (registers models; view-creation noise against an empty DB is harmless)
engine = create_engine(URL)

OLD_CHECK = ("(note_type = 'description' AND result_id IS NULL) OR "
             "(note_type IN ('modification', 'result_note') AND result_id IS NOT NULL) OR "
             "(note_type = 'observation')")

with engine.begin() as c:
    c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
Base.metadata.create_all(engine)
with engine.begin() as c:
    # Simulate the pre-change schema: no event_date, old CHECK, no v_notes.
    c.execute(text("ALTER TABLE experiment_notes DROP CONSTRAINT ck_note_scope"))
    c.execute(text("ALTER TABLE experiment_notes DROP COLUMN event_date"))
    c.execute(text(f"ALTER TABLE experiment_notes ADD CONSTRAINT ck_note_scope CHECK ({OLD_CHECK})"))
    c.execute(text("INSERT INTO experiments (experiment_id, experiment_number, status) VALUES ('REH_001', 1, 'ONGOING')"))
    c.execute(text("INSERT INTO experiment_notes (experiment_id, experiment_fk, note_text, note_type) "
                   "SELECT 'REH_001', id, 'seed', 'observation' FROM experiments WHERE experiment_id='REH_001'"))

alembic("stamp", "c4d8f1a2b6e7")
alembic("upgrade", "head")
with engine.begin() as c:
    cols = {r[0] for r in c.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='experiment_notes'"))}
    assert "event_date" in cols, cols
    idx = {r[0] for r in c.execute(text("SELECT indexname FROM pg_indexes WHERE tablename='experiment_notes'"))}
    assert "ix_experiment_notes_event_date" in idx, idx
    # New CHECK accepts a date-only modification and still rejects a bare one.
    c.execute(text("INSERT INTO experiment_notes (experiment_id, experiment_fk, note_text, note_type, event_date) "
                   "SELECT 'REH_001', id, 'dated mod', 'modification', DATE '2026-09-24' FROM experiments WHERE experiment_id='REH_001'"))
    try:
        with engine.begin() as c2:
            c2.execute(text("INSERT INTO experiment_notes (experiment_id, experiment_fk, note_text, note_type) "
                            "SELECT 'REH_001', id, 'bare mod', 'modification' FROM experiments WHERE experiment_id='REH_001'"))
        sys.exit("bare modification was accepted -- CHECK not applied")
    except Exception as exc:  # noqa: BLE001
        assert "ck_note_scope" in str(exc), exc
    n = c.execute(text("SELECT count(*) FROM v_notes WHERE event_date = DATE '2026-09-24'")).scalar_one()
    assert n == 1, n
print("upgrade verified: column, index, CHECK, v_notes.event_date")

# Refusal path: a date-only modification blocks the downgrade.
alembic("downgrade", "-1", expect_fail=True)
with engine.begin() as c:
    c.execute(text("DELETE FROM experiment_notes WHERE note_text = 'dated mod'"))
alembic("downgrade", "-1")
with engine.begin() as c:
    cols = {r[0] for r in c.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='experiment_notes'"))}
    assert "event_date" not in cols, cols
    vcols = {r[0] for r in c.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='v_notes'"))}
    assert "event_date" not in vcols and "note_id" in vcols, vcols
print("downgrade verified: refused with the dated row, clean without it")
alembic("upgrade", "head")
print("re-upgrade ok (idempotent)")

# Cleanup so the DB is empty again for pytest (memory: shared-test-db-hazards).
from database.event_listeners import _VIEWS  # noqa: E402
with engine.begin() as c:
    for name, _ in _VIEWS:
        c.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
    c.execute(text("DROP TABLE IF EXISTS alembic_version"))
Base.metadata.drop_all(engine)
with engine.begin() as c:
    c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
print("cleanup done")
```
Expected output ends with `cleanup done`, and the `downgrade -1` line prints `FAILED` once (the refusal) then `ok`. Paste the run's output in your report.

- [ ] **Step 8: Single head, then the full backend suite on a fresh `experiments_test`**

```
.venv/Scripts/alembic.exe heads          # expected: e5b2d9c7a1f4 (head)  -- exactly one line
psql -U postgres -d experiments_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
.venv/Scripts/pytest.exe tests/models tests/views tests/api tests/test_icp_handling.py tests/services tests/regression tests/data_migrations -q
```
Expected: 1,380 passed (1,369 baseline + 10 model + 1 view), 0 failed. Record the real number.

- [ ] **Step 9: Commit**

```bash
git add database/models/experiments.py database/event_listeners.py alembic/versions/e5b2d9c7a1f4_note_event_date.py tests/models/test_note_event_date_scope.py tests/views/test_typed_notes_views.py
git commit -F <scratchpad>/msg1.txt
```
`msg1.txt`:
```
[#122] Add event_date anchor to experiment notes

- experiment_notes.event_date DATE NULL + index; ck_note_scope lets a
  'modification' anchor to a result OR a date; v_notes exposes event_date
- Alembic e5b2d9c7a1f4 off c4d8f1a2b6e7; downgrade refuses while any
  modification is dated-only; rehearsed up/down/up on experiments_test
- Tests added: yes (models 10, views +1)
- Docs updated: no (MODELS.md in Task 9)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 2: `event_date` through the notes API and service, plus the TS types

**Files:**
- Modify: `backend/api/schemas/experiments.py` (`NoteCreate`, `NoteUpdate`, `NoteResponse`, ~lines 119-165)
- Modify: `backend/services/notes.py` (`add_note` signature and constructor)
- Modify: `backend/api/routers/experiments.py` (`add_note` route ~1473-1537; `patch_note` ~1540-1612)
- Modify: `frontend/src/api/experiments.ts` (`ExperimentNote`, `NoteCreate`, `NotePatch`, lines 8-32)
- Modify: `tests/api/test_notes.py` (append tests)

**Interfaces:**
- Consumes: Task 1's column and CHECK.
- Produces: `add_note(db, experiment, note_text, *, note_type, result_id, created_by, needs_review, created_at, event_date: Optional[date] = None)`; `POST /experiments/{id}/notes` body accepts `event_date: "YYYY-MM-DD" | null`; `PATCH` accepts `event_date` (explicit `null` clears); responses carry `event_date`. Task 3 calls `add_note(..., event_date=...)`; Task 6 posts `{ note_type: 'modification', event_date }`.

- [ ] **Step 1: Write the failing API tests**

Append to `tests/api/test_notes.py`:

```python
# --- issue #122 PR-B: event_date -------------------------------------------

def _make_experiment(db, exp_id="EVD_API_001", number=7101):
    exp = Experiment(experiment_id=exp_id, experiment_number=number, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def test_post_modification_with_event_date_and_no_result(client, db_session):
    exp = _make_experiment(db_session)
    resp = client.post(f"/api/experiments/{exp.experiment_id}/notes",
                       json={"note_text": "swapped stir shaft", "note_type": "modification",
                             "event_date": "2026-09-24"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["note_type"] == "modification"
    assert body["result_id"] is None
    assert body["event_date"] == "2026-09-24"
    assert body["created_by"] == "test@addisenergy.com"


def test_post_modification_with_neither_anchor_is_422_with_exact_text(client, db_session):
    exp = _make_experiment(db_session, "EVD_API_002", 7102)
    resp = client.post(f"/api/experiments/{exp.experiment_id}/notes",
                       json={"note_text": "x", "note_type": "modification"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "A 'modification' note must be scoped to a result or carry an event_date."


def test_post_observation_may_carry_event_date(client, db_session):
    exp = _make_experiment(db_session, "EVD_API_003", 7103)
    resp = client.post(f"/api/experiments/{exp.experiment_id}/notes",
                       json={"note_text": "cloudy", "event_date": "2026-09-20"})
    assert resp.status_code == 201
    assert resp.json()["event_date"] == "2026-09-20"
    assert resp.json()["note_type"] == "observation"


def test_post_result_note_with_date_only_is_422(client, db_session):
    exp = _make_experiment(db_session, "EVD_API_004", 7104)
    resp = client.post(f"/api/experiments/{exp.experiment_id}/notes",
                       json={"note_text": "x", "note_type": "result_note", "event_date": "2026-09-24"})
    assert resp.status_code == 422
    assert "must name the result_id" in resp.json()["detail"]


def test_patch_sets_event_date_and_logs_it(client, db_session):
    exp = _make_experiment(db_session, "EVD_API_005", 7105)
    note = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text="obs")
    db_session.add(note)
    db_session.commit()
    resp = client.patch(f"/api/experiments/{exp.experiment_id}/notes/{note.id}",
                        json={"event_date": "2026-09-21"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["event_date"] == "2026-09-21"
    log = db_session.execute(
        select(ModificationsLog).where(ModificationsLog.modified_table == "experiment_notes")
        .order_by(ModificationsLog.id.desc())
    ).scalars().first()
    assert log.old_values == {"event_date": None}
    assert log.new_values == {"event_date": "2026-09-21"}


def test_patch_can_retype_a_dated_observation_to_modification(client, db_session):
    exp = _make_experiment(db_session, "EVD_API_006", 7106)
    note = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text="obs",
                           event_date=datetime.date(2026, 9, 21))
    db_session.add(note)
    db_session.commit()
    resp = client.patch(f"/api/experiments/{exp.experiment_id}/notes/{note.id}",
                        json={"note_type": "modification"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["note_type"] == "modification"


def test_patch_clearing_the_only_anchor_of_a_modification_is_422(client, db_session):
    # Review Focus 1: the check runs on the state AFTER the patch.
    exp = _make_experiment(db_session, "EVD_API_007", 7107)
    note = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text="mod",
                           note_type=NoteType.modification, event_date=datetime.date(2026, 9, 21))
    db_session.add(note)
    db_session.commit()
    resp = client.patch(f"/api/experiments/{exp.experiment_id}/notes/{note.id}",
                        json={"event_date": None})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "A 'modification' note must be scoped to a result or carry an event_date."


def test_patch_retype_to_modification_without_any_anchor_is_422(client, db_session):
    exp = _make_experiment(db_session, "EVD_API_008", 7108)
    note = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text="obs")
    db_session.add(note)
    db_session.commit()
    resp = client.patch(f"/api/experiments/{exp.experiment_id}/notes/{note.id}",
                        json={"note_type": "modification"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "A 'modification' note must be scoped to a result or carry an event_date."


def test_patch_with_only_event_date_null_on_an_observation_clears_it(client, db_session):
    exp = _make_experiment(db_session, "EVD_API_009", 7109)
    note = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text="obs",
                           event_date=datetime.date(2026, 9, 21))
    db_session.add(note)
    db_session.commit()
    resp = client.patch(f"/api/experiments/{exp.experiment_id}/notes/{note.id}",
                        json={"event_date": None})
    assert resp.status_code == 200, resp.text
    assert resp.json()["event_date"] is None
```
Add at the top of `tests/api/test_notes.py`: `import datetime` and extend the enums import to `from database.models.enums import ExperimentStatus, NoteType`.

- [ ] **Step 2: Run to see them fail**

`.venv/Scripts/pytest.exe tests/api/test_notes.py -q`
Expected: the nine new tests fail (422 from Pydantic "extra"/unknown-field behaviour or `KeyError: 'event_date'`; the "neither anchor" test fails on the detail text, which still reads "must name the result_id"); the existing tests pass.

- [ ] **Step 3: Schemas**

In `backend/api/schemas/experiments.py` (add `from datetime import date` to the imports if not present — `datetime` is already imported for `created_at`):

`NoteCreate`: add after `result_id`:
```python
    # Issue #122 PR-B: a calendar-date anchor. Required (instead of result_id) for
    # a 'modification' not tied to a result -- the dashboard's reactor form.
    event_date: Optional[date] = None
```
and extend its docstring's last sentence: `... Nothing here is required beyond the text itself -- behaviour change comes from visibility, not validators. 'modification' needs result_id OR event_date (issue #122 PR-B).`

`NoteUpdate`: add `event_date: Optional[date] = None` after `note_type`, and change the validator to use `model_fields_set` so an explicit `null` counts as a field:
```python
    @model_validator(mode="after")
    def _at_least_one_field(self):
        # A field validator would not run for an omitted field, so check the
        # model. `event_date: null` is a real instruction (clear the date), so
        # look at what was SET, not at what is non-None.
        if not self.model_fields_set:
            raise ValueError("provide at least one of note_text, note_type, needs_review, event_date")
        return self
```
Extend the docstring: `` `event_date` (issue #122 PR-B) sets or, with an explicit null, clears the date anchor; a 'modification' must keep at least one anchor.``

`NoteResponse`: add `event_date: Optional[date] = None` after `result_id`.

- [ ] **Step 4: Service**

In `backend/services/notes.py::add_note`, add the keyword parameter `event_date: Optional[date] = None` after `created_at`, pass `event_date=event_date` in the `ExperimentNotes(...)` constructor, and add `from datetime import date, datetime` (replace the existing `from datetime import datetime`). Extend the docstring's first paragraph: `` `event_date` is the calendar anchor a 'modification' may carry instead of a result (issue #122 PR-B).``

- [ ] **Step 5: Router — POST**

In `backend/api/routers/experiments.py::add_note`, replace the second scope check:
```python
    if payload.note_type in (NoteType.modification, NoteType.result_note) and payload.result_id is None:
        raise HTTPException(
            status_code=422,
            detail=f"A '{payload.note_type.value}' note must name the result_id it describes.",
        )
```
with:
```python
    if payload.note_type is NoteType.modification and payload.result_id is None and payload.event_date is None:
        raise HTTPException(
            status_code=422,
            detail="A 'modification' note must be scoped to a result or carry an event_date.",
        )
    if payload.note_type is NoteType.result_note and payload.result_id is None:
        raise HTTPException(
            status_code=422,
            detail="A 'result_note' note must name the result_id it describes.",
        )
```
and pass `event_date=payload.event_date,` to `notes_service.add_note(...)`.

- [ ] **Step 6: Router — PATCH**

In `patch_note`, replace the block from `old_values: dict = {}` through the `needs_review` branch with a version that (a) computes the post-patch state first, (b) checks scope on that state, (c) then records changes:

```python
    old_values: dict = {}
    new_values: dict = {}
    new_type = payload.note_type if payload.note_type is not None else note.note_type
    date_changed = "event_date" in payload.model_fields_set
    new_date = payload.event_date if date_changed else note.event_date

    # Mirror of ck_note_scope on the state AFTER this patch (issue #122 PR-B):
    # a retype and a date change can each remove a 'modification's only anchor.
    if new_type is NoteType.description and note.result_id is not None:
        raise HTTPException(
            status_code=422,
            detail="A result-scoped note cannot become the 'description'; it is experiment-level.",
        )
    if new_type is NoteType.modification and note.result_id is None and new_date is None:
        raise HTTPException(
            status_code=422,
            detail="A 'modification' note must be scoped to a result or carry an event_date.",
        )
    if new_type is NoteType.result_note and note.result_id is None:
        raise HTTPException(
            status_code=422,
            detail="A 'result_note' note must be scoped to a result.",
        )

    if payload.note_text is not None and payload.note_text != note.note_text:
        old_values["note_text"], new_values["note_text"] = note.note_text, payload.note_text
        note.note_text = payload.note_text
    if payload.note_type is not None and payload.note_type is not note.note_type:
        old_values["note_type"], new_values["note_type"] = note.note_type.value, payload.note_type.value
        note.note_type = payload.note_type
    if date_changed and new_date != note.event_date:
        old_values["event_date"] = note.event_date.isoformat() if note.event_date else None
        new_values["event_date"] = new_date.isoformat() if new_date else None
        note.event_date = new_date
    if payload.needs_review is not None and payload.needs_review != note.needs_review:
        old_values["needs_review"], new_values["needs_review"] = note.needs_review, payload.needs_review
        note.needs_review = payload.needs_review
```
Keep everything after (`if not new_values: return ...`, the flush/409 handling, the `ModificationsLog` row, commit, refresh) unchanged. Note the pre-existing 422 text for `result_note` on PATCH (`"A 'result_note' note must be scoped to a result."`) is preserved so `tests/api/test_notes_review.py::test_patch_rejects_modification_without_result` — check that test's assertion: if it asserts on `"must be scoped to a result"` as a substring, the new modification text still contains it; if it asserts the full old string `"A 'modification' note must be scoped to a result."`, update that single assertion to the new exact text and say so in your report.

- [ ] **Step 7: TypeScript types**

In `frontend/src/api/experiments.ts`:
- `ExperimentNote`: after `result_id`, add
  ```ts
  /** Calendar-date anchor for a 'modification' not tied to a result (issue #122 PR-B). */
  event_date?: string | null
  ```
- `NoteCreate`: add `event_date?: string | null`
- `NotePatch`: add `event_date?: string | null`

- [ ] **Step 8: Run to see them pass**

```
.venv/Scripts/pytest.exe tests/api/test_notes.py tests/api/test_notes_review.py tests/services/test_notes_helper.py -q
cd frontend && npx tsc --noEmit
```
Expected: all pass; tsc shows only the 3 baseline errors.

- [ ] **Step 9: Commit**

```bash
git add backend/api/schemas/experiments.py backend/services/notes.py backend/api/routers/experiments.py frontend/src/api/experiments.ts tests/api/test_notes.py   # plus tests/api/test_notes_review.py if one assertion changed
git commit -F <scratchpad>/msg2.txt
```
`msg2.txt`:
```
[#122] Accept event_date on note create and patch

- NoteCreate/NoteUpdate/NoteResponse + add_note carry event_date; POST and
  PATCH mirror the new ck_note_scope as 422 on the post-patch state
- TS ExperimentNote/NoteCreate/NotePatch gain optional event_date
- Tests added: yes (tests/api/test_notes.py +9)
- Docs updated: no (API_REFERENCE in Task 9)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 3: The 021 backfill script and its tests

**Files:**
- Create: `database/data_migrations/migrate_reactor_change_requests_021.py`
- Create: `tests/data_migrations/test_migrate_change_requests_021.py`

**Interfaces:**
- Consumes: `notes_service.add_note(..., event_date=..., created_at=...)` from Task 2; `ReactorChangeRequest` (`database/models/notion_sync.py`: `id, reactor_label, experiment_id (FK → experiments.experiment_id, ON DELETE SET NULL), requested_change, notion_status, carried_forward, sync_date, notion_page_id, created_at`).
- Produces: `SOURCE_TAG = "migrate_change_requests_021"`; `build_plan(db) -> Plan`; `print_report(plan)`; `apply_plan(db, plan) -> list[int]`; `after_counts(db) -> dict`; CLI `python database/data_migrations/migrate_reactor_change_requests_021.py [--apply]`. Task 4 runs the dry run.

- [ ] **Step 1: Write the failing tests**

Create `tests/data_migrations/test_migrate_change_requests_021.py`:

```python
"""Pins the 021 conversion (issue #122 PR-B): every reactor_change_requests row
with a resolvable experiment becomes ONE dated 'modification' note plus ONE
ModificationsLog snapshot; NULL-experiment and blank rows are reported, not
converted; a second run converts nothing; a dry run writes nothing."""
from __future__ import annotations

import datetime

from sqlalchemy import select, func

from database.data_migrations.migrate_reactor_change_requests_021 import (
    SOURCE_TAG,
    apply_plan,
    build_plan,
)
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus, NoteType
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.notion_sync import ReactorChangeRequest

D1 = datetime.date(2026, 8, 1)
D2 = datetime.date(2026, 8, 3)
T0 = datetime.datetime(2026, 8, 1, 9, 30, tzinfo=datetime.timezone.utc)


def _exp(db, eid, num, reactor=None):
    exp = Experiment(experiment_id=eid, experiment_number=num, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    if reactor is not None:
        db.add(ExperimentalConditions(experiment_fk=exp.id, experiment_id=eid,
                                      reactor_number=reactor, experiment_type="HPHT"))
        db.flush()
    return exp


def _cr(db, label, eid, text_, day, **kw):
    row = ReactorChangeRequest(reactor_label=label, experiment_id=eid, requested_change=text_,
                               sync_date=day, created_at=kw.pop("created_at", T0), **kw)
    db.add(row)
    db.flush()
    return row


def _notes(db, exp):
    return db.execute(
        select(ExperimentNotes).where(ExperimentNotes.experiment_fk == exp.id).order_by(ExperimentNotes.id)
    ).scalars().all()


def test_converts_dashboard_and_notion_rows_alike(migration_session):
    db = migration_session
    exp = _exp(db, "CR021_001", 81001, reactor=5)
    typed = _cr(db, "R05", exp.experiment_id, "  Swapped stir shaft  ", D1)
    imported = _cr(db, "R05", exp.experiment_id, "Topped up catalyst", D2,
                   notion_page_id="a" * 32, notion_status="Done", carried_forward=True)
    plan = build_plan(db)
    assert [r.id for r in plan.convertible] == [typed.id, imported.id]
    ids = apply_plan(db, plan)
    db.commit()
    notes = _notes(db, exp)
    assert [n.id for n in notes] == ids
    assert [n.note_text for n in notes] == ["Swapped stir shaft", "Topped up catalyst"]
    assert all(n.note_type is NoteType.modification for n in notes)
    assert [n.event_date for n in notes] == [D1, D2]
    assert all(n.result_id is None for n in notes)
    assert all(n.created_by == SOURCE_TAG for n in notes)
    assert notes[0].created_at == T0


def test_null_experiment_rows_are_reported_not_converted(migration_session):
    db = migration_session
    _exp(db, "CR021_002", 81002)
    orphan = _cr(db, "R07", None, "reactor cleaned", D1)
    plan = build_plan(db)
    assert [r.id for r in plan.orphaned] == [orphan.id]
    assert plan.convertible == []
    apply_plan(db, plan)
    db.commit()
    assert db.execute(select(func.count()).select_from(ExperimentNotes)).scalar_one() == 0


def test_blank_text_rows_are_reported_not_converted(migration_session):
    db = migration_session
    exp = _exp(db, "CR021_003", 81003)
    blank = _cr(db, "R01", exp.experiment_id, "   ", D1)
    plan = build_plan(db)
    assert [r.id for r in plan.blank] == [blank.id]
    assert plan.convertible == []


def test_snapshot_shape(migration_session):
    db = migration_session
    exp = _exp(db, "CR021_004", 81004, reactor=9)
    row = _cr(db, "R09", exp.experiment_id, "Vented headspace", D1, notion_status="In progress")
    plan = build_plan(db)
    (note_id,) = apply_plan(db, plan)
    db.commit()
    log = db.execute(
        select(ModificationsLog).where(ModificationsLog.modified_table == "reactor_change_requests")
    ).scalar_one()
    assert log.modification_type == "update"
    assert log.modified_by == SOURCE_TAG
    assert log.experiment_fk == exp.id
    assert log.experiment_id == exp.experiment_id
    assert log.new_values == {"note_id": note_id}
    assert log.old_values["id"] == row.id
    assert log.old_values["reactor_label"] == "R09"
    assert log.old_values["requested_change"] == "Vented headspace"
    assert log.old_values["notion_status"] == "In progress"
    assert log.old_values["carried_forward"] is False
    assert log.old_values["sync_date"] == "2026-08-01"
    assert log.old_values["notion_page_id"] is None
    assert log.old_values["created_at"] == T0.isoformat()


def test_second_run_is_a_no_op(migration_session):
    db = migration_session
    exp = _exp(db, "CR021_005", 81005)
    _cr(db, "R02", exp.experiment_id, "Replaced septum", D1)
    first = build_plan(db)
    apply_plan(db, first)
    db.commit()
    second = build_plan(db)
    assert second.convertible == []
    assert len(second.already_converted) == 1
    apply_plan(db, second)
    db.commit()
    assert len(_notes(db, exp)) == 1
    assert db.execute(select(func.count()).select_from(ModificationsLog)
                      .where(ModificationsLog.modified_table == "reactor_change_requests")).scalar_one() == 1


def test_same_experiment_date_text_under_two_labels_collapses_to_one_note(migration_session):
    # Review Focus 2: the unique key allows this pair; the idempotency key does not.
    db = migration_session
    exp = _exp(db, "CR021_006", 81006)
    a = _cr(db, "R03", exp.experiment_id, "moved to R04", D1)
    b = _cr(db, "R04", exp.experiment_id, "moved to R04", D1)
    plan = build_plan(db)
    assert [r.id for r in plan.convertible] == [a.id]
    assert [r.id for r in plan.collapsed] == [b.id]
    apply_plan(db, plan)
    db.commit()
    assert len(_notes(db, exp)) == 1


def test_label_disagreement_is_counted_informationally(migration_session):
    db = migration_session
    exp = _exp(db, "CR021_007", 81007, reactor=5)        # reactor_slot derives to R05
    _cr(db, "R05", exp.experiment_id, "agrees", D1)
    _cr(db, "R06", exp.experiment_id, "disagrees", D2)
    plan = build_plan(db)
    assert plan.label_disagreements == 1
    assert len(plan.convertible) == 2                     # informational only, both convert


def test_dry_run_writes_nothing(migration_session):
    db = migration_session
    exp = _exp(db, "CR021_008", 81008)
    _cr(db, "R08", exp.experiment_id, "dry", D1)
    build_plan(db)                                        # no apply_plan
    db.commit()
    assert _notes(db, exp) == []
    assert db.execute(select(func.count()).select_from(ModificationsLog)).scalar_one() == 0
```

- [ ] **Step 2: Run to see them fail**

`.venv/Scripts/pytest.exe tests/data_migrations/test_migrate_change_requests_021.py -q`
Expected: `ModuleNotFoundError: No module named 'database.data_migrations.migrate_reactor_change_requests_021'`.

- [ ] **Step 3: Write the script**

Create `database/data_migrations/migrate_reactor_change_requests_021.py`:

```python
"""One-time backfill: convert reactor_change_requests rows into dated
'modification' notes (issue #122, PR-B; phase-2 spec decisions 1, 2, 9-11).

Background
----------
The dashboard reactor card's "Reactor Modification" form wrote to
reactor_change_requests, a table the retired Notion sync created (one row per
reactor per date, upserted). Typed experiment notes (issue #118) made that a
second, disconnected home for the same fact: v_dim_timepoints.modification_note
read only notes, so Power BI and the card disagreed. PR-B gives experiment_notes
an event_date anchor and makes the card write 'modification' notes; this script
moves the existing rows across. Nothing is deleted from reactor_change_requests
-- dropping the table is a separately authorized follow-up (PR-E2).

Rules, in id order (deterministic; nothing is guessed)
-------------------------------------------------------
1. experiment_id IS NULL -> ORPHANED, reported, not converted. The column is an
   FK to experiments.experiment_id with ON DELETE SET NULL, so NULL means the
   experiment was deleted after the row was written, or a Notion import never
   matched one. There is no string to resolve; guessing an experiment from the
   reactor label would attribute a modification to whoever occupies the slot
   today.
2. A non-NULL experiment_id resolves EXACTLY against experiments.experiment_id
   (the FK guarantees the match). No fuzzy matching, no _id_match.normalize_id.
3. requested_change blank after strip -> BLANK, reported, not converted.
4. Otherwise the row becomes ONE note via backend.services.notes.add_note:
   note_type='modification', event_date=sync_date, result_id NULL,
   note_text=requested_change.strip(), created_by=SOURCE_TAG,
   created_at=row.created_at. Dashboard-typed and Notion-imported rows convert
   alike -- both record a real modification. reactor_label is NOT carried onto
   the note (decision 2: the card knows its slot); the whole original row is
   snapshotted to ModificationsLog(modified_table='reactor_change_requests',
   modification_type='update', old_values=<row>, new_values={'note_id': id},
   experiment_fk=<exp.id>) so label, Notion status and page id are recoverable.
   experiment_fk is set on purpose: these snapshots belong to the experiment
   and die with it.
5. Idempotent. A row is ALREADY CONVERTED when a note exists with the same
   experiment_fk, event_date, note_text and created_by=SOURCE_TAG. Two source
   rows sharing (experiment, date, text) -- possible only under two different
   reactor_labels, because of the table's unique key -- COLLAPSE into one
   note; the second is reported as collapsed, never doubled or dropped silently.
6. Informational: how many convertible rows carry a reactor_label that differs
   from the experiment's current experimental_conditions.reactor_slot. A
   difference is expected when an experiment moved reactors; it is reported so
   Mat can judge whether the label must be kept (decision 2's open question).

Usage
-----
    # Dry run (default): prints the report, writes nothing
    PYTHONPATH=. python database/data_migrations/migrate_reactor_change_requests_021.py

    # Apply -- ONLY after Mat has audited the dry-run report
    PYTHONPATH=. python database/data_migrations/migrate_reactor_change_requests_021.py --apply

    # Against a specific database (defaults to $DATABASE_URL, then the dev DB)
    DATABASE_URL=postgresql://... python database/data_migrations/migrate_reactor_change_requests_021.py
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.services.notes import add_note
from database.database import get_db
from database.models.conditions import ExperimentalConditions
from database.models.enums import NoteType
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.notion_sync import ReactorChangeRequest

SOURCE_TAG = "migrate_change_requests_021"
SAMPLE_SIZE = 20


@dataclass
class Plan:
    total: int = 0
    convertible: list[ReactorChangeRequest] = field(default_factory=list)
    orphaned: list[ReactorChangeRequest] = field(default_factory=list)      # experiment_id IS NULL
    blank: list[ReactorChangeRequest] = field(default_factory=list)
    already_converted: list[ReactorChangeRequest] = field(default_factory=list)
    collapsed: list[ReactorChangeRequest] = field(default_factory=list)     # same (exp, date, text) as an earlier row
    label_disagreements: int = 0
    dashboard_typed: int = 0      # notion_page_id IS NULL
    notion_imported: int = 0      # notion_page_id IS NOT NULL
    experiments: dict[str, Experiment] = field(default_factory=dict)        # experiment_id -> row (resolved)


def _row_dict(row: ReactorChangeRequest) -> dict:
    """The full original row, JSON-safe, for the ModificationsLog snapshot."""
    def iso(v):
        return v.isoformat() if isinstance(v, (date, datetime)) else v
    return {
        "id": row.id,
        "reactor_label": row.reactor_label,
        "experiment_id": row.experiment_id,
        "requested_change": row.requested_change,
        "notion_status": row.notion_status,
        "carried_forward": row.carried_forward,
        "sync_date": iso(row.sync_date),
        "notion_page_id": row.notion_page_id,
        "created_at": iso(row.created_at),
    }


def build_plan(db: Session) -> Plan:
    """Read-only. Everything --apply will do is decided here."""
    plan = Plan()
    rows = db.execute(select(ReactorChangeRequest).order_by(ReactorChangeRequest.id)).scalars().all()
    plan.total = len(rows)

    exp_ids = sorted({r.experiment_id for r in rows if r.experiment_id is not None})
    if exp_ids:
        for exp in db.execute(select(Experiment).where(Experiment.experiment_id.in_(exp_ids))).scalars():
            plan.experiments[exp.experiment_id] = exp
    slots: dict[int, Optional[str]] = {}
    if plan.experiments:
        fks = [e.id for e in plan.experiments.values()]
        for fk, slot in db.execute(
            select(ExperimentalConditions.experiment_fk, ExperimentalConditions.reactor_slot)
            .where(ExperimentalConditions.experiment_fk.in_(fks))
        ).all():
            slots[fk] = slot

    existing = {
        (n.experiment_fk, n.event_date, n.note_text)
        for n in db.execute(
            select(ExperimentNotes.experiment_fk, ExperimentNotes.event_date, ExperimentNotes.note_text)
            .where(ExperimentNotes.created_by == SOURCE_TAG, ExperimentNotes.note_type == NoteType.modification)
        ).all()
    }
    seen_this_run: set[tuple[int, date, str]] = set()

    for row in rows:
        if row.notion_page_id is None:
            plan.dashboard_typed += 1
        else:
            plan.notion_imported += 1
        if row.experiment_id is None:
            plan.orphaned.append(row)
            continue
        exp = plan.experiments.get(row.experiment_id)
        if exp is None:
            # Cannot happen while the FK holds; reported rather than raised so a
            # dry run against a DB with the FK dropped still produces a report.
            plan.orphaned.append(row)
            continue
        text_ = (row.requested_change or "").strip()
        if not text_:
            plan.blank.append(row)
            continue
        key = (exp.id, row.sync_date, text_)
        if key in existing:
            plan.already_converted.append(row)
            continue
        if key in seen_this_run:
            plan.collapsed.append(row)
            continue
        seen_this_run.add(key)
        plan.convertible.append(row)
        if slots.get(exp.id) != row.reactor_label:
            plan.label_disagreements += 1
    return plan


def _sample(items, n=SAMPLE_SIZE):
    return items[:n]


def _short(text_: Optional[str], width: int = 60) -> str:
    t = (text_ or "").replace("\n", " ")
    return t if len(t) <= width else t[: width - 1] + "…"


def print_report(plan: Plan) -> None:
    p = print
    p("== migrate_reactor_change_requests_021 -- dry-run report ==")
    p(f"reactor_change_requests rows:                    {plan.total}")
    p(f"  typed on the dashboard (notion_page_id NULL):  {plan.dashboard_typed}")
    p(f"  imported from Notion:                          {plan.notion_imported}")
    p(f"convertible (-> one 'modification' note each):   {len(plan.convertible)}")
    p(f"orphaned (experiment_id NULL; FK ON DELETE SET NULL): {len(plan.orphaned)}")
    for r in plan.orphaned:
        p(f"    row {r.id}: {r.reactor_label} {r.sync_date} {'notion' if r.notion_page_id else 'dashboard'} "
          f"'{_short(r.requested_change)}'")
    p(f"blank requested_change:                          {len(plan.blank)}")
    for r in plan.blank:
        p(f"    row {r.id}: {r.reactor_label} {r.sync_date} exp={r.experiment_id}")
    p(f"already converted by a prior run (skipped):      {len(plan.already_converted)}")
    p(f"collapsed under (experiment, date, text):        {len(plan.collapsed)}")
    for r in plan.collapsed:
        p(f"    row {r.id}: {r.reactor_label} {r.sync_date} exp={r.experiment_id} '{_short(r.requested_change)}'")
    p(f"reactor_label != current conditions.reactor_slot: {plan.label_disagreements} of {len(plan.convertible)} (informational)")
    p(f"-- sample of {min(SAMPLE_SIZE, len(plan.convertible))} convertible rows --")
    for r in _sample(plan.convertible):
        p(f"    row {r.id}: {r.reactor_label} {r.sync_date} exp={r.experiment_id} "
          f"{'notion' if r.notion_page_id else 'dashboard'} '{_short(r.requested_change)}'")


def apply_plan(db: Session, plan: Plan) -> list[int]:
    """Convert every plan.convertible row; return the new note ids in order."""
    note_ids: list[int] = []
    for row in plan.convertible:
        exp = plan.experiments[row.experiment_id]
        note = add_note(
            db,
            exp,
            (row.requested_change or "").strip(),
            note_type=NoteType.modification,
            event_date=row.sync_date,
            created_by=SOURCE_TAG,
            created_at=row.created_at,
        )
        db.add(ModificationsLog(
            experiment_id=exp.experiment_id,
            experiment_fk=exp.id,
            modified_by=SOURCE_TAG,
            modification_type="update",
            modified_table="reactor_change_requests",
            old_values=_row_dict(row),
            new_values={"note_id": note.id},
        ))
        note_ids.append(note.id)
    db.flush()
    return note_ids


def after_counts(db: Session) -> dict:
    def q(sql: str) -> int:
        from sqlalchemy import text
        return db.execute(text(sql)).scalar_one()
    return {
        "change_request_rows": q("SELECT COUNT(*) FROM reactor_change_requests"),
        "modification_notes": q("SELECT COUNT(*) FROM experiment_notes WHERE note_type = 'modification'"),
        "dated_modification_notes": q("SELECT COUNT(*) FROM experiment_notes WHERE note_type = 'modification' AND event_date IS NOT NULL"),
        "notes_by_021": q(f"SELECT COUNT(*) FROM experiment_notes WHERE created_by = '{SOURCE_TAG}'"),
        "snapshots_by_021": q("SELECT COUNT(*) FROM modifications_log WHERE modified_table = 'reactor_change_requests'"),
        "notes_total": q("SELECT COUNT(*) FROM experiment_notes"),
    }


def main(apply: bool) -> None:
    db = next(get_db())
    try:
        before = after_counts(db)
        plan = build_plan(db)
        print_report(plan)
        print("before:", before)
        if not apply:
            print("\nDry run — pass --apply to commit changes.")
            return
        ids = apply_plan(db, plan)
        db.commit()
        after = after_counts(db)
        print("after: ", after)
        expected = before["notes_by_021"] + len(plan.convertible)
        if after["notes_by_021"] != expected or len(ids) != len(plan.convertible):
            print(f"WARNING: converted {len(ids)}, expected {len(plan.convertible)}; "
                  f"notes_by_021 {after['notes_by_021']} vs expected {expected}", file=sys.stderr)
            sys.exit(2)
        print(f"\nApplied. {len(ids)} notes created (matches the dry-run plan).")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Commit changes (default: dry run)")
    args = parser.parse_args()
    main(apply=args.apply)
```
Check `database/database.py` exports `get_db` the way `reclassify_notes_020.py` imports it (copy that script's import line if it differs).

- [ ] **Step 4: Run to see them pass**

`.venv/Scripts/pytest.exe tests/data_migrations/test_migrate_change_requests_021.py -q`
Expected: 8 passed.

Then the dry run against `experiments_test` must print a report with `reactor_change_requests rows: 0` and `Dry run — pass --apply` (a smoke test that the CLI wiring works; the real dry run is Task 4):
`PYTHONPATH=. DATABASE_URL=postgresql://experiments_user:password@localhost:5432/experiments_test .venv/Scripts/python.exe database/data_migrations/migrate_reactor_change_requests_021.py`
(If the test DB tables are absent after the suite's teardown, the command errors on the missing table — acceptable; say so and skip the smoke test.)

- [ ] **Step 5: Commit**

```bash
git add database/data_migrations/migrate_reactor_change_requests_021.py tests/data_migrations/test_migrate_change_requests_021.py
git commit -F <scratchpad>/msg3.txt
```
`msg3.txt`:
```
[#122] Add 021 backfill: change requests to dated notes

- migrate_reactor_change_requests_021.py: dry run default, --apply,
  idempotent on (experiment, date, text, source tag), one ModificationsLog
  snapshot per converted row, NULL-experiment and blank rows reported
- Tests added: yes (tests/data_migrations, 8)
- Docs updated: no (dry-run report in Task 4)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 4 (Conductor, not a subagent): migrate the mirror, dry run, report, STOP

The dev DB `experiments` was refreshed on 2026-09-24 from `docs/sample_data/experiments_20260923_010002.sql` (production data through 2026-09-22 16:30), upgraded to `c4d8f1a2b6e7`, and `reclassify_notes_020.py --apply` was rehearsed on it (1,429 descriptions, 151 modification notes, review queue 1,288 — production's own 020 run reported 1,432 / 151 / 1,288).

- [ ] `.venv/Scripts/alembic.exe upgrade head` against the dev DB (additive; brings it to `e5b2d9c7a1f4`). Confirm `alembic current`.
- [ ] `PYTHONPATH=. .venv/Scripts/python.exe database/data_migrations/migrate_reactor_change_requests_021.py` (dry run). Save the full output to the scratchpad.
- [ ] Write `docs/issues/migrate-change-requests-021-dryrun-2026-09-24.md`: mirror provenance (backup file, data horizon, schema revision, 020 rehearsal counts); the report's numbers (total, dashboard-typed vs Notion, convertible, orphaned with the row list, blank, already-converted, collapsed, label disagreements); the sample of 20; the "before" counts; the pre-measured table (`rcr_total 333, typed 196, imported 137, dated ≥ 2026-08-01 154, dated > 2026-09-04 39, experiment_id NULL 26, blank 0, distinct labels 21, label≠slot 8, dup (exp,date,text) 0`); the correction to the spec's "26 unresolvable IDs" (they are NULLs, FK `ON DELETE SET NULL`); the decision-2 question (prefix migrated text with `[R05] `? default no); and the exact `--apply` command Mat would run on the mirror after approval.
- [ ] Commit the report: `[#122] Add 021 dry-run report (2026-09-23 mirror)` — Tests added: no; Docs updated: yes.
- [ ] **STOP.** Post the report to Mat and wait. Do not run `--apply`. Do not start Task 5.

---

# PHASE 2 — after Mat's approval and `--apply` on the mirror (Tasks 5–9)

### Task 5: Dashboard reads today's and the latest modification from notes

**Files:**
- Modify: `backend/api/schemas/dashboard.py` (`ReactorCardData` and a new `LatestModification` model before it)
- Modify: `backend/api/routers/dashboard.py` (imports lines 7-11; section 2b ~lines 161-180)
- Modify: `tests/api/test_dashboard.py` (the block from `test_reactor_card_data_schema_todays_modification_defaults_none` through `test_dashboard_modification_lookup_is_single_batched_query`, ~lines 822-1004)
- Modify: `frontend/src/api/dashboard.ts` (`ReactorCardData`)

**Interfaces:**
- Consumes: `ExperimentNotes.event_date`, `NoteType.modification`.
- Produces: `ReactorCardData.todays_modification: Optional[str]` (unchanged name; now the `'; '`-joined `modification` notes with `event_date == today (UTC)` in id order) and `ReactorCardData.latest_modification: Optional[LatestModification]` where `LatestModification = {note_text: str, event_date: Optional[date], created_at: datetime}` — the most recent `modification` note by `(COALESCE(event_date, created_at::date), id)`. TS mirror: `latest_modification: { note_text: string; event_date: string | null; created_at: string } | null`. Task 6 renders it.

- [ ] **Step 1: Rewrite the dashboard modification tests**

In `tests/api/test_dashboard.py`, replace every `ReactorChangeRequest` seed in the modification tests with a `modification` note, keep the test names, and add the two new behaviours. Replace the block from `def test_reactor_card_data_schema_todays_modification_defaults_none` up to (not including) the `# Workday-window KPI` banner with:

```python
def test_reactor_card_data_schema_todays_modification_defaults_none():
    from backend.api.schemas.dashboard import ReactorCardData
    r = ReactorCardData(reactor_number=5, reactor_label="R05")
    assert r.todays_modification is None
    assert r.latest_modification is None


def _card_exp(db, eid, number, reactor):
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus
    exp = Experiment(experiment_id=eid, experiment_number=number, status=ExperimentStatus.ONGOING,
                     created_at=datetime.datetime.utcnow())
    db.add(exp)
    db.flush()
    db.add(ExperimentalConditions(experiment_fk=exp.id, experiment_id=eid,
                                  reactor_number=reactor, experiment_type="HPHT"))
    db.flush()
    return exp


def _mod(db, exp, text_, event_date=None, result_id=None, created_at=None):
    from database.models.experiments import ExperimentNotes
    from database.models.enums import NoteType
    n = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text=text_,
                        note_type=NoteType.modification, event_date=event_date, result_id=result_id)
    if created_at is not None:
        n.created_at = created_at
    db.add(n)
    db.flush()
    return n


def test_reactor_card_shows_todays_modification(client, db_session):
    """A 'modification' note with event_date == today (UTC) is the card's todays_modification."""
    exp = _card_exp(db_session, "MOD_TODAY_001", 72001, 4)
    _mod(db_session, exp, "Swapped stir shaft; topped up catalyst", event_date=_utc_today())
    db_session.commit()
    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}
    assert cards["R04"]["todays_modification"] == "Swapped stir shaft; topped up catalyst"
    assert cards["R04"]["latest_modification"]["note_text"] == "Swapped stir shaft; topped up catalyst"
    assert cards["R04"]["latest_modification"]["event_date"] == _utc_today().isoformat()


def test_reactor_card_prior_day_modification_not_shown_as_today_but_is_latest(client, db_session):
    exp = _card_exp(db_session, "MOD_YDAY_001", 72002, 5)
    _mod(db_session, exp, "yesterday's change", event_date=_utc_today() - datetime.timedelta(days=1))
    db_session.commit()
    resp = client.get("/api/dashboard/")
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}
    assert cards["R05"]["todays_modification"] is None
    assert cards["R05"]["latest_modification"]["note_text"] == "yesterday's change"


def test_several_todays_modifications_are_joined_in_id_order(client, db_session):
    # Review Focus 4
    exp = _card_exp(db_session, "MOD_MULTI_001", 72003, 6)
    _mod(db_session, exp, "first", event_date=_utc_today())
    _mod(db_session, exp, "second", event_date=_utc_today())
    db_session.commit()
    resp = client.get("/api/dashboard/")
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}
    assert cards["R06"]["todays_modification"] == "first; second"


def test_latest_modification_orders_by_event_date_then_id_and_falls_back_to_created_at(client, db_session):
    # Review Focus 3: a result-anchored modification (no event_date) counts by created_at::date
    # for "latest" but is never "today's".
    from database.models.results import ExperimentalResults
    exp = _card_exp(db_session, "MOD_LATEST_001", 72004, 7)
    r = ExperimentalResults(experiment_fk=exp.id, time_post_reaction_days=1.0,
                            time_post_reaction_bucket_days=1.0, description="seed")
    db_session.add(r)
    db_session.flush()
    long_ago = datetime.datetime(2026, 1, 5, 12, 0, tzinfo=datetime.timezone.utc)
    _mod(db_session, exp, "old dated", event_date=datetime.date(2026, 3, 1))
    newest = _mod(db_session, exp, "result-anchored today", result_id=r.id,
                  created_at=datetime.datetime.now(datetime.timezone.utc))
    _mod(db_session, exp, "ancient by created_at", result_id=r.id, created_at=long_ago)
    db_session.commit()
    resp = client.get("/api/dashboard/")
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}
    assert cards["R07"]["todays_modification"] is None
    assert cards["R07"]["latest_modification"]["note_text"] == "result-anchored today"
    assert cards["R07"]["latest_modification"]["event_date"] is None
    assert newest.id  # sanity: the row exists


def test_todays_modification_keys_on_experiment_not_reactor(client, db_session):
    """Two cards, each shows only its own experiment's note; an empty card shows none."""
    a = _card_exp(db_session, "MOD_KEY_A", 72005, 8)
    b = _card_exp(db_session, "MOD_KEY_B", 72006, 9)
    _mod(db_session, a, "mod A", event_date=_utc_today())
    _mod(db_session, b, "mod B", event_date=_utc_today())
    db_session.commit()
    resp = client.get("/api/dashboard/")
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}
    assert cards["R08"]["todays_modification"] == "mod A"
    assert cards["R09"]["todays_modification"] == "mod B"
    assert cards["R10"]["todays_modification"] is None
    assert cards["R10"]["latest_modification"] is None


def test_dashboard_modification_lookup_is_single_batched_query(client, db_session):
    """At most two statements touch experiment_notes for any number of cards: the
    card query (whose description subquery reads notes) and ONE batched
    modification query. No per-card N+1."""
    import sqlalchemy
    from sqlalchemy.engine import Engine
    for i, rn in enumerate((10, 11, 12)):
        exp = _card_exp(db_session, f"MOD_BATCH_{rn}", 72100 + i, rn)
        _mod(db_session, exp, f"mod {rn}", event_date=_utc_today())
    db_session.commit()

    statements: list[str] = []

    def counter(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sqlalchemy.event.listen(Engine, "before_cursor_execute", counter)
    try:
        resp = client.get("/api/dashboard/")
    finally:
        sqlalchemy.event.remove(Engine, "before_cursor_execute", counter)

    assert resp.status_code == 200
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}
    assert cards["R10"]["todays_modification"] == "mod 10"
    assert cards["R12"]["todays_modification"] == "mod 12"
    notes_queries = [s for s in statements if "experiment_notes" in s]
    assert len(notes_queries) <= 2, (
        f"Expected the card query plus one batched notes query, got {len(notes_queries)}"
    )
    assert not any("reactor_change_requests" in s for s in statements)
```
Remove the now-unused `from database.models.notion_sync import ReactorChangeRequest` imports inside those tests (they were function-local; the replacement has none).

- [ ] **Step 2: Run to see them fail**

`.venv/Scripts/pytest.exe tests/api/test_dashboard.py -q -k "modification"`
Expected: fail — `latest_modification` missing from the response / schema; `todays_modification` None where a note exists.

- [ ] **Step 3: Schema**

In `backend/api/schemas/dashboard.py`, add before `class ReactorCardData` (ensure `from datetime import date, datetime` and `Optional` are imported):
```python
class LatestModification(BaseModel):
    """The most recent 'modification' note on a card's experiment (issue #122 PR-B):
    ordered by COALESCE(event_date, created_at::date), then id."""
    note_text: str
    event_date: Optional[date] = None
    created_at: datetime
```
In `ReactorCardData`, replace the `todays_modification` line with:
```python
    # Issue #122 PR-B: both read 'modification' notes, not reactor_change_requests.
    todays_modification: Optional[str] = None   # notes with event_date == today (UTC), '; '-joined in id order
    latest_modification: Optional[LatestModification] = None
```

- [ ] **Step 4: Router**

In `backend/api/routers/dashboard.py`:
- Replace `from database.models.experiments import Experiment, ModificationsLog` with `from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog`; replace `from database.models.enums import ExperimentStatus` with `from database.models.enums import ExperimentStatus, NoteType`; **delete** `from database.models.notion_sync import ReactorChangeRequest`; add `LatestModification` to the `backend.api.schemas.dashboard` import.
- Replace section 2b (from the `# ── 2b.` banner through `c.todays_modification = mods.get(...)`) with:

```python
    # ── 2b. Reactor modifications per card (issue #72, re-sourced by #122 PR-B) ─
    # A reactor modification is a 'modification' note anchored to an event_date
    # (dashboard saves, the 021 backfill) or to a result (Add Results). One
    # batched query over the cards' experiments keeps this endpoint's "no N+1"
    # contract; the reduction to "today's" and "latest" happens here. "Today" is
    # UTC, matching the card's save path (todayISO() is the UTC date).
    today = now.date()
    card_fks = [c.experiment_db_id for c in reactor_cards if c.experiment_db_id]
    if card_fks:
        mod_rows = db.execute(
            select(
                ExperimentNotes.experiment_fk,
                ExperimentNotes.id,
                ExperimentNotes.note_text,
                ExperimentNotes.event_date,
                ExperimentNotes.created_at,
            )
            .where(
                ExperimentNotes.experiment_fk.in_(card_fks),
                ExperimentNotes.note_type == NoteType.modification,
            )
            .order_by(ExperimentNotes.experiment_fk, ExperimentNotes.id)
        ).all()
        todays: dict[int, list[str]] = {}
        latest: dict[int, tuple] = {}   # experiment_fk -> ((anchor_date, id), row)
        for r in mod_rows:
            if r.event_date == today:
                todays.setdefault(r.experiment_fk, []).append(r.note_text or "")
            anchor = (r.event_date or r.created_at.date(), r.id)
            if r.experiment_fk not in latest or anchor > latest[r.experiment_fk][0]:
                latest[r.experiment_fk] = (anchor, r)
        for c in reactor_cards:
            if not c.experiment_db_id:
                continue
            texts = todays.get(c.experiment_db_id)
            c.todays_modification = "; ".join(texts) if texts else None
            hit = latest.get(c.experiment_db_id)
            if hit is not None:
                _, r = hit
                c.latest_modification = LatestModification(
                    note_text=r.note_text or "", event_date=r.event_date, created_at=r.created_at,
                )
```
Confirm `reactor_cards` entries are built with `experiment_db_id=` (they are — `ReactorCardData.experiment_db_id`); if the card constructor uses a different attribute name for the PK, use that one.

- [ ] **Step 5: TS type**

In `frontend/src/api/dashboard.ts`, in `ReactorCardData`, after `todays_modification: string | null`, add:
```ts
  /** Most recent 'modification' note on this card's experiment (issue #122 PR-B). */
  latest_modification: { note_text: string; event_date: string | null; created_at: string } | null
```
Then update every `makeCard`/fixture in `frontend/src/pages/__tests__/ReactorGrid.test.tsx` and `Dashboard.test.tsx` that builds a `ReactorCardData` literal to include `latest_modification: null` (tsc will list them).

- [ ] **Step 6: Run**

```
.venv/Scripts/pytest.exe tests/api/test_dashboard.py -q
cd frontend && npx tsc --noEmit
```
Expected: all dashboard tests pass; tsc only the 3 baseline errors.

- [ ] **Step 7: Commit**

```
[#122] Read reactor modifications from notes on the card

- dashboard.py: todays_modification and new latest_modification come from
  'modification' notes in one batched query; ReactorChangeRequest import gone
- Tests added: yes (test_dashboard.py modification block rewritten, +2)
- Docs updated: no (API_REFERENCE in Task 9)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 6: The dashboard card saves a dated modification note

**Files:**
- Modify: `frontend/src/pages/ReactorGrid.tsx` (~lines 281-330 state/query/mutation; ~505-550 the "REACTOR MODIFICATION" section)
- Modify: `frontend/src/pages/__tests__/ReactorGrid.test.tsx`, `frontend/src/pages/__tests__/Dashboard.test.tsx` (mocks)

**Interfaces:**
- Consumes: `experimentsApi.addNote(id, text, { note_type: 'modification', event_date })` (Task 2); `card.latest_modification` (Task 5).
- Produces: nothing downstream.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/pages/__tests__/ReactorGrid.test.tsx`, change the `@/api/experiments` mock to
```ts
vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    patchStatus: vi.fn(),
    patch: vi.fn(),
    addNote: vi.fn(() => Promise.resolve({})),
  },
}))
```
add `latest_modification: null,` to `makeCard`'s defaults, and append a describe block. The card's pop-out is opened by clicking the experiment id on the card (look at how the existing double-booking test at ~line 101 opens the status menu / modal and reuse that path; if the pop-out is the `ReactorDetailModal` opened by clicking the card, use `fireEvent.click(screen.getByText('HPHT_MH_072'))`):

```ts
describe('ReactorCard — reactor modification saves a dated note (issue #122 PR-B)', () => {
  it('posts a modification note with the picked event_date and clears the textarea', async () => {
    renderGrid([makeCard()])
    fireEvent.click(screen.getByText('HPHT_MH_072'))
    const date = screen.getByLabelText('Modification date') as HTMLInputElement
    fireEvent.change(date, { target: { value: '2026-09-20' } })
    const box = screen.getByPlaceholderText(/enter a reactor modification/i) as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: '  Swapped stir shaft  ' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() =>
      expect(experimentsApi.addNote).toHaveBeenCalledWith(
        'HPHT_MH_072', 'Swapped stir shaft', { note_type: 'modification', event_date: '2026-09-20' },
      ),
    )
    await waitFor(() => expect(box.value).toBe(''))
    expect(await screen.findByText(/Modification saved for 2026-09-20/)).toBeInTheDocument()
  })

  it('Save is disabled while the textarea is blank (Review Focus 5)', () => {
    renderGrid([makeCard()])
    fireEvent.click(screen.getByText('HPHT_MH_072'))
    const box = screen.getByPlaceholderText(/enter a reactor modification/i)
    fireEvent.change(box, { target: { value: '   ' } })
    expect(screen.getByRole('button', { name: /^save$/i })).toBeDisabled()
    expect(experimentsApi.addNote).not.toHaveBeenCalled()
  })

  it('renders the latest prior modification from the card payload, not a change-request query', () => {
    renderGrid([makeCard({
      latest_modification: { note_text: 'Replaced septum', event_date: '2026-09-18', created_at: '2026-09-18T10:00:00Z' },
    })])
    fireEvent.click(screen.getByText('HPHT_MH_072'))
    expect(screen.getByText('Replaced septum')).toBeInTheDocument()
  })
})
```
In `Dashboard.test.tsx`, replace the two change-request mocks with `addNote: vi.fn()`.

- [ ] **Step 2: Run to see them fail**

`npx vitest run src/pages/__tests__/ReactorGrid.test.tsx src/pages/__tests__/Dashboard.test.tsx` (from `frontend/`)
Expected: the three new tests fail (`getRecentChangeRequests is not a function` or `addNote` never called).

- [ ] **Step 3: Implement in `ReactorGrid.tsx`**

(a) Delete the `recentCR` query (`useQuery({ queryKey: ['reactorModificationRecent', ...] })`), the `crLoadedForDate` state, and the pre-populate `useEffect` that sets `crText` from `recentCR.selected`. Keep `crDate` (default `todayISO`) and `crText`. If `useQuery`/`useEffect` become unused imports, remove them from the import lines (eslint will tell you).

(b) Replace `crMutation`:
```tsx
  // Issue #122 PR-B (decision 9): each save is a NEW dated 'modification' note.
  // Corrections happen in the experiment's Notes tab; there is no per-date upsert.
  const crMutation = useMutation({
    mutationFn: (text: string) =>
      experimentsApi.addNote(card.experiment_id as string, text, {
        note_type: 'modification',
        event_date: crDate,
      }),
    onSuccess: () => {
      setCrText('')
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['experiment', card.experiment_id] })
      success(`Modification saved for ${crDate}`)
    },
    onError: (err: Error) => {
      toastError('Save failed', err.message || 'Could not save reactor modification')
    },
  })
```

(c) In the "REACTOR MODIFICATION section", replace the `recentCR?.previous && (...)` block with:
```tsx
            {/* Most recent modification on this experiment — read only (from the card payload) */}
            {card.latest_modification && (
              <div className="mb-3 p-2.5 bg-surface-raised rounded border border-surface-border">
                <p className="text-2xs text-ink-muted mb-1">
                  {formatDateShort(card.latest_modification.event_date ?? card.latest_modification.created_at)}
                </p>
                <p className="text-xs text-ink-secondary leading-relaxed">
                  {card.latest_modification.note_text}
                </p>
              </div>
            )}
```
The date input, textarea, and Save button stay as they are (`onClick={() => crMutation.mutate(crText.trim())}`, `disabled={!crText.trim() || crMutation.isPending}`).

- [ ] **Step 4: Run and lint**

```
npx vitest run src/pages/__tests__/ReactorGrid.test.tsx src/pages/__tests__/Dashboard.test.tsx
npx eslint src/pages/ReactorGrid.tsx src/pages/__tests__ --ext .ts,.tsx
npx tsc --noEmit
```
Expected: all pass; no new eslint problems; tsc baseline only.

- [ ] **Step 5: Commit**

```
[#122] Save reactor modifications as dated notes

- ReactorGrid: crMutation posts a 'modification' note with event_date;
  previous entry renders card.latest_modification; per-date query and
  pre-populate effect removed (decision 9, append-only)
- Tests added: yes (ReactorGrid.test.tsx +3)
- Docs updated: no

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 7: Remove the Reactor Modifications tab

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/index.tsx` (`:16` import, `:18` `TABS`, `:514` render branch)
- Delete: `frontend/src/pages/ExperimentDetail/ChangeRequestsTab.tsx`, `frontend/src/pages/ExperimentDetail/__tests__/ChangeRequestsTab.test.tsx`

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/pages/ExperimentDetail/__tests__/NotesTab.buttons.test.tsx`? No — the tab list lives in `index.tsx`. Find the existing ExperimentDetail page test that renders the tab strip (`grep -ln "Entry Logs" frontend/src/pages/ExperimentDetail/__tests__/*.tsx`); in that file add:
```ts
it('has no Reactor Modifications tab (issue #122 PR-B); Notes and Entry Logs remain', async () => {
  // reuse the file's existing render helper for the detail page
  expect(await screen.findByRole('button', { name: /^notes/i })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /entry logs/i })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /reactor modifications/i })).toBeNull()
})
```
If no existing test renders the page's tab strip, create `frontend/src/pages/ExperimentDetail/__tests__/Tabs.test.tsx` modelled on `DeleteExperiment.test.tsx`'s mocks and render, with only that test.

- [ ] **Step 2: Run to see it fail**, then **Step 3: implement** — in `index.tsx` delete the `ChangeRequestsTab` import, remove `'Reactor Modifications'` from `TABS`, delete the `{activeTab === 'Reactor Modifications' && ...}` line; `git rm` the two files.

- [ ] **Step 4: Run** `npx vitest run src/pages/ExperimentDetail` and `npx tsc --noEmit`; **Step 5: Commit**
```
[#122] Remove the Reactor Modifications tab

- ExperimentDetail: tab, render branch and ChangeRequestsTab deleted; the
  Notes tab already lists 'modification' notes
- Tests added: yes (tab strip assertion)
- Docs updated: no

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 8: `DeleteImpact` loses `change_requests` in every layer

**Files:**
- Modify: `backend/services/experiment_deletion.py` (dataclass `:108`, `total` `:125`, `collect_delete_impact` `:162-163`, `new_values["impact"]` `:373`; **keep** the purge at `:320-324` and the `ReactorChangeRequest` import it needs)
- Modify: `backend/api/schemas/experiments.py` (`DeleteImpactResponse`), `backend/api/routers/experiments.py::_impact_to_response`
- Modify: `frontend/src/api/experiments.ts` (`DeleteImpact` `:128`), `frontend/src/components/experiments/DeleteExperimentModal.tsx` (`IMPACT_ROWS` `:28`)
- Modify tests: `grep -rn "change_requests" tests/ frontend/src` — every fixture/assertion (known: `frontend/src/api/__tests__/experiments.deleteExperiment.test.ts:20`, `frontend/src/components/experiments/DeleteExperimentModal.test.tsx:19`, `frontend/src/pages/ExperimentDetail/__tests__/DeleteExperiment.test.tsx:43`, plus any in `tests/api/test_experiments.py` / `tests/services/test_experiment_deletion.py`)

- [ ] **Step 1**: add to `tests/services/test_experiment_deletion.py` a test that `DeleteImpact(...)` has no `change_requests` attribute and that `total` still equals the sum of the remaining nine counts:
```python
def test_delete_impact_has_no_change_requests_field():
    from backend.services.experiment_deletion import DeleteImpact
    impact = DeleteImpact(experiment_id="X", conditions=1, results=2, scalar_results=3, icp_results=4,
                          result_files=5, notes=6, additives=7, external_analyses=8, xrd_phases=9)
    assert not hasattr(impact, "change_requests")
    assert impact.total == 45
```
Run → fails (`TypeError`/`AssertionError`).
- [ ] **Step 2**: remove the field from all seven layers listed in MODELS.md's deletion section (dataclass, `total`, `collect_delete_impact`, `DeleteImpactResponse`, `_impact_to_response`, TS `DeleteImpact`, `IMPACT_ROWS`) and from `new_values["impact"]`; update every fixture the grep found. Leave the purge statement and its comment; add to that comment: `The count left DeleteImpact in #122 PR-B (the data now lives in experiment_notes and is counted under notes); the purge stays until PR-E removes the model.`
- [ ] **Step 3**: `.venv/Scripts/pytest.exe tests/services/test_experiment_deletion.py tests/api/test_experiments.py -q`; `npx vitest run src/components src/api src/pages/ExperimentDetail/__tests__/DeleteExperiment.test.tsx`; `npx tsc --noEmit`. `grep -rn "change_requests" backend/api frontend/src` must return only the deprecated client methods/types in `frontend/src/api/experiments.ts` (removed in PR-E) and nothing in `backend/api`.
- [ ] **Step 4**: Commit
```
[#122] Drop change_requests from the delete impact

- Removed from the dataclass, total, collector, response schema, router
  mapper, TS type and dialog rows; purge statement kept until PR-E
- Tests added: yes
- Docs updated: no (MODELS.md in Task 9)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 9: Deprecations, docs, decision record, full verification

**Files:**
- Modify: `backend/api/routers/experiments.py` (docstrings of `list_change_requests` `:961`, `get_recent_change_requests` `:981`, `upsert_change_request` `:1023`)
- Modify: `docs/api/API_REFERENCE.md` (`:25-29`), `.claude/rules/MODELS.md` (`ExperimentNotes` section; deletion-impact list `:80`; the purge bullet `:55` stays), `docs/POWERBI_MODEL.md` (`:22` `v_notes` columns; `:101-102` join notes), `docs/user_guide/DASHBOARD.md` (reactor card section), `docs/working/decisions.md` (new dated entry), `docs/working/issue-log.md`
- Nothing under `docs/project_context/` directly.

- [ ] **Step 1**: prefix each of the three route docstrings with `DEPRECATED (2026-09, issue #122 PR-B): removed by PR-E. Data migrated to experiment_notes by migrate_reactor_change_requests_021.py; new writes go through POST /experiments/{id}/notes with note_type='modification' and event_date.` `tests/api/test_change_requests.py` still passes (the routes work until PR-E).
- [ ] **Step 2**: `API_REFERENCE.md` — rows 25/26: `POST`/`PATCH` notes gain `event_date` (`"event_date": "2026-09-24"`; `modification` needs `result_id` OR `event_date`; `PATCH {"event_date": null}` clears it, 422 if that leaves a modification unanchored). Rows 27-29: append `**Deprecated 2026-09; removed by PR-E. Data migrated to `experiment_notes` by 021.**`. The dashboard response section (search `todays_modification`): now from notes; add `latest_modification`.
- [ ] **Step 3**: `MODELS.md` `ExperimentNotes`: add an `**event_date**` bullet (nullable DATE, indexed; the calendar anchor of a reactor modification; set by the dashboard form and the 021 backfill); update the `ck_note_scope` bullet to the new rule; note the 021 backfill and `SOURCE_TAG`. Deletion section: remove `change_requests` from the `DeleteImpact` list (line 80) and say the count left in PR-B while the purge stays until PR-E.
- [ ] **Step 4**: `POWERBI_MODEL.md`: add `event_date` to the `v_notes` column list and one sentence: dated reactor modifications are `note_type = 'modification' AND event_date IS NOT NULL`.
- [ ] **Step 5**: `DASHBOARD.md`: in the reactor-card section, describe the Reactor Modification box: each Save adds a dated Modification note to the experiment (visible on its Notes tab); the box shows today's note(s) and the most recent prior one; corrections are made in the Notes tab.
- [ ] **Step 6**: `decisions.md`: append a `2026-09-24` entry: "A reactor modification is a `modification` note anchored to a result OR an `event_date`; the Reactor Modifications tab is retired; this reverses the 2026-09-23 line 'the Reactor Modifications tab keeps its own name; they are different objects' — the tab's source was the Notion-era table, now migrated by 021 (decision 12)". Also record decisions 9 (append-only saves) and 10 (no dedicated endpoint).
- [ ] **Step 7**: Full verification — backend suite on a fresh `experiments_test` (record counts), `npx vitest run`, `npx eslint src --ext .ts,.tsx`, `npx tsc --noEmit`; `grep -rn "ReactorChangeRequest\|change_requests\|change-requests" backend/api/routers/dashboard.py frontend/src` must return only the deprecated client methods/types in `frontend/src/api/experiments.ts`.
- [ ] **Step 8**: issue-log entry (house format: Files changed, Root cause, Decisions, Verification counts, Tests added/Docs updated) and commit:
```
[#122] Deprecate change-request routes; document PR-B

- Docstrings + API_REFERENCE deprecation; MODELS.md event_date + CHECK +
  delete impact; POWERBI_MODEL v_notes.event_date; DASHBOARD.md; decisions
- Tests added: no
- Docs updated: yes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

## After the tasks (Conductor)

1. Chrome DevTools: dashboard card save → note appears on the experiment's Notes tab with the date and in `v_notes`; the card shows today's and the latest; the detail page has no Reactor Modifications tab; delete-experiment dialog lists no change requests. No row written to `reactor_change_requests` from any UI path (compare `count(*)` before/after).
2. Post-`--apply` counts on the mirror vs the dry-run report (attach both to the PR).
3. Whole-branch review on the most capable model; `gh pr create --base develop` with the dry-run report linked, pre-authorization 1 cited, the bulk-retype mirror flagged for post-#123, and the `🤖 Generated with [Claude Code](https://claude.com/claude-code)` footer.
