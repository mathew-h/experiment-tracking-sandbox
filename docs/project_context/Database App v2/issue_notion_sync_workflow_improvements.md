# Notion Sync: Prevent Duplicate Change Requests and Clarify Status Workflow

## Problem

Two related gaps in the Notion reactor dashboard sync create friction for the lab's morning standup workflow.

### Gap 1 — Duplicate entries from carried-forward requests

When a reactor stays "In Progress" and the owner does not update the change request text before the 6 AM sync, the sync records a new `ReactorChangeRequest` DB row with the same text and `carried_forward=True`. This produces long chains of identical entries — one per calendar day — for what is a single ongoing task. The Change Requests tab on an experiment page becomes unreadable, and any downstream reporting counts these as separate events.

The root cause is that the sync has no memory of what it recorded yesterday: it re-imports whatever text is in Notion, regardless of whether that text changed.

### Gap 2 — Status values are confusing; workflow breaks on absence

The current statuses (`Pending`, `In Progress`, `Completed`) don't map cleanly to the intended workflow:

- "In Progress" is ambiguous — it implies active work happening right now, but in practice it just means "nobody set it to Completed yet."
- "Pending" (the default/idle state) reads as "waiting for something" rather than "no task today," which creates hesitation about what it means.
- There is no way to explicitly say "I checked this reactor today and there is nothing to do," which makes absence indistinguishable from an active ongoing task.

---

## Proposed Fixes

### Fix 1 — Dedup at import time in the sync service

**File:** `backend/services/notion_sync/service.py` (or equivalent import handler)

Before writing a new `ReactorChangeRequest` row, check whether the most recent existing row for that `reactor_label` has the same `requested_change` text. If it does, skip the insert entirely — don't write a new row, and don't clear Notion (the request is still open).

**Pseudo-logic (import loop, per-reactor):**

```python
existing_latest = (
    session.query(ReactorChangeRequest)
    .filter_by(reactor_label=reactor_label)
    .order_by(ReactorChangeRequest.sync_date.desc())
    .first()
)

text_unchanged = (
    existing_latest is not None
    and (existing_latest.requested_change or "").strip()
       == (incoming_text or "").strip()
)

if text_unchanged:
    # User hasn't changed anything since the last sync — skip.
    log.info("notion_sync_skip_unchanged", reactor=reactor_label)
    continue  # do not write a new row, do not clear Notion
```

This is a one-line behavioral change with no schema impact. The unique constraint `(reactor_label, sync_date)` already prevents double-imports on the same calendar day; this fix prevents redundant rows across days.

**What this does NOT affect:**
- Genuinely new text each day — still imported normally.
- The first time a change request appears — still imported normally.
- Export step — unchanged.

---

### Fix 2 — Rename "In Progress" to "Ongoing"

Rename the existing `In Progress` status to `Ongoing`. No other status changes; the three-status set becomes `No Change`, `Ongoing`, `Completed`.

**Rationale:** "In Progress" implies something is actively happening right now, which creates mid-day ambiguity. "Ongoing" better conveys that a task spans multiple days and should persist through the next sync.

Sync behavior is unchanged — `Ongoing` is treated identically to the current `In Progress`: import with `carried_forward=True`, do not clear Notion.

**Migration path:** The import handler already logs a warning and skips unrecognised status values, so renaming in Notion does not break existing rows or the sync logic. A one-time find-and-replace of `In Progress` → `Ongoing` in the Notion database is all that's needed. Update the constant in `backend/services/notion_sync/client.py` to match.

---

### Fix 3 — Replace "Pending" with "No Change" as the default status

Replace the `Pending` status with `No Change` as the idle/default state for a reactor slot.

**Rationale:** "Pending" reads as "waiting for something to happen," which causes hesitation — is the system waiting for me, or am I waiting for the system? "No Change" is an explicit, active acknowledgment: the reactor owner has looked at this slot and there is nothing to do today. It also serves as the "nothing to record on absence" signal, which is the main workflow gap.

**Sync behavior for `No Change`:** identical to current `Pending` — skip import, treat as empty. No new logic required.

**Status set summary after Fixes 2 and 3:**

| Status | Meaning | What sync does |
|---|---|---|
| `No Change` | Default. No task today; owner has reviewed or slot is idle. | Skip import. |
| `Ongoing` | Active multi-day task. Carry forward. | Import with `carried_forward=True`; do NOT clear. Dedup via Fix 1. |
| `Completed` | Task finished. Record it and reset. | Import; clear field and reset to `No Change`. |

**Migration path:** Same as Fix 2 — find-and-replace `Pending` → `No Change` in Notion. Update the constant in `client.py`. No DB schema change needed; `notion_status` is a free-form string column.

---

## Implementation Priority

1. **Fix 1** (dedup at import time) — backend only, low risk, immediate value. Pair with the [deduplication migration script](./migrate_deduplicate_change_requests.py) to clean up existing historical data first.
2. **Fix 2 + Fix 3** (status rename) — coordinate a one-time Notion update with the team; update `client.py` constants and `docs/NOTION_SYNC.md` to match.

---

## Files Affected

- `backend/services/notion_sync/service.py` — import loop dedup logic (Fix 1)
- `backend/services/notion_sync/client.py` — status constants `PROP_CHANGE_STATUS` values (Fix 2, Fix 3)
- `docs/NOTION_SYNC.md` — update status table and sync sequence description (Fix 1, Fix 2, Fix 3)
- `migrate_deduplicate_change_requests.py` — one-time data cleanup (companion to Fix 1)
