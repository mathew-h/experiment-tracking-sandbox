# Notion Sync — Reactor Dashboard

This document is the source of truth for the Notion sync integration.
Read it before editing any file in `backend/services/notion_sync/`.

---

## Notion Database

| Field | Value |
|-------|-------|
| Database Name | Reactor Dashboard |
| Database URL | https://www.notion.so/53ec4778508541efa31eaf0e4accac35 |
| Database ID | `53ec4778508541efa31eaf0e4accac35` |
| Data Source ID | `d8d499ab-d6ef-44ce-9f67-d650dfaf5319` |
| Rows | 18 (R01–R16, CF01, CF02) |

The "Daily Standup" gallery view is what team members use to enter change requests.

---

## Notion Property Map

All property names are defined as constants in `backend/services/notion_sync/client.py`.
**If the Notion schema changes, update client.py constants AND this table.**

| Constant | Notion Property Name | Type | Direction |
|----------|---------------------|------|-----------|
| `PROP_REACTOR_LABEL` | `Name` | Title | Read (import + export lookup) |
| `PROP_CHANGE_REQUEST` | `Change Request` | rich_text | Read (import), Clear (import) |
| `PROP_CHANGE_STATUS` | `Change Request Status` | select | Read (import), Write (import clear, export) |
| `PROP_EXPERIMENT_ID` | `Experiment ID` | rich_text | Write (export) |
| `PROP_EXPERIMENT_DESC` | `Experiment Description` | rich_text | Write (export) |
| `PROP_DATE_STARTED` | `Date Started` | date | Write (export) |

### Change Request Status values

| Value | Meaning |
|-------|---------|
| `Pending` | Default state; ready for a new request |
| `In Progress` | Team member is actively working on this reactor |
| `Carried Forward` | Request was not completed; carries to next day |
| `Completed` | Request was completed; import will clear and reset to Pending |

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NOTION_TOKEN` | Notion integration token (`secret_...`) |
| `NOTION_DATABASE_ID` | 32-char database ID (no hyphens) |
| `NOTION_DATA_SOURCE_ID` | Data source ID (for reference) |
| `NOTION_SYNC_HOUR` | Hour (0–23, America/New_York) for daily job; default `6` |

The scheduler only starts when `NOTION_TOKEN` is non-empty.

---

## Sync Sequence

The sync runs daily at `NOTION_SYNC_HOUR` (America/New_York) via APScheduler,
and can be triggered on demand via `POST /api/admin/notion-sync/trigger`.

### Step 1 — Import

1. Query all 18 Notion rows in one SDK call.
2. For each row:
   - **Empty Change Request** → skip (no DB write, no Notion call)
   - **In Progress** → upsert to DB with `carried_forward=False`; do NOT clear Notion
   - **Carried Forward** → upsert to DB with `carried_forward=True`; do NOT clear Notion
   - **Completed** or **Pending with content** → upsert to DB; then clear Change Request + set status to Pending
3. The Notion clear is called **only after** the DB `commit()`. A Notion failure after commit is logged and counted in `errors` but does not undo the DB row.
4. `Carried Forward` rows accumulate: same reactor on different sync dates = different DB rows (the unique constraint is on `(reactor_label, sync_date)`).

### Step 2 — Export

1. Query all ONGOING experiments with a `reactor_number` assigned.
2. For each occupied slot, write `Experiment ID`, `Experiment Description`, and `Date Started` to the corresponding Notion page.
3. If the Notion page was cleared in Step 1, also reset `Change Request Status` to Pending.
4. If status is `In Progress` or `Carried Forward` and the page was NOT cleared, the status column is not touched.
5. Idle reactor slots (no ONGOING experiment) are skipped entirely — no Notion writes.

### Step 3 — Log

```
structlog.info("notion_sync_complete",
    imported=N, exported=N, carried_forward=N, errors=[...])
```

---

## Reactor Label Mapping

DB `reactor_number` (integer) maps to Notion reactor label as follows:

| DB `experiment_type` | Label formula | Examples |
|---------------------|--------------|---------|
| `"Core Flood"` | `CF{reactor_number:02d}` | CF01, CF02 |
| anything else | `R{reactor_number:02d}` | R01 … R16 |

The same formula is used in `backend/api/routers/dashboard.py` (`REACTOR_SPECS`).

---

## DB Model

`ReactorChangeRequest` in `database/models/notion_sync.py`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto |
| `reactor_label` | String(10) | "R05", "CF01" |
| `experiment_id` | String, nullable FK | Ref to `experiments.experiment_id`; NULL on import |
| `requested_change` | String | Change Request text at import time |
| `notion_status` | String(50) | Status value at import time |
| `carried_forward` | Boolean | True if Carried Forward at import |
| `sync_date` | Date | Sync cycle date |
| `notion_page_id` | String(32) | Notion page UUID, hyphens stripped |
| `created_at` | DateTime | Auto |

Unique constraint: `(reactor_label, sync_date)` — re-running sync on the same day upserts rather than duplicates.

---

## API Endpoint

`POST /api/admin/notion-sync/trigger`

Requires Firebase auth (Bearer token). Runs a full sync cycle and returns:

```json
{
  "imported": 3,
  "exported": 12,
  "carried_forward": 1,
  "errors": []
}
```

Sync errors (Notion outage, individual row failures) are returned in `errors` at HTTP 200.
The endpoint only returns HTTP 500 if the sync itself raises an unhandled exception.
HTTP 503 is returned when `NOTION_TOKEN` is not configured.
