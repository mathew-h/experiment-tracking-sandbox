# Dashboard User Guide

## Overview

The Dashboard provides a live overview of the lab's reactor status, experiment progress, and recent activity. It loads all data in a single API call and auto-refreshes every 60 seconds.

---

## Summary Metrics

Four cards at the top of the page:

| Metric | Description |
|--------|-------------|
| **Active Experiments** | Count of all experiments with status `ONGOING` |
| **Reactors In Use** | Count of reactors with an active (`ONGOING`) experiment assigned |
| **Completed This Month** | Experiments marked `COMPLETED` since the 1st of the current month |
| **Pending Results** | `ONGOING` experiments with no result recorded in the last 7 days |

---

## Reactor Grid

Shows all 18 reactor slots:

- **R01–R16** — Standard serum, HPHT, and autoclave reactors
- **CF01–CF02** — Core flood reactors

**Occupied slots** display:
- Reactor label (e.g. `R05`, `CF01`)
- Experiment ID
- Sample ID (if assigned)
- Description (first note entry, truncated to 2 lines)
- Experiment type
- Temperature (°C)
- Elapsed days (Day N)
- Pulsing green dot for `ONGOING` status

**Empty slots** appear greyed out with "Empty" badge.

### Reactor Detail Modal

Click any occupied reactor slot to open a detail panel showing all card fields in full, plus the experiment start date. A **View Detail →** button navigates to the experiment's full detail page.

---

## Experiment Timeline (Gantt)

Horizontal bar chart showing up to 100 experiments sorted by most-recent start date.

- Bar **width** is proportional to experiment duration relative to the longest experiment shown
- **Colors:** green = ONGOING, teal/blue = COMPLETED, grey = CANCELLED
- Click any bar to navigate to that experiment's detail page
- Axis shows 0d / mid / max scale

### Filtering the Timeline

Use the filter controls above the grid to narrow the timeline:

| Filter | Options |
|--------|---------|
| **Status** | Ongoing / Completed / Cancelled (multi-select) |
| **Type** | HPHT / Serum / Core Flood / Autoclave / Other (multi-select) |
| **From / To** | Date range applied to experiment start date |

Filters are applied client-side — no extra API call is made. A **(filtered)** label appears when any filter is active. Click **Clear** to reset all filters.

---

## Recent Activity Feed

Shows the last 20 entries from the modifications audit log:

- **Action** — Created / Updated / Deleted (color-coded)
- **Table** — which database table was affected
- **Experiment ID** — click to navigate to the experiment (when available)
- **Who** — the user who made the change (if recorded)
- **When** — relative time (e.g. "5m ago", "2d ago")

---

## Auto-Refresh

The dashboard automatically refreshes every 60 seconds via React Query's `refetchInterval`. Data updates silently in the background without a loading flicker.
