# Drop `reactor_change_requests` (issue #122, PR-E / E2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drop the Notion-era `reactor_change_requests` table and delete its `ReactorChangeRequest` model and every remaining importer, now that the production 021 backfill (2026-10-09: 357 rows, 331 converted, 26 orphaned) has moved its data into `experiment_notes` and Mat has signed off on the non-additive migration.

**Architecture:** One Alembic migration (`a7d3e9f1c2b4`, parent `e5b2d9c7a1f4`) drops the table; its `downgrade()` recreates the table **empty** in the final shape the three historical migrations left it in (no data restore). The model file, its package exports, its model test and the root-level dedupe script are deleted. The 021 backfill script is frozen into a stub that keeps its rules docstring and `SOURCE_TAG` and refuses to run with a clear message; its test is rewritten to pin that refusal. Three literal-grep stragglers are reworded so the §4 acceptance grep is mechanically clean. Docs record the production run and the drop.

**Tech Stack:** Alembic 1.x + SQLAlchemy 2 on PostgreSQL 18 (`experiments_test` for rehearsal, dev DB `experiments` for the real run); pytest; no frontend code changes.

**Spec:** `docs/working/issues/07-notes-overhaul-phase-2.md` §4 "PR-E" → "E2 — table drop" and "Acceptance (E2)"; §2 ("E2 authorized 2026-10-09" — the §7 sign-off); §3 decision 11. Gap calls below were approved by Mat in chat on 2026-10-09 ("proceed").

## Gap calls (approved 2026-10-09)

1. **Three literal-grep stragglers are reworded, not declared.** The §4 acceptance grep is literal (E1 precedent). `tests/api/test_notion_sync_removed.py` becomes `tests/api/test_notion_removed.py` with two functions renamed and the removed package's import path assembled from two string parts; `tests/api/test_dashboard.py:973` (an assertion that no SQL names the table — vacuous once the table cannot exist) is deleted and the docstring at `:1344` reworded; the comment at `database/models/experiments.py:138` is reworded (comment only, in a locked file — Mat's OK given 2026-10-09).
2. **The 021 script is frozen to a stub.** Module docstring (the rules record) and `SOURCE_TAG` stay; `Plan`, `build_plan`, `print_report`, `apply_plan`, `after_counts` are deleted; `main()` calls `check_source_table(db)` and exits 3 with a message naming the drop revision, the production counts, and `git show 32da995:database/data_migrations/migrate_reactor_change_requests_021.py` for the last runnable version. The test file is rewritten to two cases. Rejected alternative: keep the logic on a Core `Table` so it could re-run against a pre-E2 backup — that case never recurs, and every converted row's original is in its `modifications_log` snapshot.
3. **One new guard test** `tests/models/test_change_request_table_dropped.py` pins: the Alembic script directory has exactly one head and it is `a7d3e9f1c2b4` with `down_revision == "e5b2d9c7a1f4"`; the table that migration's `TABLE` constant names is absent from `Base.metadata.tables`; `database` and `database.models` export no `ReactorChangeRequest`. The table name is read from the migration module, so the test file itself contains no literal table name.
4. **Dev DB counts.** The dev DB `experiments` holds **333** rows / 307 notes / 307 snapshots (2026-09-04 mirror + 020 + 021), not 357 — 357/331/26 are production figures and are recorded as such. The dev DB is **not** refreshed; `alembic upgrade head` is run against it by the Conductor after the `experiments_test` rehearsal (Mat, 2026-10-09: "let `alembic upgrade head` drop its rows when the migration is applied there").

Settled by the spec and not re-asked: `9c358174ea54`, `ca5d57c6b272`, `13fc77a07865` are never deleted; `docs/superpowers/plans/` and `docs/issues/` keep their historical references; `docs/DIRECTORY_STRUCTURE.md` does not list the deleted root script (verified `grep -n dedup docs/DIRECTORY_STRUCTURE.md` → empty), so it is not edited.

## Global Constraints

- Branch `chore/drop-reactor-change-requests` off `develop` (created at `e456739`); PR base `develop` (`gh pr create --base develop`).
- Commit format `[#122] <imperative, under 50 chars>` + `- Tests added: yes/no` / `- Docs updated: yes/no` lines + `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Multi-line messages via `git commit -F <scratchpad file>` (PowerShell here-strings break on embedded quotes).
- **`alembic heads` must print exactly one head (`e5b2d9c7a1f4`) before the commit that adds the migration, and exactly `a7d3e9f1c2b4` after.** Never delete, rename or edit any existing file under `alembic/versions/`.
- `database/models/` is locked: the ONLY edits are deleting `notion_sync.py`, removing its import/export lines from `database/models/__init__.py` and `database/__init__.py`, and the one comment reword in `experiments.py:138` (gap call 1). No field, type or relationship changes anywhere.
- No file under `backend/services/bulk_uploads/` is touched. No new package. No frontend source change.
- Backend commands run from the repo root with `.venv/Scripts/pytest.exe`, `.venv/Scripts/alembic.exe`, `.venv/Scripts/python.exe`, `.venv/Scripts/flake8.exe`. **One pytest process at a time.** Root-level `tests/test_*.py` are never in the same invocation as `tests/api`, `tests/services` or `tests/models` (their `test_db` fixture drops all tables at teardown).
- **`experiments_test` must be reset after the model is deleted** (Task 2): `create_all`/`drop_all` only know tables in the metadata, so a `reactor_change_requests` left from an earlier run is invisible to them. Reset, as the `postgres` superuser (password `password`, from `tests/test_fresh_install_migration.py`), in ONE statement block:
  `& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -d experiments_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO experiments_user;"` with `$env:PGPASSWORD = "password"` set first (memory `experiments-test-reset-needs-schema-grant`: PG15+ grants no CREATE on a fresh `public`).
- Alembic reads `DATABASE_URL` from the environment (`alembic/env.py:21-23`), falling back to `.env` via `load_dotenv`. **Any Alembic command meant for `experiments_test` must set `DATABASE_URL=postgresql://experiments_user:password@localhost:5432/experiments_test` explicitly in that process's environment**, or it runs against the dev DB.
- `import database` with `DATABASE_URL` pointed at an empty DB logs view-creation errors (`database/event_listeners.py` module-level block). Harmless; do not "fix" it.
- Doc edits under `docs/` go through the Edit tool so the `project_context` sync hook fires. `.claude/rules/MODELS.md` is outside `docs/` and has no synced copy.
- The §4 acceptance grep is run literally: `grep -rn "ReactorChangeRequest\|reactor_change_requests\|notion_sync" backend/ database/ frontend/src tests/ alembic/env.py`. After Task 3 it must return hits **only** in `database/data_migrations/migrate_reactor_change_requests_021.py` (its docstring record and refusal message). Nothing else — not a comment, not a docstring, not a test string.
- Every claim in a DONE report must be backed by a command the implementer actually ran, with its output quoted. The Conductor re-runs `git status`, `git log --oneline develop..HEAD` and `git diff develop --stat` after every DONE report before dispatching a reviewer.

## Review Focus

1. **Upgrading a database that already lacks the table** (a dev/test DB built by `create_all` after E2 but stamped at `e5b2d9c7a1f4`) — `op.drop_table` raises `UndefinedTable`; this is accepted and deliberate (the spec says the drop cannot refuse, and the fresh-install path stamps `head` so never runs it). Pinned by Task 1's rehearsal step, which documents the error text so the PR body can say what an operator would see.
2. **Downgrading and then inserting a row whose `experiment_id` names a deleted experiment** — the recreated FK must unlink it (`ON DELETE SET NULL`), exactly as `9c358174ea54` did. Pinned in Task 1's rehearsal script (FK `ondelete` asserted from the inspector).
3. **Downgrading and inserting two rows with the same `(reactor_label, experiment_id, sync_date)`** — must fail on `uq_change_request_reactor_experiment_date`, not on the older `uq_change_request_reactor_date`. Pinned in Task 1's rehearsal script (constraint name asserted).
4. **Running the frozen 021 script by hand on the lab PC** (the runbook in the 021 report still lists it) — must exit 3 with a message that names the drop revision and the `git show` path, never a traceback about a missing table. Pinned in Task 2's `test_refuses_when_the_source_table_is_gone`.
5. **Deleting an experiment after the drop** — `delete_experiment_cascade` must still work with no statement against the vanished table. Pinned by the existing `tests/services/test_experiment_deletion.py` suite, which Task 2 runs after removing the seed row.

---

### Task 1: The drop migration, its chain guard, and the `experiments_test` rehearsal

**Files:**
- Create: `alembic/versions/a7d3e9f1c2b4_drop_reactor_change_requests.py`
- Create: `tests/models/test_change_request_table_dropped.py` (chain assertions only; Task 2 adds two more)
- Create (scratchpad, not committed): `<scratchpad>/rehearse_e2.py`

**Interfaces:**
- Consumes: nothing from other tasks. The model `ReactorChangeRequest` still exists during this task; that is expected.
- Produces: revision id `a7d3e9f1c2b4` with module-level constant `TABLE = "reactor_change_requests"` (Task 2's guard test reads `rev.module.TABLE`; Task 2's stub cites `DROP_REVISION = "a7d3e9f1c2b4"`).

- [ ] **Step 1: Confirm one head before adding the migration**

Run: `.venv/Scripts/alembic.exe heads`
Expected: exactly one line, `e5b2d9c7a1f4 (head)`. If more than one line, STOP and report.

- [ ] **Step 2: Write the failing chain-guard tests**

Create `tests/models/test_change_request_table_dropped.py`:

```python
"""Issue #122 PR-E (E2): the Notion-era reactor change-request table and its
model are gone. Alembic a7d3e9f1c2b4 drops the table; these tests pin the
migration chain and the ORM side so neither quietly comes back.

The table name is read from the migration module's TABLE constant on purpose:
the §4 acceptance grep for the dropped table is literal and must find nothing
under tests/.
"""
from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
DROP_REVISION = "a7d3e9f1c2b4"
PARENT_REVISION = "e5b2d9c7a1f4"


def _script_dir() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(REPO_ROOT / "alembic.ini")))


def test_drop_migration_is_the_single_head():
    assert _script_dir().get_heads() == [DROP_REVISION]


def test_drop_migration_revises_the_event_date_migration():
    rev = _script_dir().get_revision(DROP_REVISION)
    assert rev.down_revision == PARENT_REVISION
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest.exe tests/models/test_change_request_table_dropped.py -v`
Expected: both FAIL — `get_heads()` returns `['e5b2d9c7a1f4']`, and `get_revision('a7d3e9f1c2b4')` raises `alembic.script.revision.ResolutionError` ("No such revision").

- [ ] **Step 4: Write the migration**

Create `alembic/versions/a7d3e9f1c2b4_drop_reactor_change_requests.py`:

```python
"""Drop reactor_change_requests (issue #122, PR-E E2).

The Notion-era reactor change-request table leaves the schema. Its rows were
converted to dated 'modification' notes by
database/data_migrations/migrate_reactor_change_requests_021.py -- production
run 2026-10-09: 357 rows, 331 converted, 26 orphaned (rows whose experiment_id
was already NULL); one ModificationsLog snapshot per converted row holds the
full original row. The code that read and wrote the table left in PR-E E1
(#127). Mat authorized this drop on 2026-10-09 (phase-2 spec §2 -- the §7
sign-off for a non-additive migration).

History of the table, kept here as the shape downgrade() recreates:
  9c358174ea54  create_table; FK experiment_id -> experiments.experiment_id
                ON DELETE SET NULL; unique uq_change_request_reactor_date
  13fc77a07865  notion_status and notion_page_id become nullable
  ca5d57c6b272  unique becomes uq_change_request_reactor_experiment_date
                on (reactor_label, experiment_id, sync_date)
None of the three is deleted.

downgrade() recreates the table EMPTY in that final shape. It restores no data:
the 26 unconverted rows exist only in a pre-drop backup; the 331 converted ones
are experiment_notes rows (created_by = 'migrate_change_requests_021') with
their originals in modifications_log.old_values.

Upgrade on a database that never had the table (one built by
Base.metadata.create_all after this revision, then stamped behind it) fails
with UndefinedTable. That is deliberate: the fresh-install path stamps head and
never runs this, and a DROP that silently no-ops would hide a stamp mistake.

Revision ID: a7d3e9f1c2b4
Revises: e5b2d9c7a1f4
Create Date: 2026-10-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7d3e9f1c2b4"
down_revision: Union[str, None] = "e5b2d9c7a1f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "reactor_change_requests"


def upgrade() -> None:
    op.drop_table(TABLE)


def downgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reactor_label", sa.String(length=10), nullable=False),
        sa.Column("experiment_id", sa.String(), nullable=True),
        sa.Column("requested_change", sa.String(), nullable=False),
        sa.Column("notion_status", sa.String(length=50), nullable=True),
        sa.Column("carried_forward", sa.Boolean(), nullable=False),
        sa.Column("sync_date", sa.Date(), nullable=False),
        sa.Column("notion_page_id", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["experiments.experiment_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "reactor_label", "experiment_id", "sync_date",
            name="uq_change_request_reactor_experiment_date",
        ),
    )
```

- [ ] **Step 5: Run the tests to verify they pass, and confirm one head**

Run: `.venv/Scripts/pytest.exe tests/models/test_change_request_table_dropped.py -v`
Expected: 2 passed.

Run: `.venv/Scripts/alembic.exe heads`
Expected: exactly `a7d3e9f1c2b4 (head)`.

- [ ] **Step 6: Write the rehearsal script (scratchpad, never committed)**

Create `<scratchpad>/rehearse_e2.py`. It builds the pre-E2 schema in `experiments_test` (ORM `create_all` already creates the table while the model still exists in this task — but it must be built from the HISTORICAL DDL so the rehearsal is faithful to a lab-PC-shaped table rather than to the model), seeds two rows, then runs stamp → upgrade → downgrade → upgrade and asserts after each step. Cleanup leaves the DB empty.

```python
"""Rehearse a7d3e9f1c2b4 on experiments_test (issue #122 PR-E E2).

Run from the repo root:
  $env:PYTHONPATH = "."; .venv/Scripts/python.exe <scratchpad>/rehearse_e2.py
Pre-state is built by hand from the three historical migrations' final shape,
NOT from the ORM model, so the rehearsal matches a lab PC built through Alembic.
Leaves experiments_test empty (no tables, no alembic_version, no views).
"""
import os
import subprocess
import sys

TEST_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"
os.environ["DATABASE_URL"] = TEST_URL  # before `import database`, before alembic

from sqlalchemy import create_engine, inspect, text  # noqa: E402

from database import Base  # noqa: E402  (logs view errors against the empty DB; harmless)
from database.event_listeners import _VIEWS  # noqa: E402

ALEMBIC = os.path.join(".venv", "Scripts", "alembic.exe")
TABLE = "reactor_change_requests"
PARENT = "e5b2d9c7a1f4"
HEAD = "a7d3e9f1c2b4"

PRE_E2_DDL = f"""
CREATE TABLE {TABLE} (
    id SERIAL NOT NULL,
    reactor_label VARCHAR(10) NOT NULL,
    experiment_id VARCHAR,
    requested_change VARCHAR NOT NULL,
    notion_status VARCHAR(50),
    carried_forward BOOLEAN NOT NULL,
    sync_date DATE NOT NULL,
    notion_page_id VARCHAR(32),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (experiment_id) REFERENCES experiments (experiment_id) ON DELETE SET NULL,
    CONSTRAINT uq_change_request_reactor_experiment_date UNIQUE (reactor_label, experiment_id, sync_date)
)
"""


def alembic(*args: str) -> subprocess.CompletedProcess:
    print(f"$ alembic {' '.join(args)}")
    cp = subprocess.run([ALEMBIC, *args], capture_output=True, text=True, env=os.environ)
    print(cp.stdout.strip())
    if cp.returncode != 0:
        print(cp.stderr.strip())
        raise SystemExit(f"alembic {' '.join(args)} failed ({cp.returncode})")
    return cp


def table_shape(engine) -> dict:
    insp = inspect(engine)
    cols = {c["name"]: c["nullable"] for c in insp.get_columns(TABLE)}
    fks = [(fk["referred_table"], fk["referred_columns"], fk["options"].get("ondelete"))
           for fk in insp.get_foreign_keys(TABLE)]
    uqs = {u["name"]: u["column_names"] for u in insp.get_unique_constraints(TABLE)}
    return {"cols": cols, "fks": fks, "uqs": uqs}


EXPECTED_COLS = {
    "id": False, "reactor_label": False, "experiment_id": True, "requested_change": False,
    "notion_status": True, "carried_forward": False, "sync_date": False,
    "notion_page_id": True, "created_at": False,
}


def main() -> None:
    engine = create_engine(TEST_URL)
    insp = inspect(engine)
    if insp.get_table_names():
        raise SystemExit("experiments_test is not empty -- reset it first (see plan Global Constraints)")

    # 1. Pre-E2 schema: every current table from the ORM, then the dropped table by hand.
    #    The ORM still has the model during Task 1, so create_all would create it too --
    #    create everything EXCEPT it, then run the historical DDL.
    tables = [t for t in Base.metadata.sorted_tables if t.name != TABLE]
    Base.metadata.create_all(engine, tables=tables)
    with engine.begin() as c:
        c.execute(text(PRE_E2_DDL))
        c.execute(text("INSERT INTO experiments (experiment_id, experiment_number, status) "
                       "VALUES ('E2_REH_001', 990001, 'ONGOING')"))
        c.execute(text(f"INSERT INTO {TABLE} (reactor_label, experiment_id, requested_change, carried_forward, sync_date) "
                       f"VALUES ('R01', 'E2_REH_001', 'rehearsal row', false, '2026-10-01'), "
                       f"('R02', NULL, 'orphan row', false, '2026-10-02')"))
        n = c.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar()
    print(f"pre-state: {TABLE} has {n} rows; shape {table_shape(engine)}")
    assert table_shape(engine)["cols"] == EXPECTED_COLS

    # 2. stamp parent -> upgrade head: table gone
    alembic("stamp", PARENT)
    alembic("upgrade", "head")
    assert not inspect(engine).has_table(TABLE), "upgrade did not drop the table"
    print("after upgrade: table absent  OK")

    # 3. downgrade -1: table back, EMPTY, final historical shape
    alembic("downgrade", "-1")
    assert inspect(engine).has_table(TABLE), "downgrade did not recreate the table"
    shape = table_shape(engine)
    print(f"after downgrade: shape {shape}")
    assert shape["cols"] == EXPECTED_COLS, shape["cols"]
    assert shape["fks"] == [("experiments", ["experiment_id"], "SET NULL")], shape["fks"]
    assert shape["uqs"] == {"uq_change_request_reactor_experiment_date": ["reactor_label", "experiment_id", "sync_date"]}, shape["uqs"]
    with engine.begin() as c:
        assert c.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar() == 0, "downgrade must recreate EMPTY"
        # Review Focus 2: FK unlinks on experiment delete
        c.execute(text(f"INSERT INTO {TABLE} (reactor_label, experiment_id, requested_change, carried_forward, sync_date) "
                       f"VALUES ('R03', 'E2_REH_001', 'fk check', false, '2026-10-03')"))
        c.execute(text("DELETE FROM experiments WHERE experiment_id = 'E2_REH_001'"))
        assert c.execute(text(f"SELECT experiment_id FROM {TABLE} WHERE reactor_label = 'R03'")).scalar() is None
        # Review Focus 3: the NEW unique name fires on a duplicate key
        c.execute(text(f"INSERT INTO {TABLE} (reactor_label, experiment_id, requested_change, carried_forward, sync_date) "
                       f"VALUES ('R04', NULL, 'dup a', false, '2026-10-04')"))
    try:
        with engine.begin() as c:
            c.execute(text(f"INSERT INTO {TABLE} (reactor_label, experiment_id, requested_change, carried_forward, sync_date) "
                           f"VALUES ('R04', NULL, 'dup b', false, '2026-10-04')"))
        dup_error = "NO ERROR -- NULL experiment_id rows are distinct under a UNIQUE constraint (Postgres default); same as 9c358174ea54+ca5d57c6b272"
    except Exception as exc:  # noqa: BLE001
        dup_error = str(exc).splitlines()[0]
    print(f"duplicate (R04, NULL, 2026-10-04): {dup_error}")
    try:
        with engine.begin() as c:
            c.execute(text("INSERT INTO experiments (experiment_id, experiment_number, status) VALUES ('E2_REH_002', 990002, 'ONGOING')"))
            c.execute(text(f"INSERT INTO {TABLE} (reactor_label, experiment_id, requested_change, carried_forward, sync_date) "
                           f"VALUES ('R05', 'E2_REH_002', 'dup c', false, '2026-10-05')"))
            c.execute(text(f"INSERT INTO {TABLE} (reactor_label, experiment_id, requested_change, carried_forward, sync_date) "
                           f"VALUES ('R05', 'E2_REH_002', 'dup d', false, '2026-10-05')"))
        raise SystemExit("duplicate non-NULL key was accepted -- unique constraint missing")
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        first = str(exc).splitlines()[0]
        assert "uq_change_request_reactor_experiment_date" in first, first
        print(f"duplicate (R05, E2_REH_002, 2026-10-05): rejected by uq_change_request_reactor_experiment_date  OK")

    # 4. upgrade head again (idempotent chain)
    alembic("upgrade", "head")
    assert not inspect(engine).has_table(TABLE)
    heads = alembic("heads").stdout.strip()
    assert heads.startswith(HEAD), heads
    print(f"after second upgrade: table absent; heads = {heads}  OK")

    # 5. cleanup -> empty DB
    with engine.begin() as c:
        for view_name, _ in _VIEWS:
            c.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
        c.execute(text("DROP VIEW IF EXISTS v_primary_experiment_results CASCADE"))
        c.execute(text("DROP TABLE IF EXISTS alembic_version"))
    Base.metadata.drop_all(engine)
    with engine.begin() as c:
        c.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
    left = inspect(engine).get_table_names()
    assert left == [], left
    print("cleanup: experiments_test empty  OK")
    print("REHEARSAL PASSED")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Reset `experiments_test` and run the rehearsal**

Run (PowerShell):
```powershell
$env:PGPASSWORD = "password"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -d experiments_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO experiments_user;"
$env:PYTHONPATH = "."
.venv/Scripts/python.exe <scratchpad>/rehearse_e2.py
```
Expected: ends with `REHEARSAL PASSED`; the printed `after downgrade` shape shows the nine columns with `notion_status`/`notion_page_id`/`experiment_id` nullable, one FK `('experiments', ['experiment_id'], 'SET NULL')`, and the one unique constraint. Quote the full stdout in the DONE report — the Conductor pastes it into the PR body.

Then run the Review Focus 1 check — upgrade on a DB that never had the table:
```powershell
$env:DATABASE_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"
.venv/Scripts/python.exe -c "import os; from sqlalchemy import create_engine; from database import Base; e=create_engine(os.environ['DATABASE_URL']); Base.metadata.create_all(e, tables=[t for t in Base.metadata.sorted_tables if t.name != 'reactor_change_requests'])"
.venv/Scripts/alembic.exe stamp e5b2d9c7a1f4
.venv/Scripts/alembic.exe upgrade head
```
Expected: `upgrade head` FAILS with `psycopg2.errors.UndefinedTable: table "reactor_change_requests" does not exist`. Quote the first line of the error. Then clean up exactly as the script's step 5 does (run the reset block from the top of this step again — simplest). Confirm with:
`.venv/Scripts/python.exe -c "from sqlalchemy import create_engine, inspect; print(inspect(create_engine('postgresql://experiments_user:password@localhost:5432/experiments_test')).get_table_names())"` → `[]`.
Unset `DATABASE_URL` in the shell afterwards (`Remove-Item Env:DATABASE_URL`) so later commands use `.env`.

- [ ] **Step 8: Commit**

```powershell
git add alembic/versions/a7d3e9f1c2b4_drop_reactor_change_requests.py tests/models/test_change_request_table_dropped.py
git commit -F <scratchpad>/commit1.txt
```
with `commit1.txt`:
```
[#122] Add migration dropping reactor_change_requests

- a7d3e9f1c2b4 (parent e5b2d9c7a1f4): DROP TABLE; downgrade recreates it
  empty in the final shape of 9c358174ea54 + 13fc77a07865 + ca5d57c6b272
- Rehearsed upgrade/downgrade/upgrade on experiments_test
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 2: Delete the model and every importer; freeze the 021 script

**Files:**
- Delete: `database/models/notion_sync.py`
- Delete: `tests/models/test_notion_sync_model.py`
- Delete: `migrate_deduplicate_change_requests.py` (repo root)
- Modify: `database/models/__init__.py:11` (import), `:35-36` (comment + export)
- Modify: `database/__init__.py:20-21` (comment + import), `:52-53` (comment + export)
- Modify: `tests/services/test_experiment_deletion.py:2` (`date` import — becomes unused), `:17` (model import), `:82-83` (seed row), `:319-352` (the whole `test_delete_no_longer_touches_reactor_change_requests`)
- Rewrite: `database/data_migrations/migrate_reactor_change_requests_021.py`
- Rewrite: `tests/data_migrations/test_migrate_change_requests_021.py`
- Modify: `tests/models/test_change_request_table_dropped.py` (append two tests)

**Interfaces:**
- Consumes: `a7d3e9f1c2b4` and its `TABLE` constant (Task 1).
- Produces: `migrate_reactor_change_requests_021.SOURCE_TAG == "migrate_change_requests_021"`, `DROP_REVISION == "a7d3e9f1c2b4"`, `LAST_RUNNABLE_COMMIT == "32da995"`, `check_source_table(db: Session) -> None` (raises `RuntimeError`).

- [ ] **Step 1: Append the failing ORM-side guard tests**

Append to `tests/models/test_change_request_table_dropped.py`:

```python


def test_metadata_has_no_table_for_the_dropped_migration():
    import database  # noqa: F401  (registers every model on Base)
    from database import Base

    dropped = _script_dir().get_revision(DROP_REVISION).module.TABLE
    assert dropped not in Base.metadata.tables


def test_package_exports_no_change_request_model():
    import database
    import database.models

    assert not hasattr(database, "ReactorChangeRequest")
    assert "ReactorChangeRequest" not in database.__all__
    assert "ReactorChangeRequest" not in database.models.__all__
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/pytest.exe tests/models/test_change_request_table_dropped.py -v`
Expected: 2 passed (Task 1), 2 FAILED — `'reactor_change_requests' in Base.metadata.tables` and `hasattr(database, 'ReactorChangeRequest')` is True.

- [ ] **Step 3: Delete the model, its test, the root script, and the exports**

```powershell
git rm database/models/notion_sync.py tests/models/test_notion_sync_model.py migrate_deduplicate_change_requests.py
```

Edit `database/models/__init__.py`: delete line 11 (`from .notion_sync import ReactorChangeRequest`) and lines 35-36 (`    # Notion sync` and `    'ReactorChangeRequest',`).

Edit `database/__init__.py`: delete lines 20-21 (`# Notion sync models` and `from .models import ReactorChangeRequest`) and lines 52-53 (`    # Notion sync` and `    'ReactorChangeRequest',`).

Also remove any `database/models/__pycache__/notion_sync.*.pyc` (`Remove-Item database/models/__pycache__/notion_sync*` — untracked, harmless, but a stale `.pyc` can mask an import error).

- [ ] **Step 4: Run the guard tests, then the whole package import**

Run: `.venv/Scripts/pytest.exe tests/models/test_change_request_table_dropped.py -v`
Expected: 4 passed.

Run: `.venv/Scripts/python.exe -c "import database; import backend.api.main; print('ok')"`
Expected: `ok` (view-creation log lines may precede it).

- [ ] **Step 5: Remove the seed row and the E1 test from the deletion suite**

In `tests/services/test_experiment_deletion.py`:
- line 2: delete `from datetime import date` (its only two uses are the seed row and the E1 test — confirm with `grep -n "date(" tests/services/test_experiment_deletion.py` before and after: after, zero hits).
- line 17: delete `from database.models.notion_sync import ReactorChangeRequest`.
- lines 82-83: delete
  ```python
      db.add(ReactorChangeRequest(reactor_label="R01", experiment_id=experiment_id,
                                  requested_change="swap", sync_date=date(2026, 7, 28)))
  ```
- lines 319-352: delete the entire function `test_delete_no_longer_touches_reactor_change_requests` (from its `def` line through the final `assert row.experiment_id is None`, plus the two blank lines after it so `test_delete_purges_elemental_analysis_children` keeps two blank lines above it).

Verify: `grep -n "ReactorChangeRequest\|before_cursor_execute\|notion" tests/services/test_experiment_deletion.py` → empty.

- [ ] **Step 6: Reset `experiments_test` (model gone → stale table would be invisible to `drop_all`)**

```powershell
$env:PGPASSWORD = "password"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -d experiments_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO experiments_user;"
```

Run: `.venv/Scripts/pytest.exe tests/services/test_experiment_deletion.py -q`
Expected: all pass (the file had 1 test fewer than before; quote the count).

- [ ] **Step 7: Write the failing tests for the frozen 021 script**

Replace the entire contents of `tests/data_migrations/test_migrate_change_requests_021.py` with:

```python
"""The 021 backfill is frozen (issue #122 PR-E E2). Its source table was
dropped by Alembic a7d3e9f1c2b4 after the production run of 2026-10-09
(357 rows, 331 converted, 26 orphaned). The script stays as the record of where
the 'migrate_change_requests_021' notes came from and must REFUSE to run with
a message that says so -- never crash on a missing table."""
from __future__ import annotations

import pytest

from database.data_migrations.migrate_reactor_change_requests_021 import (
    DROP_REVISION,
    LAST_RUNNABLE_COMMIT,
    SOURCE_TAG,
    check_source_table,
)

MIGRATION_PATH = "database/data_migrations/migrate_reactor_change_requests_021.py"


def test_source_tag_is_pinned():
    # .claude/rules/MODELS.md, v_notes.created_by on 331 production rows and the
    # review-queue filter all cite this exact value; it must never drift.
    assert SOURCE_TAG == "migrate_change_requests_021"


def test_drop_revision_matches_the_alembic_chain():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    heads = ScriptDirectory.from_config(Config(str(repo_root / "alembic.ini"))).get_heads()
    assert heads == [DROP_REVISION]


def test_refuses_when_the_source_table_is_gone(migration_session):
    # experiments_test is built by create_all from the post-E2 metadata, so the
    # source table does not exist here -- exactly the lab PC's state after the
    # nightly `alembic upgrade head`.
    with pytest.raises(RuntimeError) as excinfo:
        check_source_table(migration_session)
    msg = str(excinfo.value)
    assert DROP_REVISION in msg
    assert "2026-10-09" in msg
    assert "331" in msg and "26" in msg
    assert f"git show {LAST_RUNNABLE_COMMIT}:{MIGRATION_PATH}" in msg
```

- [ ] **Step 8: Run them to verify they fail**

Run: `.venv/Scripts/pytest.exe tests/data_migrations/test_migrate_change_requests_021.py -v`
Expected: collection error — `ImportError: cannot import name 'DROP_REVISION'` (the current script still imports the deleted model and would fail even earlier with `ModuleNotFoundError: No module named 'database.models.notion_sync'`).

- [ ] **Step 9: Freeze the script**

Replace the entire contents of `database/data_migrations/migrate_reactor_change_requests_021.py` with the following. The "Rules" and "Background" paragraphs are the original docstring kept **verbatim** (they are the record of how the 331 notes were derived); only the banner at the top, the "Usage" section and the code change.

```python
"""FROZEN (issue #122 PR-E E2, 2026-10-09). The source table was dropped by
Alembic a7d3e9f1c2b4 after this script's production run on 2026-10-09: 357
rows, 331 converted, 26 orphaned. The conversion logic was removed with the
model it depended on; the last runnable version is
    git show 32da995:database/data_migrations/migrate_reactor_change_requests_021.py
and only makes sense against a database restored from a backup taken before
a7d3e9f1c2b4. Running this file now exits 3 with that message. Everything
below the banner is kept as the record of where the
created_by = 'migrate_change_requests_021' notes came from.

One-time backfill: convert reactor_change_requests rows into dated
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
5. Idempotent. A row is ALREADY CONVERTED when its ModificationsLog snapshot
   exists (modified_table='reactor_change_requests', old_values.id = the row
   id) -- this survives later edits or deletion of the note -- or, failing
   that, when a note with the same experiment_fk, event_date, note_text and
   created_by=SOURCE_TAG exists. Two source rows sharing (experiment, date,
   text) -- possible only under two different reactor_labels, because of the
   table's unique key -- COLLAPSE into one note; the second is reported as
   collapsed, never doubled or dropped silently.
6. Informational: how many convertible rows carry a reactor_label that differs
   from the experiment's current experimental_conditions.reactor_slot. A
   difference is expected when an experiment moved reactors; it is reported so
   Mat can judge whether the label must be kept (decision 2's open question).

Usage (historical)
------------------
    PYTHONPATH=. python database/data_migrations/migrate_reactor_change_requests_021.py          # dry run
    PYTHONPATH=. python database/data_migrations/migrate_reactor_change_requests_021.py --apply  # after Mat's audit

Reports: docs/issues/migrate-change-requests-021-dryrun-2026-09-24.md (dev-mirror
dry run and apply, and the production run of 2026-10-09).
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import inspect
from sqlalchemy.orm import Session

SOURCE_TAG = "migrate_change_requests_021"
SOURCE_TABLE = "reactor_change_requests"
DROP_REVISION = "a7d3e9f1c2b4"
LAST_RUNNABLE_COMMIT = "32da995"
MIGRATION_PATH = "database/data_migrations/migrate_reactor_change_requests_021.py"

_FROZEN = (
    f"migrate_reactor_change_requests_021 is frozen: its source table "
    f"{SOURCE_TABLE} was dropped by Alembic {DROP_REVISION} (issue #122 PR-E E2) "
    f"after the production run of 2026-10-09 (357 rows, 331 converted, 26 orphaned). "
    f"The {SOURCE_TAG} notes and their modifications_log snapshots are the record. "
    f"The last runnable version is `git show {LAST_RUNNABLE_COMMIT}:{MIGRATION_PATH}` "
    f"and applies only to a database restored from a backup taken before {DROP_REVISION}."
)


def check_source_table(db: Session) -> None:
    """Raise RuntimeError with the frozen-script message.

    Raised whether or not the table exists: when it is gone (every database
    at or past DROP_REVISION) the message says why; when it is still present
    (a pre-E2 restore) the conversion logic is no longer in this file, so the
    message points at the commit that holds it.
    """
    present = inspect(db.get_bind()).has_table(SOURCE_TABLE)
    state = "still present here (a pre-E2 restore?)" if present else "absent here"
    raise RuntimeError(f"{_FROZEN} {SOURCE_TABLE} is {state}.")


def main(apply: bool) -> None:  # `apply` is unused: kept so the historical CLI shape still parses
    from database import get_db

    db = next(get_db())
    try:
        check_source_table(db)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(3)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="(historical) commit changes")
    args = parser.parse_args()
    main(apply=args.apply)
```

- [ ] **Step 10: Run the tests to verify they pass, and the CLI refuses**

Run: `.venv/Scripts/pytest.exe tests/data_migrations/test_migrate_change_requests_021.py -v`
Expected: 3 passed.

Run (against the dev DB, which still has the table until the Conductor upgrades it — so this exercises the "still present" branch):
`$env:PYTHONPATH = "."; .venv/Scripts/python.exe database/data_migrations/migrate_reactor_change_requests_021.py; echo "exit $LASTEXITCODE"`
Expected: one `Error: migrate_reactor_change_requests_021 is frozen: ...` line on stderr ending `reactor_change_requests is still present here (a pre-E2 restore?).`, then `exit 3`. Quote it.

Run: `.venv/Scripts/flake8.exe database/data_migrations/migrate_reactor_change_requests_021.py tests/data_migrations/test_migrate_change_requests_021.py tests/models/test_change_request_table_dropped.py tests/services/test_experiment_deletion.py database/__init__.py database/models/__init__.py`
Expected: no output.

- [ ] **Step 11: Run the model, services and data-migration suites together**

Run: `.venv/Scripts/pytest.exe tests/models tests/services tests/data_migrations -q`
Expected: 0 failed. Quote the `N passed` line.

- [ ] **Step 12: Commit**

```powershell
git add -A database/__init__.py database/models/__init__.py database/data_migrations/migrate_reactor_change_requests_021.py tests/data_migrations/test_migrate_change_requests_021.py tests/models/test_change_request_table_dropped.py tests/services/test_experiment_deletion.py
git commit -F <scratchpad>/commit2.txt
```
(the three `git rm` deletions from Step 3 are already staged.) With `commit2.txt`:
```
[#122] Delete ReactorChangeRequest and freeze 021

- Model, exports, model test, root dedupe script removed
- 021 backfill keeps its rules docstring, refuses with exit 3
- Deletion suite loses its change-request seed and E1 test
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 3: Clear the literal acceptance grep

**Files:**
- Rename: `tests/api/test_notion_sync_removed.py` → `tests/api/test_notion_removed.py` (`git mv`), then edit
- Modify: `tests/api/test_dashboard.py:973` (delete the line), `:1343-1344` (docstring)
- Modify: `database/models/experiments.py:136-139` (comment only)

**Interfaces:**
- Consumes: nothing. Produces: nothing. Pure rewording so the §4 grep is clean.

- [ ] **Step 1: Record the grep's current hits**

Run: `grep -rn "ReactorChangeRequest\|reactor_change_requests\|notion_sync" backend/ database/ frontend/src tests/ alembic/env.py`
Expected after Task 2: hits in `database/data_migrations/migrate_reactor_change_requests_021.py` (allowed), plus exactly these stragglers: `database/models/experiments.py:138`, `tests/api/test_dashboard.py:973`, `tests/api/test_dashboard.py:1344`, and several in `tests/api/test_notion_sync_removed.py`. If anything else appears, STOP and report it.

- [ ] **Step 2: Rename and reword E1's removal test**

```powershell
git mv tests/api/test_notion_sync_removed.py tests/api/test_notion_removed.py
```

Then edit `tests/api/test_notion_removed.py`:
- Rename `test_notion_sync_routes_are_unregistered` → `test_notion_routes_are_unregistered`.
- Rename `test_notion_sync_package_is_gone` → `test_notion_package_is_gone` and replace its body with:
  ```python
  def test_notion_package_is_gone():
      # A leftover backend/services/<package>/__pycache__/ directory would still
      # resolve as a namespace package, so this only passes once the directory is
      # removed entirely, not just its .py files. The name is assembled from two
      # parts because the E2 acceptance grep for the removed integration is literal.
      removed_package = "backend.services.notion" + "_sync"
      assert importlib.util.find_spec(removed_package) is None
  ```
- Leave `test_settings_have_no_notion_fields`, `test_settings_ignore_stale_notion_env_keys` and `test_change_request_routes_are_unregistered` unchanged (none contains a grep term).

Run: `.venv/Scripts/pytest.exe tests/api/test_notion_removed.py -v` → 5 passed.

- [ ] **Step 3: Drop the vacuous dashboard assertion and reword its docstring**

In `tests/api/test_dashboard.py`:
- Delete line 973: `    assert not any("reactor_change_requests" in s for s in statements)`. The two assertions above it (`cards[...]` and the `notes_queries` count) are the test's real content and stay.
- In the docstring of `test_dashboard_query_count_not_increased` (lines 1341-1344), replace `Extends the existing before_cursor_execute counter pattern used for\n    the reactor_change_requests batching test.` with `Extends the existing before_cursor_execute counter pattern used for\n    the modification-notes batching test.`

Run: `.venv/Scripts/pytest.exe tests/api/test_dashboard.py -q -k "batch or query_count"` → all pass (quote the count).

- [ ] **Step 4: Reword the model comment (comment only)**

In `database/models/experiments.py:136-139`, replace
```python
    # Issue #122 PR-B: a calendar-date anchor for a 'modification' note that is
    # not tied to a result row (the dashboard's reactor-modification form, and the
    # 021 backfill of reactor_change_requests). Either anchor satisfies
    # ck_note_scope for 'modification'; 'result_note' still requires a result.
```
with
```python
    # Issue #122 PR-B: a calendar-date anchor for a 'modification' note that is
    # not tied to a result row (the dashboard's reactor-modification form, and the
    # 021 backfill of the retired reactor change-request table). Either anchor
    # satisfies ck_note_scope for 'modification'; 'result_note' still requires a result.
```
Verify it is comment-only: `git diff database/models/experiments.py` shows exactly four `-` and four `+` lines, all starting with `#` after indentation.

- [ ] **Step 5: Run the acceptance grep**

Run: `grep -rn "ReactorChangeRequest\|reactor_change_requests\|notion_sync" backend/ database/ frontend/src tests/ alembic/env.py | grep -v "^database/data_migrations/migrate_reactor_change_requests_021.py:"`
Expected: **empty**.

Run: `grep -rn "ReactorChangeRequest\|reactor_change_requests\|notion_sync" backend/ database/ frontend/src tests/ alembic/env.py | grep -c "^database/data_migrations/migrate_reactor_change_requests_021.py:"`
Expected: a positive count (the docstring record + the message). Quote both results.

- [ ] **Step 6: Run the API suite and commit**

Run: `.venv/Scripts/pytest.exe tests/api -q`
Expected: 0 failed. Quote the `N passed` line.

```powershell
git add tests/api/test_notion_removed.py tests/api/test_dashboard.py database/models/experiments.py
git commit -F <scratchpad>/commit3.txt
```
(the rename is already staged by `git mv`.) With `commit3.txt`:
```
[#122] Clear the E2 acceptance grep of stragglers

- E1 removal test renamed; package path split for the literal grep
- Vacuous dashboard table assertion removed; two comments reworded
- Tests added: no
- Docs updated: no

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 4: Docs — the drop, the production run, the spec row

**Files:**
- Modify: `.claude/rules/MODELS.md:55-65`, `:84-94`, `:216`
- Modify: `docs/api/API_REFERENCE.md:318-322`, `:643`
- Modify: `docs/POWERBI_MODEL.md:170-173`
- Modify: `docs/issues/migrate-change-requests-021-dryrun-2026-09-24.md` (append a section before "## Questions for Mat")
- Modify: `docs/working/issues/07-notes-overhaul-phase-2.md:38` (§1 PR-E row)

**Interfaces:** none. Use the Edit tool for every file under `docs/` so the `project_context` hook fires. `.claude/rules/MODELS.md` has no synced copy.

- [ ] **Step 1: MODELS.md — deletion path bullet (lines 55-65)**

Replace the bullet that begins `- \`reactor_change_requests\` rows for this experiment were **PURGED** by this` (through `confirmed.`) with:

```
    - The Notion-era reactor change-request rows an experiment once owned were
      **PURGED** by this service from 2026-07-29 until issue #122 PR-E E1
      (2026-10-06) removed the purge; E2 (Alembic `a7d3e9f1c2b4`, 2026-10-09)
      dropped the table itself after the production 021 run converted its rows
      (357 rows, 331 converted, 26 orphaned). That data now lives in
      `experiment_notes` (`note_type='modification'`, `event_date`,
      `created_by='migrate_change_requests_021'`) and is counted under `notes`;
      each converted row's original is in `modifications_log.old_values`
      (`modified_table='reactor_change_requests'`).
```

- [ ] **Step 2: MODELS.md — impact counts paragraph (lines 84-94)**

Replace the sentences from `\`change_requests\`\n    was dropped from this list in issue #122 PR-B (2026-09-24):` through `see the deletion-path bullet above.` with:

```
`change_requests`
    was dropped from this list in issue #122 PR-B (2026-09-24): reactor
    modifications are `experiment_notes` rows and already counted under
    `notes`, so a separate count would double-report them. The source table
    itself was dropped in PR-E E2 (2026-10-09); see the deletion-path bullet above.
```

- [ ] **Step 3: MODELS.md — `ExperimentNotes` backfill bullet (line 216)**

Replace the whole line with:

```
- **Backfill (issue #122 PR-B, 2026-09-24; source table dropped in PR-E E2, 2026-10-09):** `database/data_migrations/migrate_reactor_change_requests_021.py` converted the Notion-era reactor change-request rows into `modification` notes (`experiment_fk`, `event_date` from the row's `sync_date`, `note_text` from `requested_change`, `created_by=SOURCE_TAG`), one `ModificationsLog` snapshot per note. Reports: `docs/issues/migrate-change-requests-021-dryrun-2026-09-24.md` — dev mirror 333 rows / 307 converted / 26 orphaned (applied 2026-10-05); **production 357 / 331 / 26 (applied 2026-10-09)**. The three `/change-requests` routes left in E1 (2026-10-06); the source table was dropped by Alembic `a7d3e9f1c2b4` in E2 and the script is frozen (it refuses to run, exit 3).
```

- [ ] **Step 4: API_REFERENCE.md — purge sentence (lines 318-322) and the dashboard line (643)**

Replace the parenthetical `(\`reactor_change_requests\`\nrows were purged here until issue #122 PR-E; the service no longer touches that\ntable — its \`ON DELETE SET NULL\` FK unlinks a dangling row — and it is dropped in E2.)` so the paragraph reads:

```
Purged: the conditions row and its chemical additives, all results (scalar, ICP,
result files), notes, external analyses **and their `elemental_analysis` rows**,
XRD phase rows, and its prior `ModificationsLog` history. (The Notion-era reactor
change-request rows were purged here until issue #122 PR-E E1; E2 dropped that
table on 2026-10-09 — reactor modifications are `modification` notes, counted under `notes`.)
```

On line 643 replace `(issue #122 PR-B, re-sourced from the now-deprecated \`reactor_change_requests\`)` with `(issue #122 PR-B, re-sourced from the Notion-era change-request table, dropped in PR-E E2)`.

- [ ] **Step 5: POWERBI_MODEL.md (lines 170-173)**

Replace `this replaces\n  the retired \`reactor_change_requests\` table as the source for that data (migrated by\n  \`migrate_reactor_change_requests_021.py\`).` with:

```
this replaces
  the Notion-era `reactor_change_requests` table as the source for that data (rows
  migrated by `migrate_reactor_change_requests_021.py`; the table was dropped by Alembic
  `a7d3e9f1c2b4` on 2026-10-09 — any Power BI query that still names it will fail).
```

- [ ] **Step 6: The 021 report — "Production run 2026-10-09" section**

In `docs/issues/migrate-change-requests-021-dryrun-2026-09-24.md`, insert the following immediately **before** the line `## Questions for Mat (answered 2026-10-05: apply approved; 2 and 3 at defaults)`:

```
## Production run (2026-10-09, Mat, lab PC)

`--apply` was run directly (no prior dry run on production); the report it printed was
compared with this document afterwards. Numbers as pasted by Mat:

| Measure | Dev mirror (2026-10-05) | Production (2026-10-09) |
|---|---|---|
| `reactor_change_requests` rows | 333 | **357** (214 dashboard-typed, 143 Notion-imported) |
| convertible → converted | 307 | **331** |
| orphaned (`experiment_id` NULL) | 26 | **26** — the same April/May 2026 Notion rows on R03–R09 and AC01–AC03 |
| blank / already converted / collapsed | 0 / 0 / 0 | 0 / 0 / 0 |
| `reactor_label` ≠ current `reactor_slot` (informational) | 8 | 8 |

```
before: modification_notes 180, dated_modification_notes 0, notes_by_021 0, snapshots_by_021 0, notes_total 4317, change_request_rows 357
after:  modification_notes 511, dated_modification_notes 331, notes_by_021 331, snapshots_by_021 331, notes_total 4648, change_request_rows 357
Applied. 331 notes created (matches the plan).
```

The +24 rows over the mirror are dashboard entries written between the 2026-09-04 backup and
PR-B's deploy; all 24 converted. The post-apply idempotency dry run (runbook step 4) was not
run; it is moot now — **PR-E E2 (Alembic `a7d3e9f1c2b4`, authorized by Mat 2026-10-09) drops
`reactor_change_requests`**, so the 26 orphaned rows survive only in backups taken before that
revision, and the script above is frozen (it exits 3 with a message pointing at
`git show 32da995:database/data_migrations/migrate_reactor_change_requests_021.py`).
The runbook steps 1–4 above are therefore historical.
```

- [ ] **Step 7: Spec §1 row**

In `docs/working/issues/07-notes-overhaul-phase-2.md` line 38, replace `**E2 approved by Mat 2026-10-09 (§7 sign-off given) — Next.**` with `**E2 approved by Mat 2026-10-09 (§7 sign-off given); on \`chore/drop-reactor-change-requests\` — Alembic \`a7d3e9f1c2b4\` drops the table, model and importers deleted, 021 frozen. Plan: \`docs/superpowers/plans/2026-10-09-drop-reactor-change-requests-pr-e2.md\`.**`

- [ ] **Step 8: Verify the sync hook copied the docs, then commit**

Run: `git status --short docs/project_context/`
Expected: modified `docs/project_context/API_REFERENCE.md`, `docs/project_context/POWERBI_MODEL.md`, `docs/project_context/migrate-change-requests-021-dryrun-2026-09-24.md` (the hook copies flat by basename). If any is missing, run `.venv/Scripts/python.exe -c "import sys; sys.path.insert(0, '.claude/hooks'); import sync_docs_to_project_context as s; s.full_sync()"` and re-check.

Run: `grep -rn "dropped in E2\|is dropped in E2\|until E2\|not dropped until E2" .claude/rules/MODELS.md docs/api/API_REFERENCE.md docs/POWERBI_MODEL.md`
Expected: empty (no future-tense "dropped in E2" left).

```powershell
git add .claude/rules/MODELS.md docs/api/API_REFERENCE.md docs/POWERBI_MODEL.md docs/issues/migrate-change-requests-021-dryrun-2026-09-24.md docs/working/issues/07-notes-overhaul-phase-2.md docs/project_context/
git commit -F <scratchpad>/commit4.txt
```
With `commit4.txt`:
```
[#122] Document the E2 table drop and prod 021 run

- MODELS.md, API_REFERENCE.md, POWERBI_MODEL.md: table is gone
- 021 report gains the production section (357/331/26)
- Tests added: no
- Docs updated: yes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Conductor-only steps (after the four tasks and the whole-branch review)

Not delegated; recorded here so the PR body has one source.

1. `alembic heads` → `a7d3e9f1c2b4` only. Full §8 suites: `.venv/Scripts/pytest.exe tests/models tests/views tests/api tests/test_icp_handling.py tests/services tests/regression tests/data_migrations -q` (one process); `cd frontend; npx vitest run; npx eslint src --ext .ts,.tsx; npx tsc --noEmit` — only the #106 baselines (eslint 5, tsc 3). `.venv/Scripts/python.exe -c "import database; import backend.api.main"` clean. Acceptance grep (Task 3 Step 5) re-run.
2. Dev DB: record `SELECT count(*) FROM reactor_change_requests` (expect 333) and the 021 note/snapshot counts (307/307), then `.venv/Scripts/alembic.exe upgrade head` with `DATABASE_URL` from `.env` (the dev DB). Confirm the table is gone and the 307 notes + 307 snapshots are untouched. Record for the PR body.
3. Chrome DevTools on `http://localhost:5173`: dashboard reactor card → type a modification → save → `POST /api/experiments/{id}/notes` 201 with `note_type: "modification"` and today's `event_date`; open the experiment's Notes tab → the note is shown with the MODIFICATION badge; delete it; zero console errors. If the MCP browser profile is held by another session, Mat has authorized ending that Chrome process tree.
4. Issue-log entry (`docs/working/issue-log.md`) with the verification counts; `gh pr create --base develop` with: the §7 sign-off citation (spec §2, "E2 approved", 2026-10-09), the rehearsal stdout from Task 1 Step 7, the Review Focus 1 error line, the dev-DB before/after counts, the deploy note (`update.ps1` runs `alembic upgrade head` nightly; the drop cannot refuse; the lab PC ran 021 on 2026-10-09 so nothing unconverted is lost except the 26 orphans, recoverable only from a pre-drop backup), and the Conductor's call on the 021 script (frozen stub, gap call 2).
