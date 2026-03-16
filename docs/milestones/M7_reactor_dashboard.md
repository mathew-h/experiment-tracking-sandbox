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
