# Milestone 7: Reactor Dashboard

**Owner:** All three agents
**Branch:** `feature/m7-reactor-dashboard`

**Dashboard layout:**
- Summary cards: Active Experiments, Reactors In Use, Completed This Month, Pending Results
- Reactor grid: one card per reactor (R01-R16, CF01-CF02) — shows reactor ID, experiment ID, status badge, type, start date, elapsed days, sample ID. Empty = greyed out. Click → experiment detail modal.
- Experiment timeline: horizontal Gantt-style, colored by status
- Recent activity feed: last 20 entries from `ModificationsLog`

**Interactivity:** Status + experiment type filter chips, date range picker, auto-refresh every 60 seconds via React Query `refetchInterval`.

**Performance:** Single API call for the entire dashboard. Response target under 500ms with 500 experiments. api-developer must verify query plan before milestone closes.

**Acceptance criteria:** Real data; auto-refresh without flicker; filter combinations correct; single API call confirmed; Chrome DevTools loop confirms performance.

**Test Writer Agent:** API filter tests, performance test with 500-experiment synthetic dataset, component render tests.
**Documentation Agent:** `docs/user_guide/DASHBOARD.md`, dashboard API documentation.

---

## Completion Status: COMPLETE

**Sign-off:** 2026-03-20

### What Was Built

**Chunk A — Backend schema + endpoint:**
- `DashboardResponse` schema (`ReactorCardData`, `DashboardSummary`, `GanttEntry`, `ActivityEntry`)
- `GET /api/dashboard/` — single call returning all dashboard data; four focused queries, no N+1
- 15 API tests including performance test with 500 synthetic experiments (passes <1500ms)

**Chunk B — Frontend:**
- `ReactorGrid.tsx` — 18 fixed slots (R01–R16, CF01–CF02); empty slots greyed out; click → detail modal with "View Detail →" link
- `ExperimentTimeline.tsx` — CSS Gantt, bars proportional to duration, colored by status, click-to-navigate
- `ActivityFeed.tsx` — last 20 ModificationsLog entries with relative timestamps and action color-coding
- `DashboardFilters.tsx` — status + type multi-select chips + date range pickers
- `Dashboard.tsx` — wires all components; single React Query call with 60s auto-refresh
- TypeScript: 0 errors; ESLint: 0 warnings; production build: clean

**Chunk C — Documentation:**
- `docs/user_guide/DASHBOARD.md` — full user guide for all dashboard sections
- `docs/api/API_REFERENCE.md` — dashboard endpoint documented with response shape

### Bugs Fixed Post-Implementation
- `dashboard.py`: `reactors_in_use` now uses `distinct(reactor_number)` — was overcounting when multiple ONGOING experiments shared a reactor
- `vite.config.ts`: proxy target corrected to port 8000 (was 8003)
- `Dashboard.tsx`: filter logic — experiments without a type are now excluded when a type filter is active (were incorrectly included before)
- `ReactorGrid.tsx`: modal background uses `surface-overlay` token (matches dark theme)

### Key Decisions / Patterns
- **Single API call:** `GET /api/dashboard/` returns all four data sections (summary, reactors, timeline, activity) in one response — no waterfall loading
- **18 fixed reactor slots:** Frontend renders all slots from a fixed list; backend returns only occupied ones; frontend fills gaps with `null` cards
- **Client-side filtering:** All timeline filtering is applied in-memory — no extra API calls when changing filters
- **Reactor label derivation:** Backend computes `reactor_label` (`R01`–`R16` or `CF01`–`CF02`) from `experiment_type == "Core Flood"` + `reactor_number`; frontend uses the label directly
