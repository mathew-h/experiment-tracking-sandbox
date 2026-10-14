# Drop the Legacy Result Note Columns (issue #122 PR-D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** End the #118 dual-write: every free-text write about a result timepoint lands only in `experiment_notes`, and `experimental_results.description`, `brine_modification_description` and `has_brine_modification` are dropped by one non-additive Alembic migration.

**Architecture:** The notes model has been the only reader since #118 PR3; this PR removes the writers, the API/TS fields and the columns. The parsers' free-text `Description` column becomes an `observation` note through one mechanism in `ScalarResultsService.create_scalar_result_ex`: a `_note_source` control key (the parser's tag, which is the note's `created_by` and slot key) plus the `description` text, mirrored with `sync_result_note` after the upsert. Writers that already mirror (Master, Timepoint Modifications) lose their column writes. The description-keyed NULL-time fallback in `_find_or_create_experimental_result` is deleted (Mat's ruling 2026-10-12). Data-migration scripts that read the columns (019, 020) are frozen to refuse-to-run stubs, following the E2 precedent for 021.

**Tech Stack:** FastAPI + SQLAlchemy 2 + PostgreSQL 18 + Alembic; React/Vite + vitest; pytest.

**Spec:** `docs/working/issues/07-notes-overhaul-phase-2.md` — §4 "PR-D" (lines 559-591), §2 pre-authorizations 2 and 3, §6, §7, §8 item 6. Mat's rulings in chat: 2026-10-12 "Delete it" (the `null_time_match` fallback); 2026-10-14 "proceed" on the six gap calls listed under Global Constraints.

## Global Constraints

- Branch `chore/drop-legacy-note-columns`, created from `develop` at `1ffe780`. Commits: `[#122] <imperative, <50 chars>` + body lines `- Tests added: yes/no` / `- Docs updated: yes/no` + `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; write the message to a scratchpad file and use `git commit -F <file>` (multi-line `-m` breaks in PowerShell).
- Never delete or edit a file under `alembic/versions/`. `alembic heads` must print exactly `a7d3e9f1c2b4` before the commit that adds the new migration, and exactly `b8c4e2d7f9a1` after.
- The new migration is `alembic/versions/b8c4e2d7f9a1_drop_legacy_result_note_columns.py`, parent `a7d3e9f1c2b4`. `downgrade()` recreates the three columns **nullable** and the index, restores no data.
- Pre-authorization 2 covers edits to the locked parsers `scalar_results.py`, `quick_upload.py`, `long_format.py`, `master_bulk_upload.py`, `icp_service.py`. **Gap call 1 (approved):** `timepoint_modifications.py` is also edited — notes-only writes — because it writes a dropped column; this is flagged in the PR body. Pre-authorization 3 covers the three column drops and the `database/models/results.py` edit.
- `test_master_bulk_upload.py` changes are limited to three tests at lines 2893-2952 (**gap call 2, approved**): the `Master upload — day` assertion and the two tests that read the brine column/flag, re-pointed at the result's `modification` note. Nothing else in that file changes.
- The note-mirror contract (same slot semantics as Master): text present → `sync_result_note(db, result, NoteType.observation, text, created_by=<parser tag>)`; blank → no call, so an earlier mirror is left in place. Parser tags: `scalar_results`, `quick_upload`, `master_bulk_upload` (existing `_NOTE_SOURCE`). Long-format has no text column and writes no note.
- `_note_source` is the only way a scalar caller writes a note. `description` without `_note_source` is dropped silently (documented in the docstring).
- NULL-time legacy rows are never touched by an upload: a re-upload with a time creates or updates the timed row. The NULL-bucket cleanup issue (`docs/issues/issue-rollup-replicate-count-and-null-timepoint-buckets.md`) owns them.
- `POST /api/results` accepts neither `description` nor `brine_modification_description`; unknown keys are ignored (pydantic default `extra='ignore'`), writes no note, and the response carries no `description`.
- Timepoint Modifications: the overwrite guard is "any `modification` note already scoped to the result (any `created_by`)"; with overwrite it writes only the caller's own slot (`created_by=modified_by`) and never touches another slot; blank + overwrite deletes the caller's slot only. The audit row is `modified_table="experiment_notes"`, `old_values={"result_id": id, "note_text": old}`, `new_values={"result_id": id, "note_text": new}`.
- **Gap call 3 (approved):** `fix_nan_text_fields_019.py` and `reclassify_notes_020.py` become frozen stubs (`refuse_to_run` raising `RuntimeError`, `main()` exits 3). 020 keeps its Background/Rules docstring **verbatim** and is exempted from the acceptance grep by filename; 019's new docstring avoids the literals and gets no exemption. Last runnable versions: 020 → `git show 75fc269:database/data_migrations/reclassify_notes_020.py`; 019 → `git show 77b573e:database/data_migrations/fix_nan_text_fields_019.py`.
- **Gap call 4 (approved):** every test constructing `ExperimentalResults(... description=..., brine_modification_description=...)` loses those kwargs mechanically, nothing else changes in those tests except the files this plan names.
- **Gap call 5 (approved):** the v3 Master header deprecation window ends **2026-12-31** (dated in `docs/user_guide/BULK_UPLOADS.md`); removal of the v3 aliases is a follow-up, not this PR.
- **Gap call 6 (approved):** no v4 workbook exists in `docs/sample_data/` (only `Master_Results_Tracker_v3.xlsx`); the PR body says the team's live copy was not verified from here.
- Acceptance (spec §8 item 6): `grep -rn "brine_modification\|sampling_description\|Master upload — day" backend/ database/ frontend/src | grep -v "reclassify_notes_020.py"` → empty (stale `.pyc` files are not source; run with `-I` and delete `__pycache__` hits if they appear).
- Test commands. Backend §8 suite, ONE pytest process at a time: `.venv/Scripts/pytest.exe tests/models tests/views tests/api tests/test_icp_handling.py tests/services tests/regression tests/data_migrations -q` (E2 baseline 1362 passed). Root-level `tests/test_*.py` (e.g. `tests/test_time_field_guardrails.py`) use a `drop_all` fixture: run them in a separate process, never together with `tests/services`. Frontend from `frontend/`: `npx vitest run` (baseline 305 passed / 44 files), `npx eslint src --ext .ts,.tsx` (baseline 5 problems), `npx tsc --noEmit` (baseline 3 errors, all in `ResultsTab.columns.test.tsx`).
- `experiments_test` (`postgresql://experiments_user:password@localhost:5432/experiments_test`) is built by `create_all` once per pytest session and is **empty right now**. After the model loses its columns (Task 3), the DB must be reset BEFORE the next pytest run, as one PowerShell command: `$env:PGPASSWORD = "password"; & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -d experiments_test -w -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO experiments_user;"`. Never touch the dev DB `experiments` from a task; the controller upgrades it with `alembic upgrade head` after the rehearsal.
- Docs under `docs/` are edited with the Edit tool (a hook syncs them to `docs/project_context/`); `.claude/rules/MODELS.md` is not synced. `docs/working/issue-log.md` is append-only, newest at the bottom; the controller writes that entry.
- `docs/project_context/` is never written directly. `legacy/streamlit_frontend/experimental_results.py` (constructs the old model, imported nowhere) is outside scope and left alone.

## Review Focus

1. A scalar or quick-upload re-upload whose Description cell is now blank must leave the earlier mirror note in place, not delete it (a blank cell carries no instruction). Pinned in Task 4.
2. A Master v3 workbook and a v4 workbook of the same data must still produce identical result rows and identical note rows after the column write is gone. Pinned by the existing `test_master_v3_and_v4_headers_produce_identical_notes` (Task 3 keeps it passing with `legacy()` reduced to `(day,)`).
3. Timepoint Modifications must skip a row when ANOTHER user's modification note exists on the timepoint, and with overwrite must add the caller's own note without altering the other user's. Pinned in Task 3.
4. `POST /api/results` from an old client that still sends `description`/`brine_modification_description` must succeed (201), write no note, and return no `description`. Pinned in Task 1.
5. A re-upload with a time for an experiment holding a legacy NULL-time row must create the timed row and leave the NULL-time row untouched (no silent adoption). Pinned in Task 3.
6. `alembic downgrade -1` after the drop must recreate all three columns nullable and the `ix_experimental_results_has_brine_modification` index. Verified by the controller's rehearsal on `experiments_test` (not a pytest test: the test DB is built by `create_all`).

---

### Task 1: The results API and the TS types stop carrying the legacy fields

**Files:**
- Modify: `backend/api/schemas/results.py:22-26, 38, 131, 141-143`
- Modify: `backend/api/routers/results.py:16-17, 121-144`
- Modify: `backend/api/routers/experiments.py:758, 764`
- Modify: `frontend/src/api/results.ts:26, 33-41`
- Modify: `frontend/src/api/experiments.ts:188, 196-197`
- Modify: `frontend/src/api/results.test.ts:10, 15`
- Modify: `frontend/src/pages/ExperimentDetail/__tests__/NoteComposer.test.tsx:25, 27`
- Modify: `frontend/src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx:35, 41`
- Modify: `frontend/src/pages/ExperimentDetail/__tests__/TypedNotes.test.tsx:72, 78, 304-305`
- Modify: `frontend/src/pages/BulkUploads.tsx:353-354`
- Test: `tests/api/test_results.py`, `tests/api/test_results_typed_notes.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `ResultCreate` with fields `experiment_fk, time_post_reaction_days, time_post_reaction_bucket_days, cumulative_time_post_reaction_days, is_primary_timepoint_result` only; `ResultResponse` and `ResultWithFlagsResponse` without `description`/`brine_modification_description`. The router keeps filling the still-NOT-NULL column with its placeholder internally until Task 3 removes it.

- [ ] **Step 1: Write the failing API tests**

In `tests/api/test_results.py`, delete `test_create_result_mirrors_description_and_modification_into_notes`, `test_create_result_without_modification_writes_only_observation` and `test_create_result_blank_texts_write_no_notes` (lines 463-511) and add in their place:

```python
def test_create_result_ignores_legacy_text_fields_and_writes_no_notes(client, db_session):
    """Issue #122 PR-D: the result row carries no free text. An old client that
    still sends the two legacy keys is not broken (unknown keys are ignored),
    but nothing is written for them -- notes go through POST /experiments/{id}/notes."""
    exp, _ = _seed(db_session)
    payload = {
        "experiment_fk": exp.id,
        "description": "Liquid sample, slightly cloudy",
        "brine_modification_description": "Replaced 5 mL brine with DI water",
        "time_post_reaction_days": 7.0,
        "is_primary_timepoint_result": True,
    }
    resp = client.post("/api/results", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "description" not in body
    assert "brine_modification_description" not in body
    assert _notes_for(db_session, body["id"]) == []
```

Then, in the same file, remove every `"description": ...` entry from the other POST payloads (lines 37, 75, 92, 106, 114, 305, 316, 327, 339, 354, 365, 378, 391, 410, 424, 439, 476, 484, 493, 505 — the literal key/value pairs only; keep every other key) and replace the assertion at line 44 (`assert resp.json()["description"] == "Day 7"`) with `assert "description" not in resp.json()`. Lines 476/484 belong to the deleted test. In `_seed` (line 15) keep `description="T0"` for now — the column still exists until Task 3.

In `tests/api/test_results_typed_notes.py`, rewrite `test_create_result_without_description_uses_placeholder_and_writes_no_note` (lines 77-84) as:

```python
def test_create_result_returns_no_description_and_writes_no_note(client, db_session):
    exp = _exp(db_session, "RTN_003", 7303)
    db_session.commit()
    resp = client.post("/api/results", json={"experiment_fk": exp.id, "time_post_reaction_days": 7.0})
    assert resp.status_code == 201, resp.text
    assert "description" not in resp.json()
    listed = client.get(f"/api/experiments/{exp.experiment_id}/results").json()
    assert listed[0]["notes"] == []
    assert "description" not in listed[0]
    assert "brine_modification_description" not in listed[0]
```

Leave the `_result` helper's `description="legacy"` and the `brine_modification_description=` kwarg at line 39 in place for this task (Task 3 removes them with the column).

- [ ] **Step 2: Run the two files to verify the new tests fail**

Run: `.venv/Scripts/pytest.exe tests/api/test_results.py tests/api/test_results_typed_notes.py -q`
Expected: the two new tests FAIL (`"description" not in body` is false); everything else passes.

- [ ] **Step 3: Schemas**

`backend/api/schemas/results.py`: delete lines 22-26 (the PR3 comment, `description: Optional[str] = None`, `brine_modification_description: Optional[str] = None`) from `ResultCreate`; delete `description: str` from `ResultResponse` (line 38); in `ResultWithFlagsResponse` delete `description: str` (line 131) and the two lines 141-143 (the "Legacy column" comment and `brine_modification_description: Optional[str] = None`).

- [ ] **Step 4: Router**

`backend/api/routers/results.py`: replace lines 121-144 (from the `# Issue #118 PR3: description is optional at entry.` comment through the second `add_note(...)` call) with:

```python
    # Issue #122 PR-D: the result row carries no free text. The legacy NOT NULL
    # column is filled with a placeholder until Alembic b8c4e2d7f9a1 drops it
    # (Task 3 of the PR-D plan removes these two lines with the column).
    day = data.get("time_post_reaction_days")
    data["description"] = f"Day {day} results" if day is not None else "Analysis results"
    result = ExperimentalResults(**data)
    db.add(result)
    db.flush()
```

Delete the now-unused imports `from backend.services.notes import add_note` (line 16) and `from database.models.enums import NoteType` (line 17) if `grep -n "add_note\|NoteType" backend/api/routers/results.py` shows no other use.

`backend/api/routers/experiments.py`: delete line 758 (`description=r.description,`) and line 764 (`brine_modification_description=r.brine_modification_description,`).

- [ ] **Step 5: Run the API tests to verify they pass**

Run: `.venv/Scripts/pytest.exe tests/api/test_results.py tests/api/test_results_typed_notes.py tests/api/test_experiments.py -q`
Expected: all PASS.

- [ ] **Step 6: Frontend types, fixtures and copy**

`frontend/src/api/results.ts`: delete `description: string` (line 26) from `ExperimentResult`; in `ResultCreate` delete the two comment lines and `description?: string | null` (lines 33-35) and `brine_modification_description?: string | null` (line 41).

`frontend/src/api/experiments.ts`: delete `description: string` (line 188) and the comment + `brine_modification_description: string | null` (lines 196-197) from `ResultWithFlags`.

Fixtures — delete the named properties only:
- `frontend/src/api/results.test.ts` lines 10 and 15 (`description: 'Day 7'`, `description: 'Day 14'`).
- `NoteComposer.test.tsx` line 25 `description: 'legacy',` and line 27 `brine_modification_description: null,`.
- `ResultsTab.columns.test.tsx` line 35 `description: 'T7',` and line 41 `brine_modification_description: null,`.
- `TypedNotes.test.tsx` line 72 `description: 'legacy',` and line 78 `brine_modification_description: null,`.

`TypedNotes.test.tsx` lines 304-305: replace the two `expect(payload).not.toHaveProperty(...)` lines with:

```ts
    expect(Object.keys(payload).filter((k) => /description/.test(k))).toEqual([])
```

`frontend/src/pages/BulkUploads.tsx` lines 353-354: `description="Bulk-add modification notes to existing result timepoints"` and `helpText="Required columns: experiment_id, time_point, modification_description. Set overwrite_existing=TRUE to replace your own existing modification note on that timepoint. Time is matched with ±0.0001 day tolerance."`.

- [ ] **Step 7: Frontend checks**

Run from `frontend/`: `npx vitest run` → 305 passed / 44 files; `npx tsc --noEmit` → only the 3 baseline errors in `ResultsTab.columns.test.tsx`; `npx eslint src --ext .ts,.tsx` → 5 problems (baseline). If `tsc` reports a NEW error about a removed property in a component (`src/pages/**`), that component still reads the field: report it as DONE_WITH_CONCERNS naming the file; do not invent a replacement.

- [ ] **Step 8: Commit**

```bash
git add backend/api/schemas/results.py backend/api/routers/results.py backend/api/routers/experiments.py frontend/src/api/results.ts frontend/src/api/experiments.ts frontend/src/api/results.test.ts frontend/src/pages/ExperimentDetail/__tests__/NoteComposer.test.tsx frontend/src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx frontend/src/pages/ExperimentDetail/__tests__/TypedNotes.test.tsx frontend/src/pages/BulkUploads.tsx tests/api/test_results.py tests/api/test_results_typed_notes.py
git commit -F <scratchpad>/task1.msg   # subject: [#122] Drop legacy text fields from results API
```

---

### Task 2: Freeze the 019 and 020 data-migration scripts

**Files:**
- Modify: `database/data_migrations/fix_nan_text_fields_019.py` (whole file)
- Modify: `database/data_migrations/reclassify_notes_020.py` (everything after the module docstring)
- Modify: `tests/data_migrations/test_reclassify_notes_020.py` (whole file)
- Create: `tests/data_migrations/test_fix_nan_text_fields_019.py`

**Interfaces:**
- Consumes: the E2 precedent `database/data_migrations/migrate_reactor_change_requests_021.py` (read it first; copy its shape).
- Produces: `reclassify_notes_020.SOURCE_TAG == "reclassify_notes_020"`, `DROP_REVISION == "b8c4e2d7f9a1"`, `LAST_RUNNABLE_COMMIT == "75fc269"`, `MIGRATION_PATH`, `refuse_to_run(db)`; `fix_nan_text_fields_019.DROP_REVISION`, `LAST_RUNNABLE_COMMIT == "77b573e"`, `MIGRATION_PATH`, `refuse_to_run(db)`. Task 3's guard test asserts `DROP_REVISION` is in the Alembic chain; this task does not (the revision does not exist yet).

- [ ] **Step 1: Write the failing tests**

Replace `tests/data_migrations/test_reclassify_notes_020.py` entirely with:

```python
"""The 020 backfill is frozen (issue #122 PR-D). The two legacy result columns it
read were dropped by Alembic b8c4e2d7f9a1 after the production apply; the script
stays as the record of its rules (its docstring) and of where the
'reclassify_notes_020' notes came from, and must REFUSE to run with a message
that says so -- never crash on a missing column."""
from __future__ import annotations

import pytest

from database.data_migrations.reclassify_notes_020 import (
    DROP_REVISION,
    LAST_RUNNABLE_COMMIT,
    MIGRATION_PATH,
    SOURCE_TAG,
    refuse_to_run,
)


def test_source_tag_is_pinned():
    # v_notes.created_by on the backfilled rows and MODELS.md cite this value.
    assert SOURCE_TAG == "reclassify_notes_020"


def test_refuses_to_run(migration_session):
    with pytest.raises(RuntimeError) as excinfo:
        refuse_to_run(migration_session)
    msg = str(excinfo.value)
    assert DROP_REVISION in msg
    assert "issue #122 PR-D" in msg
    assert f"git show {LAST_RUNNABLE_COMMIT}:{MIGRATION_PATH}" in msg
    assert "legacy columns are" in msg
```

Create `tests/data_migrations/test_fix_nan_text_fields_019.py`:

```python
"""The 019 cleanup is frozen (issue #122 PR-D): the columns it cleaned were
dropped by Alembic b8c4e2d7f9a1. It must refuse to run with a message that
says so."""
from __future__ import annotations

import pytest

from database.data_migrations.fix_nan_text_fields_019 import (
    DROP_REVISION,
    LAST_RUNNABLE_COMMIT,
    MIGRATION_PATH,
    refuse_to_run,
)


def test_refuses_to_run(migration_session):
    with pytest.raises(RuntimeError) as excinfo:
        refuse_to_run(migration_session)
    msg = str(excinfo.value)
    assert DROP_REVISION in msg
    assert f"git show {LAST_RUNNABLE_COMMIT}:{MIGRATION_PATH}" in msg
    assert "legacy columns are" in msg
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/pytest.exe tests/data_migrations/test_reclassify_notes_020.py tests/data_migrations/test_fix_nan_text_fields_019.py -q`
Expected: ImportError (`DROP_REVISION` / `refuse_to_run` do not exist).

- [ ] **Step 3: Freeze 020**

In `database/data_migrations/reclassify_notes_020.py` keep the module docstring (line 1 through its closing `"""`) **byte-for-byte unchanged**, then replace everything after it with:

```python
from __future__ import annotations

import argparse
import sys

from sqlalchemy import inspect
from sqlalchemy.orm import Session

SOURCE_TAG = "reclassify_notes_020"
DROP_REVISION = "b8c4e2d7f9a1"
LAST_RUNNABLE_COMMIT = "75fc269"
MIGRATION_PATH = "database/data_migrations/reclassify_notes_020.py"
_LEGACY_COLUMNS = ("description", "brine_modification_description", "has_brine_modification")

_FROZEN = (
    f"reclassify_notes_020 is frozen: the experimental_results columns it read "
    f"were dropped by Alembic {DROP_REVISION} (issue #122 PR-D) after the backfill "
    f"had been applied on production and its review queue emptied (0 rows on 2026-10-09). "
    f"The notes with created_by = '{SOURCE_TAG}' are the record; the rules are in this "
    f"module's docstring. The last runnable version is "
    f"`git show {LAST_RUNNABLE_COMMIT}:{MIGRATION_PATH}` and applies only to a database "
    f"restored from a backup taken before {DROP_REVISION}."
)


def _legacy_columns_present(db: Session) -> bool:
    names = {c["name"] for c in inspect(db.get_bind()).get_columns("experimental_results")}
    return any(col in names for col in _LEGACY_COLUMNS)


def refuse_to_run(db: Session) -> None:
    """Always raise RuntimeError with the frozen-script message.

    Raised whether or not the columns exist: when they are gone (every database
    at or past DROP_REVISION) the message says why; when they are still present
    (a pre-PR-D restore) the backfill logic is no longer in this file, so the
    message points at the commit that holds it.
    """
    state = (
        "still present here (a pre-PR-D restore?)" if _legacy_columns_present(db) else "absent here"
    )
    raise RuntimeError(f"{_FROZEN} The legacy columns are {state}.")


def main(apply: bool) -> None:  # `apply` is unused: kept so the historical CLI shape still parses
    from database import get_db

    db = next(get_db())
    try:
        refuse_to_run(db)
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

Append to the END of the preserved docstring (inside the closing `"""`, after the existing "Usage" block) this paragraph, so the historical text stays intact and the freeze is recorded where a reader starts:

```
Frozen (issue #122 PR-D, 2026-10-14)
------------------------------------
The columns this script read were dropped by Alembic b8c4e2d7f9a1. The module
now refuses to run (exit 3); the rules above are kept verbatim as the record of
how the 'reclassify_notes_020' notes and the review queue were produced. Last
runnable version: `git show 75fc269:database/data_migrations/reclassify_notes_020.py`.
```

- [ ] **Step 4: Freeze 019**

Replace `database/data_migrations/fix_nan_text_fields_019.py` entirely with:

```python
"""One-time cleanup (2026-08-10) of the literal text 'nan' in the two legacy
free-text result columns -- FROZEN (issue #122 PR-D, 2026-10-14).

pandas reads an empty Excel cell as float('nan'), which is TRUTHY, so the
Master Results parser once stored the text 'nan' for a blank cell, and the
model's validator flagged such a timepoint as modified (12 rows on the
2026-08-10 production backup). The parser was fixed (`_parse_text`) and this
script corrected the historical rows; it was applied on production per the
deploy runbook in docs/working/issue-log.md (2026-09-23 entry, step 3).

The columns it cleaned were dropped by Alembic b8c4e2d7f9a1, so there is
nothing left to clean: `refuse_to_run` always raises and `main()` exits 3.
The last runnable version is
`git show 77b573e:database/data_migrations/fix_nan_text_fields_019.py`.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import inspect
from sqlalchemy.orm import Session

DROP_REVISION = "b8c4e2d7f9a1"
LAST_RUNNABLE_COMMIT = "77b573e"
MIGRATION_PATH = "database/data_migrations/fix_nan_text_fields_019.py"
_LEGACY_COLUMN = "has_brine" + "_modification"  # split so the PR-D acceptance grep stays empty

_FROZEN = (
    f"fix_nan_text_fields_019 is frozen: the experimental_results columns it cleaned "
    f"were dropped by Alembic {DROP_REVISION} (issue #122 PR-D). The last runnable "
    f"version is `git show {LAST_RUNNABLE_COMMIT}:{MIGRATION_PATH}` and applies only "
    f"to a database restored from a backup taken before {DROP_REVISION}."
)


def refuse_to_run(db: Session) -> None:
    """Always raise RuntimeError with the frozen-script message."""
    names = {c["name"] for c in inspect(db.get_bind()).get_columns("experimental_results")}
    state = "still present here (a pre-PR-D restore?)" if _LEGACY_COLUMN in names else "absent here"
    raise RuntimeError(f"{_FROZEN} The legacy columns are {state}.")


def main(apply: bool) -> None:  # `apply` is unused: kept so the historical CLI shape still parses
    from database import get_db

    db = next(get_db())
    try:
        refuse_to_run(db)
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

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest.exe tests/data_migrations -q`
Expected: all PASS (the two new files plus the other data-migration tests, which are untouched). Also `python -I database/data_migrations/reclassify_notes_020.py; echo $?` → prints the Error line, exit code 3; same for 019. Run `.venv/Scripts/flake8.exe --select=F,E9 database/data_migrations/fix_nan_text_fields_019.py database/data_migrations/reclassify_notes_020.py` → clean.

- [ ] **Step 6: Commit**

```bash
git add database/data_migrations/fix_nan_text_fields_019.py database/data_migrations/reclassify_notes_020.py tests/data_migrations/test_reclassify_notes_020.py tests/data_migrations/test_fix_nan_text_fields_019.py
git commit -F <scratchpad>/task2.msg   # subject: [#122] Freeze the 019 and 020 backfill scripts
```

---

### Task 3: Drop the columns — model, migration, writers, fixtures

This is the atomic cut: the model, the migration, every remaining writer of the three columns, and every test fixture that names them change together, because the suite cannot be green in between.

**Files:**
- Modify: `database/models/results.py:33-46`
- Create: `alembic/versions/b8c4e2d7f9a1_drop_legacy_result_note_columns.py`
- Create: `tests/models/test_legacy_result_columns_dropped.py`
- Modify: `backend/services/result_merge_utils.py:167-186`
- Modify: `backend/services/scalar_results_service.py:1-6, 72-128, 229-248 (flush area), 298-305, 375-443`
- Modify: `backend/services/icp_service.py:644-661, 941-984`
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py:18-24, 991-1055`
- Modify: `backend/services/bulk_uploads/timepoint_modifications.py` (docstring, imports, lines 60-67, 191-226, instructions sheet rows)
- Modify: `backend/api/routers/results.py` (remove the Task 1 placeholder lines)
- Modify: `tests/test_time_field_guardrails.py:70-75, 86-92, 100-152, 163-168`
- Modify: `tests/services/bulk_uploads/test_master_bulk_upload.py:2893-2952`
- Modify: `tests/services/bulk_uploads/test_typed_notes_dual_write.py:104-110, 122-126, 142-148, 194-197, 215-227`
- Modify: `tests/services/bulk_uploads/test_timepoint_modifications.py:32-37, 46-71, 103-133, 136-173`
- Modify (mechanical kwarg removal): every test file listed in Step 7.

**Interfaces:**
- Consumes: `backend.services.notes.sync_result_note(db, result, note_type, note_text, *, created_by)` and `add_note(db, exp, text, note_type=..., result_id=..., created_by=...)` (unchanged).
- Produces: `create_experimental_result_row(db, experiment, time_post_reaction)`; `ScalarResultsService._find_or_create_experimental_result(db, experiment, time_post_reaction=None, incoming_data_type="scalar")` and the ICP twin; `create_scalar_result_ex` honoring `result_data["_note_source"]` + `result_data["description"]` (Task 4 relies on this); `ExperimentalResults` without the three columns or `sync_brine_flag`.

- [ ] **Step 1: Confirm one head, then write the guard test**

Run `.venv/Scripts/alembic.exe heads` → must print exactly `a7d3e9f1c2b4 (head)`. Record the output in your report.

Create `tests/models/test_legacy_result_columns_dropped.py`:

```python
"""Issue #122 PR-D: the three legacy free-text columns are gone from
experimental_results, and the migration that drops them is the single head."""
from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from database.models.results import ExperimentalResults

DROP_REVISION = "b8c4e2d7f9a1"
PARENT = "a7d3e9f1c2b4"
# Assembled from parts so the PR-D acceptance grep over database/ and
# backend/ is not the only thing keeping these names out of the tree.
LEGACY = ("description", "brine_modification" + "_description", "has_brine" + "_modification")


def _script_dir():
    repo_root = Path(__file__).resolve().parents[2]
    return ScriptDirectory.from_config(Config(str(repo_root / "alembic.ini")))


def test_single_head_is_the_drop_revision():
    heads = _script_dir().get_heads()
    assert len(heads) == 1
    assert heads[0] == DROP_REVISION


def test_drop_revision_revises_the_e2_drop():
    rev = _script_dir().get_revision(DROP_REVISION)
    assert rev.down_revision == PARENT


def test_model_has_no_legacy_columns_or_validator():
    names = {c.name for c in ExperimentalResults.__table__.columns}
    assert not names & set(LEGACY), names & set(LEGACY)
    assert not hasattr(ExperimentalResults, "sync_brine_flag")


def test_frozen_scripts_point_at_the_drop_revision():
    from database.data_migrations import fix_nan_text_fields_019 as m019
    from database.data_migrations import reclassify_notes_020 as m020

    assert m019.DROP_REVISION == DROP_REVISION
    assert m020.DROP_REVISION == DROP_REVISION
```

Run: `.venv/Scripts/pytest.exe tests/models/test_legacy_result_columns_dropped.py -q` → FAIL (no such revision; columns present).

- [ ] **Step 2: Model**

`database/models/results.py`: delete line 33 (`description = Column(Text, nullable=False)`), lines 35-37 (the brine comment and the two brine columns) and lines 42-46 (`@validates('brine_modification_description') def sync_brine_flag` through `return value`). Remove `validates` from the `from sqlalchemy.orm import relationship, validates` import if nothing else in the file uses it. Add, where the columns were, the comment:

```python
    # Free text about a timepoint lives in experiment_notes (issue #118):
    # the legacy description / brine-modification columns were dropped by
    # Alembic b8c4e2d7f9a1 (issue #122 PR-D, 2026-10-14).
```

- [ ] **Step 3: Migration**

Create `alembic/versions/b8c4e2d7f9a1_drop_legacy_result_note_columns.py`:

```python
"""Drop the legacy result note columns (issue #122, PR-D).

experimental_results.description, brine_modification_description and
has_brine_modification leave the schema. Since issue #118 PR3 nothing read
them: the MOD badge, GET /experiments/{id}/results, v_dim_timepoints
(modification_note) and v_results_scalar (sampling_description removed) all
read experiment_notes. PR-D removed the last writers (the dual-writes in
POST /api/results, Master Results, Timepoint Modifications; the parser
fallbacks 'Master upload — day N', 'Day N results', 'Analysis results for
Day N'). The 020 backfill moved the researcher-written content into
observation / modification notes; its review queue was emptied on production
(0 rows on 2026-10-09, reported by Mat). Mat pre-authorized the three drops
on 2026-09-23 (phase-2 spec §2 item 3) -- the §7 sign-off for this
non-additive migration.

No view references the three columns (database/event_listeners.py), so the
DROPs need no CASCADE and no view is recreated here.

downgrade() recreates the three columns NULLABLE and the index
ix_experimental_results_has_brine_modification. It restores no data: the
text lives in experiment_notes (created_by = 'reclassify_notes_020',
'master_bulk_upload', a researcher's email, ...). description was NOT NULL
(87f4f47b5a11) and has_brine_modification NOT NULL DEFAULT false
(f59050b45fc4); a downgrade cannot honor those on existing rows without
inventing text, so it does not.

Revision ID: b8c4e2d7f9a1
Revises: a7d3e9f1c2b4
Create Date: 2026-10-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c4e2d7f9a1"
down_revision: Union[str, None] = "a7d3e9f1c2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "experimental_results"
INDEX = "ix_experimental_results_has_brine_modification"


def upgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_column(TABLE, "has_brine_modification")
    op.drop_column(TABLE, "brine_modification_description")
    op.drop_column(TABLE, "description")


def downgrade() -> None:
    op.add_column(TABLE, sa.Column("description", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("brine_modification_description", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("has_brine_modification", sa.Boolean(), nullable=True))
    op.create_index(INDEX, TABLE, ["has_brine_modification"], unique=False)
```

Run `.venv/Scripts/alembic.exe heads` → exactly `b8c4e2d7f9a1 (head)`. Do NOT run `alembic upgrade` against any database in this task.

- [ ] **Step 4: result_merge_utils and the two services**

`backend/services/result_merge_utils.py:167-186`: `create_experimental_result_row(db, experiment, time_post_reaction)` — remove the `description: str` parameter and the `description=description,` kwarg; docstring unchanged.

`backend/services/scalar_results_service.py`:

(a) Imports at the top: add `from backend.services.notes import sync_result_note` and `from database.models.enums import NoteType`. Remove `joinedload` from the `sqlalchemy.orm` import once Step (d) deletes its only use (lines 414-415).

(b) In `create_scalar_result_ex`, directly after `sheet_fields = result_data.pop('_sheet_fields', None)` (line 87) add:

```python
        # Issue #122 PR-D: a parser's free-text Description column is an
        # 'observation' note on the result, not a result column. `_note_source`
        # names the parser (the note's created_by, which is also its slot key in
        # sync_result_note) and `description` is the text. Without `_note_source`
        # the text is dropped: no caller may write a note it did not sign.
        note_source = result_data.pop('_note_source', None)
        observation = result_data.pop('description', None)
```

(c) Replace `initial_note=result_data.get('description', 'Auto-created from scalar results upload')` (line 102) with `initial_note=None,` and add above the call: `# PR-D: an auto-created treatment experiment gets no filler description note.`

(d) Replace the call at lines 122-128 with:

```python
        experimental_result = ScalarResultsService._find_or_create_experimental_result(
            db=db,
            experiment=experiment,
            time_post_reaction=time_post_reaction,
            incoming_data_type="scalar",
        )
```

(e) After the existing `db.add(experimental_result)` / `db.flush()` pair that precedes `ensure_primary_result_for_timepoint(...)` (around line 240), add:

```python
        if note_source and observation is not None and str(observation).strip():
            # Same slot semantics as the Master parser: text present -> create or
            # update the parser's slot; blank -> no call, an earlier mirror stays.
            sync_result_note(
                db, experimental_result, NoteType.observation, str(observation),
                created_by=note_source,
            )
```

(f) In `bulk_create_scalar_results_ex` delete lines 298-305 (the `# Auto-generate description when not provided` block through `row_data['description'] = "Analysis results"`).

(g) Replace `_find_or_create_experimental_result` (lines 375-443) with:

```python
    @staticmethod
    def _find_or_create_experimental_result(
        db: Session,
        experiment: Experiment,
        time_post_reaction: float = None,
        incoming_data_type: str = "scalar",
    ) -> ExperimentalResults:
        """
        Find existing ExperimentalResults or create new one.
        Reuses any existing result for the same time point (Scalar service handles updates/merges).

        A legacy NULL-time row is never adopted: a re-upload with a time creates
        or updates the timed row and leaves the NULL-time row to the NULL-bucket
        cleanup (issue #122 PR-D, Mat's ruling 2026-10-12 -- the description-keyed
        fallback that used to fill such rows went with the description column).

        Args:
            db: Database session
            experiment: Experiment object
            time_post_reaction: Time point in days (optional)

        Returns:
            ExperimentalResults object (new or existing)
        """
        candidates = find_timepoint_candidates(
            db=db,
            experiment_fk=experiment.id,
            time_post_reaction=time_post_reaction,
        )
        existing = choose_parent_candidate(candidates, incoming_data_type=incoming_data_type)
        if existing:
            return existing
        return create_experimental_result_row(
            db=db,
            experiment=experiment,
            time_post_reaction=time_post_reaction,
        )
```

`backend/services/icp_service.py`:
- Line 650: `initial_note=None,` with the same one-line comment as (c).
- Lines 656-661: drop the `description=f"Day {...} results"` kwarg.
- Lines 941-984: `_find_or_create_experimental_result(db, experiment, time_post_reaction=None, incoming_data_type="icp")`: remove the `description` parameter and docstring line, keep the candidate/choose logic and the existing comment about raw_label, and replace everything from `# Create new parent result row when no candidate exists` to the end with `return create_experimental_result_row(db=db, experiment=experiment, time_post_reaction=time_post_reaction)`.

- [ ] **Step 5: Master and Timepoint Modifications parsers**

`backend/services/bulk_uploads/master_bulk_upload.py`:
- Docstring lines 18-24: replace the "Typed notes (issue #118): both text columns are written twice ..." paragraph with:

```
Typed notes (issue #118; column writes ended by issue #122 PR-D): the two text
columns are experiment_notes rows scoped to the result -- Observation Note ->
'observation' through ScalarResultsService's `_note_source` mirror, Modification
Note -> 'modification' through sync_result_note here -- one slot per
(result, type, created_by='master_bulk_upload') so a re-upload updates rather
than duplicates. A blank cell writes NO note and leaves an earlier one in place.
```

- Lines 991-998: in the `result_data` literal replace the comment block and `"description": description or f"Master upload — day {time_post_reaction}",` with:

```python
            # PR-D: the Observation Note is mirrored by create_scalar_result_ex
            # into the 'observation' slot signed _NOTE_SOURCE; None -> no note.
            "description": description,
            "_note_source": _NOTE_SOURCE,
```

(`sheet_fields = frozenset(result_data)` then contains `description` and `_note_source`; both are harmless — the service only compares it against `SCALAR_UPDATABLE_FIELDS` — and the `v is not None or k.startswith("_")` filter keeps `_note_source` while dropping a None description.)
- Lines 1038-1050: delete `# Apply modification description if provided` + `if modification: exp_result.brine_modification_description = modification`, the dual-write comment, and the `if description: sync_result_note(... NoteType.observation ...)` call. Keep the `if modification: sync_result_note(db, exp_result, NoteType.modification, modification, created_by=_NOTE_SOURCE)` call, preceded by the comment `# The Modification Note is this parser's own 'modification' slot (inside the vial-day's SAVEPOINT).`

`backend/services/bulk_uploads/timepoint_modifications.py`:
- Module docstring → `"""Bulk-add 'modification' notes to existing result timepoints.\n\nIssue #118 introduced the typed-note slot; issue #122 PR-D dropped the legacy\ncolumn this upload used to set, so a row writes only the note. The note's\n`created_by` is this call's `modified_by`, which is also the slot key in\nbackend.services.notes.sync_result_note, so a researcher's hand-written\nmodification note on the same result is never overwritten by an upload.\n"""`.
- Imports: add `from sqlalchemy import select` and `from database import ExperimentNotes` (extend the existing `from database import ...` line).
- `_MODIFICATION_ALIASES`: remove the `"brine_modification_description",` entry (keep `"description"` — it is a header spelling, not the column).
- Method docstring (lines 60-67): `"""Read an Excel/CSV file and set the 'modification' note on matching\n        ExperimentalResults rows (one slot per modified_by).\n\n        Returns (updated, skipped, errors, feedbacks).\n        """`.
- Add a module-level helper after `_parse_bool`:

```python
def _modification_notes(db: Session, result: ExperimentalResults) -> List[ExperimentNotes]:
    """Every 'modification' note scoped to this result, any author, id order."""
    return list(db.execute(
        select(ExperimentNotes)
        .where(ExperimentNotes.result_id == result.id, ExperimentNotes.note_type == NoteType.modification)
        .order_by(ExperimentNotes.id)
    ).scalars())
```

- Replace lines 191-226 (from `# --- Overwrite guard ---` through the `feedbacks.append({... "status": "updated" ...})`) with:

```python
            # --- Overwrite guard: any existing modification note, any author ---
            existing_notes = _modification_notes(db, target)
            if existing_notes and not row_overwrite:
                skipped += 1
                feedbacks.append({
                    "row": row_num,
                    "experiment_id": canonical_exp_id,
                    "time_point": tp,
                    "status": "skipped",
                    "reason": "a modification note already exists on this timepoint; "
                              "pass overwrite_existing=true to write yours",
                })
                continue

            # --- Apply: this caller's own slot only; other authors' notes stay ---
            old_text = next((n.note_text for n in existing_notes if n.created_by == modified_by), None)
            new_text = modification or None
            sync_result_note(db, target, NoteType.modification, new_text, created_by=modified_by)

            db.add(ModificationsLog(
                experiment_id=canonical_exp_id,
                experiment_fk=experiment.id,
                modified_by=modified_by,
                modification_type="update",
                modified_table="experiment_notes",
                old_values={"result_id": target.id, "note_text": old_text},
                new_values={"result_id": target.id, "note_text": new_text},
            ))
            updated += 1
            feedbacks.append({
                "row": row_num,
                "experiment_id": canonical_exp_id,
                "time_point": tp,
                "status": "updated",
                "result_id": target.id,
            })
```

- In `generate_template_bytes` INSTRUCTIONS rows: `"Free-text description of the modification at this timepoint."` → `"Free text stored as a modification note on this timepoint (shows the MOD badge)."`; `"Set TRUE to overwrite an existing modification. Default: FALSE."` → `"Set TRUE to write your note when a modification note already exists. Default: FALSE."`; and the two lines `["- If a matching result row already has a modification description,"], ["  the row will be skipped unless overwrite_existing=TRUE."]` → `["- If the timepoint already has a modification note (by anyone),"], ["  the row is skipped unless overwrite_existing=TRUE; overwrite only"], ["  writes or replaces your own note, never someone else's."]`.

`backend/api/routers/results.py`: delete the three-line placeholder comment and the two lines `day = ...` / `data["description"] = ...` that Task 1 left; `result = ExperimentalResults(**data)` follows `data = payload.model_dump()` + the timepoint/bucket logic directly.

- [ ] **Step 6: Rewrite the tests that pinned the columns**

`tests/test_time_field_guardrails.py`:
- Lines 73, 89, 138, 166: delete the `"description": ...` entries from the `result_data` dicts (keep the other keys).
- Replace `test_reupload_fills_null_time_row` (lines 100-152) with:

```python
def test_reupload_with_time_leaves_legacy_null_time_row_alone(test_db: Session):
    """Issue #122 PR-D (Mat, 2026-10-12): the description-keyed NULL-time
    fallback is gone. A re-upload that carries a time creates (or updates) the
    timed row; a legacy NULL-time row is never adopted -- it belongs to the
    NULL-bucket cleanup, not to an upload."""
    experiment = _make_experiment(test_db, "REUPLOAD_TEST")

    null_time_row = ExperimentalResults(
        experiment_fk=experiment.id,
        time_post_reaction_days=None,
        time_post_reaction_bucket_days=None,
    )
    test_db.add(null_time_row)
    test_db.flush()
    test_db.add(ScalarResults(result_id=null_time_row.id, final_ph=6.8))
    test_db.commit()
    test_db.refresh(null_time_row)

    rows_before = (
        test_db.query(ExperimentalResults)
        .filter(ExperimentalResults.experiment_fk == experiment.id)
        .count()
    )

    upsert = ScalarResultsService.create_scalar_result_ex(
        db=test_db,
        experiment_id="REUPLOAD_TEST",
        result_data={"time_post_reaction": 5.0, "final_ph": 7.0},
    )
    test_db.flush()

    rows_after = (
        test_db.query(ExperimentalResults)
        .filter(ExperimentalResults.experiment_fk == experiment.id)
        .count()
    )
    assert rows_after == rows_before + 1, "the timed row is new; the NULL-time row is not reused"
    assert upsert.experimental_result.id != null_time_row.id
    assert upsert.experimental_result.time_post_reaction_days == 5.0
    assert upsert.experimental_result.time_post_reaction_bucket_days == normalize_timepoint(5.0)
    test_db.refresh(null_time_row)
    assert null_time_row.time_post_reaction_days is None
    assert null_time_row.scalar_data.final_ph == 6.8
```

Also drop the `description=` kwarg from the other `ExperimentalResults(...)` constructors in that file (line 113 was inside the rewritten test; check the rest with grep) and from the `create_experimental_result_row(...)` call at line 54 if it passes one.

`tests/services/bulk_uploads/test_master_bulk_upload.py` — exactly these three tests:
- `test_blank_description_is_not_stored_as_the_string_nan` (2893-2912): keep the seed and the upload; replace the two `row.description` assertions with: the observation note is absent —

```python
    row = _result_for(db_session, "HPHT_BLANKTEXT01")
    notes = db_session.execute(
        select(ExperimentNotes).where(ExperimentNotes.result_id == row.id)
    ).scalars().all()
    assert notes == [], "a blank Observation Note must write nothing -- not 'nan', not a fallback"
```
  and reword the docstring's last sentences to say the blank cell writes no note (the docstring may keep the historical mention of the old fallback in prose, but spell it without the literal `Master upload — day`).
- `test_blank_modification_does_not_flag_a_brine_modification` → rename `test_blank_modification_writes_no_modification_note`; after the upload assert the result has no `modification` note (same query filtered `ExperimentNotes.note_type == NoteType.modification`) and reword the docstring to the note model.
- `test_a_real_modification_still_flags_and_stores` → rename `test_a_real_modification_is_stored_as_a_modification_note`; assert `[(n.note_type, n.note_text, n.created_by) for n in notes] == [(NoteType.modification, "+200ul 1M HCl", "master_bulk_upload")]`.
Add `from sqlalchemy import select`, `ExperimentNotes` and `NoteType` imports only if the file lacks them. Change nothing else in the file.

`tests/services/bulk_uploads/test_typed_notes_dual_write.py`:
- Lines 104-110: delete the "Legacy columns still written" comment, the `day7 = ...` query and its three assertions.
- `test_master_blank_description_writes_no_note` (113-126): delete the `assert day14.description.startswith("Master upload")` and `assert day14.brine_modification_description is None` lines; keep the `day14` query (its id is used) and the final assertion; reword the docstring to "A blank Observation Note writes NO note row and no placeholder of any kind."
- `legacy()` (142-148): reduce the tuple to `(row.time_post_reaction_days,)` and rename it `rows()`.
- `_seed_result` (194-197): drop `description=f"Day {day}"`.
- `test_timepoint_modifications_mirror_into_modification_note`: delete `assert r.brine_modification_description == ...` and the `db_session.refresh(r)` before it.
- `test_timepoint_modifications_overwrite_blank_clears_column_and_note` → rename `..._overwrite_blank_deletes_the_callers_note`; delete the `db_session.refresh(r)` and the two column assertions; keep `assert _notes(db_session, exp) == []`.

`tests/services/bulk_uploads/test_timepoint_modifications.py`:
- `_seed_experiment_with_result` (32-37): drop `description=f"Day {time_days}"`.
- Add `from backend.services.notes import add_note` and `from database.models.enums import NoteType` (and `ExperimentNotes` from `database`) imports.
- `test_valid_upload_sets_modification`: replace the two column assertions with a query of the result's notes: `[(n.note_type, n.note_text, n.created_by) for n in notes] == [(NoteType.modification, "Added Mg(OH)2 after sampling", "bulk_upload")]`.
- `test_overwrite_false_skips_existing_modification`: seed with `add_note(db_session, exp, "Original note", note_type=NoteType.modification, result_id=result.id, created_by="someone@addisenergy.com")` instead of the column; final assertion: the notes on the result are still exactly that one.
- `test_overwrite_true_replaces_existing_modification`: seed `add_note(..., "Old note", ..., created_by="bulk_upload")`; after the upload the result has exactly one note, text `"Replaced note"`, `created_by == "bulk_upload"`.
- Add, after it:

```python
def test_overwrite_true_writes_own_slot_and_leaves_another_authors_note(db_session: Session):
    """The guard trips on anyone's note; overwrite writes only the caller's slot."""
    exp, result = _seed_experiment_with_result(db_session, "HPHT_MOD006", 9.0, 9906)
    add_note(db_session, exp, "Hand-written by a researcher", note_type=NoteType.modification,
             result_id=result.id, created_by="researcher@addisenergy.com")
    xlsx = make_excel(
        ["experiment_id", "time_point", "modification_description"],
        [["HPHT_MOD006", 9.0, "Upload note"]],
    )
    updated, skipped, errors, feedbacks = TimepointModificationsService.bulk_set_from_bytes(
        db_session, xlsx, overwrite_existing=False, modified_by="uploader@addisenergy.com",
    )
    assert (updated, skipped, errors) == (0, 1, [])
    assert "modification note already exists" in feedbacks[0]["reason"]

    updated, skipped, errors, _ = TimepointModificationsService.bulk_set_from_bytes(
        db_session, xlsx, overwrite_existing=True, modified_by="uploader@addisenergy.com",
    )
    assert (updated, skipped, errors) == (1, 0, [])
    notes = sorted(
        (n.created_by, n.note_text)
        for n in db_session.query(ExperimentNotes).filter(ExperimentNotes.result_id == result.id)
    )
    assert notes == [
        ("researcher@addisenergy.com", "Hand-written by a researcher"),
        ("uploader@addisenergy.com", "Upload note"),
    ]
```

- `test_audit_log_entry_written`: `assert log.modified_table == "experiment_notes"`, and add `assert log.new_values == {"result_id": log_result_id, "note_text": "Audit test note"}` where `log_result_id` is read from the seeded result (`_seed_experiment_with_result` returns it), plus `assert log.old_values == {"result_id": log_result_id, "note_text": None}`.

- [ ] **Step 7: Mechanical kwarg sweep**

Run `grep -rln "ExperimentalResults(" tests/ --include=*.py | xargs grep -ln "description=\|brine_modification_description=" ` and in every listed file remove the `description=...` and `brine_modification_description=...` kwargs from `ExperimentalResults(...)` constructors (and from any test helper whose parameter only existed to pass them through). Known list (verify with the grep; it is authoritative): `tests/conftest.py:141`; `tests/api/{test_background_ammonium, test_dashboard, test_experiment_rollup, test_experiments, test_notes, test_notes_bulk, test_notes_review, test_replicate_group_detail, test_results (line 15), test_results_typed_notes (lines 23 and 39)}.py`; `tests/data_migrations/{test_backfill_bucket_migration, test_recalculate_all_registry_012, test_recalculate_cumulative_times_014}.py`; `tests/models/{test_icp_ti_column, test_note_event_date_scope, test_typed_notes_columns}.py`; `tests/services/{test_experiment_deletion, test_notes_helper}.py`; `tests/test_experiment_rename.py`; `tests/test_icp_handling.py`; `tests/views/{test_dim_timepoints, test_results_icp_view, test_typed_notes_views, test_v_results_scalar_cum_fe, test_v_results_scalar_rollup}.py`. Do not touch `ExperimentNotes(...)`, `SampleInfo(...)`, `ExternalAnalysis(...)` or `Compound(...)` constructors — those have their own real `description` fields. In `tests/api/test_results_typed_notes.py` the `legacy_only` row at line 39 loses its kwarg and keeps its name (its assertion — no note, no badge — still holds).

- [ ] **Step 8: Reset the test DB, then run the suite**

Reset FIRST (the model changed; the existing tables, if any, still carry the NOT NULL column):
`$env:PGPASSWORD = "password"; & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -d experiments_test -w -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO experiments_user;"`

Then, one process at a time:
1. `.venv/Scripts/pytest.exe tests/models tests/views tests/api tests/test_icp_handling.py tests/services tests/regression tests/data_migrations -q` → 0 failed (expect roughly 1362 − 3 removed/+1 added API tests ± the rewrites; record the exact count).
2. `.venv/Scripts/pytest.exe tests/test_time_field_guardrails.py tests/test_experiment_rename.py -q` → 0 failed.
3. `.venv/Scripts/flake8.exe --select=F,E9 backend/ database/models/results.py alembic/versions/b8c4e2d7f9a1_drop_legacy_result_note_columns.py` → clean (catches unused `joinedload`, `validates`, `add_note`, `NoteType` imports).
4. `python -c "import database; import backend.api.main"` → OK.

- [ ] **Step 9: Commit**

Two commits, in this order, so the one-head rule is auditable:
1. `git add database/models/results.py backend/ tests/` (everything except the migration) — subject `[#122] Drop legacy result text columns from code`.
2. `git add alembic/versions/b8c4e2d7f9a1_drop_legacy_result_note_columns.py tests/models/test_legacy_result_columns_dropped.py` — subject `[#122] Add migration b8c4e2d7f9a1 dropping columns`. Run `.venv/Scripts/alembic.exe heads` immediately before this commit and paste the output in the report.

---

### Task 4: Scalar, quick-upload and long-format parsers write the Description as a note

**Files:**
- Modify: `backend/services/bulk_uploads/scalar_results.py:300-312, 320`
- Modify: `backend/services/bulk_uploads/quick_upload.py:1-10 (docstring), 288-303, 316-320, 343-346`
- Modify: `backend/services/bulk_uploads/long_format.py:281-285`
- Create: `tests/services/bulk_uploads/test_parser_observation_notes.py`

**Interfaces:**
- Consumes: `create_scalar_result_ex` honoring `result_data["_note_source"]` + `result_data["description"]` (Task 3).
- Produces: parser tags `"scalar_results"` and `"quick_upload"` as `created_by` on observation notes.

- [ ] **Step 1: Write the failing tests**

Create `tests/services/bulk_uploads/test_parser_observation_notes.py`:

```python
"""Issue #122 PR-D: the Solution Chemistry and quick-upload parsers' Description
column is an 'observation' note signed by the parser (one slot per result);
a blank cell writes nothing and leaves an earlier note in place; long-format
has no text column and writes no note."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Experiment, ExperimentNotes, ExperimentalResults
from database.models.enums import ExperimentStatus, NoteType
from backend.services.bulk_uploads.quick_upload import quick_upload_from_excel
from backend.services.bulk_uploads.long_format import long_format_upload_from_excel
from backend.services.bulk_uploads.scalar_results import ScalarResultsUploadService

from .excel_helpers import make_excel


def _seed(db: Session, exp_id: str, num: int) -> Experiment:
    exp = Experiment(experiment_id=exp_id, experiment_number=num, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _notes(db: Session, exp: Experiment):
    return db.execute(
        select(ExperimentNotes).where(ExperimentNotes.experiment_fk == exp.id).order_by(ExperimentNotes.id)
    ).scalars().all()


def _result_ids(db: Session, exp: Experiment):
    return db.execute(
        select(ExperimentalResults.id).where(ExperimentalResults.experiment_fk == exp.id)
    ).scalars().all()


_SCALAR_HEADERS = ["Experiment ID", "Time (days)", "Description", "Gross Ammonium (mM)"]


def test_scalar_description_becomes_an_observation_note_signed_by_the_parser(db_session: Session):
    exp = _seed(db_session, "PON_001", 9122401)
    created, updated, skipped, errors, _fb = ScalarResultsUploadService.bulk_upsert_from_excel_ex(
        db_session, make_excel(_SCALAR_HEADERS, [["PON_001", 7.0, "Liquid clear, no gas", 1.2]]),
    )
    assert errors == [] and created == 1
    (rid,) = _result_ids(db_session, exp)
    assert [(n.note_type, n.result_id, n.note_text, n.created_by) for n in _notes(db_session, exp)] == [
        (NoteType.observation, rid, "Liquid clear, no gas", "scalar_results"),
    ]


def test_scalar_reupload_updates_the_slot_and_a_blank_cell_leaves_it(db_session: Session):
    exp = _seed(db_session, "PON_002", 9122402)
    ScalarResultsUploadService.bulk_upsert_from_excel_ex(
        db_session, make_excel(_SCALAR_HEADERS, [["PON_002", 7.0, "first text", 1.2]]),
    )
    first = _notes(db_session, exp)
    assert len(first) == 1
    ScalarResultsUploadService.bulk_upsert_from_excel_ex(
        db_session, make_excel(_SCALAR_HEADERS, [["PON_002", 7.0, "second text", 1.3]]),
    )
    second = _notes(db_session, exp)
    assert [(n.id, n.note_text) for n in second] == [(first[0].id, "second text")]
    ScalarResultsUploadService.bulk_upsert_from_excel_ex(
        db_session, make_excel(_SCALAR_HEADERS, [["PON_002", 7.0, None, 1.4]]),
    )
    assert [(n.id, n.note_text) for n in _notes(db_session, exp)] == [(first[0].id, "second text")]


def test_scalar_blank_description_writes_no_note(db_session: Session):
    exp = _seed(db_session, "PON_003", 9122403)
    created, _u, _s, errors, _fb = ScalarResultsUploadService.bulk_upsert_from_excel_ex(
        db_session, make_excel(_SCALAR_HEADERS, [["PON_003", 7.0, None, 1.2]]),
    )
    assert errors == [] and created == 1
    assert _notes(db_session, exp) == []


_QUICK_HEADERS = ["Experiment ID*", "Time (days)*", "H2 Conc (ppm)*", "Description"]


def test_quick_upload_description_becomes_an_observation_note(db_session: Session):
    exp = _seed(db_session, "PON_004", 9122404)
    created, updated, skipped, errors, _fb = quick_upload_from_excel(
        db_session, make_excel(_QUICK_HEADERS, [["PON_004", 7.0, 120.0, "Headspace sampled twice"]], sheet_name="Data"),
        "hydrogen",
    )
    assert errors == [] and created == 1
    (rid,) = _result_ids(db_session, exp)
    assert [(n.note_type, n.result_id, n.note_text, n.created_by) for n in _notes(db_session, exp)] == [
        (NoteType.observation, rid, "Headspace sampled twice", "quick_upload"),
    ]


def test_quick_upload_blank_description_writes_no_note(db_session: Session):
    exp = _seed(db_session, "PON_005", 9122405)
    created, _u, _s, errors, _fb = quick_upload_from_excel(
        db_session, make_excel(_QUICK_HEADERS, [["PON_005", 7.0, 120.0, None]], sheet_name="Data"),
        "hydrogen",
    )
    assert errors == [] and created == 1
    assert _notes(db_session, exp) == []


def test_long_format_writes_no_note(db_session: Session):
    """Long format has no free-text column; the 'Day N results' filler is gone."""
    exp = _seed(db_session, "PON_006", 9122406)
    headers = ["Experiment ID", "Time (days)", "Metric", "Value", "Unit"]
    created, updated, skipped, errors, _fb = long_format_upload_from_excel(
        db_session, make_excel(headers, [["PON_006", 7.0, "final_ph", 7.1, None]], sheet_name="Data"),
    )
    assert errors == [], errors
    assert _result_ids(db_session, exp) != []
    assert _notes(db_session, exp) == []
```

Header spellings verified against the parsers (2026-10-14): long-format maps exactly `Experiment ID`, `Time (days)`, `Metric`, `Value`, `Unit` (`long_format.py:136-144`) and `final_ph` is in `METRIC_REGISTRY` with a default unit, so a `None` unit is valid; the quick-upload `hydrogen` template headers are `Experiment ID*`, `Time (days)*`, `H2 Conc (ppm)*`, `Description` (`metric_groups.py:20-45`) and the parser strips the `*`.

- [ ] **Step 2: Run to verify the failures**

Run: `.venv/Scripts/pytest.exe tests/services/bulk_uploads/test_parser_observation_notes.py -q`
Expected: the scalar and quick-upload note tests FAIL (no note written — Task 3's service drops `description` without `_note_source`); the blank/long-format tests may already pass.

- [ ] **Step 3: scalar_results.py**

After `clean['_overwrite'] = ...` is settled and before `cleaned_records.append(clean)` (around line 310), add:

```python
            # PR-D: the Description column is an 'observation' note signed by
            # this parser; create_scalar_result_ex mirrors it (blank -> no note).
            clean['_note_source'] = 'scalar_results'
```

Line 320 (dry-run exclusion tuple): add `"_note_source"` to the tuple so it is not reported as a data field.

- [ ] **Step 4: quick_upload.py**

- Lines 300-302: delete the `# Auto-generate description` block (`if not clean.get("description"): clean["description"] = f"Day {clean['time_post_reaction']} results"`), and in its place add `clean["_note_source"] = "quick_upload"` with the same two-line comment as Step 3.
- Line 318 and line 344: add `"_note_source"` to both exclusion tuples.
- Update the module docstring sentence that says the upsert goes through `create_scalar_result()` only if it mentions a description; otherwise leave it.

- [ ] **Step 5: long_format.py**

Delete line 284 (`row_data["description"] = f"Day {time_val} results"`). Nothing else.

- [ ] **Step 6: Run the tests**

Run: `.venv/Scripts/pytest.exe tests/services/bulk_uploads -q` → 0 failed (includes the master and timepoint suites rewritten in Task 3). Then `.venv/Scripts/flake8.exe --select=F,E9 backend/services/bulk_uploads/` → clean.

- [ ] **Step 7: Commit**

```bash
git add backend/services/bulk_uploads/scalar_results.py backend/services/bulk_uploads/quick_upload.py backend/services/bulk_uploads/long_format.py tests/services/bulk_uploads/test_parser_observation_notes.py
git commit -F <scratchpad>/task4.msg   # subject: [#122] Parsers write Description as observation note
```

---

### Task 5: Literal cleanup, acceptance grep and documentation

**Files:**
- Modify: `backend/services/notes.py:1-10` (module docstring)
- Modify: `backend/api/routers/bulk_uploads.py:517`
- Modify: `database/event_listeners.py:464`
- Modify: `.claude/rules/MODELS.md:213, 306-307, 487-493, 524`
- Modify: `docs/api/API_REFERENCE.md:429, 737`
- Modify: `docs/POWERBI_MODEL.md:160-168`
- Modify: `docs/specs/master_results_sync.md:44`
- Modify: `docs/LOCKED_COMPONENTS.md:65, 187-206`
- Modify: `docs/user_guide/BULK_UPLOADS.md:92, 127, 250-258`
- Modify: `docs/upload_templates/master_bulk_upload.md:21`, `docs/upload_templates/timepoint_modifications.md:6, 27, 38-41`, `docs/upload_templates/scalar_results.md:21`
- Modify: `docs/working/issues/07-notes-overhaul-phase-2.md` (§1 PR-D row, line 39)
- Modify: `docs/working/decisions.md` (append one entry)

**Interfaces:** none (docs and comments only; the controller writes the issue-log entry after the rehearsal).

- [ ] **Step 1: Source-tree literals**

- `backend/services/notes.py` docstring lines 4-5: rewrite the sentence listing the four legacy places so it names them in prose without the column identifiers, e.g. "the positional 'first note', the two free-text result columns dropped by issue #122 PR-D, and ordinary notes".
- `backend/api/routers/bulk_uploads.py:517`: `"""Bulk-add 'modification' notes to existing result timepoints (one slot per uploader; writes audit log)."""`.
- `database/event_listeners.py:464`: `# modification_note (issue #118 PR3) replaced the legacy per-result modification column (dropped by issue #122 PR-D):`.
- Run the acceptance grep: `grep -rnI "brine_modification\|sampling_description\|Master upload — day" backend/ database/ frontend/src | grep -v "reclassify_notes_020.py"` → must print nothing. If a `__pycache__` path appears, delete that `.pyc` and re-run. Paste the (empty) result in the report.

- [ ] **Step 2: MODELS.md** (`.claude/rules/MODELS.md`, not synced)

- Line 213 (Dual-write bullet): change the opening to **Dual-write (PR1 of #118, 2026-09-08 → ended by issue #122 PR-D, 2026-10-14).** and the first sentence to past tense: "Every legacy write path wrote BOTH its old column and a typed note until PR-D dropped the columns (Alembic `b8c4e2d7f9a1`); since then every path writes the note only: ..." keeping the list that follows, and replace the final sentence about `POST /api/results` with "`POST /api/results` takes no free text at all since PR-D; notes go through `POST /experiments/{id}/notes`."
- Lines 306-307: replace both bullets with one: "- **Legacy free-text columns dropped (issue #122 PR-D, Alembic `b8c4e2d7f9a1`, 2026-10-14):** `description`, `brine_modification_description` and `has_brine_modification` no longer exist. Their content lives in `experiment_notes` (`observation` / `modification` notes scoped to the result; the 020 backfill moved the historical text). The scalar and quick-upload parsers mirror their `Description` column into an `observation` note signed with the parser tag via `ScalarResultsService.create_scalar_result_ex`'s `_note_source` control key; Timepoint Modifications writes the uploader's `modification` slot only. A re-upload with a time never adopts a legacy NULL-time row (the description-keyed fallback went with the column)."
- Lines 487-493: leave the two PR3 view paragraphs (history) but append to the `v_results_scalar` one: "The column itself was dropped by PR-D (2026-10-14)."
- Line 524: remove `result_description` from the column list and add at the top of the `v_primary_experiment_results` section the line: "> **Not a live view.** `database/event_listeners.py` only drops it (`DROP VIEW IF EXISTS v_primary_experiment_results CASCADE`); the definition below is historical. Use `v_dim_timepoints` / `v_results_*` / `v_notes`."

- [ ] **Step 3: Other docs** (Edit tool; the hook syncs to `docs/project_context/`)

- `docs/api/API_REFERENCE.md:429`: "| POST | `/api/results` | Create result entry (time, bucket, primary flag). Carries no free text since #122 PR-D: observations and modifications are notes via `POST /api/experiments/{id}/notes` with `result_id`. |". Line 737: "| POST | `/api/bulk-uploads/timepoint-modifications` | Bulk-add `modification` notes to result timepoints (one slot per uploader). Writes audit log (`modified_table='experiment_notes'`). |".
- `docs/POWERBI_MODEL.md` after line 168's bullet: add "- **Legacy columns dropped (issue #122 PR-D, 2026-10-14).** `experimental_results.description`, `brine_modification_description` and `has_brine_modification` no longer exist; any custom query naming them fails. Read `v_notes` (`note_type = 'observation'` / `'modification'`, `result_id` → `v_dim_timepoints`) and `v_dim_timepoints.modification_note`." (Here the names are the point of the sentence; `docs/` is outside the grep.)
- `docs/specs/master_results_sync.md:44`: "| `Modification` | No | `experiment_notes` (`note_type='modification'`, scoped to the result, `created_by='master_bulk_upload'`) | Free text |".
- `docs/LOCKED_COMPONENTS.md:65`: "| `timepoint_modifications.py` | Timepoint-level modification notes |⁶". Footnote ⁶ (187-206): replace the last two sentences ("The mirror is transitional — ... makes Power BI and the app disagree.") with: "**PR-D (issue #122, 2026-10-14, pre-authorization 2 plus Mat's 'proceed' on editing this sixth parser) dropped the legacy columns; the mirror is now the only write.** `master_bulk_upload.py` passes `description` + `_note_source='master_bulk_upload'` to `create_scalar_result_ex` (observation) and calls `sync_result_note` itself for the modification; `timepoint_modifications.py` writes the uploader's `modification` slot only — the overwrite guard is any modification note on the timepoint, and overwrite never touches another author's note; `scalar_results.py` and `quick_upload.py` sign their `Description` column `scalar_results` / `quick_upload`; `long_format.py` writes no note. v3 `Description`/`Modification` headers stay accepted until 2026-12-31."
- `docs/user_guide/BULK_UPLOADS.md:92`: keep. Line 127: replace "upload identically for now; please move to the v4 headers." with "upload identically **until 2026-12-31**, after which only the v4 headers are accepted — please move to the v4 headers before then." Lines 250-258: "Bulk-adds a modification note to existing result timepoints." / the `modification_description` row: "| modification_description | ✓ | Stored as a **modification note** on the timepoint (shows in the experiment's Notes with the MOD badge). Also accepted: `Modification Note`. A timepoint that already has a modification note by anyone is skipped unless `overwrite_existing=TRUE`; overwrite writes or replaces **your** note only |".
- `docs/upload_templates/master_bulk_upload.md:21`: append to the bullet: "Since issue #122 PR-D the notes are the only place the text is stored (the legacy result columns are gone); the v3 spellings are accepted until 2026-12-31."
- `docs/upload_templates/timepoint_modifications.md`: line 6 → "Bulk-adds a `modification` note (`experiment_notes`, scoped to the result, `created_by` = the uploader) to existing `experimental_results` rows at specific timepoints. The legacy per-result column it once set was dropped by issue #122 PR-D." Line 27: remove `brine_modification_description` from the alias list. Lines 38-41 (Write Logic): "- Blank modification + `overwrite_existing=False` → Row is skipped. / - Blank modification + `overwrite_existing=True` → Deletes the uploader's own note on that timepoint (a blank Excel cell parses to empty, not `nan`). / - Non-blank modification → Creates or updates the uploader's note; a `ModificationsLog` row (`modified_table='experiment_notes'`) records the old and new text and the result id. / - **Guard:** a timepoint with any existing modification note (any author) is skipped unless `overwrite_existing=true`; overwrite writes only the uploader's slot and never alters another author's note."
- `docs/upload_templates/scalar_results.md:21`: after the Optional Columns line add: "- `Description` is stored as an **observation note** on the timepoint (`created_by='scalar_results'`, one per result — a re-upload updates it, a blank cell leaves it unchanged). Since issue #122 PR-D nothing is written to the result row itself."
- Spec `docs/working/issues/07-notes-overhaul-phase-2.md` §1 PR-D row (line 39): replace the State cell with "**In review** — `chore/drop-legacy-note-columns`: Alembic `b8c4e2d7f9a1` drops the three columns; plan `docs/superpowers/plans/2026-10-14-drop-legacy-note-columns-pr-d.md`. Gate: production review queue 0 on 2026-10-09 (Mat-reported). `null_time_match` fallback deleted (Mat, 2026-10-12). Six gap calls approved 2026-10-14 (timepoint_modifications.py edited; three master-test edits; 019/020 frozen; fixture sweep; v3 window to 2026-12-31; no v4 workbook in repo)."
- `docs/working/decisions.md`: append

```
## 2026-10-14 — A parser signs the notes it writes (issue #122 PR-D)

**Decision:** free text about a result timepoint is stored only as `experiment_notes`
rows. A scalar-pipeline caller writes an `observation` note by passing
`_note_source=<its tag>` with `description` to `ScalarResultsService.create_scalar_result_ex`;
`description` without `_note_source` is dropped. The tag is the note's `created_by`
and its slot key (`sync_result_note`), so every parser owns one note per result and a
researcher's hand-written note is never overwritten by an upload. A blank cell writes
nothing and leaves an earlier note in place (same as the Master parser since PR1).

**Also decided:** the description-keyed NULL-time fallback is gone (Mat, 2026-10-12) —
an upload never adopts a legacy NULL-time row; Timepoint Modifications' overwrite guard
is "any modification note on the timepoint" and overwrite writes the uploader's slot only.

**Related:** `docs/superpowers/plans/2026-10-14-drop-legacy-note-columns-pr-d.md`;
Alembic `b8c4e2d7f9a1`; the 2026-09-08 entry above (dual-write).
```

- [ ] **Step 4: Verify and commit**

`git status` must show the `docs/project_context/` copies updated by the hook for every `docs/` file you edited (if a copy is missing, run `python -c "import sys; sys.path.insert(0,'.claude/hooks'); import sync_docs_to_project_context as s; s.full_sync()"`). Re-run the acceptance grep from Step 1. Then:

```bash
git add backend/services/notes.py backend/api/routers/bulk_uploads.py database/event_listeners.py .claude/rules/MODELS.md docs/
git commit -F <scratchpad>/task5.msg   # subject: [#122] Document the PR-D column drop
```

---

## Controller steps after Task 5 (not subagent tasks)

1. Final whole-branch review (most capable model) with the ledger's deferred minors; one fix wave + scoped re-review.
2. Migration rehearsal on `experiments_test`: reset schema; `python -c "import database"` (views), `Base.metadata.create_all` from the **parent** model shape is impossible after the drop, so build the pre-state by `create_all` + `ALTER TABLE experimental_results ADD COLUMN description text NOT NULL DEFAULT 'x', ADD COLUMN brine_modification_description text, ADD COLUMN has_brine_modification boolean NOT NULL DEFAULT false; CREATE INDEX ix_experimental_results_has_brine_modification ON experimental_results (has_brine_modification);` + 2 seeded rows; `alembic stamp a7d3e9f1c2b4`; `upgrade head` (columns absent, index absent, rows intact, views present); `downgrade -1` (three columns back, all nullable, index back, values NULL); `upgrade head`; `heads` = `b8c4e2d7f9a1`; reset the DB afterwards.
3. Dev DB `experiments`: `alembic upgrade head` only (no refresh); record before/after `has_column` checks and the `v_*` count.
4. Full §8 suite + frontend baselines at HEAD; acceptance grep.
5. DevTools on `http://localhost:5173`: Notes tab, Results tab (MOD badge from notes), a Master Results upload (seeded experiment, from_bytes_ex style per memory) — zero console errors.
6. Issue-log entry + `gh pr create --base develop` with: gate reading (0 on 2026-10-09, Mat-reported), the three prerequisites, pre-authorizations 2 and 3, the six gap calls, the rehearsal output, counts, the `test_master_bulk_upload.py` deviation (three tests, not one), the `timepoint_modifications.py` scope flag, and the v3 window date.
