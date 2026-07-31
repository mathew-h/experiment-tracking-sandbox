# Dashboard User Guide

## Overview

The Dashboard provides a live overview of the lab's reactor status, experiment progress, and recent activity. It loads all data in a single API call and auto-refreshes every 60 seconds.

---

## Summary Metrics

Four cards at the top of the page:

| Metric | Description |
|--------|-------------|
| **Reactor Occupancy** | Segmented bar over the 16 HPHT vessel slots (R01–R16): green ticks = ongoing, amber = queued, grey = empty. Subtitle shows queued/empty counts. |
| **GC Measurements** | Count of results whose **GC Run Date** falls in the last 7 workdays, plus the number of distinct experiments they came from. |
| **Serum Vials Started** | Count of Serum experiment vials (including replicates) whose start date falls in the last 7 workdays, plus the number of distinct base experiments. |
| **Core Floods Ongoing** | Segmented bar over the 3 core flood rig slots (CF01–CF03), same tick treatment as Reactor Occupancy. |

**"Last 7 workdays"** means the last 7 Monday–Friday dates in the lab's local timezone (`America/New_York`), including today if today is a workday. US federal holidays are not skipped and are treated as ordinary workdays. The exact window (e.g. "Jul 21 – Jul 29") is shown on hover over the GC Measurements and Serum Vials Started cards.

### A GC Measurements count of 0 means "no GC Run Date recorded," not "no GC work"

The card only counts a result if its **GC Run Date** field is filled in. A
result can have a hydrogen (H₂) reading — meaning GC was actually run — and
still not be counted here, if the run date was never entered. When that
happens, the card's subtitle says so directly: "no GC Run Date recorded in
this window," rather than "across 0 experiments," so a `0` doesn't read as an
idle lab when it actually means a data-entry gap. Hovering over the card
shows a tooltip stating exactly what it counts.

Two places help close that gap:

- **Master Results upload** now warns when a row arrives with an H₂ reading
  but a blank `GC Run Date` column, naming the affected spreadsheet rows so
  they can be corrected and re-uploaded.
- **The Results tab** shows the NMR, ICP, GC, and XRD run dates for each
  timepoint. If a timepoint has an H₂ reading but no GC run date, the GC line
  reads "not recorded" in place of a date, with a short note explaining that
  it isn't counted on the Dashboard until the date is filled in.

---

## Reactor Grid

Shows all 19 reactor slots:

- **R01–R16** — Standard serum, HPHT, and autoclave reactors
- **CF01–CF03** — Core flood reactors

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
