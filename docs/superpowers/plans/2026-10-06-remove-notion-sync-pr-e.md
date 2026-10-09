# Remove the Notion Sync Integration (issue #122, PR-E / E1; absorbs #117) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the deprecated Notion reactor sync (service package, scheduler, admin route, settings, two dependencies), the three `/change-requests` routes it fed, their Pydantic and TypeScript types, the `reactor_change_requests` purge in the deletion service, every test that exercised them, and the Notion docs — with no schema change and no change to what a researcher sees.

**Architecture:** Pure removal in four layers plus docs. Backend: unregister the admin router, strip the lifespan to its `reset_postgres_sequences()` call, drop four `Settings` fields, delete the service package and its only private helper (`canonical_slot_label`). The three `/change-requests` routes go with their schema module; `delete_experiment_cascade` stops touching `reactor_change_requests` and relies on the `ON DELETE SET NULL` FK that both the model and Alembic `9c358174ea54` declare. Frontend: remove the three client methods and two types nobody calls, and two dead query-key entries. The `ReactorChangeRequest` model, its table, its model test and its three migrations are **not touched** (E2 owns them, not yet authorized).

**Tech Stack:** FastAPI + Pydantic v2 + pydantic-settings; SQLAlchemy 2 against `experiments_test`; React 18 + TypeScript strict + TanStack Query v5; pytest, vitest, flake8, eslint, tsc.

**Spec:** `docs/working/issues/07-notes-overhaul-phase-2.md` §4 "PR-E" (E1 only), §2 pre-authorization 4 ("absorb #117"), §3 decisions 11 and 12, §8 items 3 and 5. GitHub issue #117 holds the original scope table. Gap calls below were approved by Mat in chat on 2026-10-06 ("Proceed as proposed").

## Gap calls (approved 2026-10-06)

1. **The purge in `experiment_deletion.py` is removed although the table still exists.** Safe because `reactor_change_requests.experiment_id` is `ForeignKey("experiments.experiment_id", ondelete="SET NULL")` in `database/models/notion_sync.py` **and** `sa.ForeignKeyConstraint([...], ondelete='SET NULL')` in `alembic/versions/9c358174ea54_add_reactor_change_requests.py:34`, so the lab PC (built through Alembic) and the test DB (built by `create_all`) agree. Deploy-ordering note for the PR body: if E1 reaches production before the 021 `--apply`, deleting an experiment turns its unconverted rows into 021 "orphans" (string NULLed) instead of destroying them; the post-apply orphan count may then exceed the dry run's 26.
2. **`canonical_slot_label` is deleted** from `database/reactor_slot.py` with its test cases and the `_SLOT_LABEL_RE` regex. Its only caller was `backend/services/notion_sync/import_.py`. `database/reactor_slot.py` is not a model file and is not locked.
3. **Dead query keys `'changeRequests'` and `'reactorModificationRecent'`** leave `PER_EXPERIMENT_QUERY_KEYS` in `ExperimentDetail/index.tsx` and the matching list in `DeleteExperiment.test.tsx`. No `useQuery` uses either key.
4. **Stale "change requests" text left by PR-B is corrected**: the delete-impact example and purge sentence in `docs/api/API_REFERENCE.md`, the field lists in `scripts/delete_experiments_via_api.ps1`, the bulk-deletion help text in `frontend/src/pages/BulkUploads.tsx`, and the deletion-path paragraphs in `.claude/rules/MODELS.md`.
5. **`migrate_deduplicate_change_requests.py` (repo root) stays** until E2; it is a model consumer, not Notion-sync code.

Also settled by the spec and not re-asked: `database/models/notion_sync.py`, `tests/models/test_notion_sync_model.py`, the `ReactorChangeRequest` exports in `database/__init__.py` and `database/models/__init__.py`, the three migrations, `database/data_migrations/migrate_reactor_change_requests_021.py` and its test, and historical references under `docs/superpowers/plans/`, `docs/issues/` and `docs/POWERBI_MODEL.md` all stay.

## Global Constraints

- Branch `chore/remove-notion-sync` off `develop` (already created at `12cc2e4`); PR base `develop` (`gh pr create --base develop`).
- Commit format `[#122] <imperative, under 50 chars>` + `- Tests added: yes/no` / `- Docs updated: yes/no` lines + `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Multi-line messages via `git commit -F <scratchpad file>` (PowerShell here-strings break on embedded quotes).
- **No schema change, no migration, no file under `database/models/`, `backend/services/bulk_uploads/` or `alembic/versions/` is touched. No new package.** `alembic heads` stays `e5b2d9c7a1f4`.
- **E1 merges only after Mat confirms in chat that `NOTION_TOKEN` has been blanked on the lab PC and the app has run one day** (#117 verification step; the lab PC's `.env` was found to have a live token on 2026-10-06). Never write the token's value anywhere.
- The dev `.env` (gitignored) also has the four `NOTION_*` keys set. Do not edit it. `Settings` has `extra="ignore"`, so stale keys are harmless once the fields are gone — Task 1 pins this.
- Removed-route tests assert via the FastAPI route registry (`[r.path for r in app.routes if ... ]`), **never** via HTTP 404: the SPA catch-all answers unknown GET paths with `index.html`. Precedent: `tests/api/test_bulk_uploads.py::test_master_results_config_endpoints_removed`.
- Backend commands run from the repo root with `.venv/Scripts/pytest.exe`, `.venv/Scripts/flake8.exe`, `.venv/Scripts/pip.exe`. **One pytest process at a time.** Root-level `tests/test_*.py` files are never in the same invocation as `tests/api` or `tests/services` (their `test_db` fixture drops all tables at teardown).
- Frontend commands run from `frontend/`: `npx vitest run <path>`, `npx eslint src --ext .ts,.tsx`, `npx tsc --noEmit`. Baseline (#106): eslint 5 problems, tsc 3 errors all in `ResultsTab.columns.test.tsx`. Nothing new may be added to either.
- Doc edits under `docs/` go through the Edit tool so the `project_context` sync hook fires. The hook does not delete: remove `docs/project_context/NOTION_SYNC.md` by hand (Task 4).
- Whole-directory deletions use `git rm -r` so `__pycache__` goes too; a leftover `backend/services/notion_sync/__pycache__/` would make the package importable as a namespace package (Task 1's `find_spec` test catches this).
- Every claim in a DONE report must be backed by a command the implementer actually ran, with its output quoted. The Conductor re-runs `git status`, `git log --oneline develop..HEAD` and `git diff develop --stat` after every DONE report before dispatching a reviewer.

## Review Focus

1. **Deleting an experiment that still has a `reactor_change_requests` row pointing at it** — must succeed, the row must be unlinked by the database (`experiment_id` NULL), and the service must issue no statement against the table. Pinned in Task 2 (`test_delete_no_longer_touches_reactor_change_requests`).
2. **A deployed `.env` that still carries `NOTION_TOKEN=...`** — `Settings` must construct and must not grow a `notion_token` attribute. Pinned in Task 1 (`test_settings_ignore_stale_notion_env_keys`).
3. **A stale `__pycache__` left where the service package was** — `importlib.util.find_spec("backend.services.notion_sync")` must be `None`. Pinned in Task 1.
4. **Booting the app with `apscheduler` and `notion-client` uninstalled** — `import backend.api.main` must succeed; the dependencies come out of the venv in Task 1 before the import check, not after.
5. **A frontend bundle that still knows the `/change-requests` URLs** — `experimentsApi` exposes none of the three methods and `grep` over `frontend/src` finds no `change-requests`. Pinned in Task 3.

---

### Task 1: Remove the Notion sync service, scheduler, settings and dependencies

**Files:**
- Delete (whole directory): `backend/services/notion_sync/` (`__init__.py`, `client.py`, `export.py`, `import_.py`, `sync.py`, `__pycache__/`)
- Delete: `backend/api/routers/notion_sync.py`
- Delete: `tests/api/test_notion_sync.py`, `tests/services/test_notion_sync_client.py`, `tests/services/test_notion_sync_export.py`, `tests/services/test_notion_sync_import.py`, `tests/services/test_notion_sync_integration.py`, `tests/test_notion_sync_scheduler.py`
- Modify: `backend/api/main.py:15-18` (router tuple), `:24-49` (lifespan), `:92` (`include_router`)
- Modify: `backend/config/settings.py:33-37`
- Modify: `requirements.txt:81` (`apscheduler>=3.11.0`), `:88` (`notion-client>=2.2.1,<2.3`)
- Modify: `.env.example:20-29` (the `# Notion Sync — Reactor Dashboard` block and the blank line above it)
- Modify: `database/reactor_slot.py:15` (docstring line), `:28` (`import re`), `:45` (`_SLOT_LABEL_RE`), `:103-115` (`canonical_slot_label`)
- Modify: `tests/test_reactor_slot.py:13` (import), `:97-114` (the `test_canonical_slot_label` parametrize block)
- Create: `tests/api/test_notion_sync_removed.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `tests/api/test_notion_sync_removed.py` — Task 2 appends one test to this file. `backend/api/routers/experiments.py`, `backend/api/schemas/notion_sync.py` and `backend/services/experiment_deletion.py` still import the model/schemas after this task; that is Task 2's job and is expected.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_notion_sync_removed.py`:

```python
"""Issue #122 PR-E (E1, absorbs #117): the Notion sync integration is gone.

Removed-route assertions go through the route registry, never HTTP 404 — the
SPA catch-all in backend/api/main.py answers unknown GET paths with index.html
(precedent: tests/api/test_bulk_uploads.py::test_master_results_config_endpoints_removed).
"""
from __future__ import annotations

import importlib.util

from backend.api.main import app
from backend.config.settings import Settings


def test_notion_sync_routes_are_unregistered():
    assert [r.path for r in app.routes if "notion" in getattr(r, "path", "")] == []


def test_settings_have_no_notion_fields():
    for name in ("notion_token", "notion_database_id", "notion_data_source_id", "notion_sync_hour"):
        assert name not in Settings.model_fields, name


def test_settings_ignore_stale_notion_env_keys():
    """A deployed .env may still carry NOTION_TOKEN=... — Settings is
    extra="ignore", so it must construct and must not grow the attribute."""
    s = Settings(_env_file=None, notion_token="stale", notion_sync_hour=6)
    assert not hasattr(s, "notion_token")
    assert not hasattr(s, "notion_sync_hour")


def test_notion_sync_package_is_gone():
    # A leftover backend/services/notion_sync/__pycache__/ directory would still
    # resolve as a namespace package, so this only passes once the directory is
    # removed entirely, not just its .py files.
    assert importlib.util.find_spec("backend.services.notion_sync") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest.exe tests/api/test_notion_sync_removed.py -q`
Expected: 4 failed — the route `/api/admin/notion-sync/trigger` is registered, the four fields exist on `Settings`, `hasattr(s, "notion_token")` is True, and `find_spec` returns a spec.

- [ ] **Step 3: Delete the service package, the admin router and the six test files**

```bash
git rm -r -q backend/services/notion_sync
git rm -q backend/api/routers/notion_sync.py
git rm -q tests/api/test_notion_sync.py tests/services/test_notion_sync_client.py tests/services/test_notion_sync_export.py tests/services/test_notion_sync_import.py tests/services/test_notion_sync_integration.py tests/test_notion_sync_scheduler.py
ls backend/services/notion_sync 2>&1   # expected: No such file or directory
```

If `ls` still shows the directory (an untracked `__pycache__` survives `git rm`), remove it: `rm -rf backend/services/notion_sync`.

- [ ] **Step 4: Edit `backend/api/main.py`**

Replace lines 15–18:

```python
from backend.api.routers import (
    experiments, conditions, results, samples,
    chemicals, analysis, dashboard, admin, bulk_uploads, auth, additives, notion_sync,
)
```

with:

```python
from backend.api.routers import (
    experiments, conditions, results, samples,
    chemicals, analysis, dashboard, admin, bulk_uploads, auth, additives,
)
```

Replace the whole lifespan (lines 24–49, from `@asynccontextmanager` through `log.info("notion_sync_scheduler_stopped")`) with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    from database.database import reset_postgres_sequences
    reset_postgres_sequences()
    yield
```

Delete line 92:

```python
app.include_router(notion_sync.router)
```

Then run `.venv/Scripts/flake8.exe --select=F401,F821 backend/api/main.py`. Expected: no output. (`get_settings` is still used at line 20 for `settings = get_settings()`; `log` is still used elsewhere in the file — if flake8 reports either as unused, remove only what it reports and say so in the DONE report.)

- [ ] **Step 5: Edit `backend/config/settings.py`**

Delete lines 33–37 and the blank line that would otherwise be doubled:

```python
    # Notion sync — reactor dashboard
    notion_token: str = ""
    notion_database_id: str = ""
    notion_data_source_id: str = ""
    notion_sync_hour: int = 6  # Hour of day (24h) in America/New_York to run daily sync
```

so that `actlabs_similarity_threshold` is followed by one blank line and then `@property`.

- [ ] **Step 6: Edit `requirements.txt` and `.env.example`**

`requirements.txt`: delete the two lines `apscheduler>=3.11.0` (line 81) and `notion-client>=2.2.1,<2.3` (line 88). Nothing else changes. (`httpx==0.28.1`, `pytz`, `tzdata` are pinned on their own lines and stay; `tzlocal` was only ever pulled in by APScheduler.)

`.env.example`: delete lines 20–29 — the blank line and the block:

```
# Notion Sync — Reactor Dashboard
# Token from Notion integration settings (secret_...)
NOTION_TOKEN=
# Reactor Dashboard database ID (32-char UUID without dashes)
NOTION_DATABASE_ID=53ec4778508541efa31eaf0e4accac35
# Data source ID for the Reactor Dashboard
NOTION_DATA_SOURCE_ID=d8d499ab-d6ef-44ce-9f67-d650dfaf5319
# Hour (0-23, America/New_York) to run the daily sync
NOTION_SYNC_HOUR=6
```

The file should end with `PUBLIC_COPY_DIR=./public_copies` followed by a single newline.

- [ ] **Step 7: Delete `canonical_slot_label` and its regex from `database/reactor_slot.py`; fix its docstring**

Delete line 15 of the module docstring:

```
  - backend/services/notion_sync/import_.py
```

Delete line 28 (`import re`) and line 45:

```python
_SLOT_LABEL_RE = re.compile(r"(CF|R)0*(\d+)", re.IGNORECASE)
```

(and the blank line that paired with it, so surrounding blank-line spacing stays at the file's convention of two blank lines between top-level definitions).

Delete lines 103–115 — the two blank lines before it and the whole function:

```python
def canonical_slot_label(label: str | None) -> str | None:
    """Normalize an externally supplied label ('r5', 'CF1') to canonical form ('R05', 'CF01').

    Used on the Notion sync path, where the reactor label comes from a Notion
    page title and is not guaranteed to be zero-padded or upper-cased.
    """
    if not label:
        return None
    match = _SLOT_LABEL_RE.fullmatch(label.strip())
    if match is None:
        return None
    return _format_slot(match.group(1).upper(), int(match.group(2)))
```

The file now ends with `derive_reactor_slot`'s `return _format_slot(prefix, number)` and one trailing newline.

Run `.venv/Scripts/flake8.exe database/reactor_slot.py`. Expected: no output.

- [ ] **Step 8: Remove the `canonical_slot_label` cases from `tests/test_reactor_slot.py`**

In the import block (lines 12–18) delete the line `    canonical_slot_label,`. Delete lines 97–114 (the two blank lines after `test_derive_reactor_slot_tolerates_float_and_string_numbers` and the whole block):

```python
@pytest.mark.parametrize(
    "label,expected",
    [
        ("R01", "R01"),
        ("R1", "R01"),        # Notion labels are not guaranteed zero-padded
        ("r5", "R05"),
        ("CF1", "CF01"),
        ("cf03", "CF03"),
        ("R00", None),        # zero is not a slot
        ("X01", None),
        ("R", None),
        ("", None),
        (None, None),
    ],
)
def test_canonical_slot_label(label, expected):
    assert canonical_slot_label(label) == expected
```

The file now ends with `assert derive_reactor_slot("not a number", "HPHT") is None` and one trailing newline.

- [ ] **Step 9: Uninstall the two dependencies and prove the app still imports**

```bash
.venv/Scripts/pip.exe uninstall -y apscheduler notion-client tzlocal
.venv/Scripts/pip.exe check
.venv/Scripts/python.exe -c "import backend.api.main as m; print(type(m.app).__name__, len(m.app.routes))"
```

Expected: `pip check` prints `No broken requirements found.`; the python line prints `FastAPI <n>` with no traceback. Quote both outputs in the DONE report. (If `pip check` reports anything, stop and report it — do not install anything.)

- [ ] **Step 10: Run the tests**

Run: `.venv/Scripts/pytest.exe tests/api/test_notion_sync_removed.py tests/api/test_dashboard.py -q`
Expected: all pass (`test_notion_sync_removed.py` 4 passed; `test_dashboard.py` unchanged count, 0 failed).

Run, **as its own invocation afterwards**: `.venv/Scripts/pytest.exe tests/test_reactor_slot.py -q`
Expected: all pass, 10 fewer tests than before (the parametrized cases).

Run: `grep -rn -i "notion" backend/ requirements.txt .env.example`
Expected: hits only in `backend/api/routers/experiments.py` (2 import lines), `backend/api/schemas/notion_sync.py` (the file itself) and `backend/services/experiment_deletion.py` (1 import line + comments). Those are Task 2's. Any other hit is a miss in this task.

- [ ] **Step 11: Commit**

Write the message to a scratchpad file and commit with `-F`:

```
[#122] Remove the Notion sync service and scheduler

- Delete backend/services/notion_sync/, the admin trigger router, the
  lifespan scheduler block, the four notion_* settings, apscheduler and
  notion-client (requirements), the .env.example block, and
  canonical_slot_label (its only caller was the Notion importer)
- Delete the five Notion sync test files and the scheduler test
- Add tests/api/test_notion_sync_removed.py (route registry, Settings
  fields, stale env keys ignored, package not importable)
- Tests added: yes
- Docs updated: no (Task 4)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

```bash
git add -A backend/api/main.py backend/config/settings.py requirements.txt .env.example database/reactor_slot.py tests/test_reactor_slot.py tests/api/test_notion_sync_removed.py
git commit -F <scratchpad>/commit-task1.txt
git status --short   # expected: clean
```

---

### Task 2: Remove the `/change-requests` routes, their schema, and the deletion-service purge

**Files:**
- Delete: `backend/api/schemas/notion_sync.py`, `tests/api/test_change_requests.py`
- Modify: `backend/api/routers/experiments.py:37` (model import), `:39-41` (schema import), `:1148-1286` (three routes), then whatever `flake8` reports at `:2` (`date`) and `:7` (`pg_insert`)
- Modify: `backend/services/experiment_deletion.py:31-34` (docstring item 3), `:80` (model import), `:316-325` (the purge)
- Modify: `tests/api/test_experiments.py:783-849` (the change-request endpoint block)
- Modify: `tests/services/test_experiment_deletion.py:319-331` (replace `test_delete_purges_change_requests`); the `ReactorChangeRequest` import at `:17` and the seed row at `:82-83` **stay**
- Modify: `tests/api/test_notion_sync_removed.py` (append one test)

**Interfaces:**
- Consumes: `tests/api/test_notion_sync_removed.py` from Task 1 (imports `app` from `backend.api.main`).
- Produces: `backend/api` and `backend/services` free of `ReactorChangeRequest`, `change_requests` and `change-requests` (the §4 E1 acceptance grep). Task 3 relies on the routes being gone; Task 4 documents it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_notion_sync_removed.py`:

```python


def test_change_request_routes_are_unregistered():
    """The three /experiments/{id}/change-requests routes left with the Notion sync
    (#122 PR-E). Their data lives in experiment_notes since the 021 backfill."""
    assert [r.path for r in app.routes if "change-requests" in getattr(r, "path", "")] == []
```

In `tests/services/test_experiment_deletion.py`, replace lines 319–331 (`test_delete_purges_change_requests`, from its `def` through the closing `).scalar_one() == 0`) with:

```python
def test_delete_no_longer_touches_reactor_change_requests(db):
    """#122 PR-E (E1): the service-level purge is gone. The table outlives the
    code until E2, and its FK is ondelete="SET NULL" in BOTH the model and
    Alembic 9c358174ea54, so a dangling row is unlinked by the database — the
    service must neither read nor write the table (#117 scope)."""
    import sqlalchemy
    from sqlalchemy.engine import Engine
    from backend.services.experiment_deletion import delete_experiment_cascade

    exp = _full_experiment(db, "DEL_CR_001", 7207)
    db.add(ReactorChangeRequest(reactor_label="R09", experiment_id="DEL_CR_001",
                                requested_change="pr-e dangling row", sync_date=date(2026, 7, 29)))
    db.commit()

    statements: list[str] = []

    def counter(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sqlalchemy.event.listen(Engine, "before_cursor_execute", counter)
    try:
        delete_experiment_cascade(db, exp, modified_by="tester@addisenergy.com")
    finally:
        sqlalchemy.event.remove(Engine, "before_cursor_execute", counter)

    assert not any("reactor_change_requests" in s for s in statements), (
        "the deletion service still touches reactor_change_requests"
    )
    row = db.execute(
        select(ReactorChangeRequest)
        .where(ReactorChangeRequest.requested_change == "pr-e dangling row")
    ).scalar_one()
    assert row.experiment_id is None
```

(`date`, `select`, `ReactorChangeRequest` and `_full_experiment` are already imported/defined at the top of this module.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest.exe tests/api/test_notion_sync_removed.py::test_change_request_routes_are_unregistered tests/services/test_experiment_deletion.py::test_delete_no_longer_touches_reactor_change_requests -q`
Expected: 2 failed — three paths listed by the registry; the deletion test fails on the `assert not any(...)` because the purge still emits `DELETE FROM reactor_change_requests`.

- [ ] **Step 3: Delete the schema module and the route test file**

```bash
git rm -q backend/api/schemas/notion_sync.py tests/api/test_change_requests.py
```

- [ ] **Step 4: Remove the routes and imports from `backend/api/routers/experiments.py`**

Delete line 37:

```python
from database.models.notion_sync import ReactorChangeRequest
```

Delete lines 39–41:

```python
from backend.api.schemas.notion_sync import (
    ChangeRequestResponse, ChangeRequestUpsertRequest, RecentChangeRequestsResponse,
)
```

Delete lines 1148–1286: from `@router.get("/{experiment_id}/change-requests", response_model=list[ChangeRequestResponse])` through the `return ChangeRequestResponse.model_validate(record)` of `upsert_change_request` and the two blank lines after it, so that the `@router.get("/{experiment_id}", response_model=ExperimentDetailResponse)` decorator of `get_experiment` is preceded by exactly two blank lines after `check_experiment_id_exists`'s `return {"exists": exists is not None}`. Verify the boundaries first:

```bash
sed -n '1146,1149p;1283,1288p' backend/api/routers/experiments.py
```

Then run `.venv/Scripts/flake8.exe --select=F401,F821 backend/api/routers/experiments.py`. Expected: exactly two F401 reports — `'datetime.date' imported but unused` (line 2) and `'sqlalchemy.dialects.postgresql.insert as pg_insert' imported but unused` (line 7). Delete those two import lines (`from datetime import date` and `from sqlalchemy.dialects.postgresql import insert as pg_insert`). Re-run flake8; expected: no output. If flake8 reports anything else, stop and include it verbatim in the DONE report instead of guessing.

- [ ] **Step 5: Remove the purge from `backend/services/experiment_deletion.py`**

Delete line 80:

```python
from database.models.notion_sync import ReactorChangeRequest
```

Replace docstring lines 31–34:

```
  3. reactor_change_requests.experiment_id -- ondelete="SET NULL", but the
     rows are purged (they belong to the experiment); since #122 PR-B they
     are no longer counted in DeleteImpact -- the migrated data lives in
     experiment_notes and is counted under notes.
```

with:

```
  3. reactor_change_requests.experiment_id -- ondelete="SET NULL" in both the
     model and Alembic 9c358174ea54. Since #122 PR-E (E1) this service neither
     purges nor counts those rows: the data was migrated to experiment_notes
     by migrate_reactor_change_requests_021.py and is counted under notes, and
     the database unlinks any row still pointing here. Table dropped in E2.
```

Delete lines 316–325 (the comment and the statement) plus the blank line after them, so `# 2. Ammonium background provenance ...`'s `db.execute(...)` is followed by one blank line and then `# 3b. elemental_analysis children ...`:

```python
    # 3. Reactor change requests are PURGED, not unlinked (product decision,
    #    2026-07-29): they belong to this experiment, and change_requests was
    #    summed into impact.total, which is documented as rows destroyed.
    #    The count left DeleteImpact in #122 PR-B (the data now lives in
    #    experiment_notes and is counted under notes); the purge stays until
    #    PR-E removes the model.
    db.execute(
        sql_delete(ReactorChangeRequest)
        .where(ReactorChangeRequest.experiment_id == experiment_id)
    )
```

Leave the `# 3b.` label as is (renumbering would churn the audit-trail cross-references in MODELS.md). Run `.venv/Scripts/flake8.exe --select=F401,F821 backend/services/experiment_deletion.py`. Expected: no output (`sql_delete` is still used for `XRDPhase` and `ElementalAnalysis`).

- [ ] **Step 6: Remove the change-request endpoint tests from `tests/api/test_experiments.py`**

Delete lines 783–849: from the comment `# --- Change Requests endpoint tests ---` through `test_get_change_requests_experiment_not_found`'s `assert resp.status_code == 404` and the two blank lines after it, so the `# ============================================================` banner of "Issue #57: Change sample_id on existing experiment" is preceded by exactly two blank lines after `assert "2026-03-15" in log_entry.new_values["date"]`. Verify the boundaries first:

```bash
sed -n '780,784p;846,851p' tests/api/test_experiments.py
```

Run `.venv/Scripts/flake8.exe --select=F401,F821 tests/api/test_experiments.py`. Expected: no output (the `from datetime import date` that block used was local to the deleted helper).

- [ ] **Step 7: Run the tests**

Run: `.venv/Scripts/pytest.exe tests/api/test_notion_sync_removed.py tests/api/test_experiments.py tests/services/test_experiment_deletion.py -q`
Expected: 0 failed. `test_experiments.py` has 4 fewer tests than on `develop`; `test_experiment_deletion.py` has the same count.

Run: `grep -rn "ReactorChangeRequest\|change_requests\|change-requests" backend/api backend/services`
Expected: no output.

Run: `grep -rn -i "notion" backend/`
Expected: no output.

- [ ] **Step 8: Commit**

```
[#122] Remove the change-request routes and purge

- Delete the three /experiments/{id}/change-requests routes, their
  schema module and tests/api/test_change_requests.py
- delete_experiment_cascade no longer touches reactor_change_requests;
  the ON DELETE SET NULL FK (model and Alembic 9c358174ea54 agree)
  unlinks any dangling row
- Replace test_delete_purges_change_requests with a statement-capture
  test proving the service never names the table; add the route-registry
  test for change-requests
- Tests added: yes
- Docs updated: no (Task 4)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

```bash
git add -A backend/api/routers/experiments.py backend/services/experiment_deletion.py tests/api/test_experiments.py tests/services/test_experiment_deletion.py tests/api/test_notion_sync_removed.py
git commit -F <scratchpad>/commit-task2.txt
git status --short   # expected: clean
```

---

### Task 3: Remove the change-request client surface and dead query keys from the frontend

**Files:**
- Modify: `frontend/src/api/experiments.ts:240-253` (two interfaces), `:419-437` (three methods)
- Modify: `frontend/src/pages/ExperimentDetail/index.tsx:37-38`
- Modify: `frontend/src/pages/ExperimentDetail/__tests__/DeleteExperiment.test.tsx:115`
- Modify: `frontend/src/pages/BulkUploads.tsx:422` (help text)
- Create: `frontend/src/api/__tests__/experiments.changeRequests.removed.test.ts`

**Interfaces:**
- Consumes: nothing from other tasks (the backend routes are gone after Task 2, which is why the client methods are dead).
- Produces: `experimentsApi` without `getChangeRequests`, `getRecentChangeRequests`, `createChangeRequest`; no `ChangeRequestEntry` / `RecentChangeRequestsResponse` types. `grep -rn "change-requests\|change_requests\|ChangeRequest" frontend/src` is empty.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/__tests__/experiments.changeRequests.removed.test.ts` (same module mock as `experiments.deleteExperiment.test.ts`, because `experiments.ts` imports the Axios client at module load):

```ts
import { describe, it, expect, vi } from 'vitest'

vi.mock('../client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

import { experimentsApi } from '../experiments'

describe('experimentsApi — issue #122 PR-E', () => {
  it('exposes no change-request methods (the routes were removed with the Notion sync)', () => {
    expect(experimentsApi).not.toHaveProperty('getChangeRequests')
    expect(experimentsApi).not.toHaveProperty('getRecentChangeRequests')
    expect(experimentsApi).not.toHaveProperty('createChangeRequest')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`): `npx vitest run src/api/__tests__/experiments.changeRequests.removed.test.ts`
Expected: 1 failed — `expected ... not to have property "getChangeRequests"`.

- [ ] **Step 3: Remove the types and methods from `frontend/src/api/experiments.ts`**

Delete lines 240–253 and the blank line that would be doubled:

```ts
export interface ChangeRequestEntry {
  id: number
  reactor_label: string
  requested_change: string
  notion_status: string | null
  carried_forward: boolean
  sync_date: string
  created_at: string
}

export interface RecentChangeRequestsResponse {
  selected: ChangeRequestEntry | null
  previous: ChangeRequestEntry | null
}
```

Delete lines 419–437 and the blank line that would be doubled, so `deleteNote` is followed by one blank line and then `getDeleteImpact`:

```ts
  getChangeRequests: (experimentId: string) =>
    apiClient.get<ChangeRequestEntry[]>(
      `/experiments/${experimentId}/change-requests`
    ).then((r) => r.data),

  getRecentChangeRequests: (experimentId: string, date?: string) =>
    apiClient
      .get<RecentChangeRequestsResponse>(`/experiments/${experimentId}/change-requests/recent`, {
        params: date ? { date } : undefined,
      })
      .then((r) => r.data),

  createChangeRequest: (
    experimentId: string,
    payload: { reactor_label: string; requested_change: string; sync_date?: string },
  ) =>
    apiClient
      .post<ChangeRequestEntry>(`/experiments/${experimentId}/change-requests`, payload)
      .then((r) => r.data),
```

- [ ] **Step 4: Drop the two dead query keys**

`frontend/src/pages/ExperimentDetail/index.tsx` lines 37–38 — delete:

```ts
  'changeRequests',
  'reactorModificationRecent',
```

`frontend/src/pages/ExperimentDetail/__tests__/DeleteExperiment.test.tsx` lines 113–117 — replace:

```ts
    for (const key of [
      'experiment', 'delete-impact', 'conditions', 'additives',
      'experiment-results', 'changeRequests', 'reactorModificationRecent',
      'xrd', 'external-analysis', 'replicate-group',
    ]) {
```

with:

```ts
    for (const key of [
      'experiment', 'delete-impact', 'conditions', 'additives',
      'experiment-results', 'xrd', 'external-analysis', 'replicate-group',
    ]) {
```

- [ ] **Step 5: Correct the bulk-deletion help text in `frontend/src/pages/BulkUploads.tsx:422`**

In the `helpText` string, replace `external analyses, XRD phases, change requests) is permanently destroyed` with `external analyses, XRD phases) is permanently destroyed`. Nothing else in the string changes.

- [ ] **Step 6: Run the frontend checks**

From `frontend/`:

```bash
npx vitest run src/api src/pages/ExperimentDetail/__tests__/DeleteExperiment.test.tsx src/pages/__tests__/BulkUploads.test.tsx
npx tsc --noEmit
npx eslint src --ext .ts,.tsx
```

Expected: vitest 0 failed (if `src/pages/__tests__/BulkUploads.test.tsx` does not exist, drop that path and say so); `tsc` reports exactly the 3 baseline errors, all in `ResultsTab.columns.test.tsx`; eslint reports exactly 5 problems (baseline). Quote the summary lines.

Run from the repo root: `grep -rn "change-requests\|change_requests\|ChangeRequest\|changeRequests\|reactorModificationRecent" frontend/src`
Expected: no output.

- [ ] **Step 7: Commit**

```
[#122] Drop the change-request client methods

- Remove getChangeRequests, getRecentChangeRequests, createChangeRequest,
  ChangeRequestEntry and RecentChangeRequestsResponse (no callers since
  PR-B; the routes left in the previous commit)
- Drop the dead 'changeRequests' / 'reactorModificationRecent' eviction
  keys on the detail page and its delete test
- Bulk-deletion help text no longer lists change requests
- Tests added: yes
- Docs updated: no (Task 4)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

```bash
git add frontend/src/api/experiments.ts frontend/src/api/__tests__/experiments.changeRequests.removed.test.ts frontend/src/pages/ExperimentDetail/index.tsx frontend/src/pages/ExperimentDetail/__tests__/DeleteExperiment.test.tsx frontend/src/pages/BulkUploads.tsx
git commit -F <scratchpad>/commit-task3.txt
git status --short   # expected: clean
```

---

### Task 4: Retire the Notion docs and correct the stale change-request text

**Files:**
- Delete: `docs/NOTION_SYNC.md`, `docs/notion_sync/NOTION_SYNC.md` (and the now-empty `docs/notion_sync/` directory), `docs/project_context/NOTION_SYNC.md` (by hand — the hook never deletes)
- Modify (Edit tool, so the hook syncs the copy): `docs/DIRECTORY_STRUCTURE.md:30-32`, `docs/api/API_REFERENCE.md:29-31`, `:297`, `:322-325`, `docs/user_guide/BULK_UPLOADS.md:418-419`
- Modify: `.claude/rules/MODELS.md:55-64`, `:92-94`; `database/CLAUDE.md:37`; `scripts/delete_experiments_via_api.ps1:106`, `:118-119`

**Interfaces:**
- Consumes: the code state after Tasks 1–3 (what the docs now describe).
- Produces: docs matching the code. The issue-log entry and the spec §1 row are **not** in this task — the Conductor writes them in Task 5 with the final verification counts.

- [ ] **Step 1: Delete the three Notion doc copies**

```bash
git rm -q docs/NOTION_SYNC.md docs/notion_sync/NOTION_SYNC.md docs/project_context/NOTION_SYNC.md
ls docs/notion_sync 2>&1   # expected: No such file or directory (git removes the empty dir); if it remains, rmdir docs/notion_sync
```

- [ ] **Step 2: `docs/DIRECTORY_STRUCTURE.md`**

Replace lines 30–32:

```
│       ├── bulk_uploads/              ← locked parsers, do not modify logic
│       ├── database/                  ← query helpers
│       └── notion_sync/
```

with:

```
│       ├── bulk_uploads/              ← locked parsers, do not modify logic
│       └── database/                  ← query helpers
```

- [ ] **Step 3: `docs/api/API_REFERENCE.md`**

Delete the three table rows at lines 29–31 (the `GET .../change-requests`, `GET .../change-requests/recent` and `POST .../change-requests` rows that already carry "**Deprecated 2026-09; removed by PR-E**").

Delete line 297 from the delete-impact example JSON:

```
  "change_requests": 0,
```

(`"total": 16` is already the sum of the remaining nine counts; do not change it.)

Replace lines 322–325:

```
Purged: the conditions row and its chemical additives, all results (scalar, ICP,
result files), notes, external analyses **and their `elemental_analysis` rows**,
XRD phase rows, this experiment's `reactor_change_requests` rows, and its prior
`ModificationsLog` history.
```

with:

```
Purged: the conditions row and its chemical additives, all results (scalar, ICP,
result files), notes, external analyses **and their `elemental_analysis` rows**,
XRD phase rows, and its prior `ModificationsLog` history. (`reactor_change_requests`
rows were purged here until issue #122 PR-E; the service no longer touches that
table — its `ON DELETE SET NULL` FK unlinks a dangling row — and it is dropped in E2.)
```

- [ ] **Step 4: `docs/user_guide/BULK_UPLOADS.md:418-419`**

Replace `files, notes, additives, external analyses, XRD phases and reactor change requests. Two` with `files, notes, additives, external analyses and XRD phases. Two`. Re-wrap only that sentence if the line exceeds the paragraph's width.

- [ ] **Step 5: `.claude/rules/MODELS.md`**

Replace lines 55–64 (the `reactor_change_requests` bullet of the deletion path):

```
    - `reactor_change_requests` rows for this experiment are **PURGED**, not
      unlinked (product decision, 2026-07-29). They belong to the experiment, and
      `change_requests` is summed into `total`, which is documented as rows
      destroyed — nulling instead of deleting made that count overstate
      destruction. **(issue #122 PR-B, 2026-09-24):** `change_requests` is
      dropped from `DeleteImpact`/`IMPACT_ROWS` — the data this table held now
      lives in `experiment_notes` (`note_type='modification'`) and is counted
      under `notes` instead. The purge above still runs unchanged; only the
      *count* moved. `reactor_change_requests` and this purge step are removed
      entirely in PR-E, once the model itself is dropped.
```

with:

```
    - `reactor_change_requests` rows for this experiment were **PURGED** by this
      service from 2026-07-29 (product decision) until issue #122 PR-E (E1,
      2026-10-06) removed the purge together with the Notion sync code. The data
      this table held lives in `experiment_notes` (`note_type='modification'`,
      migrated by `migrate_reactor_change_requests_021.py`) and is counted under
      `notes` (PR-B dropped the separate `change_requests` count). The service
      no longer reads or writes the table; a row still pointing at a deleted
      experiment is unlinked by the database — the FK is `ondelete="SET NULL"`
      in both the model and Alembic `9c358174ea54`. The table and
      `ReactorChangeRequest` are dropped in E2, once the production 021 run is
      confirmed.
```

Replace lines 92–94 (the tail of the "Impact counts" paragraph):

```
    writes notes instead of rows. The `reactor_change_requests` purge in the
    deletion service itself is unaffected and stays until PR-E removes the
    model.
```

with:

```
    writes notes instead of rows. The `reactor_change_requests` purge itself was
    removed in PR-E (E1, 2026-10-06); see the deletion-path bullet above.
```

- [ ] **Step 6: `database/CLAUDE.md:37`**

Replace `gate never fires, and the Notion export clears every reactor page to idle. **The slot column` with `gate never fires. **The slot column`.

- [ ] **Step 7: `scripts/delete_experiments_via_api.ps1`**

Line 106: replace `external_analyses = 0; xrd_phases = 0; change_requests = 0; note = ''` with `external_analyses = 0; xrd_phases = 0; note = ''`.

Lines 118–119: replace

```powershell
            foreach ($f in @('total','results','conditions','notes','additives',
                             'external_analyses','xrd_phases','change_requests')) {
```

with

```powershell
            foreach ($f in @('total','results','conditions','notes','additives',
                             'external_analyses','xrd_phases')) {
```

- [ ] **Step 8: Verify the sync and the greps**

```bash
git status --short docs/project_context/
diff docs/DIRECTORY_STRUCTURE.md docs/project_context/DIRECTORY_STRUCTURE.md && echo SAME
diff docs/api/API_REFERENCE.md docs/project_context/API_REFERENCE.md && echo SAME
diff docs/user_guide/BULK_UPLOADS.md docs/project_context/BULK_UPLOADS.md && echo SAME
```

Expected: the three `project_context` copies show as modified and each `diff` prints `SAME`. If any differs, the hook did not fire (an edit was made outside the Edit tool): run `.venv/Scripts/python.exe -c "import sys; sys.path.insert(0, '.claude/hooks'); import sync_docs_to_project_context as s; s.full_sync()"` and re-check.

```bash
grep -rn -i "notion" docs/ --include=*.md -l | grep -v "docs/superpowers/\|docs/issues/\|docs/working/\|POWERBI_MODEL\|project_context/API_REFERENCE\|docs/api/API_REFERENCE"
```

Expected: no output. (`API_REFERENCE.md` keeps one historical sentence at its dashboard section — "re-sourced from the now-deprecated `reactor_change_requests`" — which does not say "notion"; if the grep lists it anyway, quote the line in the DONE report rather than editing it.)

- [ ] **Step 9: Commit**

```
[#122] Retire the Notion sync docs

- Delete docs/NOTION_SYNC.md, docs/notion_sync/ and the project_context
  copy; drop notion_sync/ from DIRECTORY_STRUCTURE.md
- API_REFERENCE: remove the three deprecated change-request rows, the
  stale change_requests impact field, and update the purge sentence
- MODELS.md, BULK_UPLOADS.md, database/CLAUDE.md and
  delete_experiments_via_api.ps1 no longer describe a change-request purge
- Tests added: no
- Docs updated: yes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

```bash
git add -A docs/ .claude/rules/MODELS.md database/CLAUDE.md scripts/delete_experiments_via_api.ps1
git commit -F <scratchpad>/commit-task4.txt
git status --short   # expected: clean
```

---

### Task 5 (Conductor, not a subagent): whole-branch verification, DevTools check, issue log, PR

**Files:**
- Modify: `docs/working/issue-log.md` (append the PR-E E1 entry), `docs/working/issues/07-notes-overhaul-phase-2.md` §1 table (PR-E row)

- [ ] **Step 1: Full backend suite, one process, fresh `experiments_test` not required (no model change)**

Run: `.venv/Scripts/pytest.exe tests/models tests/views tests/api tests/test_icp_handling.py tests/services tests/regression tests/data_migrations -q`
Expected: 0 failed. Record the passed count (PR-C's baseline was 1428; this branch deletes tests from seven files and adds 6, so the number is lower — state the actual value, not an estimate).

Then, alone: `.venv/Scripts/pytest.exe tests/test_reactor_slot.py -q` — 0 failed.

- [ ] **Step 2: Frontend suite and static checks**

From `frontend/`: `npx vitest run` (0 failed; record count and file count), `npx eslint src --ext .ts,.tsx` (5 problems), `npx tsc --noEmit` (3 errors, all `ResultsTab.columns.test.tsx`).

- [ ] **Step 3: The §4 E1 acceptance checks, verbatim**

```bash
grep -rn -i "notion" backend/ frontend/src requirements.txt
grep -rn "ReactorChangeRequest\|change_requests\|change-requests" backend/api backend/services frontend/src
.venv/Scripts/pip.exe check
.venv/Scripts/python.exe -c "import backend.api.main"
.venv/Scripts/alembic.exe heads
```

Expected: first two greps empty; `No broken requirements found.`; silent import; `e5b2d9c7a1f4 (head)`.

- [ ] **Step 4: Chrome DevTools check on `http://localhost:5173` (Mat is signed in)**

The running backend on :8000 must be restarted so it loads the branch's `main.py` (the uvicorn reloader may already have done this — confirm by hitting `GET /openapi.json` and checking no path contains `notion` or `change-requests`). Then:

1. Dashboard: open a reactor card with an ONGOING experiment, type a modification in the "Reactor Modification" box, Save. Expect a `POST /api/experiments/{id}/notes` with `note_type: "modification"` and today's `event_date` in the Network panel, 201, and the text on the card after refetch. Console: no errors.
2. Experiment detail page for that experiment: tabs are Results, Conditions, Analysis, Notes, Entry Logs (or whatever the current set is) — **no "Reactor Modifications" tab**. Notes tab shows the modification just saved with its date chip.
3. Delete the test note from the Notes tab so the dev DB is left as found (one create + one delete `ModificationsLog` row remain, as in PR-C).

Record what was observed in the PR body.

- [ ] **Step 5: Issue log and spec row**

Append to `docs/working/issue-log.md` a `## 2026-10-06 | issue #122 PR-E (E1) — Remove the Notion sync integration (`chore/remove-notion-sync`)` entry in the house format (Files changed / Why / Gap calls / Verification with the real counts / Found during the work / Tests added: yes / Docs updated: yes). Update the PR-E row of the spec's §1 table to "**E1 in review** (PR #<n>, 2026-10-06). Merge gated on the lab PC's `NOTION_TOKEN` being blanked and the app running one day (found set 2026-10-06). E2 waits for the production 021 run." Commit: `[#122] Log PR-E E1; mark it in review` (`- Tests added: no`, `- Docs updated: yes`).

- [ ] **Step 6: Open the PR and comment on #117**

`gh pr create --base develop --title "[#122] PR-E (E1): remove the Notion sync integration" --body-file <scratchpad>/pr-body.md`. The body states: pre-authorization 4 (§2) and decisions 11/12 (§3); the lab-PC token finding and that the merge is held for #117's verification step; the five gap calls; the deploy-ordering note from gap call 1; the verification counts and the DevTools observations; what E2 still owns. End with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

Comment on #117 linking the PR and stating the verification step is in progress. **Do not close #117** — close it when E1 merges.

- [ ] **Step 7: Final whole-branch review on the most capable model** (per `superpowers:subagent-driven-development`), then stop and wait for Mat's merge confirmation.
