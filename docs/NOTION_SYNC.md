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

## Deduplication

When a reactor stays `Ongoing` and the owner does not update the Change Request
text before the 6 AM sync, the import step **skips writing a new DB row**
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
