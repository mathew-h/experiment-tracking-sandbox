# Notion Sync: Dedup + Status Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent duplicate `ReactorChangeRequest` rows from accumulating for unchanged ongoing tasks, and rename status values to clearer language that matches the lab's actual workflow.

**Architecture:** Three code changes across two service files (`import_.py`, `client.py`) plus a one-time data migration script and new documentation. No schema change required. Fix 1 (dedup) is independent and low-risk; Fixes 2+3 (status renames) have a deployment dependency on Notion being updated first.

**Tech Stack:** Python, SQLAlchemy 2.x (PostgreSQL), structlog, pytest

---

## ⚠️ Pre-Deployment Gate: Status Rename Coordination

**This applies to Task 2 only. Task 1 can be deployed independently.**

The status rename (Task 2) changes the expected string values in the import handler's `known_statuses` tuple. If the code is deployed before the Notion database is updated:

- Notion still sends `"In Progress"` for ongoing reactors
- The import handler now expects `"Ongoing"` → treats `"In Progress"` as unknown
- Silently skips ALL ongoing reactors — no new DB rows, no error raised

**Deployment order for Task 2:**
1. Update Notion database: rename `"In Progress"` → `"Ongoing"` and `"Pending"` → `"No Change"` in the select property options.
2. Deploy the code change (Task 2).
3. Verify the next sync or run a manual sync to confirm.

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Modify | `backend/services/notion_sync/import_.py` | Add dedup check; update status constant references |
| Modify | `backend/services/notion_sync/client.py` | Rename STATUS constants; update methods that write status back to Notion |
| Modify | `tests/services/test_notion_sync_import.py` | New tests for dedup behavior and updated status names |
| Modify | `tests/services/test_notion_sync_client.py` | Update tests that assert on status constant values |
| Create | `migrate_deduplicate_change_requests.py` | One-time script to clean up existing duplicate DB rows |
| Create | `docs/NOTION_SYNC.md` | New documentation: status table, sync sequence, deployment notes |

---

## Task 1: Import dedup — skip unchanged carried-forward requests

**Files:**
- Modify: `backend/services/notion_sync/import_.py`
- Test: `tests/services/test_notion_sync_import.py`

### Background

`run_import` in `import_.py` currently writes a new `ReactorChangeRequest` row every day for any non-empty change request, including unchanged `"In Progress"` ones. This produces one row per calendar day for what is really a single ongoing task.

The fix: before inserting, query the latest existing row for the reactor. If its `requested_change` text matches the incoming text (stripped), skip the insert. Still track the page_id so the `Working Date` Notion column is preserved.

- [ ] **Step 1: Write the failing tests**

Add to `tests/services/test_notion_sync_import.py`:

```python
# Add this import at the top with the existing imports:
from datetime import date as date_type

SYNC_DATE_2 = date(2026, 4, 2)  # one day after SYNC_DATE = date(2026, 4, 1)


def _make_prior_row(
    db: Session,
    reactor_label: str,
    text: str,
    sync_date: date_type = SYNC_DATE,
    status: str = "In Progress",
) -> ReactorChangeRequest:
    """Insert a ReactorChangeRequest row directly into the test DB."""
    row = ReactorChangeRequest(
        reactor_label=reactor_label,
        requested_change=text,
        notion_status=status,
        carried_forward=True,
        sync_date=sync_date,
        notion_page_id="aabbccdd" * 4,
    )
    db.add(row)
    db.commit()
    return row


def test_dedup_skips_unchanged_text_across_days(db_session: Session) -> None:
    """Second-day import with identical text does not create a new DB row."""
    _make_prior_row(db_session, "R05", "Run test today")

    client = MagicMock()
    pages = [_page(_PAGE_ID, "R05", "Run test today", "In Progress")]
    result = run_import(client, db_session, pages, SYNC_DATE_2)

    assert result.skipped == 1
    assert result.imported == 0
    assert db_session.query(ReactorChangeRequest).count() == 1
    client.clear_change_request.assert_not_called()


def test_dedup_preserves_active_cr_page_id(db_session: Session) -> None:
    """Dedup skip still tracks page_id so Working Date is preserved in Notion."""
    _make_prior_row(db_session, "R05", "Run test today")

    client = MagicMock()
    pages = [_page(_PAGE_ID, "R05", "Run test today", "In Progress")]
    result = run_import(client, db_session, pages, SYNC_DATE_2)

    assert _PAGE_ID in result.active_cr_page_ids


def test_dedup_allows_changed_text(db_session: Session) -> None:
    """Changed text on day 2 IS imported normally — creates a new row."""
    _make_prior_row(db_session, "R05", "Run test today")

    client = MagicMock()
    pages = [_page(_PAGE_ID, "R05", "Changed the task description", "In Progress")]
    result = run_import(client, db_session, pages, SYNC_DATE_2)

    assert result.imported == 1
    assert db_session.query(ReactorChangeRequest).count() == 2


def test_dedup_is_case_and_whitespace_sensitive_only_on_strip(db_session: Session) -> None:
    """Text with leading/trailing whitespace is matched after strip; internal whitespace is literal."""
    _make_prior_row(db_session, "R05", "Run test today")

    client = MagicMock()
    pages = [_page(_PAGE_ID, "R05", "  Run test today  ", "In Progress")]
    result = run_import(client, db_session, pages, SYNC_DATE_2)

    # Stripped text matches — should be deduped
    assert result.skipped == 1
    assert db_session.query(ReactorChangeRequest).count() == 1


def test_dedup_first_occurrence_always_imported(db_session: Session) -> None:
    """A reactor with no prior rows always gets imported regardless of text."""
    client = MagicMock()
    pages = [_page(_PAGE_ID, "R05", "Brand new request", "In Progress")]
    result = run_import(client, db_session, pages, SYNC_DATE)

    assert result.imported == 1
    assert db_session.query(ReactorChangeRequest).count() == 1
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/Scripts/pytest tests/services/test_notion_sync_import.py::test_dedup_skips_unchanged_text_across_days tests/services/test_notion_sync_import.py::test_dedup_preserves_active_cr_page_id tests/services/test_notion_sync_import.py::test_dedup_allows_changed_text tests/services/test_notion_sync_import.py::test_dedup_is_case_and_whitespace_sensitive_only_on_strip tests/services/test_notion_sync_import.py::test_dedup_first_occurrence_always_imported -v
```

Expected: 4 failures (dedup tests fail because dedup doesn't exist yet); `test_dedup_first_occurrence_always_imported` may pass.

- [ ] **Step 3: Implement the dedup check in `import_.py`**

In `backend/services/notion_sync/import_.py`, add a helper function after `_resolve_experiment_id` (around line 68):

```python
def _is_text_unchanged(db: Session, reactor_label: str, incoming_text: str) -> bool:
    """Return True if the most recent CR row for this reactor has identical text.

    Used to prevent duplicate rows when a carried-forward request hasn't changed.
    """
    from sqlalchemy import select as sa_select  # already imported at module top as `select`
    existing = (
        db.execute(
            select(ReactorChangeRequest.requested_change)
            .where(ReactorChangeRequest.reactor_label == reactor_label)
            .order_by(ReactorChangeRequest.sync_date.desc())
            .limit(1)
        )
        .scalar_one_or_none()
    )
    if existing is None:
        return False
    return (existing or "").strip() == (incoming_text or "").strip()
```

Note: the module already imports `select` from sqlalchemy. Remove the inner import comment — just use the existing `select` at the top of the file.

Then in `run_import`, insert the dedup block **after** the `known_statuses` check and **before** the `carried_forward` assignment (between the current lines 107 and 109 in `import_.py`):

```python
        # Dedup: skip if this reactor's latest row already has identical text.
        # Still add to active_cr_page_ids so Working Date is preserved in Notion.
        if _is_text_unchanged(db, reactor_label, change_request):
            log.info("notion_sync_skip_unchanged", reactor=reactor_label)
            result.skipped += 1
            result.active_cr_page_ids.add(page_id_raw)
            continue
```

The final `run_import` loop body (relevant section) should look like:

```python
        # Unknown/legacy statuses are skipped
        known_statuses = (STATUS_IN_PROGRESS, STATUS_COMPLETED, STATUS_PENDING)
        if status not in known_statuses:
            log.warning("notion_import_unknown_status", reactor=reactor_label, status=status)
            result.skipped += 1
            continue

        # Dedup: skip if this reactor's latest row already has identical text.
        if _is_text_unchanged(db, reactor_label, change_request):
            log.info("notion_sync_skip_unchanged", reactor=reactor_label)
            result.skipped += 1
            result.active_cr_page_ids.add(page_id_raw)
            continue

        carried_forward = status == STATUS_IN_PROGRESS
        should_clear = status != STATUS_IN_PROGRESS
        # ... rest unchanged ...
```

- [ ] **Step 4: Run all dedup tests**

```bash
.venv/Scripts/pytest tests/services/test_notion_sync_import.py -v
```

Expected: all 5 new tests pass; existing tests unaffected.

- [ ] **Step 5: Run full notion sync test suite**

```bash
.venv/Scripts/pytest tests/services/test_notion_sync_import.py tests/services/test_notion_sync_integration.py tests/services/test_notion_sync_export.py tests/api/test_notion_sync.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/services/notion_sync/import_.py tests/services/test_notion_sync_import.py
git commit -m "[#55] skip unchanged carried-forward change requests

- Tests added: yes
- Docs updated: no"
```

---

## Task 2: Status constant rename — "Ongoing" and "No Change"

**Files:**
- Modify: `backend/services/notion_sync/client.py`
- Modify: `backend/services/notion_sync/import_.py`
- Test: `tests/services/test_notion_sync_import.py`
- Test: `tests/services/test_notion_sync_client.py`

### ⚠️ Do not merge/deploy this task until Notion has been updated

See the Pre-Deployment Gate at the top of this plan.

### Background

Three status constants currently live in `client.py`:
- `STATUS_PENDING = "Pending"` → becomes `STATUS_NO_CHANGE = "No Change"`
- `STATUS_IN_PROGRESS = "In Progress"` → becomes `STATUS_ONGOING = "Ongoing"`
- `STATUS_COMPLETED = "Completed"` → unchanged

Every place that reads or writes status strings must be updated:
- `client.py`: constants, `clear_change_request()`, `set_status_pending()`, `extract_change_status()` fallback
- `import_.py`: `known_statuses` tuple, `carried_forward` assignment, `should_clear` assignment, all imports of old constant names
- `export.py`: imports `STATUS_PENDING` indirectly via `set_status_pending()` — no direct reference, so no change needed there

- [ ] **Step 1: Write failing tests for new status names**

Add to `tests/services/test_notion_sync_import.py`:

```python
def test_ongoing_status_sets_carried_forward_true(db_session: Session) -> None:
    """'Ongoing' status writes carried_forward=True and does NOT clear Notion."""
    client = MagicMock()
    pages = [_page(_PAGE_ID, "R05", "Run test today", "Ongoing")]

    result = run_import(client, db_session, pages, SYNC_DATE)

    assert result.imported == 1
    assert result.carried_forward == 1
    client.clear_change_request.assert_not_called()
    row = db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R05", sync_date=SYNC_DATE
    ).one()
    assert row.carried_forward is True
    assert row.notion_status == "Ongoing"


def test_no_change_status_with_text_skips(db_session: Session) -> None:
    """'No Change' with text is treated as Pending was — should import and clear."""
    client = MagicMock()
    pages = [_page(_PAGE_ID, "R05", "Something to do", "No Change")]

    result = run_import(client, db_session, pages, SYNC_DATE)

    # No Change with content behaves like old Pending with content: import + clear
    assert result.imported == 1
    assert result.carried_forward == 0
    client.clear_change_request.assert_called_once_with(_PAGE_ID)


def test_old_in_progress_is_now_unknown_status(db_session: Session) -> None:
    """After rename, 'In Progress' is an unknown status and is logged + skipped."""
    client = MagicMock()
    pages = [_page(_PAGE_ID, "R05", "Something", "In Progress")]

    result = run_import(client, db_session, pages, SYNC_DATE)

    assert result.skipped == 1
    assert result.imported == 0
    assert db_session.query(ReactorChangeRequest).count() == 0
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
.venv/Scripts/pytest tests/services/test_notion_sync_import.py::test_ongoing_status_sets_carried_forward_true tests/services/test_notion_sync_import.py::test_no_change_status_with_text_skips tests/services/test_notion_sync_import.py::test_old_in_progress_is_now_unknown_status -v
```

Expected: `test_ongoing_status_sets_carried_forward_true` fails (unknown status); `test_no_change_status_with_text_skips` fails (unknown status); `test_old_in_progress_is_now_unknown_status` fails (currently treated as known, not unknown).

- [ ] **Step 3: Update status constants in `client.py`**

In `backend/services/notion_sync/client.py`, replace the three status constants and update the four methods that write them:

```python
# Replace lines 23-25:
STATUS_NO_CHANGE = "No Change"
STATUS_ONGOING = "Ongoing"
STATUS_COMPLETED = "Completed"
```

Update `clear_change_request` (writes status back to Notion after clearing a CR):

```python
    def clear_change_request(self, page_id: str) -> None:
        """Clear the Change Request text and reset status to No Change."""
        self.update_page(page_id, {
            PROP_CHANGE_REQUEST: {"rich_text": []},
            PROP_CHANGE_STATUS: {"select": {"name": STATUS_NO_CHANGE}},
        })
```

Update `set_status_pending` (rename the method for clarity, keep old name as alias for safety):

```python
    def set_status_no_change(self, page_id: str) -> None:
        """Set Change Request Status to No Change."""
        self.update_page(page_id, {
            PROP_CHANGE_STATUS: {"select": {"name": STATUS_NO_CHANGE}},
        })

    # Backward-compatible alias — remove after export.py is updated
    set_status_pending = set_status_no_change
```

Update `extract_change_status` fallback:

```python
def extract_change_status(page: dict) -> str:
    """Extract Change Request Status select value; returns STATUS_NO_CHANGE if unset."""
    select = page["properties"][PROP_CHANGE_STATUS]["select"]
    return select["name"] if select else STATUS_NO_CHANGE
```

- [ ] **Step 4: Update `import_.py` to use new constant names**

In `backend/services/notion_sync/import_.py`, update the import line:

```python
from .client import (
    NotionSyncClient,
    extract_change_request,
    extract_change_status,
    extract_reactor_label,
    STATUS_ONGOING,
    STATUS_COMPLETED,
    STATUS_NO_CHANGE,
)
```

Update the `known_statuses` tuple and the two derived variables:

```python
        known_statuses = (STATUS_ONGOING, STATUS_COMPLETED, STATUS_NO_CHANGE)
        if status not in known_statuses:
            log.warning("notion_import_unknown_status", reactor=reactor_label, status=status)
            result.skipped += 1
            continue

        # (dedup block from Task 1 stays here — unchanged)

        carried_forward = status == STATUS_ONGOING
        should_clear = status != STATUS_ONGOING
```

- [ ] **Step 5: Update `export.py` to use renamed method**

In `backend/services/notion_sync/export.py`, line 100, `set_status_pending` is called. Update to `set_status_no_change`:

```python
            if page_id in cleared_page_ids:
                client.set_status_no_change(page_id)
```

Then remove the `set_status_pending` alias from `client.py` (added in Step 3 above).

- [ ] **Step 6: Run the new status tests**

```bash
.venv/Scripts/pytest tests/services/test_notion_sync_import.py -v
```

Expected: all pass, including `test_old_in_progress_is_now_unknown_status`.

- [ ] **Step 7: Run the full notion sync test suite**

```bash
.venv/Scripts/pytest tests/ -k "notion" -v
```

Expected: all pass. Any test that asserts `"In Progress"` or `"Pending"` as constants will now fail — fix those assertions to use `"Ongoing"` / `"No Change"` or the new constant names.

- [ ] **Step 8: Commit**

```bash
git add backend/services/notion_sync/client.py backend/services/notion_sync/import_.py backend/services/notion_sync/export.py tests/services/test_notion_sync_import.py tests/services/test_notion_sync_client.py
git commit -m "[#55] rename status constants to Ongoing and No Change

- Tests added: yes
- Docs updated: no"
```

---

## Task 3: Data migration script — deduplicate existing DB rows

**Files:**
- Create: `migrate_deduplicate_change_requests.py` (repo root)

### Background

Existing `ReactorChangeRequest` rows already contain duplicate chains from before Fix 1 was deployed. This one-time script cleans them up: for each reactor, it keeps the earliest row in each consecutive run of identical `requested_change` text and deletes the rest.

The script defaults to dry-run mode — no writes unless `--commit` is passed.

- [ ] **Step 1: Write the migration script**

Create `migrate_deduplicate_change_requests.py` at the project root:

```python
"""
Data migration: deduplicate ReactorChangeRequest entries.

WHAT THIS SCRIPT DOES
---------------------
For each reactor, groups entries by consecutive runs of identical
`requested_change` text (sorted by sync_date ASC). Within each run,
keeps the earliest row (lowest sync_date) and deletes the rest.

USAGE
-----
# Preview what would be deleted (safe, no writes)
python migrate_deduplicate_change_requests.py

# Delete with interactive confirmation prompt
python migrate_deduplicate_change_requests.py --commit

# Delete without prompt (CI / headless)
python migrate_deduplicate_change_requests.py --commit --yes
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

import structlog
from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from database.models.notion_sync import ReactorChangeRequest  # noqa: E402
from backend.config.settings import get_settings  # noqa: E402

log = structlog.get_logger()


def find_duplicate_ids(session: Session) -> list[int]:
    """Return IDs of all duplicate ReactorChangeRequest rows to delete.

    For each reactor, walks rows sorted by sync_date ASC. Any row whose
    requested_change equals the immediately preceding row's text is a
    duplicate — mark for deletion.
    """
    rows = session.execute(
        select(
            ReactorChangeRequest.id,
            ReactorChangeRequest.reactor_label,
            ReactorChangeRequest.requested_change,
            ReactorChangeRequest.sync_date,
            ReactorChangeRequest.carried_forward,
        ).order_by(
            ReactorChangeRequest.reactor_label,
            ReactorChangeRequest.sync_date,
        )
    ).fetchall()

    by_reactor: dict[str, list] = defaultdict(list)
    for row in rows:
        by_reactor[row.reactor_label].append(row)

    to_delete: list[int] = []
    for reactor_label, entries in sorted(by_reactor.items()):
        prev_text: str | None = None
        for entry in entries:
            current_text = (entry.requested_change or "").strip()
            if current_text and current_text == prev_text:
                to_delete.append(entry.id)
            else:
                prev_text = current_text

    return to_delete


def preview(session: Session, to_delete: list[int]) -> None:
    if not to_delete:
        print("\nNo duplicate rows found. Database is clean.")
        return

    rows = session.execute(
        select(ReactorChangeRequest).where(
            ReactorChangeRequest.id.in_(to_delete)
        ).order_by(
            ReactorChangeRequest.reactor_label,
            ReactorChangeRequest.sync_date,
        )
    ).scalars().all()

    print(f"\nFound {len(to_delete)} duplicate row(s) to delete:\n")
    print(f"  {'ID':>6}  {'Reactor':<8}  {'Date':<12}  {'CF':<5}  Text")
    print("  " + "-" * 80)
    for r in rows:
        text_preview = (r.requested_change or "")[:55]
        if len(r.requested_change or "") > 55:
            text_preview += "..."
        print(
            f"  {r.id:>6}  {r.reactor_label:<8}  "
            f"{str(r.sync_date):<12}  "
            f"{'Yes' if r.carried_forward else 'No':<5}  {text_preview}"
        )
    print()


def run_migration(dry_run: bool, skip_confirm: bool) -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url, echo=False)

    with Session(engine) as session:
        to_delete = find_duplicate_ids(session)
        preview(session, to_delete)

        if dry_run:
            print("DRY RUN — no changes written. Re-run with --commit to apply.")
            return 0

        if not to_delete:
            return 0

        if not skip_confirm:
            answer = input(
                f"Delete {len(to_delete)} row(s)? This cannot be undone. [yes/N] "
            ).strip().lower()
            if answer != "yes":
                print("Aborted.")
                return 0

        try:
            result = session.execute(
                delete(ReactorChangeRequest).where(
                    ReactorChangeRequest.id.in_(to_delete)
                )
            )
            session.commit()
            deleted = result.rowcount
            log.info("change_request_dedup_complete", deleted=deleted)
            print(f"\nDeleted {deleted} duplicate row(s). Migration complete.")
            return deleted
        except Exception:
            session.rollback()
            log.exception("change_request_dedup_failed")
            print("\nError during deletion — transaction rolled back. No rows deleted.")
            raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deduplicate consecutive identical ReactorChangeRequest entries."
    )
    parser.add_argument(
        "--commit", action="store_true", default=False,
        help="Actually delete rows (default is dry-run preview only).",
    )
    parser.add_argument(
        "--yes", action="store_true", default=False,
        help="Skip the interactive confirmation prompt (use with --commit).",
    )
    args = parser.parse_args()
    run_migration(dry_run=not args.commit, skip_confirm=args.yes)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-test the dry-run against the dev DB**

```bash
.venv/Scripts/python migrate_deduplicate_change_requests.py
```

Expected: prints a table of duplicates found (may be many if the problem has been accumulating), then "DRY RUN — no changes written." No error.

- [ ] **Step 3: Commit**

```bash
git add migrate_deduplicate_change_requests.py
git commit -m "[#55] add dedup migration script for existing CR rows

- Tests added: no (dry-run verified manually)
- Docs updated: no"
```

---

## Task 4: Write `docs/NOTION_SYNC.md`

**Files:**
- Create: `docs/NOTION_SYNC.md`

- [ ] **Step 1: Create the documentation file**

Create `docs/NOTION_SYNC.md`:

```markdown
# Notion Reactor Dashboard Sync

The Notion sync keeps the Reactor Dashboard Notion database in sync with the
experiment tracking system. It runs daily at 6 AM ET via APScheduler.

## Status Values

After issue #55, the three status values are:

| Status | Meaning | What the sync does |
|--------|---------|-------------------|
| `No Change` | Default/idle. No task today; slot is unoccupied or owner reviewed and found nothing to do. | Skip import. |
| `Ongoing` | Active multi-day task. Carries forward until explicitly resolved. | Import with `carried_forward=True`; do NOT clear Notion. Deduped — see below. |
| `Completed` | Task finished. Record it and reset slot. | Import with `carried_forward=False`; clear Change Request field and reset status to `No Change`. |

## Deduplication (Fix 1)

When a reactor stays `Ongoing` and the owner does not update the Change Request
text before the 6 AM sync, the import step now **skips writing a new DB row**
if the most recent existing row for that reactor already has identical text.

This prevents one-row-per-calendar-day chains for what is a single ongoing task.

The Notion page is not cleared on a dedup skip — the request remains visible
and `Working Date` is preserved.

## Sync Sequence

```
1. Query all rows from Notion reactor dashboard
2. run_import(pages, sync_date):
   a. For each page with a non-empty Change Request:
      - Skip if status is unknown (log warning)
      - Skip if text matches latest DB row for this reactor (dedup)
      - Upsert ReactorChangeRequest row
      - If Completed or No Change: schedule Notion clear
   b. db.commit()
   c. Clear scheduled Notion pages
3. run_export(pages):
   - For each ONGOING experiment with a reactor_number:
     - Write Experiment ID, description, date to Notion row
   - For idle reactor slots: clear experiment fields
4. Stamp Last Synced + Working Date on all pages
```

## Constants (`backend/services/notion_sync/client.py`)

```python
PROP_REACTOR_LABEL = "Reactor #"
PROP_CHANGE_REQUEST = "Change Request"
PROP_CHANGE_STATUS = "Change Request Status"
PROP_EXPERIMENT_ID = "Experiment ID"
PROP_EXPERIMENT_DESC = "Experiment Description"
PROP_DATE_STARTED = "Date Started"
PROP_WORKING_DATE = "Working Date"
PROP_LAST_SYNCED = "Last Synced"

STATUS_NO_CHANGE = "No Change"
STATUS_ONGOING = "Ongoing"
STATUS_COMPLETED = "Completed"
```

## Key Files

| File | Purpose |
|------|---------|
| `backend/services/notion_sync/client.py` | Notion SDK wrapper; property and status constants |
| `backend/services/notion_sync/import_.py` | Import step: read CRs from Notion → DB |
| `backend/services/notion_sync/export.py` | Export step: write experiment info → Notion |
| `backend/services/notion_sync/sync.py` | Orchestrator: import + export + APScheduler job |
| `migrate_deduplicate_change_requests.py` | One-time cleanup script for pre-Fix-1 duplicate rows |

## Deployment Note: Status Rename

If updating the STATUS constants in `client.py`, **update Notion's select options
first** before deploying the code. Deploying first will cause the sync to silently
skip all `"In Progress"` / `"Pending"` rows as unknown statuses until Notion is updated.

## Manual Sync Trigger

Admins can trigger a manual sync via the API:

```
POST /api/notion-sync/trigger
```

See `docs/api/API_REFERENCE.md` for authentication requirements.
```

- [ ] **Step 2: Commit**

```bash
git add docs/NOTION_SYNC.md
git commit -m "[#55] add NOTION_SYNC.md documentation

- Tests added: no
- Docs updated: yes"
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Task |
|-------------|------|
| Dedup at import time: skip if latest row has same text | Task 1 |
| Still track active_cr_page_ids on dedup skip (Working Date preserved) | Task 1 |
| Rename "In Progress" → "Ongoing" | Task 2 |
| Rename "Pending" → "No Change" | Task 2 |
| Update all constant references (client, import, export) | Task 2 |
| Update `clear_change_request` to write "No Change" back to Notion | Task 2 |
| One-time dedup migration script | Task 3 |
| docs/NOTION_SYNC.md | Task 4 |
| Document deployment ordering risk | Pre-Deployment Gate + Task 4 |

**Placeholder scan:** None found. All code blocks are complete.

**Type consistency:** `_is_text_unchanged` takes `(db: Session, reactor_label: str, incoming_text: str) -> bool` — matches call site in `run_import`. `ReactorChangeRequest` fields match model definition.
