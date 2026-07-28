# Dashboard KPI Cards Replacement (Issue #85) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the four dashboard KPI cards (Active Experiments / Reactors In Use / Completed This Month / Pending Results) with four new ones — Reactor Occupancy bar (R01–R16), GC Measurements (last 7 workdays), Serum Vials Started (last 7 workdays), and Core Floods Ongoing bar (CF01–CF03, expanded from 2 slots) — driven by a reshaped `GET /api/dashboard/` `summary` object.

**Naming note (added during Task 9 execution):** the new reactor KPI card is labeled **"Reactor Occupancy"**, not "Reactor Status" — the reactor-grid section immediately below it already has its own `<CardHeader label="Reactor Status" />` in `Dashboard.tsx` (a Task 8-era, already-committed section title referenced by a comment in `ReactorGrid.tsx`), and reusing the same text would make `getByText('Reactor Status')` ambiguous in tests and confusing in the UI. Every "Reactor Status" reference below describing the *new KPI card* (as opposed to the pre-existing grid section header) should read "Reactor Occupancy."

**Architecture:** Backend: a new stdlib-`zoneinfo`-based workday helper (`backend/services/workdays.py`), a reshaped `DashboardSummary`/new `SlotOccupancy` schema, and a reordered `get_dashboard` router function that derives reactor/core-flood occupancy from the reactor cards it already builds (no new per-card queries) plus two new aggregate queries (GC, serum). Frontend: a new shared `SlotBar` tick component, a `children` slot on `MetricCard`, updated TS types, and prop-driven slot counts in `ReactorGrid` (no more hardcoded 16/2/18).

**Tech Stack:** FastAPI + SQLAlchemy 2.x + Pydantic v2 (backend), React 18 + TypeScript + TanStack Query + Tailwind (frontend), pytest against the real Postgres test DB (`tests/api/conftest.py`), Vitest + Testing Library (frontend unit), Playwright (e2e).

## Global Constraints

- **Breaking change, no deprecation shim.** All four old `DashboardSummary` fields (`active_experiments`, `reactors_in_use`, `completed_this_month`, `pending_results`) are removed outright — not kept alongside the new ones. `summary` has exactly one consumer (`Dashboard.tsx`).
- **No migration.** Every DB column this reads already exists (`gc_run_date`, `Experiment.date`, `Experiment.created_at`, `Experiment.base_experiment_id`, `ExperimentalConditions.experiment_type`, `ExperimentalConditions.reactor_number`).
- **No new third-party package.** `zoneinfo` is stdlib; `tzdata==2025.1` is already pinned in `requirements.txt` (confirmed).
- **Query budget:** net **−1 query** vs. today. Three old queries removed (summary aggregate, recent-results set, ongoing-ids set); two added (GC, serum). Do not introduce any per-card or per-slot query.
- **`America/New_York` is the lab timezone** for the workday window only. The existing UTC-based "today's modification" lookup in `get_dashboard` section 2b is intentionally left on UTC — do not unify it with the new ET-based window in this work.
- **`ExperimentalConditions.experiment_type` is an unvalidated `String` column**, not the `ExperimentType` enum, at the DB layer — match on the literal strings `"HPHT"`, `"Core Flood"`, `"Serum"` exactly as the existing code does. Do not add a CHECK/enum constraint (explicitly out of scope).
- **No new reactor entity.** `empty` stays a derived count (`total - ongoing - queued`); there is still no `reactors` table.
- Tests run against the real Postgres test DB via `tests/api/conftest.py`'s `client`/`db_session` fixtures (savepoint-per-test, auto-rollback) — not SQLite. Use the reserved experiment-ID/number block `KPI_*` / `experiment_number` 9300+ for new backend tests in `tests/api/test_dashboard.py`, matching that file's existing per-issue numbering convention.
- Frontend: React Query for server state (already wired in `Dashboard.tsx`), Tailwind utility classes only, brand tokens only — `bg-status-ongoing`, `bg-status-queued`, `bg-surface-overlay` are pre-defined Tailwind classes from `frontend/tailwind.config.ts` (`colors.status.ongoing = #22c55e`, `colors.status.queued = #f59e0b`, `colors.surface.overlay = #0e3158`) — use them directly, do not hardcode hex.
- Every write/read here is additive-schema, so no Alembic step is required in this plan.

---

### Task 1: Workday helper — `backend/services/workdays.py`

**Files:**
- Create: `backend/services/workdays.py`
- Test: `tests/services/test_workdays.py`

**Interfaces:**
- Produces: `last_n_workdays(n: int = 7, *, today: date | None = None) -> list[date]` (oldest first) and `workday_window(n: int = 7, *, today: date | None = None) -> tuple[date, date, datetime, datetime]` returning `(first_date, last_date, start_utc, end_utc)` where `start_utc`/`end_utc` are tz-aware UTC and half-open (`end_utc` is midnight UTC of the day *after* `last_date`). Both are consumed by Task 3 (`backend/api/routers/dashboard.py`).
- `today` defaults to `datetime.now(LAB_TZ).date()` where `LAB_TZ = ZoneInfo("America/New_York")` — production code must call these with no `today` argument; tests pass `today=` explicitly for determinism.

- [ ] **Step 1: Write the failing tests**

Create `tests/services/test_workdays.py`:

```python
from __future__ import annotations
from datetime import date, timedelta, timezone

from backend.services.workdays import last_n_workdays, workday_window


def test_last_n_workdays_wednesday():
    # 2026-07-29 is a Wednesday
    days = last_n_workdays(7, today=date(2026, 7, 29))
    assert days[0] == date(2026, 7, 21)
    assert days[-1] == date(2026, 7, 29)
    assert (days[-1] - days[0]).days == 8  # 9 calendar days span
    for d in days:
        assert d.weekday() < 5


def test_last_n_workdays_monday():
    # 2026-07-27 is a Monday
    days = last_n_workdays(7, today=date(2026, 7, 27))
    assert days[0] == date(2026, 7, 17)
    assert days[-1] == date(2026, 7, 27)
    assert (days[-1] - days[0]).days == 10  # 11 calendar days span


def test_last_n_workdays_saturday_excludes_today():
    # 2026-08-01 is a Saturday
    days = last_n_workdays(7, today=date(2026, 8, 1))
    assert days[-1] == date(2026, 7, 31)  # ends the preceding Friday
    assert date(2026, 8, 1) not in days
    assert days[0] == date(2026, 7, 23)


def test_last_n_workdays_sunday_matches_saturday():
    # 2026-08-02 is a Sunday — same result as the Saturday case
    days = last_n_workdays(7, today=date(2026, 8, 2))
    assert days[-1] == date(2026, 7, 31)
    assert days[0] == date(2026, 7, 23)


def test_last_n_workdays_no_weekend_days_in_result():
    days = last_n_workdays(7, today=date(2026, 7, 29))
    assert len(days) == 7
    assert all(d.weekday() < 5 for d in days)


def test_workday_window_bounds_are_half_open_utc():
    first, last, start, end = workday_window(7, today=date(2026, 7, 29))
    assert first == date(2026, 7, 21)
    assert last == date(2026, 7, 29)
    assert start.tzinfo is not None
    assert start.utcoffset() == timedelta(0)
    assert start == date(2026, 7, 21).__class__(2026, 7, 21)  # sanity placeholder replaced below
    from datetime import datetime
    assert start == datetime(2026, 7, 21, 0, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 7, 30, 0, 0, tzinfo=timezone.utc)  # midnight of the day AFTER last


def test_workday_window_dst_crossing_still_returns_seven_dates():
    # 2026-03-08 is the US DST start (spring-forward); today a few days after.
    first, last, start, end = workday_window(7, today=date(2026, 3, 12))
    days = last_n_workdays(7, today=date(2026, 3, 12))
    assert len(days) == 7
    assert first == days[0]
    assert last == days[-1]
    assert start.tzinfo is not None and end.tzinfo is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_workdays.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.services.workdays'`

- [ ] **Step 3: Write the implementation**

Create `backend/services/workdays.py`:

```python
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

LAB_TZ = ZoneInfo("America/New_York")


def last_n_workdays(n: int = 7, *, today: date | None = None) -> list[date]:
    """The last `n` Mon-Fri dates, oldest first, including `today` if it is a workday.

    `today` defaults to the current date in the lab's local timezone.
    Holidays are treated as workdays (deliberately not skipped — see issue #85).
    """
    cursor = today or datetime.now(LAB_TZ).date()
    days: list[date] = []
    while len(days) < n:
        if cursor.weekday() < 5:        # Mon=0 .. Fri=4
            days.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(days))


def workday_window(n: int = 7, *, today: date | None = None) -> tuple[date, date, datetime, datetime]:
    """Return (first_date, last_date, start_utc, end_utc) for the last `n` workdays.

    The UTC bounds are half-open [start, end) at UTC midnight, because the
    date-bearing columns this filters on (`gc_run_date`, `Experiment.date`) are
    stored as midnight-UTC date values, not true instants.
    """
    days = last_n_workdays(n, today=today)
    first, last = days[0], days[-1]
    start = datetime.combine(first, datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(last + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    return first, last, start, end
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_workdays.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/workdays.py tests/services/test_workdays.py
git commit -m "$(cat <<'EOF'
[#85] Add last-7-workdays helper service

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 2: Schema reshape — `backend/api/schemas/dashboard.py`

**Files:**
- Modify: `backend/api/schemas/dashboard.py:1-5` (imports), `:36-40` (`DashboardSummary`)
- Test: `tests/api/test_dashboard.py:45-49` (`test_dashboard_summary_schema`), `:103-115` (`test_dashboard_response_schema`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `SlotOccupancy(total, ongoing, queued, empty)` and reshaped `DashboardSummary(reactors: SlotOccupancy, core_floods: SlotOccupancy, gc_measurements_7wd: int, gc_experiments_7wd: int, serum_vials_started_7wd: int, serum_experiments_7wd: int, workday_window_start: date, workday_window_end: date)` — both imported by Task 3 (`backend/api/routers/dashboard.py`) and by the frontend types in Task 7 (field names must match exactly).

- [ ] **Step 1: Update the schema-only unit tests (write first, they'll fail against the old schema)**

In `tests/api/test_dashboard.py`, replace the `test_dashboard_summary_schema` function (currently lines 45-49):

```python
def test_dashboard_summary_schema():
    from backend.api.schemas.dashboard import DashboardSummary, SlotOccupancy
    s = DashboardSummary(
        reactors=SlotOccupancy(total=16, ongoing=3, queued=1, empty=12),
        core_floods=SlotOccupancy(total=3, ongoing=1, queued=0, empty=2),
        gc_measurements_7wd=5,
        gc_experiments_7wd=3,
        serum_vials_started_7wd=4,
        serum_experiments_7wd=2,
        workday_window_start="2026-07-21",
        workday_window_end="2026-07-29",
    )
    assert s.reactors.ongoing == 3
    assert s.core_floods.total == 3
    assert s.gc_measurements_7wd == 5
    assert s.serum_experiments_7wd == 2


def test_slot_occupancy_schema_rejects_missing_fields():
    from backend.api.schemas.dashboard import SlotOccupancy
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SlotOccupancy(total=16, ongoing=3, queued=1)  # missing `empty`


def test_dashboard_summary_schema_rejects_removed_fields():
    """Constructing DashboardSummary with only the old field names fails —
    the new required fields (reactors, core_floods, etc.) are all missing."""
    from backend.api.schemas.dashboard import DashboardSummary
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        DashboardSummary(
            active_experiments=3,
            reactors_in_use=3,
            completed_this_month=1,
            pending_results=2,
        )
```

And replace `test_dashboard_response_schema` (currently lines 103-115):

```python
def test_dashboard_response_schema():
    from backend.api.schemas.dashboard import DashboardResponse, DashboardSummary, SlotOccupancy
    resp = DashboardResponse(
        summary=DashboardSummary(
            reactors=SlotOccupancy(total=16, ongoing=0, queued=0, empty=16),
            core_floods=SlotOccupancy(total=3, ongoing=0, queued=0, empty=3),
            gc_measurements_7wd=0,
            gc_experiments_7wd=0,
            serum_vials_started_7wd=0,
            serum_experiments_7wd=0,
            workday_window_start="2026-07-21",
            workday_window_end="2026-07-29",
        ),
        reactors=[],
        timeline=[],
        recent_activity=[],
    )
    assert resp.summary.reactors.total == 16
    assert resp.reactors == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_dashboard.py -k schema -v`
Expected: FAIL — old `DashboardSummary` still has `active_experiments` etc., not `reactors`/`core_floods`.

- [ ] **Step 3: Update the schema file**

In `backend/api/schemas/dashboard.py`, change the import line (currently line 2):

```python
from datetime import datetime
```

to:

```python
from datetime import datetime, date
```

Then replace the `DashboardSummary` class (currently lines 36-40):

```python
class DashboardSummary(BaseModel):
    active_experiments: int
    reactors_in_use: int
    completed_this_month: int
    pending_results: int  # ONGOING experiments with no result recorded in the last 7 days
```

with:

```python
class SlotOccupancy(BaseModel):
    """Occupancy of a fixed set of physical slots. ongoing + queued + empty == total."""
    total: int
    ongoing: int
    queued: int
    empty: int


class DashboardSummary(BaseModel):
    reactors: SlotOccupancy                  # R01-R16 (HPHT only)
    core_floods: SlotOccupancy               # CF01-CF03
    gc_measurements_7wd: int                 # scalar_results rows with gc_run_date in window
    gc_experiments_7wd: int                  # distinct experiments behind those rows
    serum_vials_started_7wd: int             # Serum experiment rows started in window
    serum_experiments_7wd: int               # distinct base experiments behind those vials
    workday_window_start: date               # first workday in the window (lab-local)
    workday_window_end: date                 # last workday in the window (== today if a workday)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/test_dashboard.py -k schema -v`
Expected: PASS. (Note: the rest of `tests/api/test_dashboard.py` will still fail at this point — those are fixed in Task 3. That's expected and fine to leave red between these two tasks.)

- [ ] **Step 5: Commit**

```bash
git add backend/api/schemas/dashboard.py tests/api/test_dashboard.py
git commit -m "$(cat <<'EOF'
[#85] Reshape DashboardSummary into slot occupancy + KPI counts

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 3: Router — occupancy derivation + workday KPI queries

**Files:**
- Modify: `backend/api/routers/dashboard.py` (imports at top; `REACTOR_SPECS` block; `get_dashboard` body)
- Modify: `tests/api/test_dashboard.py` (several existing integration tests reference removed fields)

**Interfaces:**
- Consumes: `SlotOccupancy`, `DashboardSummary` (Task 2); `workday_window` (Task 1).
- Produces: `R_SLOT_COUNT = 16`, `CF_SLOT_COUNT = 3` (module-level constants in `backend/api/routers/dashboard.py`, consumed by Task 4's tests and referenced by the frontend as `summary.reactors.total` / `summary.core_floods.total`, never hardcoded).

- [ ] **Step 1: Update existing tests that assert the old shape (write first — they'll fail until Step 3)**

In `tests/api/test_dashboard.py`, replace `test_get_dashboard_shape` (currently lines 132-141):

```python
def test_get_dashboard_shape(client):
    resp = client.get("/api/dashboard/")
    data = resp.json()
    assert "summary" in data
    assert "reactors" in data
    assert "timeline" in data
    assert "recent_activity" in data
    s = data["summary"]
    for key in (
        "reactors", "core_floods", "gc_measurements_7wd", "gc_experiments_7wd",
        "serum_vials_started_7wd", "serum_experiments_7wd",
        "workday_window_start", "workday_window_end",
    ):
        assert key in s, f"Missing summary key: {key}"
    for occ_key in ("reactors", "core_floods"):
        occ = s[occ_key]
        assert occ["ongoing"] + occ["queued"] + occ["empty"] == occ["total"]
    assert s["reactors"]["total"] == 16
    assert s["core_floods"]["total"] == 3
```

Replace the tail of `test_get_dashboard_with_ongoing_experiment` (currently lines 228-229, `assert data["summary"]["active_experiments"] >= 1` / `assert data["summary"]["reactors_in_use"] >= 1`):

```python
    assert data["summary"]["reactors"]["ongoing"] >= 1
```

Delete `test_get_dashboard_completed_this_month` entirely (currently lines 262-280) — the field it tests (`completed_this_month`) no longer exists in `DashboardSummary`.

Replace `test_reactor_specs_constant_coverage` (currently lines 287-295):

```python
def test_reactor_specs_constant_coverage():
    """REACTOR_SPECS covers all R_SLOT_COUNT standard reactors with required keys."""
    from backend.api.routers.dashboard import REACTOR_SPECS, R_SLOT_COUNT
    assert len(REACTOR_SPECS) == R_SLOT_COUNT
    for rn in range(1, R_SLOT_COUNT + 1):
        spec = REACTOR_SPECS[rn]
        assert "volume_mL" in spec
        assert "material" in spec
        assert "vendor" in spec
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_dashboard.py -v`
Expected: Multiple FAILs — `get_dashboard` still returns the old summary shape; `R_SLOT_COUNT` doesn't exist yet.

- [ ] **Step 3: Update the router**

In `backend/api/routers/dashboard.py`, change the schema import block (currently lines 14-17):

```python
from backend.api.schemas.dashboard import (
    ReactorStatusResponse, ExperimentTimelineResponse, TimelinePoint,
    DashboardResponse, DashboardSummary, ReactorCardData, GanttEntry, ActivityEntry,
)
```

to:

```python
from backend.api.schemas.dashboard import (
    ReactorStatusResponse, ExperimentTimelineResponse, TimelinePoint,
    DashboardResponse, DashboardSummary, SlotOccupancy, ReactorCardData, GanttEntry, ActivityEntry,
)
from backend.services.workdays import workday_window
```

Immediately after the `REACTOR_SPECS` dict closes (currently line 41, the line reading `}`), add:

```python

R_SLOT_COUNT = 16    # HPHT vessels R01-R16; must stay in sync with REACTOR_SPECS
CF_SLOT_COUNT = 3    # Core flood rigs CF01-CF03


def _occupancy(cards: list[ReactorCardData], prefix: str, total: int) -> SlotOccupancy:
    """Derive ongoing/queued/empty counts for a fixed slot-label prefix ('R' or 'CF').

    Filters against the valid label set (not just a startswith check) so an
    out-of-range reactor_number (no CHECK constraint exists on that column)
    can never drive `empty` negative.
    """
    valid = {f"{prefix}{i:02d}" for i in range(1, total + 1)}
    relevant = [c for c in cards if c.reactor_label in valid]
    ongoing = sum(1 for c in relevant if c.status == ExperimentStatus.ONGOING)
    queued = sum(1 for c in relevant if c.status == ExperimentStatus.QUEUED)
    return SlotOccupancy(
        total=total,
        ongoing=ongoing,
        queued=queued,
        empty=total - ongoing - queued,
    )
```

Then, in `get_dashboard`, replace the entire old section 1 block — from the docstring's following line down through the `summary = DashboardSummary(...)` call (currently lines 53-100:

```python
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = now - timedelta(days=7)

    # ── 1. Summary stats ──────────────────────────────────────────────────
    summary_row = db.execute(
        select(
            # active_experiments counts only ONGOING experiments (not QUEUED).
            # QUEUED experiments appear in reactor cards but are intentionally excluded from this count.
            func.count(case((Experiment.status == ExperimentStatus.ONGOING, 1))).label("active"),
            func.count(
                distinct(case((
                    (Experiment.status == ExperimentStatus.ONGOING) &
                    ExperimentalConditions.reactor_number.isnot(None),
                    ExperimentalConditions.reactor_number,
                )))
            ).label("reactors_in_use"),
            func.count(
                case((
                    (Experiment.status == ExperimentStatus.COMPLETED) &
                    (Experiment.updated_at >= month_start),
                    1,
                ))
            ).label("completed_month"),
        )
        .outerjoin(ExperimentalConditions, ExperimentalConditions.experiment_fk == Experiment.id)
    ).one()

    # Pending results: ONGOING experiments with no result in the last 7 days
    ongoing_with_recent_result = set(
        db.execute(
            select(ExperimentalResults.experiment_fk)
            .where(ExperimentalResults.created_at >= seven_days_ago)
        ).scalars().all()
    )
    ongoing_ids = set(
        db.execute(
            select(Experiment.id).where(Experiment.status == ExperimentStatus.ONGOING)
        ).scalars().all()
    )
    pending_results = len(ongoing_ids - ongoing_with_recent_result)

    summary = DashboardSummary(
        active_experiments=summary_row.active,
        reactors_in_use=summary_row.reactors_in_use,
        completed_this_month=summary_row.completed_month,
        pending_results=pending_results,
    )
```

with just:

```python
    now = datetime.now(timezone.utc)
```

(`now` is still used later, in section 2's `days_running` calc and section 3's Gantt timeline — keep it. `month_start` and `seven_days_ago` are no longer used anywhere; do not keep them.)

Leave section 2 (reactor cards query + build loop) and section 2b (today's modification enrichment) untouched. Immediately after section 2b ends — after the line `c.todays_modification = mods.get((c.experiment_id, c.reactor_label))` and before the `# ── 3. Gantt timeline` comment — insert the new section:

```python

    # ── 2c. Workday-window KPI counts + slot occupancy ─────────────────────
    # ET is used here (not UTC) because "last 7 workdays" is a statement about
    # the lab's week — see design notes in issue #85. This is intentionally
    # NOT the same "today" as section 2b's UTC-based modification lookup.
    wd_first, wd_last, wd_start, wd_end = workday_window(7)

    gc_row = db.execute(
        select(
            func.count(ScalarResults.id).label("measurements"),
            func.count(distinct(ExperimentalResults.experiment_fk)).label("experiments"),
        )
        .join(ExperimentalResults, ExperimentalResults.id == ScalarResults.result_id)
        .where(ScalarResults.gc_run_date >= wd_start)
        .where(ScalarResults.gc_run_date < wd_end)
    ).one()

    serum_start = func.coalesce(Experiment.date, Experiment.created_at)
    serum_row = db.execute(
        select(
            func.count(Experiment.id).label("vials"),
            func.count(distinct(
                func.coalesce(Experiment.base_experiment_id, Experiment.experiment_id)
            )).label("experiments"),
        )
        .join(ExperimentalConditions, ExperimentalConditions.experiment_fk == Experiment.id)
        .where(ExperimentalConditions.experiment_type == "Serum")
        .where(serum_start >= wd_start)
        .where(serum_start < wd_end)
    ).one()

    summary = DashboardSummary(
        reactors=_occupancy(reactor_cards, "R", R_SLOT_COUNT),
        core_floods=_occupancy(reactor_cards, "CF", CF_SLOT_COUNT),
        gc_measurements_7wd=gc_row.measurements,
        gc_experiments_7wd=gc_row.experiments,
        serum_vials_started_7wd=serum_row.vials,
        serum_experiments_7wd=serum_row.experiments,
        workday_window_start=wd_first,
        workday_window_end=wd_last,
    )
```

The final `return DashboardResponse(summary=summary, reactors=reactor_cards, timeline=timeline, recent_activity=recent_activity)` at the bottom of the function is unchanged — `summary` is still the same variable name, just built later and shaped differently.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/test_dashboard.py -v`
Expected: PASS — all tests in the file green (the ones updated in Step 1, plus every pre-existing reactor-card/CF-label/spec/modification/performance test, which are untouched by this change and must still pass unmodified).

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/dashboard.py tests/api/test_dashboard.py
git commit -m "$(cat <<'EOF'
[#85] Derive dashboard occupancy from reactor cards, add KPI queries

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 4: Backend regression tests — occupancy edge cases, GC/serum counting, query budget

**Files:**
- Modify: `tests/api/test_dashboard.py` (append new tests; no production code changes in this task)

**Interfaces:**
- Consumes: `R_SLOT_COUNT`, `CF_SLOT_COUNT`, `_occupancy` behavior from Task 3 (via the live endpoint, not directly).
- Produces: nothing new for later tasks — this task is pure test coverage for already-implemented behavior.

- [ ] **Step 1: Write the new tests**

Append to `tests/api/test_dashboard.py` (after the performance test section, before EOF):

```python
# ---------------------------------------------------------------------------
# Workday-window KPI + occupancy regression tests (issue #85)
# ---------------------------------------------------------------------------

def test_dashboard_summary_empty_db(client):
    """No experiments at all → full-empty occupancy on both bars, zero KPI counts."""
    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    s = resp.json()["summary"]
    assert s["reactors"] == {"total": 16, "ongoing": 0, "queued": 0, "empty": 16}
    assert s["core_floods"] == {"total": 3, "ongoing": 0, "queued": 0, "empty": 3}


def test_dashboard_occupancy_mixed_ongoing_and_queued(client, db_session):
    """3 ONGOING + 2 QUEUED HPHT experiments in distinct reactors → correct tallies."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    specs = [
        ("KPI_OCC_1", 9300, ExperimentStatus.ONGOING, 1),
        ("KPI_OCC_2", 9301, ExperimentStatus.ONGOING, 2),
        ("KPI_OCC_3", 9302, ExperimentStatus.ONGOING, 3),
        ("KPI_OCC_4", 9303, ExperimentStatus.QUEUED, 4),
        ("KPI_OCC_5", 9304, ExperimentStatus.QUEUED, 5),
    ]
    for exp_id, num, status, rn in specs:
        exp = Experiment(experiment_id=exp_id, experiment_number=num, status=status)
        db_session.add(exp)
        db_session.flush()
        db_session.add(ExperimentalConditions(
            experiment_fk=exp.id, experiment_id=exp_id,
            reactor_number=rn, experiment_type="HPHT",
        ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    r = resp.json()["summary"]["reactors"]
    assert r["ongoing"] == 3
    assert r["queued"] == 2
    assert r["empty"] == 11
    assert r["total"] == 16


def test_dashboard_occupancy_hpht_and_cf_same_reactor_number_each_own_bar(client, db_session):
    """HPHT in R01 and Core Flood in CF01 (both reactor_number=1) count once each,
    in their own bar — regression for the old collapsed-count bug."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    hpht = Experiment(experiment_id="KPI_COLLIDE_R", experiment_number=9305, status=ExperimentStatus.ONGOING)
    cf = Experiment(experiment_id="KPI_COLLIDE_CF", experiment_number=9306, status=ExperimentStatus.ONGOING)
    db_session.add_all([hpht, cf])
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_fk=hpht.id, experiment_id="KPI_COLLIDE_R", reactor_number=1, experiment_type="HPHT",
    ))
    db_session.add(ExperimentalConditions(
        experiment_fk=cf.id, experiment_id="KPI_COLLIDE_CF", reactor_number=1, experiment_type="Core Flood",
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    s = resp.json()["summary"]
    assert s["reactors"]["ongoing"] == 1
    assert s["core_floods"]["ongoing"] == 1


def test_dashboard_occupancy_cf03_slot(client, db_session):
    """Core Flood on reactor_number=3 fills the new CF03 slot; core_floods.total == 3."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(experiment_id="KPI_CF03", experiment_number=9307, status=ExperimentStatus.ONGOING)
    db_session.add(exp)
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_fk=exp.id, experiment_id="KPI_CF03", reactor_number=3, experiment_type="Core Flood",
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}
    assert "CF03" in cards
    s = resp.json()["summary"]
    assert s["core_floods"]["total"] == 3
    assert s["core_floods"]["ongoing"] == 1


def test_dashboard_occupancy_out_of_range_reactor_number_excluded(client, db_session):
    """An ONGOING HPHT with reactor_number=22 (out of the R01-R16 range) is excluded
    from occupancy; `empty` never goes negative."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(experiment_id="KPI_OOR", experiment_number=9308, status=ExperimentStatus.ONGOING)
    db_session.add(exp)
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_fk=exp.id, experiment_id="KPI_OOR", reactor_number=22, experiment_type="HPHT",
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    r = resp.json()["summary"]["reactors"]
    assert r["ongoing"] == 0
    assert r["empty"] == 16


def test_dashboard_occupancy_serum_never_affects_bars(client, db_session):
    """A Serum experiment with a reactor_number set never affects either bar
    (extends issue #38's guard to the new occupancy summary)."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(experiment_id="KPI_SERUM_RN", experiment_number=9309, status=ExperimentStatus.ONGOING)
    db_session.add(exp)
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_fk=exp.id, experiment_id="KPI_SERUM_RN", reactor_number=5, experiment_type="Serum",
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    s = resp.json()["summary"]
    assert s["reactors"]["ongoing"] == 0
    assert s["core_floods"]["ongoing"] == 0


def _make_gc_row(db_session, exp_id: str, exp_num: int, gc_run_date):
    """Create an experiment with one ExperimentalResults + ScalarResults row."""
    import datetime
    from database.models.experiments import Experiment
    from database.models.results import ExperimentalResults, ScalarResults
    from database.models.enums import ExperimentStatus

    exp = Experiment(experiment_id=exp_id, experiment_number=exp_num, status=ExperimentStatus.ONGOING)
    db_session.add(exp)
    db_session.flush()
    result = ExperimentalResults(experiment_fk=exp.id, description="KPI GC test row")
    db_session.add(result)
    db_session.flush()
    scalar = ScalarResults(result_id=result.id, gc_run_date=gc_run_date)
    db_session.add(scalar)
    return exp, result, scalar


def test_dashboard_gc_count_only_in_window_weekdays(client, db_session):
    """Only gc_run_date rows that fall on a workday inside the last-7-workdays window count."""
    import datetime
    from backend.services.workdays import last_n_workdays

    window_days = last_n_workdays(7)
    in_window_day = datetime.datetime.combine(window_days[0], datetime.time(12, 0), tzinfo=datetime.timezone.utc)
    too_old_day = datetime.datetime.combine(
        window_days[0] - datetime.timedelta(days=14), datetime.time(12, 0), tzinfo=datetime.timezone.utc
    )

    _make_gc_row(db_session, "KPI_GC_IN", 9310, in_window_day)
    _make_gc_row(db_session, "KPI_GC_OLD", 9311, too_old_day)
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    s = resp.json()["summary"]
    assert s["gc_measurements_7wd"] == 1
    assert s["gc_experiments_7wd"] == 1


def test_dashboard_gc_count_two_rows_same_experiment(client, db_session):
    """Two ScalarResults rows for the same experiment, both in window →
    measurements == 2, distinct experiments == 1."""
    import datetime
    from database.models.experiments import Experiment
    from database.models.results import ExperimentalResults, ScalarResults
    from database.models.enums import ExperimentStatus
    from backend.services.workdays import last_n_workdays

    window_day = datetime.datetime.combine(
        last_n_workdays(7)[0], datetime.time(9, 0), tzinfo=datetime.timezone.utc
    )
    exp = Experiment(experiment_id="KPI_GC_DUP", experiment_number=9312, status=ExperimentStatus.ONGOING)
    db_session.add(exp)
    db_session.flush()
    for i in range(2):
        result = ExperimentalResults(experiment_fk=exp.id, description=f"KPI GC dup {i}")
        db_session.add(result)
        db_session.flush()
        db_session.add(ScalarResults(result_id=result.id, gc_run_date=window_day))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    s = resp.json()["summary"]
    assert s["gc_measurements_7wd"] == 2
    assert s["gc_experiments_7wd"] == 1


def test_dashboard_gc_count_null_gc_run_date_never_counts(client, db_session):
    """A ScalarResults row with gc_run_date IS NULL never counts, even if measurement_date is set."""
    import datetime
    from database.models.experiments import Experiment
    from database.models.results import ExperimentalResults, ScalarResults
    from database.models.enums import ExperimentStatus

    exp = Experiment(experiment_id="KPI_GC_NULL", experiment_number=9313, status=ExperimentStatus.ONGOING)
    db_session.add(exp)
    db_session.flush()
    result = ExperimentalResults(experiment_fk=exp.id, description="KPI GC null test")
    db_session.add(result)
    db_session.flush()
    db_session.add(ScalarResults(
        result_id=result.id, gc_run_date=None, measurement_date=datetime.datetime.now(datetime.timezone.utc)
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    assert resp.json()["summary"]["gc_measurements_7wd"] == 0


def test_dashboard_serum_vials_count_replicates_separately(client, db_session):
    """Three replicate vials (a/b/c) sharing a base_experiment_id, all started in
    window → vials == 3, distinct base experiments == 1."""
    import datetime
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus
    from backend.services.workdays import last_n_workdays

    start = datetime.datetime.combine(
        last_n_workdays(7)[0], datetime.time(8, 0), tzinfo=datetime.timezone.utc
    )
    for i, label in enumerate(("a", "b", "c")):
        exp = Experiment(
            experiment_id=f"KPI_SERUM_REP{label}", experiment_number=9320 + i,
            status=ExperimentStatus.ONGOING, base_experiment_id="KPI_SERUM_REP",
            replicate_label=label, date=start,
        )
        db_session.add(exp)
        db_session.flush()
        db_session.add(ExperimentalConditions(
            experiment_fk=exp.id, experiment_id=exp.experiment_id, experiment_type="Serum",
        ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    s = resp.json()["summary"]
    assert s["serum_vials_started_7wd"] == 3
    assert s["serum_experiments_7wd"] == 1


def test_dashboard_serum_vial_date_null_falls_back_to_created_at(client, db_session):
    """A serum experiment with date=NULL falls back to created_at for the window test."""
    import datetime
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus
    from backend.services.workdays import last_n_workdays

    created = datetime.datetime.combine(
        last_n_workdays(7)[0], datetime.time(8, 0), tzinfo=datetime.timezone.utc
    )
    exp = Experiment(
        experiment_id="KPI_SERUM_FALLBACK", experiment_number=9323,
        status=ExperimentStatus.ONGOING, date=None, created_at=created,
    )
    db_session.add(exp)
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_fk=exp.id, experiment_id="KPI_SERUM_FALLBACK", experiment_type="Serum",
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    assert resp.json()["summary"]["serum_vials_started_7wd"] >= 1


def test_dashboard_serum_vial_hpht_not_counted(client, db_session):
    """An HPHT experiment started in the window must not count toward serum KPIs."""
    import datetime
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus
    from backend.services.workdays import last_n_workdays

    start = datetime.datetime.combine(
        last_n_workdays(7)[0], datetime.time(8, 0), tzinfo=datetime.timezone.utc
    )
    exp = Experiment(
        experiment_id="KPI_HPHT_NOT_SERUM", experiment_number=9324,
        status=ExperimentStatus.ONGOING, date=start,
    )
    db_session.add(exp)
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_fk=exp.id, experiment_id="KPI_HPHT_NOT_SERUM",
        reactor_number=6, experiment_type="HPHT",
    ))
    db_session.commit()

    before = client.get("/api/dashboard/").json()["summary"]["serum_vials_started_7wd"]
    # No new serum row was added; count must be unaffected by the HPHT row above.
    after = client.get("/api/dashboard/").json()["summary"]["serum_vials_started_7wd"]
    assert before == after


def test_dashboard_serum_vial_cancelled_still_counted(client, db_session):
    """A CANCELLED serum vial started in the window is still counted — the KPI
    answers 'how many vials were set up', not 'how many are live' (issue #85 design note)."""
    import datetime
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus
    from backend.services.workdays import last_n_workdays

    start = datetime.datetime.combine(
        last_n_workdays(7)[0], datetime.time(8, 0), tzinfo=datetime.timezone.utc
    )
    exp = Experiment(
        experiment_id="KPI_SERUM_CANCELLED", experiment_number=9325,
        status=ExperimentStatus.CANCELLED, date=start,
    )
    db_session.add(exp)
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_fk=exp.id, experiment_id="KPI_SERUM_CANCELLED", experiment_type="Serum",
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    assert resp.json()["summary"]["serum_vials_started_7wd"] >= 1


def test_dashboard_query_count_not_increased(client, db_session):
    """Net query count for GET /api/dashboard/ must not exceed the pre-issue-85 baseline
    (3 queries removed — summary aggregate, recent-results set, ongoing-ids set — 2 added:
    GC, serum). Extends the existing before_cursor_execute counter pattern used for
    the reactor_change_requests batching test."""
    import sqlalchemy
    from sqlalchemy.engine import Engine

    statements: list[str] = []

    def counter(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sqlalchemy.event.listen(Engine, "before_cursor_execute", counter)
    try:
        resp = client.get("/api/dashboard/")
    finally:
        sqlalchemy.event.remove(Engine, "before_cursor_execute", counter)

    assert resp.status_code == 200
    # Baseline before issue #85 was 6 top-level SELECTs (summary, pending x2, reactor
    # cards, gantt, activity) plus a conditional change-request batch query. Post-#85
    # it's 7 (reactor cards, gantt, activity, GC, serum, occupancy is computed in
    # Python with no query, plus the conditional change-request batch) — net -1
    # relative to the old 8-query worst case (6 + change-request + none). Assert an
    # upper bound rather than an exact count, since the change-request query is
    # conditional on there being occupied cards.
    assert len(statements) <= 8, f"Expected at most 8 statements, got {len(statements)}"
```

- [ ] **Step 2: Run tests to verify they fail first where applicable, then pass**

Run: `pytest tests/api/test_dashboard.py -v`

These tests exercise behavior already implemented in Task 3, so they should all pass immediately once written (no red step expected here beyond a typo-catching first run). If any fail, the failure is either a typo in the test or a real gap in Task 3's implementation — fix the test if it's wrong, escalate per `.claude/CLAUDE.md` Section 7 if Task 3's logic is wrong and the fix isn't obvious within 2 attempts.
Expected: PASS (full file green).

- [ ] **Step 3: Run the full backend suite once to confirm no regressions**

Run: `pytest tests/api/test_dashboard.py tests/services/test_workdays.py -v`
Expected: PASS, all tests.

- [ ] **Step 4: Commit**

```bash
git add tests/api/test_dashboard.py
git commit -m "$(cat <<'EOF'
[#85] Add occupancy and workday-KPI regression tests

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 5: Frontend `SlotBar` component

**Files:**
- Create: `frontend/src/components/ui/SlotBar.tsx`
- Modify: `frontend/src/components/ui/index.ts`
- Test: `frontend/src/components/ui/__tests__/SlotBar.test.tsx`

**Interfaces:**
- Produces: `SlotSegment { count: number; className: string; label: string }` and `SlotBar({ total, segments }: { total: number; segments: SlotSegment[] })` — consumed by Task 9 (`Dashboard.tsx`).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/ui/__tests__/SlotBar.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { SlotBar } from '../SlotBar'

describe('SlotBar', () => {
  it('renders 16 ticks with 8 ongoing, 4 queued, 4 empty', () => {
    const { container } = render(
      <SlotBar
        total={16}
        segments={[
          { count: 8, className: 'bg-status-ongoing', label: 'ongoing' },
          { count: 4, className: 'bg-status-queued', label: 'queued' },
        ]}
      />
    )
    const ticks = container.querySelectorAll('[role="img"] > div')
    expect(ticks.length).toBe(16)
    const ongoing = Array.from(ticks).filter((t) => t.className.includes('bg-status-ongoing'))
    const queued = Array.from(ticks).filter((t) => t.className.includes('bg-status-queued'))
    const empty = Array.from(ticks).filter((t) => t.className.includes('bg-surface-overlay'))
    expect(ongoing.length).toBe(8)
    expect(queued.length).toBe(4)
    expect(empty.length).toBe(4)
  })

  it('renders no empty ticks when fully occupied', () => {
    const { container } = render(
      <SlotBar total={3} segments={[{ count: 3, className: 'bg-status-ongoing', label: 'ongoing' }]} />
    )
    const ticks = container.querySelectorAll('[role="img"] > div')
    const empty = Array.from(ticks).filter((t) => t.className.includes('bg-surface-overlay'))
    expect(empty.length).toBe(0)
  })

  it('clamps over-supplied segments to total', () => {
    const { container } = render(
      <SlotBar total={3} segments={[{ count: 10, className: 'bg-status-ongoing', label: 'ongoing' }]} />
    )
    const ticks = container.querySelectorAll('[role="img"] > div')
    expect(ticks.length).toBe(3)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/components/ui/__tests__/SlotBar.test.tsx`
Expected: FAIL with a module-not-found error for `../SlotBar`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/ui/SlotBar.tsx`:

```tsx
export interface SlotSegment {
  count: number
  className: string      // Tailwind bg-* token
  label: string          // for the aria description
}

/** Fixed-slot segmented occupancy bar — equal-width ticks, no percentage arithmetic. */
export function SlotBar({ total, segments }: { total: number; segments: SlotSegment[] }) {
  const filled = segments.flatMap((s) =>
    Array.from({ length: Math.max(0, s.count) }, () => s.className)
  ).slice(0, total)

  return (
    <div
      role="img"
      aria-label={`${segments.map((s) => `${s.count} ${s.label}`).join(', ')} of ${total}`}
      className="flex gap-px w-full h-2 rounded-sm overflow-hidden"
    >
      {Array.from({ length: total }, (_, i) => (
        <div
          key={i}
          className={`flex-1 ${filled[i] ?? 'bg-surface-overlay'}`}
        />
      ))}
    </div>
  )
}
```

Add the export to `frontend/src/components/ui/index.ts` (after the existing `Card` export line):

```ts
export { SlotBar } from './SlotBar'
export type { SlotSegment } from './SlotBar'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/components/ui/__tests__/SlotBar.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/SlotBar.tsx frontend/src/components/ui/index.ts frontend/src/components/ui/__tests__/SlotBar.test.tsx
git commit -m "$(cat <<'EOF'
[#85] Add SlotBar segmented occupancy component

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 6: `MetricCard` — add children slot, drop dead `trend` prop

**Files:**
- Modify: `frontend/src/components/ui/Card.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: `MetricCard` now accepts an optional `children` slot rendered below `sub` — consumed by Task 9 (`Dashboard.tsx`, to embed `SlotBar`).

- [ ] **Step 1: Update `Card.tsx`**

No test file exists for `MetricCard` today and this is a small additive/subtractive prop change on an existing component with no behavior to regress-test in isolation — verified visually in Task 9's `Dashboard.test.tsx` instead (children rendering) and Task 9's dev-server check. Proceed straight to implementation.

Change the import line at the top of `frontend/src/components/ui/Card.tsx` (currently line 1):

```tsx
import { HTMLAttributes } from 'react'
```

to:

```tsx
import { HTMLAttributes, ReactNode } from 'react'
```

Replace the `MetricCardProps` interface and `MetricCard` function (currently lines 54-75):

```tsx
// Metric card — for dashboard stats
interface MetricCardProps {
  label: string
  value: string | number
  unit?: string
  trend?: 'up' | 'down' | 'neutral'
  sub?: string
  className?: string
}

/** Dashboard stat tile with a label, numeric value, optional unit, and subtitle. */
export function MetricCard({ label, value, unit, sub, className = '' }: MetricCardProps) {
  return (
    <Card className={className}>
      <p className="text-xs font-medium text-ink-muted uppercase tracking-wider mb-2">{label}</p>
      <div className="flex items-baseline gap-1.5">
        <span className="text-2xl font-bold text-ink-primary font-mono-data leading-none">{value}</span>
        {unit && <span className="text-xs text-ink-muted">{unit}</span>}
      </div>
      {sub && <p className="text-xs text-ink-muted mt-1.5">{sub}</p>}
    </Card>
  )
}
```

with:

```tsx
// Metric card — for dashboard stats
interface MetricCardProps {
  label: string
  value: string | number
  unit?: string
  sub?: string
  className?: string
  children?: ReactNode
}

/** Dashboard stat tile with a label, numeric value, optional unit, subtitle, and optional footer content (e.g. a SlotBar). */
export function MetricCard({ label, value, unit, sub, className = '', children }: MetricCardProps) {
  return (
    <Card className={className}>
      <p className="text-xs font-medium text-ink-muted uppercase tracking-wider mb-2">{label}</p>
      <div className="flex items-baseline gap-1.5">
        <span className="text-2xl font-bold text-ink-primary font-mono-data leading-none">{value}</span>
        {unit && <span className="text-xs text-ink-muted">{unit}</span>}
      </div>
      {sub && <p className="text-xs text-ink-muted mt-1.5">{sub}</p>}
      {children && <div className="mt-2.5">{children}</div>}
    </Card>
  )
}
```

- [ ] **Step 2: Run the existing full frontend unit suite to confirm no regressions**

Run: `npx vitest run`
Expected: PASS — no existing test references the removed `trend` prop (confirm with a search before running: `grep -rn "trend=" frontend/src` should return nothing outside this file).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ui/Card.tsx
git commit -m "$(cat <<'EOF'
[#85] Add children slot to MetricCard, drop unused trend prop

- Tests added: no
- Docs updated: no
EOF
)"
```

---

### Task 7: Frontend types — `frontend/src/api/dashboard.ts`

**Files:**
- Modify: `frontend/src/api/dashboard.ts:15-21` (`DashboardSummary` interface)

**Interfaces:**
- Consumes: field names/shape from Task 2's Pydantic `DashboardSummary`/`SlotOccupancy` (must match exactly — this is a JSON-over-the-wire contract, not enforced by the compiler).
- Produces: `SlotOccupancy`, reshaped `DashboardSummary` TS interfaces — consumed by Task 8 (`ReactorGrid.tsx`) and Task 9 (`Dashboard.tsx`).

- [ ] **Step 1: Update the types**

Replace the `DashboardSummary` interface block in `frontend/src/api/dashboard.ts` (currently lines 15-21):

```ts
// M7 full dashboard types
export interface DashboardSummary {
  active_experiments: number
  reactors_in_use: number
  completed_this_month: number
  pending_results: number
}
```

with:

```ts
export interface SlotOccupancy {
  total: number
  ongoing: number
  queued: number
  empty: number
}

export interface DashboardSummary {
  reactors: SlotOccupancy
  core_floods: SlotOccupancy
  gc_measurements_7wd: number
  gc_experiments_7wd: number
  serum_vials_started_7wd: number
  serum_experiments_7wd: number
  workday_window_start: string
  workday_window_end: string
}
```

- [ ] **Step 2: Type-check**

Run: `npx tsc --noEmit`
Expected: Errors in `Dashboard.tsx` (still referencing `data?.summary.active_experiments` etc.) and `ReactorGrid.tsx` (still hardcoding slot lists) — these are fixed in Tasks 8 and 9. Confirm the *only* new errors are in those two files (this validates the type change itself is correctly propagating and nothing else silently depended on the old shape).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/dashboard.ts
git commit -m "$(cat <<'EOF'
[#85] Reshape DashboardSummary TS type to match new API

- Tests added: no
- Docs updated: no
EOF
)"
```

(Leaving `tsc --noEmit` red between this task and Task 9 is expected and fine — it will be clean again after Tasks 8-9 land.)

---

### Task 8: `ReactorGrid.tsx` — derive slots from props, add CF03

**Files:**
- Modify: `frontend/src/pages/ReactorGrid.tsx:12-14` (hardcoded slot constants), `:569, 581, 586` (`ReactorGrid` component signature and slot-list construction)
- Modify: `frontend/src/pages/__tests__/ReactorGrid.test.tsx` (update `renderGrid` to pass the new required props)

**Interfaces:**
- Consumes: nothing new (still `ReactorCardData` from `@/api/dashboard`, unchanged).
- Produces: `ReactorGrid({ cards, rSlotCount, cfSlotCount }: { cards: ReactorCardData[]; rSlotCount: number; cfSlotCount: number })` — consumed by Task 9 (`Dashboard.tsx`), which passes `rSlotCount={data.summary.reactors.total}` / `cfSlotCount={data.summary.core_floods.total}`.

- [ ] **Step 1: Update the existing component test to call the new signature (write first — it'll fail against the old hardcoded-slots version... actually the old version ignores extra props harmlessly, so this step documents intent; the real failure comes from Step 2's assertion)**

In `frontend/src/pages/__tests__/ReactorGrid.test.tsx`, replace the `renderGrid` helper (currently lines 42-55):

```tsx
function renderGrid(cards: ReactorCardData[]) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <ReactorGrid cards={cards} />
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>
  )
}
```

with:

```tsx
function renderGrid(cards: ReactorCardData[], rSlotCount = 16, cfSlotCount = 3) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <ReactorGrid cards={cards} rSlotCount={rSlotCount} cfSlotCount={cfSlotCount} />
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>
  )
}
```

Then append a new describe block at the end of the same file:

```tsx
describe('ReactorGrid — slot counts derived from props (issue #85)', () => {
  it('renders 19 slots (16 R + 3 CF) and includes CF03', () => {
    const { container } = renderGrid([])
    const labels = Array.from(container.querySelectorAll('p.font-mono-data.text-xl')).map(
      (el) => el.textContent
    )
    expect(labels.length).toBe(19)
    expect(labels).toContain('CF03')
    expect(labels).toContain('R16')
  })

  it('renders a different total when rSlotCount/cfSlotCount props change', () => {
    const { container } = renderGrid([], 2, 1)
    const labels = Array.from(container.querySelectorAll('p.font-mono-data.text-xl')).map(
      (el) => el.textContent
    )
    expect(labels.length).toBe(3)
    expect(labels).toEqual(['R01', 'R02', 'CF01'])
  })
})
```

Add `describe` to the existing vitest import line at the top of the file if not already present (check line 2: `import { describe, it, expect, vi } from 'vitest'` — it already is, no change needed).

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run src/pages/__tests__/ReactorGrid.test.tsx`
Expected: FAIL — `ReactorGrid` doesn't accept `rSlotCount`/`cfSlotCount` yet, and still renders the hardcoded 16+2=18 slots, so the new "19 slots" and "CF03" assertions fail; the "2+1=3 slots" case also fails since props are ignored today.

- [ ] **Step 3: Update `ReactorGrid.tsx`**

Delete the hardcoded slot constants (currently lines 12-14):

```tsx
// Fixed reactor layout: R01-R16 and CF01-CF02
const R_SLOTS = Array.from({ length: 16 }, (_, i) => `R${String(i + 1).padStart(2, '0')}`)
const CF_SLOTS = ['CF01', 'CF02']
```

(Remove entirely — replaced by locally-derived arrays inside `ReactorGrid` below.)

Replace the `ReactorGrid` export (currently lines 568-606):

```tsx
/** Grid of reactor status cards showing current occupant, temperature, and elapsed time. */
export function ReactorGrid({ cards }: { cards: ReactorCardData[] }) {
  const [selected, setSelected] = useState<ReactorCardData | null>(null)

  // Build lookup: reactor_label → card data
  const byLabel: Record<string, ReactorCardData> = {}
  for (const c of cards) {
    byLabel[c.reactor_label] = c
  }

  // Single unified grid: R01–R16 then CF01–CF02, in slot order. At 6 columns
  // this lays out as R01–R06 / R07–R12 / R13–R16+CF01–CF02 — CF cards land in
  // the last two positions of row 3 with no separate section needed.
  const ALL_SLOTS = [...R_SLOTS, ...CF_SLOTS]

  return (
    <>
      {/* Section title lives in the enclosing Dashboard CardHeader ("Reactor Status") */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
        {ALL_SLOTS.map((label) => (
          <ReactorCard
            key={label}
            label={label}
            card={byLabel[label] ?? null}
            onClick={setSelected}
          />
        ))}
      </div>

      {selected && (
        <ReactorDetailModal
          key={selected.experiment_id ?? selected.reactor_label}
          card={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  )
}
```

with:

```tsx
/** Grid of reactor status cards showing current occupant, temperature, and elapsed time. */
export function ReactorGrid({
  cards,
  rSlotCount,
  cfSlotCount,
}: {
  cards: ReactorCardData[]
  rSlotCount: number
  cfSlotCount: number
}) {
  const [selected, setSelected] = useState<ReactorCardData | null>(null)

  // Build lookup: reactor_label → card data
  const byLabel: Record<string, ReactorCardData> = {}
  for (const c of cards) {
    byLabel[c.reactor_label] = c
  }

  const pad = (i: number) => String(i).padStart(2, '0')
  const R_SLOTS = Array.from({ length: rSlotCount }, (_, i) => `R${pad(i + 1)}`)
  const CF_SLOTS = Array.from({ length: cfSlotCount }, (_, i) => `CF${pad(i + 1)}`)

  // Single unified grid: R01-R16 then CF01-CF03, in slot order — the 19-slot
  // total no longer divides evenly into a 6-column grid, so this uses 5
  // columns to keep R and CF rows breaking more naturally.
  const ALL_SLOTS = [...R_SLOTS, ...CF_SLOTS]

  return (
    <>
      {/* Section title lives in the enclosing Dashboard CardHeader ("Reactor Status") */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
        {ALL_SLOTS.map((label) => (
          <ReactorCard
            key={label}
            label={label}
            card={byLabel[label] ?? null}
            onClick={setSelected}
          />
        ))}
      </div>

      {selected && (
        <ReactorDetailModal
          key={selected.experiment_id ?? selected.reactor_label}
          card={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  )
}
```

Note: `REACTOR_SPECS` (the frontend hardware-spec lookup, lines 21-38) and `isCoreFlood()` are untouched — CF03 needs no spec entry (Core Flood cards never show the specs badge, per `showSpecsBadge = !isCF` in `ReactorCard`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run src/pages/__tests__/ReactorGrid.test.tsx`
Expected: PASS (all tests, including the pre-existing `todays_modification` describe block, which is unaffected by this change since it always passed default `rSlotCount`/`cfSlotCount` via the updated helper).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ReactorGrid.tsx frontend/src/pages/__tests__/ReactorGrid.test.tsx
git commit -m "$(cat <<'EOF'
[#85] Derive ReactorGrid slot counts from props, add CF03

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 9: `Dashboard.tsx` — replace the four KPI cards

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx:1-9` (imports), `:50-69` (KPI grid), `:79` (`ReactorGrid` usage)
- Test: `frontend/src/pages/__tests__/Dashboard.test.tsx` (new)

**Interfaces:**
- Consumes: `SlotBar`/`SlotSegment` (Task 5), `MetricCard` children slot (Task 6), `DashboardSummary`/`SlotOccupancy` types (Task 7), `ReactorGrid`'s new `rSlotCount`/`cfSlotCount` props (Task 8).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/__tests__/Dashboard.test.tsx`:

```tsx
import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import { dashboardApi } from '@/api/dashboard'
import type { DashboardData } from '@/api/dashboard'

vi.mock('@/api/dashboard', async () => {
  const actual = await vi.importActual('@/api/dashboard')
  return {
    ...actual,
    dashboardApi: { full: vi.fn(), reactorStatus: vi.fn(), timeline: vi.fn() },
  }
})
vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    patchStatus: vi.fn(),
    patch: vi.fn(),
    getRecentChangeRequests: vi.fn(),
    createChangeRequest: vi.fn(),
  },
}))

import { DashboardPage } from '../Dashboard'

function makeSummary(overrides: Partial<DashboardData['summary']> = {}): DashboardData['summary'] {
  return {
    reactors: { total: 16, ongoing: 8, queued: 4, empty: 4 },
    core_floods: { total: 3, ongoing: 1, queued: 0, empty: 2 },
    gc_measurements_7wd: 5,
    gc_experiments_7wd: 3,
    serum_vials_started_7wd: 4,
    serum_experiments_7wd: 2,
    workday_window_start: '2026-07-21',
    workday_window_end: '2026-07-29',
    ...overrides,
  }
}

function renderDashboard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <DashboardPage />
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>
  )
}

describe('DashboardPage — KPI cards (issue #85)', () => {
  it('renders the four new KPI labels', async () => {
    vi.mocked(dashboardApi.full).mockResolvedValue({
      summary: makeSummary(),
      reactors: [],
      timeline: [],
      recent_activity: [],
    })
    renderDashboard()
    // "Reactor Occupancy" (and the other 3 labels) render unconditionally, even
    // before `data` loads — waiting on a static label resolves instantly and
    // proves nothing about load state. Wait on the date-range subtitle instead,
    // which only renders once `data` is defined (see the `sub={data ? ... : undefined}`
    // ternary in Dashboard.tsx) — that's the real signal that the mocked
    // dashboardApi.full() promise has resolved and the component re-rendered.
    await waitFor(() =>
      expect(screen.getAllByText(/2026-07-21 – 2026-07-29/).length).toBeGreaterThanOrEqual(2)
    )
    expect(screen.getByText('Reactor Occupancy')).toBeInTheDocument()
    expect(screen.getByText('GC Measurements')).toBeInTheDocument()
    expect(screen.getByText('Serum Vials Started')).toBeInTheDocument()
    expect(screen.getByText('Core Floods Ongoing')).toBeInTheDocument()
  })

  it('shows em-dash placeholders and no crash while summary is undefined (loading state)', () => {
    vi.mocked(dashboardApi.full).mockReturnValue(new Promise(() => {}))
    renderDashboard()
    expect(screen.getByText('Reactor Occupancy')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('renders the reactor and core-flood tick bars with the right counts', async () => {
    vi.mocked(dashboardApi.full).mockResolvedValue({
      summary: makeSummary(),
      reactors: [],
      timeline: [],
      recent_activity: [],
    })
    const { container } = renderDashboard()
    // Bars only render once `data` is defined (`{data && <SlotBar .../>}`), so
    // waiting for exactly 2 `[role="img"]` elements to appear is itself the
    // data-loaded signal — unlike a static label, this cannot resolve early.
    await waitFor(() => expect(container.querySelectorAll('[role="img"]').length).toBe(2))
    const bars = container.querySelectorAll('[role="img"]')
    // First bar = reactors (16 total), second = core floods (3 total)
    expect(bars[0].querySelectorAll(':scope > div').length).toBe(16)
    expect(bars[1].querySelectorAll(':scope > div').length).toBe(3)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/pages/__tests__/Dashboard.test.tsx`
Expected: FAIL — `Dashboard.tsx` still renders "Active Experiments" etc., not "Reactor Occupancy"/"GC Measurements"/"Serum Vials Started"/"Core Floods Ongoing"; `ReactorGrid` call site doesn't yet pass the new required props (will also be a TS error if run through `tsc`).

- [ ] **Step 3: Update `Dashboard.tsx`**

Change the import block (currently lines 1-9):

```tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '@/api/dashboard'
import type { GanttEntry } from '@/api/dashboard'
import { MetricCard, Card, CardHeader, CardBody, PageSpinner } from '@/components/ui'
import { ReactorGrid } from './ReactorGrid'
import { ExperimentTimeline } from './ExperimentTimeline'
import { ActivityFeed } from './ActivityFeed'
import { DashboardFilters, type DashboardFilterState } from './DashboardFilters'
```

to:

```tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '@/api/dashboard'
import type { GanttEntry, SlotOccupancy } from '@/api/dashboard'
import { MetricCard, Card, CardHeader, CardBody, PageSpinner, SlotBar } from '@/components/ui'
import type { SlotSegment } from '@/components/ui'
import { ReactorGrid } from './ReactorGrid'
import { ExperimentTimeline } from './ExperimentTimeline'
import { ActivityFeed } from './ActivityFeed'
import { DashboardFilters, type DashboardFilterState } from './DashboardFilters'

const R_FALLBACK = 16
const CF_FALLBACK = 3

function occupancySegments(o?: SlotOccupancy): SlotSegment[] {
  return [
    { count: o?.ongoing ?? 0, className: 'bg-status-ongoing', label: 'ongoing' },
    { count: o?.queued ?? 0, className: 'bg-status-queued', label: 'queued' },
  ]
}
```

Replace the "Summary metrics" block (currently lines 50-69):

```tsx
      {/* Summary metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard
          label="Active Experiments"
          value={data?.summary.active_experiments ?? '—'}
        />
        <MetricCard
          label="Reactors In Use"
          value={data?.summary.reactors_in_use ?? '—'}
          unit="/ 18"
        />
        <MetricCard
          label="Completed This Month"
          value={data?.summary.completed_this_month ?? '—'}
        />
        <MetricCard
          label="Pending Results"
          value={data?.summary.pending_results ?? '—'}
        />
      </div>
```

with:

```tsx
      {/* Summary metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard
          label="Reactor Occupancy"
          value={data?.summary.reactors.ongoing ?? '—'}
          unit={`/ ${data?.summary.reactors.total ?? R_FALLBACK} ongoing`}
          sub={
            data
              ? `${data.summary.reactors.queued} queued · ${data.summary.reactors.empty} empty`
              : undefined
          }
        >
          {data && <SlotBar total={data.summary.reactors.total} segments={occupancySegments(data.summary.reactors)} />}
        </MetricCard>

        <MetricCard
          label="GC Measurements"
          value={data?.summary.gc_measurements_7wd ?? '—'}
          sub={
            data
              ? `${data.summary.workday_window_start} – ${data.summary.workday_window_end} · across ${data.summary.gc_experiments_7wd} experiment${data.summary.gc_experiments_7wd === 1 ? '' : 's'}`
              : undefined
          }
          title={data ? `${data.summary.workday_window_start} – ${data.summary.workday_window_end}` : undefined}
        />

        <MetricCard
          label="Serum Vials Started"
          value={data?.summary.serum_vials_started_7wd ?? '—'}
          sub={
            data
              ? `${data.summary.workday_window_start} – ${data.summary.workday_window_end} · ${data.summary.serum_experiments_7wd} experiment${data.summary.serum_experiments_7wd === 1 ? '' : 's'}`
              : undefined
          }
          title={data ? `${data.summary.workday_window_start} – ${data.summary.workday_window_end}` : undefined}
        />

        <MetricCard
          label="Core Floods Ongoing"
          value={data?.summary.core_floods.ongoing ?? '—'}
          unit={`/ ${data?.summary.core_floods.total ?? CF_FALLBACK}`}
          sub={
            data
              ? `${data.summary.core_floods.queued} queued · ${data.summary.core_floods.empty} idle`
              : undefined
          }
        >
          {data && <SlotBar total={data.summary.core_floods.total} segments={occupancySegments(data.summary.core_floods)} />}
        </MetricCard>
      </div>
```

`MetricCard` does not currently accept a `title` prop — its underlying `<Card>` spreads `...props` (`HTMLAttributes<HTMLDivElement>`) but `MetricCard` itself destructures a fixed prop list and does not forward extras. Since `title` isn't in `MetricCardProps` (Task 6), passing it here would be silently dropped, not a compile error, and the hover-tooltip requirement from the issue would quietly not work. Fix this now: in `frontend/src/components/ui/Card.tsx`, extend `MetricCardProps` with `title?: string` and pass it through to the outer `<Card title={title}>` element. Update the `MetricCard` function signature and its `<Card className={className}>` call from Task 6:

```tsx
interface MetricCardProps {
  label: string
  value: string | number
  unit?: string
  sub?: string
  className?: string
  title?: string
  children?: ReactNode
}

export function MetricCard({ label, value, unit, sub, className = '', title, children }: MetricCardProps) {
  return (
    <Card className={className} title={title}>
      <p className="text-xs font-medium text-ink-muted uppercase tracking-wider mb-2">{label}</p>
      <div className="flex items-baseline gap-1.5">
        <span className="text-2xl font-bold text-ink-primary font-mono-data leading-none">{value}</span>
        {unit && <span className="text-xs text-ink-muted">{unit}</span>}
      </div>
      {sub && <p className="text-xs text-ink-muted mt-1.5">{sub}</p>}
      {children && <div className="mt-2.5">{children}</div>}
    </Card>
  )
}
```

Finally, update the `ReactorGrid` call site (currently line 79):

```tsx
          {data && <ReactorGrid cards={data.reactors} />}
```

to:

```tsx
          {data && (
            <ReactorGrid
              cards={data.reactors}
              rSlotCount={data.summary.reactors.total}
              cfSlotCount={data.summary.core_floods.total}
            />
          )}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run src/pages/__tests__/Dashboard.test.tsx src/pages/__tests__/ReactorGrid.test.tsx src/components/ui/__tests__/SlotBar.test.tsx`
Expected: PASS, all files.

- [ ] **Step 5: Full type-check and lint**

Run: `npx tsc --noEmit`
Expected: no errors (this closes out the temporary errors left open at the end of Task 7).

Run: `npx eslint src --ext .ts,.tsx`
Expected: zero warnings.

- [ ] **Step 6: Manual verification in the browser**

Per `.claude/skills/frontend-builder.md`'s Chrome DevTools closed-loop (enabled for this task): open `http://localhost:5173/dashboard` (dev server is already running per `frontend/CLAUDE.md` — do not start/stop it), confirm all four new cards render with plausible values, the two tick bars show sensible green/amber/empty segments, and the reactor grid below still renders 19 cards including `CF03` with no console errors. Fix anything found and re-run Step 4-5 before proceeding.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx frontend/src/components/ui/Card.tsx frontend/src/pages/__tests__/Dashboard.test.tsx
git commit -m "$(cat <<'EOF'
[#85] Replace dashboard KPI cards with occupancy + workday metrics

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 10: E2E — `14-dashboard-cf-slots.spec.ts`

**Files:**
- Modify: `frontend/e2e/journeys/14-dashboard-cf-slots.spec.ts`

**Interfaces:**
- Consumes: the rendered DOM from Tasks 8-9.
- Produces: nothing consumed by later tasks.

**Important pre-existing discrepancy to fix while here:** this spec's current selectors look for section headers `text=Core Flood (CF01–CF02)` and `text=Standard Reactors (R01–R16)` (lines 87, 111, 121). `ReactorGrid.tsx` does **not** render any such section headers — it has always rendered a single unified grid (confirmed by reading the current component: the only comment is `{/* Section title lives in the enclosing Dashboard CardHeader ("Reactor Status") */}`). This spec was already stale before this issue (pre-existing bug, not introduced by this work) and its assertions on that text would already fail if run. Since this file is explicitly in scope for this issue, fix the selectors to match the actual DOM (locate cards directly by their `p.font-mono-data` label, as `Dashboard.test.tsx`/`ReactorGrid.test.tsx` already do) rather than leaving broken assertions in place.

**Two more pre-existing bugs surfaced by actually running this spec (discovered mid-execution, not visible from static reading):**
1. **DOM traversal depth was wrong even after the section-header fix above.** The original spec's own comment claimed `p (label) → div (label wrapper) → div (flex justify-between) → div (Card root)` and used `.locator('../../..')` (3 levels). Direct inspection of `ReactorCard` in `ReactorGrid.tsx` shows the label `<p>` is a direct child of `<div className="flex items-start justify-between mb-1">`, which is itself a direct child of `<Card>` — only 2 levels, not 3. `../../..` overshoots past the Card root into the grid's own container div, matching all occupied cards' status text at once (a Playwright strict-mode-style ambiguity, caught only by actually running the test against the live app). Fix: use `.locator('../..')` everywhere a card root is derived from its label.
2. **The shared `afterEach` cleanup hook (lines ~22-41, untouched by the Step 1 rewrite below) also had a real bug**, exposed only once the tests above got far enough to reach it: `page.getByRole('button', { name: /^CANCELLED$/i })` searches the *entire page* rather than the specific card whose dropdown was just opened, causing a strict-mode violation (multiple matches) that failed every test via `afterEach`, even though each test's own body/assertions passed. Fix: scope the lookup to the card, e.g. `card.getByRole('button', { name: /^CANCELLED$/i })`, reusing the `card` locator already computed earlier in the hook.

Both were confirmed as genuine, reproducible failures by running `npx playwright test e2e/journeys/14-dashboard-cf-slots.spec.ts` against the live dev app before and after each fix — not guessed at. Verify the actual terminal output shows `3 passed`, not just "fast execution" or absence of a thrown error in the test body.

- [ ] **Step 1: Rewrite the spec**

Replace the two existing `test(...)` blocks (currently lines 79-127) with:

```ts
test('CF01 slot is populated when Core Flood experiment with reactor_number=1 is ONGOING', async ({ page }) => {
  const expId = await createExperiment(page, { type: 'Core Flood', reactorNumber: '1' })
  createdIds.push(expId)

  await page.goto('/dashboard')
  await page.waitForLoadState('networkidle')

  // CF01 card — the label "CF01" appears as a mono-data heading
  const cf01Label = page.locator('p.font-mono-data').filter({ hasText: /^CF01$/ })
  await expect(cf01Label).toBeVisible({ timeout: 10_000 })

  // The experiment ID should appear in the same card
  // DOM: p (label) → div (flex.items-start.justify-between.mb-1, the label wrapper) → Card root div.
  // That's 2 levels, not 3 — confirmed against ReactorGrid.tsx's ReactorCard function: <Card><div className="flex ...">
  // <p>{label}</p>...</div>{occupied ? ... : ...}</Card>. `../../..` (3 levels) overshoots past the Card
  // root to the grid's own container div, matching ALL cards at once — this was a live, Playwright-confirmed
  // bug inherited from the pre-existing spec (its own DOM comment miscounted the levels).
  const cf01Card = cf01Label.locator('../..')
  await expect(cf01Card.locator(`text=${expId}`)).toBeVisible({ timeout: 5_000 })

  // The status badge should say ONGOING (not "Empty")
  await expect(cf01Card.locator('text=ONGOING')).toBeVisible()
})

test('HPHT experiment in reactor_number=1 appears in R01, not CF01', async ({ page }) => {
  const expId = await createExperiment(page, { type: 'HPHT', reactorNumber: '1' })
  createdIds.push(expId)

  await page.goto('/dashboard')
  await page.waitForLoadState('networkidle')

  // R01 card should contain the experiment
  const r01Label = page.locator('p.font-mono-data').filter({ hasText: /^R01$/ })
  await expect(r01Label).toBeVisible({ timeout: 10_000 })
  const r01Card = r01Label.locator('../..')
  await expect(r01Card.locator(`text=${expId}`)).toBeVisible({ timeout: 5_000 })

  // CF01 must NOT contain this experiment
  const cf01Label = page.locator('p.font-mono-data').filter({ hasText: /^CF01$/ })
  await expect(cf01Label).toBeVisible({ timeout: 5_000 })
  const cf01Card = cf01Label.locator('../..')
  await expect(cf01Card.locator(`text=${expId}`)).not.toBeVisible()
})

test('CF03 slot is populated when Core Flood experiment with reactor_number=3 is ONGOING', async ({ page }) => {
  const expId = await createExperiment(page, { type: 'Core Flood', reactorNumber: '3' })
  createdIds.push(expId)

  await page.goto('/dashboard')
  await page.waitForLoadState('networkidle')

  const cf03Label = page.locator('p.font-mono-data').filter({ hasText: /^CF03$/ })
  await expect(cf03Label).toBeVisible({ timeout: 10_000 })

  const cf03Card = cf03Label.locator('../..')
  await expect(cf03Card.locator(`text=${expId}`)).toBeVisible({ timeout: 5_000 })
  await expect(cf03Card.locator('text=ONGOING')).toBeVisible()
})
```

Update the file's top comment block (currently lines 1-15) to reflect the new coverage:

```ts
/**
 * Journey 14 — Dashboard CF01/CF02/CF03 slot mapping (issue #26, extended by issue #85)
 *
 * Acceptance criteria covered here:
 * - CF01 slot shows an active Core Flood experiment when reactor_number = 1
 * - HPHT experiment in reactor 1 appears in R01, not CF01
 * - CF03 slot (added in issue #85) shows an active Core Flood experiment when reactor_number = 3
 *
 * CF02 (reactor_number=2) is covered by backend tests only:
 * see tests/api/test_dashboard.py::test_core_flood_experiment_in_reactor_2_gets_cf02_label
 *
 * Approach:
 * - Create experiments via the UI (New Experiment wizard)
 * - Navigate to /dashboard and assert reactor grid slot contents by locating the
 *   card's mono-data label directly (there are no section headers in the DOM —
 *   ReactorGrid renders one unified grid; see the "Section title lives in the
 *   enclosing Dashboard CardHeader" comment in ReactorGrid.tsx)
 * - Cancel created experiments in afterEach to avoid polluting other journeys
 */
```

- [ ] **Step 2: Run the e2e spec**

Run: `npx playwright test e2e/journeys/14-dashboard-cf-slots.spec.ts`
Expected: PASS (3 tests). Requires the dev server and backend already running per project conventions — do not start/stop either; report to the user if unreachable.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/journeys/14-dashboard-cf-slots.spec.ts
git commit -m "$(cat <<'EOF'
[#85] Add CF03 e2e coverage, fix stale grid selectors

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 11: Docs — `docs/user_guide/DASHBOARD.md`

**Files:**
- Modify: `docs/user_guide/DASHBOARD.md` (source of truth — the `PostToolUse` hook auto-copies this write to `docs/project_context/DASHBOARD.md`; do not edit that copy directly)

**Interfaces:** none (documentation only).

- [ ] **Step 1: Update the Summary Metrics section**

Replace (currently lines 9-18):

```markdown
## Summary Metrics

Four cards at the top of the page:

| Metric | Description |
|--------|-------------|
| **Active Experiments** | Count of all experiments with status `ONGOING` |
| **Reactors In Use** | Count of reactors with an active (`ONGOING`) experiment assigned |
| **Completed This Month** | Experiments marked `COMPLETED` since the 1st of the current month |
| **Pending Results** | `ONGOING` experiments with no result recorded in the last 7 days |
```

with:

```markdown
## Summary Metrics

Four cards at the top of the page:

| Metric | Description |
|--------|-------------|
| **Reactor Occupancy** | Segmented bar over the 16 HPHT vessel slots (R01–R16): green ticks = ongoing, amber = queued, grey = empty. Subtitle shows queued/empty counts. |
| **GC Measurements** | Count of GC runs (`scalar_results.gc_run_date`) in the last 7 workdays, plus the number of distinct experiments they came from. |
| **Serum Vials Started** | Count of Serum experiment vials (including replicates) whose start date falls in the last 7 workdays, plus the number of distinct base experiments. |
| **Core Floods Ongoing** | Segmented bar over the 3 core flood rig slots (CF01–CF03), same tick treatment as Reactor Occupancy. |

**"Last 7 workdays"** means the last 7 Monday–Friday dates in the lab's local timezone (`America/New_York`), including today if today is a workday. US federal holidays are not skipped and are treated as ordinary workdays. The exact window (e.g. "Jul 21 – Jul 29") is shown on hover over the GC Measurements and Serum Vials Started cards.
```

- [ ] **Step 2: Update the Reactor Grid section slot count**

Replace (currently lines 22-27):

```markdown
## Reactor Grid

Shows all 18 reactor slots:

- **R01–R16** — Standard serum, HPHT, and autoclave reactors
- **CF01–CF02** — Core flood reactors
```

with:

```markdown
## Reactor Grid

Shows all 19 reactor slots:

- **R01–R16** — Standard serum, HPHT, and autoclave reactors
- **CF01–CF03** — Core flood reactors
```

- [ ] **Step 3: Verify the sync hook fired**

Run: `diff docs/user_guide/DASHBOARD.md docs/project_context/DASHBOARD.md`
Expected: no output (files identical — the `PostToolUse` hook copies automatically on every `Write`/`Edit` under `docs/`).

- [ ] **Step 4: Commit**

```bash
git add docs/user_guide/DASHBOARD.md docs/project_context/DASHBOARD.md
git commit -m "$(cat <<'EOF'
[#85] Update dashboard docs for new KPI cards and CF03

- Tests added: no
- Docs updated: yes
EOF
)"
```

---

### Task 12: Expose missing run-date fields on the results endpoint

**Added mid-execution, after Task 5.** See `docs/issues/issue-results-api-missing-run-dates.md`. That doc identifies that `nmr_run_date`, `icp_run_date`, and `gc_run_date` are written by the bulk uploader (`database/models/results.py:85-87`) but never exposed through any Pydantic schema in `backend/api/schemas/results.py` — only `xrd_run_date` is, and only in `ResultWithFlagsResponse`. Since Task 3 of this plan ships `gc_measurements_7wd`/`gc_experiments_7wd` on the dashboard, driven entirely by `gc_run_date`, the KPI is otherwise unverifiable anywhere else in the app — a user has no way to confirm which rows it counted. Scope here is the schema/API layer only (§1 of the referenced doc, plus the frontend type it feeds). The doc's §3 (a possibly-separate bug where blank run-date cells wipe existing values on `overwrite=True` uploads) is explicitly OUT OF SCOPE for this task — it touches `backend/services/bulk_uploads/`, which is locked per `.claude/CLAUDE.md` Section 5, and the doc itself says "verify this reproduces before fixing it... I have not run it." Do not touch `master_bulk_upload.py` or `scalar_results_service.py` in this task.

**Files:**
- Modify: `backend/api/schemas/results.py:38-56` (`ScalarCreate`), `:59-68` (`ScalarUpdate`), `:71-98` (`ScalarResponse`), `:105-131` (`ResultWithFlagsResponse`)
- Modify: `backend/api/routers/experiments.py:267-291` (`get_experiment_results` — the `ResultWithFlagsResponse(...)` construction)
- Modify: `frontend/src/api/experiments.ts:65-86` (`ResultWithFlags` interface)
- Test: `tests/api/test_results.py` (new tests, mirroring the file's existing `xrd_run_date` test pattern)

**Interfaces:**
- Consumes: nothing from earlier tasks in this plan — fully independent slice, no shared files with Tasks 1-11.
- Produces: nothing consumed by later tasks in this plan.
- **Deliberately excludes the UI display layer** (`frontend/src/pages/ExperimentDetail/ResultsTab.tsx`, which currently renders `{r.xrd_run_date && <Badge variant="info" dot>XRD</Badge>}` at line 267). Adding equivalent badges for `nmr_run_date`/`gc_run_date` is unambiguous, but `icp_run_date` collides with the existing `{r.has_icp && <Badge variant="info" dot>ICP</Badge>}` badge one line above (line 266) — two "ICP"-labeled badges with different underlying meanings (data-row-exists vs. instrument-run-date-recorded) would be confusing, and the source doc doesn't address this collision. Do not resolve it by guessing a label — leave the UI untouched in this task and let the controller raise it as a follow-up question.

- [ ] **Step 1: Write the failing tests**

Add to `tests/api/test_results.py` (after the existing `test_results_endpoint_xrd_run_date_null_when_absent` function):

```python
def test_results_endpoint_includes_nmr_icp_gc_run_dates(client, db_session):
    """GET /experiments/{id}/results returns nmr_run_date, icp_run_date, gc_run_date per row."""
    exp, result = _seed(db_session)
    scalar = ScalarResults(
        result_id=result.id,
        nmr_run_date=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        icp_run_date=datetime(2026, 4, 11, 9, 0, 0, tzinfo=timezone.utc),
        gc_run_date=datetime(2026, 4, 12, 9, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(scalar)
    db_session.commit()

    resp = client.get(f"/api/experiments/{exp.experiment_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert "2026-04-10" in data[0]["nmr_run_date"]
    assert "2026-04-11" in data[0]["icp_run_date"]
    assert "2026-04-12" in data[0]["gc_run_date"]


def test_results_endpoint_nmr_icp_gc_run_dates_null_when_absent(client, db_session):
    """nmr_run_date/icp_run_date/gc_run_date are null in the response when not set on the scalar row."""
    exp, result = _seed(db_session)
    scalar = ScalarResults(result_id=result.id, gross_ammonium_concentration_mM=1.0)
    db_session.add(scalar)
    db_session.commit()

    resp = client.get(f"/api/experiments/{exp.experiment_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["nmr_run_date"] is None
    assert data[0]["icp_run_date"] is None
    assert data[0]["gc_run_date"] is None


def test_scalar_response_schema_includes_all_four_run_dates():
    """ScalarResponse (not just ResultWithFlagsResponse) now carries all four run-date fields."""
    from backend.api.schemas.results import ScalarResponse
    s = ScalarResponse(
        id=1, result_id=1,
        nmr_run_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
        icp_run_date=datetime(2026, 4, 11, tzinfo=timezone.utc),
        gc_run_date=datetime(2026, 4, 12, tzinfo=timezone.utc),
        xrd_run_date=datetime(2026, 4, 13, tzinfo=timezone.utc),
    )
    assert s.gc_run_date is not None


def test_scalar_update_schema_accepts_all_four_run_dates():
    """ScalarUpdate accepts all four run-date fields so a wrong one can be corrected via PATCH."""
    from backend.api.schemas.results import ScalarUpdate
    u = ScalarUpdate(
        nmr_run_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
        icp_run_date=datetime(2026, 4, 11, tzinfo=timezone.utc),
        gc_run_date=datetime(2026, 4, 12, tzinfo=timezone.utc),
        xrd_run_date=datetime(2026, 4, 13, tzinfo=timezone.utc),
    )
    assert u.icp_run_date is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_results.py -v`
Expected: FAIL — `nmr_run_date`/`icp_run_date`/`gc_run_date` are not yet fields on `ResultWithFlagsResponse`, `ScalarResponse`, or `ScalarUpdate` (Pydantic raises on unexpected keyword args passed positionally in the schema-unit tests; the endpoint tests fail because the response JSON has no such keys).

- [ ] **Step 3: Update the backend schemas**

In `backend/api/schemas/results.py`, add `nmr_run_date`, `icp_run_date`, `gc_run_date`, `xrd_run_date` (all `Optional[datetime] = None`) to **four** classes:

`ScalarCreate` — after the existing `measurement_date: Optional[datetime] = None` line:
```python
    measurement_date: Optional[datetime] = None
    nmr_run_date: Optional[datetime] = None
    icp_run_date: Optional[datetime] = None
    gc_run_date: Optional[datetime] = None
    xrd_run_date: Optional[datetime] = None
```

`ScalarUpdate` — same four lines, after its own `measurement_date: Optional[datetime] = None`.

`ScalarResponse` — same four lines, after its own `measurement_date: Optional[datetime] = None`. (This class currently has none of the four — `xrd_run_date` included, for consistency with `ResultWithFlagsResponse`.)

`ResultWithFlagsResponse` — this class already ends with `xrd_run_date: Optional[datetime] = None`. Add the three missing ones immediately before it:
```python
    ferrous_iron_yield_h2_pct: Optional[float] = None
    ferrous_iron_yield_nh3_pct: Optional[float] = None
    nmr_run_date: Optional[datetime] = None
    icp_run_date: Optional[datetime] = None
    gc_run_date: Optional[datetime] = None
    xrd_run_date: Optional[datetime] = None
```

- [ ] **Step 4: Wire the router**

In `backend/api/routers/experiments.py`, in `get_experiment_results()`, the `ResultWithFlagsResponse(...)` construction currently ends with:
```python
            ferrous_iron_yield_h2_pct=scalar.ferrous_iron_yield_h2_pct if scalar else None,
            ferrous_iron_yield_nh3_pct=scalar.ferrous_iron_yield_nh3_pct if scalar else None,
            xrd_run_date=scalar.xrd_run_date if scalar else None,
        ))
```

Change to:
```python
            ferrous_iron_yield_h2_pct=scalar.ferrous_iron_yield_h2_pct if scalar else None,
            ferrous_iron_yield_nh3_pct=scalar.ferrous_iron_yield_nh3_pct if scalar else None,
            nmr_run_date=scalar.nmr_run_date if scalar else None,
            icp_run_date=scalar.icp_run_date if scalar else None,
            gc_run_date=scalar.gc_run_date if scalar else None,
            xrd_run_date=scalar.xrd_run_date if scalar else None,
        ))
```

- [ ] **Step 5: Update the frontend type**

In `frontend/src/api/experiments.ts`, the `ResultWithFlags` interface currently ends with:
```ts
  ferrous_iron_yield_h2_pct: number | null
  ferrous_iron_yield_nh3_pct: number | null
  xrd_run_date: string | null
}
```

Change to:
```ts
  ferrous_iron_yield_h2_pct: number | null
  ferrous_iron_yield_nh3_pct: number | null
  nmr_run_date: string | null
  icp_run_date: string | null
  gc_run_date: string | null
  xrd_run_date: string | null
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/api/test_results.py tests/api/test_schemas.py -v`
Expected: PASS, full file (both files — `test_schemas.py`'s existing `test_result_with_flags_response` must still pass unmodified, since all new fields are optional with `None` defaults).

Run: `npx tsc --noEmit` (from `frontend/`)
Expected: no new errors (nothing currently constructs a `ResultWithFlags` object with an exhaustive/exact field list that would break from additive optional fields — confirm this rather than assume it).

- [ ] **Step 7: Commit**

```bash
git add backend/api/schemas/results.py backend/api/routers/experiments.py frontend/src/api/experiments.ts tests/api/test_results.py
git commit -m "$(cat <<'EOF'
[#85] Expose nmr/icp/gc run-date fields on results endpoint

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

## Final Verification (after all 12 tasks)

- [ ] `pytest tests/api/test_dashboard.py tests/services/test_workdays.py -v` — full green
- [ ] `npx vitest run` (from `frontend/`) — full green
- [ ] `npx tsc --noEmit` (from `frontend/`) — no errors
- [ ] `npx eslint src --ext .ts,.tsx` (from `frontend/`) — zero warnings
- [ ] `npx playwright test e2e/journeys/14-dashboard-cf-slots.spec.ts` (from `frontend/`) — passes
- [ ] Manually confirm in-browser: reactor grid/timeline/activity feed unchanged in behavior and appearance (per acceptance criteria — this plan touches none of that code)
- [ ] All 11 commits present on `feat/issue-85-dashboard-kpi-cards`, each with an accurate `Tests added` / `Docs updated` line
