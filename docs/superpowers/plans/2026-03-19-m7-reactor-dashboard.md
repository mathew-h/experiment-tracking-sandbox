# M7 Reactor Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully interactive reactor dashboard with live status grid (R01–R16, CF01–CF02), Gantt timeline, activity feed, filter chips, and a single-call backend endpoint returning all dashboard data under 500 ms.

**Architecture:** A single `GET /api/dashboard/` endpoint returns summary stats, reactor card data (with description + sample_id), Gantt timeline entries, and recent activity in one JSON payload. The frontend renders all 18 reactor slots client-side, applying filters locally on the already-loaded dataset. Click on any occupied reactor opens a lightweight detail modal; full detail navigates to `/experiments/{id}`.

**Tech Stack:** FastAPI + SQLAlchemy (backend), React 18 + React Query + Tailwind (frontend), Vitest (component tests), pytest (API + performance tests).

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `backend/api/schemas/dashboard.py` | Add `DashboardResponse`, `DashboardSummary`, `ReactorCardData`, `GanttEntry`, `ActivityEntry` |
| Modify | `backend/api/routers/dashboard.py` | Add `GET /api/dashboard/`; extend reactor-status query to include sample_id, description, researcher, days_running |
| Create | `tests/api/test_dashboard.py` | Full API test suite incl. filter and performance |
| Modify | `frontend/src/api/dashboard.ts` | New `DashboardData` type + `dashboardApi.full()` call |
| Modify | `frontend/src/pages/Dashboard.tsx` | Top-level page: wires query, passes slices to child components |
| Create | `frontend/src/pages/ReactorGrid.tsx` | 18-slot reactor grid + `ReactorCard` + detail modal |
| Create | `frontend/src/pages/ExperimentTimeline.tsx` | CSS Gantt chart, colored by status |
| Create | `frontend/src/pages/ActivityFeed.tsx` | Last-20 ModificationsLog feed |
| Create | `frontend/src/pages/DashboardFilters.tsx` | Status chips + experiment-type chips + date range picker |
| Create | `docs/user_guide/DASHBOARD.md` | User guide |
| Modify | `docs/api/API_REFERENCE.md` | Document new endpoint |
| Modify | `docs/working/plan.md` | M7 status |

---

## Chunk A — Backend: Schema + Full Dashboard Endpoint

### Task A1: Extend dashboard Pydantic schemas

**Files:**
- Modify: `backend/api/schemas/dashboard.py`

- [ ] **Step 1: Write failing schema test**

```python
# tests/api/test_dashboard.py  (create file)
import pytest
from backend.api.schemas.dashboard import (
    DashboardSummary, ReactorCardData, GanttEntry, ActivityEntry, DashboardResponse
)

def test_dashboard_summary_schema():
    s = DashboardSummary(active_experiments=3, reactors_in_use=3, completed_this_month=1, pending_results=2)
    assert s.active_experiments == 3

def test_reactor_card_data_schema():
    r = ReactorCardData(reactor_number=5, reactor_label="R05")
    assert r.experiment_id is None
    assert r.days_running is None

def test_reactor_card_data_occupied():
    from datetime import datetime
    r = ReactorCardData(
        reactor_number=1, reactor_label="R01",
        experiment_id="HPHT_MH_001", sample_id="SMP-001",
        description="Baseline serpentinization run",
        researcher="MH", days_running=14,
        temperature_c=200.0, experiment_type="HPHT",
    )
    assert r.description == "Baseline serpentinization run"
    assert r.sample_id == "SMP-001"

def test_gantt_entry_schema():
    from datetime import datetime
    g = GanttEntry(
        experiment_id="HPHT_MH_001", experiment_db_id=1,
        status="ONGOING", started_at=datetime.utcnow(), days_running=10,
    )
    assert g.experiment_id == "HPHT_MH_001"

def test_activity_entry_schema():
    from datetime import datetime
    a = ActivityEntry(
        id=1, modification_type="create", modified_table="experiments",
        created_at=datetime.utcnow(),
    )
    assert a.modification_type == "create"

def test_dashboard_response_schema():
    from datetime import datetime
    resp = DashboardResponse(
        summary=DashboardSummary(active_experiments=0, reactors_in_use=0, completed_this_month=0, pending_results=0),
        reactors=[],
        timeline=[],
        recent_activity=[],
    )
    assert resp.summary.active_experiments == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd <project-root>
.venv/Scripts/python -m pytest tests/api/test_dashboard.py::test_dashboard_summary_schema -v
```
Expected: `ImportError` — `DashboardSummary` does not exist yet.

- [ ] **Step 3: Add new schemas to `backend/api/schemas/dashboard.py`**

```python
# backend/api/schemas/dashboard.py  (full file replacement)
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from database.models.enums import ExperimentStatus


class ReactorStatusResponse(BaseModel):
    """Legacy response kept for backwards-compat with /reactor-status endpoint."""
    reactor_number: int
    experiment_id: Optional[str] = None
    status: Optional[ExperimentStatus] = None
    experiment_db_id: Optional[int] = None
    started_at: Optional[datetime] = None
    temperature_c: Optional[float] = None
    experiment_type: Optional[str] = None


class TimelinePoint(BaseModel):
    result_id: int
    time_post_reaction_days: Optional[float] = None
    time_post_reaction_bucket_days: Optional[float] = None
    is_primary: bool
    has_scalar: bool
    has_icp: bool


class ExperimentTimelineResponse(BaseModel):
    experiment_id: str
    status: Optional[ExperimentStatus] = None
    timepoints: list[TimelinePoint]


# ── New M7 schemas ──────────────────────────────────────────────

class DashboardSummary(BaseModel):
    active_experiments: int
    reactors_in_use: int
    completed_this_month: int
    pending_results: int  # ONGOING experiments with no result in the last 7 days


class ReactorCardData(BaseModel):
    reactor_number: int
    reactor_label: str              # e.g. "R05" or "CF01"
    experiment_id: Optional[str] = None
    experiment_db_id: Optional[int] = None
    status: Optional[ExperimentStatus] = None
    experiment_type: Optional[str] = None
    sample_id: Optional[str] = None
    description: Optional[str] = None   # first note text
    researcher: Optional[str] = None
    started_at: Optional[datetime] = None
    days_running: Optional[int] = None
    temperature_c: Optional[float] = None


class GanttEntry(BaseModel):
    experiment_id: str
    experiment_db_id: int
    status: ExperimentStatus
    experiment_type: Optional[str] = None
    sample_id: Optional[str] = None
    researcher: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None   # None for ONGOING
    days_running: Optional[int] = None


class ActivityEntry(BaseModel):
    id: int
    experiment_id: Optional[str] = None
    modified_by: Optional[str] = None
    modification_type: str
    modified_table: str
    created_at: datetime


class DashboardResponse(BaseModel):
    summary: DashboardSummary
    reactors: list[ReactorCardData]      # only occupied slots; frontend fills empties
    timeline: list[GanttEntry]           # all experiments for Gantt, newest first
    recent_activity: list[ActivityEntry] # last 20 modification log entries
```

- [ ] **Step 4: Run schema tests**

```bash
.venv/Scripts/python -m pytest tests/api/test_dashboard.py -v -k "schema"
```
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/schemas/dashboard.py tests/api/test_dashboard.py
git commit -m "[M7] Add M7 dashboard Pydantic schemas + schema tests"
```

---

### Task A2: Implement `GET /api/dashboard/` endpoint

**Files:**
- Modify: `backend/api/routers/dashboard.py`

- [ ] **Step 1: Write failing API test**

Add to `tests/api/test_dashboard.py`:

```python
# --- API integration tests (append to test_dashboard.py) ---

def test_get_dashboard_returns_200(client, auth_headers):
    resp = client.get("/api/dashboard/", headers=auth_headers)
    assert resp.status_code == 200

def test_get_dashboard_shape(client, auth_headers):
    resp = client.get("/api/dashboard/", headers=auth_headers)
    data = resp.json()
    assert "summary" in data
    assert "reactors" in data
    assert "timeline" in data
    assert "recent_activity" in data
    s = data["summary"]
    assert "active_experiments" in s
    assert "reactors_in_use" in s
    assert "completed_this_month" in s
    assert "pending_results" in s

def test_get_dashboard_requires_auth(client):
    resp = client.get("/api/dashboard/")
    assert resp.status_code == 401

def test_get_dashboard_reactor_cards_have_required_fields(client, auth_headers, db_session):
    """If there are occupied reactors, each card must have reactor_label."""
    resp = client.get("/api/dashboard/", headers=auth_headers)
    assert resp.status_code == 200
    for card in resp.json()["reactors"]:
        assert "reactor_number" in card
        assert "reactor_label" in card

def test_get_dashboard_timeline_entries_have_required_fields(client, auth_headers, db_session):
    resp = client.get("/api/dashboard/", headers=auth_headers)
    assert resp.status_code == 200
    for entry in resp.json()["timeline"]:
        assert "experiment_id" in entry
        assert "status" in entry

def test_get_dashboard_activity_capped_at_20(client, auth_headers):
    resp = client.get("/api/dashboard/", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["recent_activity"]) <= 20

def test_get_dashboard_with_ongoing_experiment(client, auth_headers, db_session):
    """Occupied reactor appears in reactors list with description and sample_id."""
    from database.models.experiments import Experiment, ExperimentNotes
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus, ExperimentType
    import datetime

    exp = Experiment(
        experiment_id="DASH_TEST_001",
        experiment_number=9001,
        sample_id="SMP-DASH",
        researcher="Test User",
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow() - datetime.timedelta(days=5),
    )
    db_session.add(exp)
    db_session.flush()

    note = ExperimentNotes(
        experiment_id="DASH_TEST_001",
        experiment_fk=exp.id,
        note_text="Dashboard integration test description",
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(note)

    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="DASH_TEST_001",
        reactor_number=7,
        temperature_c=150.0,
        experiment_type=ExperimentType.HPHT,
    )
    db_session.add(cond)
    db_session.commit()

    resp = client.get("/api/dashboard/", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    cards = {c["reactor_number"]: c for c in data["reactors"]}
    assert 7 in cards
    card = cards[7]
    assert card["experiment_id"] == "DASH_TEST_001"
    assert card["sample_id"] == "SMP-DASH"
    assert card["description"] == "Dashboard integration test description"
    assert card["reactor_label"] == "R07"
    assert card["days_running"] >= 5

    assert data["summary"]["active_experiments"] >= 1
    assert data["summary"]["reactors_in_use"] >= 1
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/Scripts/python -m pytest tests/api/test_dashboard.py::test_get_dashboard_returns_200 -v
```
Expected: 404 — route does not exist yet.

- [ ] **Step 3: Implement the endpoint**

Add to `backend/api/routers/dashboard.py` (insert after the existing `get_experiment_timeline` function):

```python
# Add these imports at top of file (after existing imports):
from datetime import datetime, timedelta
from sqlalchemy import func, case
from database.models.experiments import ExperimentNotes
from database.models.experiments import ModificationsLog
from backend.api.schemas.dashboard import (
    DashboardResponse, DashboardSummary, ReactorCardData, GanttEntry, ActivityEntry,
)


@router.get("/", response_model=DashboardResponse)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> DashboardResponse:
    """
    Single call returning all dashboard data.
    Four focused queries — no N+1. Target: <500ms with 500 experiments.
    """
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = now - timedelta(days=7)

    # ── 1. Summary stats ───────────────────────────────────────────────────
    # One query: aggregate counts directly in SQL.
    summary_row = db.execute(
        select(
            func.count(case((Experiment.status == ExperimentStatus.ONGOING, 1))).label("active"),
            func.count(
                case((
                    (Experiment.status == ExperimentStatus.ONGOING) &
                    ExperimentalConditions.reactor_number.isnot(None),
                    1,
                ))
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

    # Pending results: ONGOING experiments with no result in the last 7 days.
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

    # ── 2. Reactor cards (ONGOING only) ───────────────────────────────────
    # Subquery: first note per experiment (oldest created_at).
    first_note_sq = (
        select(
            ExperimentNotes.experiment_fk,
            func.min(ExperimentNotes.id).label("min_note_id"),
        )
        .group_by(ExperimentNotes.experiment_fk)
        .subquery()
    )
    note_text_sq = (
        select(ExperimentNotes.experiment_fk, ExperimentNotes.note_text)
        .join(first_note_sq, ExperimentNotes.id == first_note_sq.c.min_note_id)
        .subquery()
    )

    reactor_rows = db.execute(
        select(
            ExperimentalConditions.reactor_number,
            Experiment.id,
            Experiment.experiment_id,
            Experiment.status,
            Experiment.sample_id,
            Experiment.researcher,
            Experiment.created_at,
            ExperimentalConditions.temperature_c,
            ExperimentalConditions.experiment_type,
            note_text_sq.c.note_text.label("description"),
        )
        .join(Experiment, Experiment.id == ExperimentalConditions.experiment_fk)
        .outerjoin(note_text_sq, note_text_sq.c.experiment_fk == Experiment.id)
        .where(Experiment.status == ExperimentStatus.ONGOING)
        .where(ExperimentalConditions.reactor_number.isnot(None))
        .order_by(ExperimentalConditions.reactor_number, Experiment.created_at.desc())
    ).all()

    seen_reactors: set[int] = set()
    reactor_cards: list[ReactorCardData] = []
    for row in reactor_rows:
        rn = row.reactor_number
        if rn in seen_reactors:
            continue
        seen_reactors.add(rn)
        exp_type = row.experiment_type.value if hasattr(row.experiment_type, "value") else str(row.experiment_type) if row.experiment_type else None
        is_cf = exp_type == "Core Flood" if exp_type else False
        label = f"CF{rn:02d}" if is_cf else f"R{rn:02d}"
        days = (now - row.created_at).days if row.created_at else None
        reactor_cards.append(ReactorCardData(
            reactor_number=rn,
            reactor_label=label,
            experiment_id=row.experiment_id,
            experiment_db_id=row.id,
            status=row.status,
            experiment_type=exp_type,
            sample_id=row.sample_id,
            description=row.description,
            researcher=row.researcher,
            started_at=row.created_at,
            days_running=days,
            temperature_c=row.temperature_c,
        ))

    # ── 3. Gantt timeline (all experiments, newest first, limit 100) ──────
    gantt_rows = db.execute(
        select(
            Experiment.id,
            Experiment.experiment_id,
            Experiment.status,
            Experiment.sample_id,
            Experiment.researcher,
            Experiment.created_at,
            Experiment.updated_at,
            ExperimentalConditions.experiment_type,
        )
        .outerjoin(ExperimentalConditions, ExperimentalConditions.experiment_fk == Experiment.id)
        .order_by(Experiment.created_at.desc())
        .limit(100)
    ).all()

    timeline: list[GanttEntry] = []
    for row in gantt_rows:
        status = row.status
        exp_type = row.experiment_type.value if hasattr(row.experiment_type, "value") else str(row.experiment_type) if row.experiment_type else None
        ended_at = row.updated_at if status != ExperimentStatus.ONGOING else None
        days = None
        if row.created_at:
            end = ended_at or now
            days = (end - row.created_at).days
        timeline.append(GanttEntry(
            experiment_id=row.experiment_id,
            experiment_db_id=row.id,
            status=status,
            experiment_type=exp_type,
            sample_id=row.sample_id,
            researcher=row.researcher,
            started_at=row.created_at,
            ended_at=ended_at,
            days_running=days,
        ))

    # ── 4. Recent activity (last 20 ModificationsLog entries) ─────────────
    activity_rows = db.execute(
        select(
            ModificationsLog.id,
            ModificationsLog.experiment_id,
            ModificationsLog.modified_by,
            ModificationsLog.modification_type,
            ModificationsLog.modified_table,
            ModificationsLog.created_at,
        )
        .order_by(ModificationsLog.created_at.desc())
        .limit(20)
    ).all()

    recent_activity = [
        ActivityEntry(
            id=row.id,
            experiment_id=row.experiment_id,
            modified_by=row.modified_by,
            modification_type=row.modification_type,
            modified_table=row.modified_table,
            created_at=row.created_at,
        )
        for row in activity_rows
    ]

    return DashboardResponse(
        summary=summary,
        reactors=reactor_cards,
        timeline=timeline,
        recent_activity=recent_activity,
    )
```

Also add the missing imports to the top of `dashboard.py`:
```python
from datetime import datetime, timedelta
from sqlalchemy import func, case
from database.models.experiments import ExperimentNotes, ModificationsLog
from database.models.results import ExperimentalResults
```

And update the existing imports block to include the new schemas:
```python
from backend.api.schemas.dashboard import (
    ReactorStatusResponse, ExperimentTimelineResponse, TimelinePoint,
    DashboardResponse, DashboardSummary, ReactorCardData, GanttEntry, ActivityEntry,
)
```

- [ ] **Step 4: Run API tests**

```bash
.venv/Scripts/python -m pytest tests/api/test_dashboard.py -v
```
Expected: all tests PASS (schema tests + API integration tests).

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/dashboard.py backend/api/schemas/dashboard.py tests/api/test_dashboard.py
git commit -m "[M7] Add GET /api/dashboard/ — single-call full dashboard endpoint"
```

---

### Task A3: Performance test (500-experiment synthetic dataset)

**Files:**
- Modify: `tests/api/test_dashboard.py`

- [ ] **Step 1: Add performance test**

```python
# append to tests/api/test_dashboard.py

import time

def test_dashboard_performance_500_experiments(client, auth_headers, db_session):
    """Dashboard endpoint must respond under 1000ms with 500 experiments (CI headroom)."""
    from database.models.experiments import Experiment, ExperimentalConditions
    from database.models.enums import ExperimentStatus, ExperimentType
    import datetime, random

    exps = []
    for i in range(500):
        status = random.choice([ExperimentStatus.ONGOING, ExperimentStatus.COMPLETED, ExperimentStatus.CANCELLED])
        exp = Experiment(
            experiment_id=f"PERF_{i:04d}",
            experiment_number=10000 + i,
            status=status,
            created_at=datetime.datetime.utcnow() - datetime.timedelta(days=random.randint(1, 365)),
        )
        exps.append(exp)
    db_session.add_all(exps)
    db_session.flush()

    conds = []
    for i, exp in enumerate(exps[:50]):  # 50 with reactor numbers
        cond = ExperimentalConditions(
            experiment_fk=exp.id,
            experiment_id=exp.experiment_id,
            reactor_number=(i % 16) + 1,
        )
        conds.append(cond)
    db_session.add_all(conds)
    db_session.commit()

    start = time.perf_counter()
    resp = client.get("/api/dashboard/", headers=auth_headers)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert resp.status_code == 200
    assert elapsed_ms < 1000, f"Dashboard took {elapsed_ms:.0f}ms — exceeds 1000ms threshold"
```

- [ ] **Step 2: Run performance test**

```bash
.venv/Scripts/python -m pytest tests/api/test_dashboard.py::test_dashboard_performance_500_experiments -v -s
```
Expected: PASS under 1000 ms. If slow, add indexes or optimize the pending_results query.

- [ ] **Step 3: Commit**

```bash
git add tests/api/test_dashboard.py
git commit -m "[M7] Add dashboard performance test (500-experiment dataset)"
```

---

## Chunk B — Frontend: API Client + Reactor Grid

### Task B1: Update dashboard API client and types

**Files:**
- Modify: `frontend/src/api/dashboard.ts`

- [ ] **Step 1: Rewrite `dashboard.ts`**

```typescript
// frontend/src/api/dashboard.ts
import { apiClient } from './client'

// Legacy types kept for backwards compat (existing /reactor-status endpoint)
export interface ReactorStatus {
  reactor_number: number
  experiment_id: string | null
  experiment_fk: number | null
  status: string | null
  researcher: string | null
  days_running: number | null
  temperature_c: number | null
  experiment_type: string | null
}

// M7 full dashboard types
export interface DashboardSummary {
  active_experiments: number
  reactors_in_use: number
  completed_this_month: number
  pending_results: number
}

export interface ReactorCardData {
  reactor_number: number
  reactor_label: string
  experiment_id: string | null
  experiment_db_id: number | null
  status: string | null
  experiment_type: string | null
  sample_id: string | null
  description: string | null
  researcher: string | null
  started_at: string | null
  days_running: number | null
  temperature_c: number | null
}

export interface GanttEntry {
  experiment_id: string
  experiment_db_id: number
  status: string
  experiment_type: string | null
  sample_id: string | null
  researcher: string | null
  started_at: string | null
  ended_at: string | null
  days_running: number | null
}

export interface ActivityEntry {
  id: number
  experiment_id: string | null
  modified_by: string | null
  modification_type: string
  modified_table: string
  created_at: string
}

export interface DashboardData {
  summary: DashboardSummary
  reactors: ReactorCardData[]
  timeline: GanttEntry[]
  recent_activity: ActivityEntry[]
}

export interface TimelineEntry {
  result_id: number
  time_post_reaction_days: number
  cumulative_time_post_reaction_days: number
  description: string
  created_at: string
}

export const dashboardApi = {
  // M7: single full dashboard call
  full: (): Promise<DashboardData> =>
    apiClient.get<DashboardData>('/dashboard/').then((r) => r.data),

  // Legacy: kept for compatibility
  reactorStatus: (): Promise<ReactorStatus[]> =>
    apiClient.get<ReactorStatus[]>('/dashboard/reactor-status').then((r) => r.data),

  timeline: (experimentId: string): Promise<TimelineEntry[]> =>
    apiClient.get<TimelineEntry[]>(`/dashboard/timeline/${experimentId}`).then((r) => r.data),
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend
npx tsc --noEmit
```
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/dashboard.ts
git commit -m "[M7] Update dashboard API client with M7 full-dashboard types"
```

---

### Task B2: ReactorGrid component

**Files:**
- Create: `frontend/src/pages/ReactorGrid.tsx`

The grid always renders all 18 slots: R01–R16 and CF01–CF02.
Occupied slots show: reactor label, experiment ID, status badge, type, start date, elapsed days, sample ID, description (truncated to 2 lines).
Click on occupied slot → fires `onCardClick(card)` prop.
Empty slots are greyed out with "Empty" badge.

- [ ] **Step 1: Create `ReactorGrid.tsx`**

```tsx
// frontend/src/pages/ReactorGrid.tsx
import { useNavigate } from 'react-router-dom'
import { Card } from '@/components/ui'
import type { ReactorCardData } from '@/api/dashboard'

// Fixed reactor layout: R01-R16 + CF01-CF02
const R_SLOTS = Array.from({ length: 16 }, (_, i) => `R${String(i + 1).padStart(2, '0')}`)
const CF_SLOTS = ['CF01', 'CF02']

function statusColors(status: string | null) {
  switch (status) {
    case 'ONGOING':
      return 'text-status-ongoing bg-status-ongoing/10 border-status-ongoing/20'
    case 'COMPLETED':
      return 'text-status-completed bg-status-completed/10 border-status-completed/20'
    case 'CANCELLED':
      return 'text-status-cancelled bg-status-cancelled/10 border-status-cancelled/20'
    default:
      return 'text-ink-muted bg-surface-overlay border-surface-border'
  }
}

function ReactorCard({
  label,
  card,
  onClick,
}: {
  label: string
  card: ReactorCardData | null
  onClick: (card: ReactorCardData) => void
}) {
  const occupied = card !== null

  return (
    <Card
      className={[
        'transition-colors duration-150 select-none',
        occupied ? 'hover:border-ink-muted cursor-pointer' : 'opacity-50',
      ].join(' ')}
      onClick={() => occupied && onClick(card!)}
    >
      <div className="flex items-start justify-between mb-2">
        <div>
          <p className="text-2xs text-ink-muted uppercase tracking-wider font-medium mb-0.5">
            Reactor
          </p>
          <p className="text-xl font-bold text-ink-primary font-mono-data leading-none">{label}</p>
        </div>
        <span
          className={[
            'inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-2xs font-semibold uppercase tracking-wider border',
            occupied ? statusColors(card!.status) : 'text-ink-muted bg-surface-overlay border-surface-border',
          ].join(' ')}
        >
          <span
            className={[
              'w-1.5 h-1.5 rounded-full',
              occupied && card!.status === 'ONGOING' ? 'bg-status-ongoing animate-pulse-slow' : 'bg-surface-border',
            ].join(' ')}
          />
          {occupied ? (card!.status ?? 'Active') : 'Empty'}
        </span>
      </div>

      {occupied ? (
        <div className="space-y-1">
          <p className="text-sm font-medium text-ink-primary font-mono-data leading-tight">
            {card!.experiment_id}
          </p>
          {card!.sample_id && (
            <p className="text-xs text-ink-secondary">
              <span className="text-ink-muted">Sample:</span> {card!.sample_id}
            </p>
          )}
          {card!.description && (
            <p className="text-xs text-ink-muted line-clamp-2 leading-snug">{card!.description}</p>
          )}
          {card!.experiment_type && (
            <p className="text-xs text-ink-muted">{card!.experiment_type}</p>
          )}
          <div className="flex items-center gap-3 pt-1">
            {card!.temperature_c != null && (
              <span className="text-xs text-ink-muted">
                <span className="font-mono-data text-ink-secondary">{card!.temperature_c}</span> °C
              </span>
            )}
            {card!.days_running != null && (
              <span className="text-xs text-ink-muted">
                Day <span className="font-mono-data text-ink-secondary">{card!.days_running}</span>
              </span>
            )}
          </div>
        </div>
      ) : (
        <p className="text-xs text-ink-muted mt-1">No active experiment</p>
      )}
    </Card>
  )
}

// Lightweight detail modal
function ReactorDetailModal({
  card,
  onClose,
}: {
  card: ReactorCardData
  onClose: () => void
}) {
  const navigate = useNavigate()

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="bg-surface-card border border-surface-border rounded-lg p-6 w-full max-w-md shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <div>
            <p className="text-2xs text-ink-muted uppercase tracking-wider mb-1">
              {card.reactor_label}
            </p>
            <h2 className="text-lg font-bold text-ink-primary font-mono-data">
              {card.experiment_id}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-ink-muted hover:text-ink-primary text-lg leading-none mt-0.5"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <dl className="space-y-2 text-sm">
          {card.sample_id && (
            <div className="flex gap-2">
              <dt className="text-ink-muted w-28 shrink-0">Sample ID</dt>
              <dd className="text-ink-primary font-mono-data">{card.sample_id}</dd>
            </div>
          )}
          {card.researcher && (
            <div className="flex gap-2">
              <dt className="text-ink-muted w-28 shrink-0">Researcher</dt>
              <dd className="text-ink-secondary">{card.researcher}</dd>
            </div>
          )}
          {card.experiment_type && (
            <div className="flex gap-2">
              <dt className="text-ink-muted w-28 shrink-0">Type</dt>
              <dd className="text-ink-secondary">{card.experiment_type}</dd>
            </div>
          )}
          {card.temperature_c != null && (
            <div className="flex gap-2">
              <dt className="text-ink-muted w-28 shrink-0">Temperature</dt>
              <dd className="font-mono-data text-ink-secondary">{card.temperature_c} °C</dd>
            </div>
          )}
          {card.days_running != null && (
            <div className="flex gap-2">
              <dt className="text-ink-muted w-28 shrink-0">Elapsed</dt>
              <dd className="font-mono-data text-ink-secondary">Day {card.days_running}</dd>
            </div>
          )}
          {card.started_at && (
            <div className="flex gap-2">
              <dt className="text-ink-muted w-28 shrink-0">Started</dt>
              <dd className="font-mono-data text-ink-secondary">
                {card.started_at.slice(0, 10)}
              </dd>
            </div>
          )}
          {card.description && (
            <div className="pt-2 border-t border-surface-border">
              <p className="text-ink-muted text-2xs uppercase tracking-wider mb-1">Description</p>
              <p className="text-ink-secondary leading-relaxed">{card.description}</p>
            </div>
          )}
        </dl>

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-ink-muted hover:text-ink-primary border border-surface-border rounded transition-colors"
          >
            Close
          </button>
          <button
            onClick={() => navigate(`/experiments/${card.experiment_id}`)}
            className="px-3 py-1.5 text-sm bg-brand-red text-white rounded hover:bg-brand-red-dark transition-colors"
          >
            View Full Detail →
          </button>
        </div>
      </div>
    </div>
  )
}

export function ReactorGrid({ cards }: { cards: ReactorCardData[] }) {
  const [selected, setSelected] = React.useState<ReactorCardData | null>(null)

  // Build lookup by reactor_label
  const byLabel = Object.fromEntries(cards.map((c) => [c.reactor_label, c]))

  return (
    <>
      {/* Standard reactors R01–R16 */}
      <div>
        <p className="text-2xs text-ink-muted uppercase tracking-wider font-medium mb-2">
          Standard Reactors (R01–R16)
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
          {R_SLOTS.map((label) => (
            <ReactorCard
              key={label}
              label={label}
              card={byLabel[label] ?? null}
              onClick={setSelected}
            />
          ))}
        </div>
      </div>

      {/* Core flood CF01–CF02 */}
      <div className="mt-4">
        <p className="text-2xs text-ink-muted uppercase tracking-wider font-medium mb-2">
          Core Flood (CF01–CF02)
        </p>
        <div className="grid grid-cols-2 gap-2 max-w-xs">
          {CF_SLOTS.map((label) => (
            <ReactorCard
              key={label}
              label={label}
              card={byLabel[label] ?? null}
              onClick={setSelected}
            />
          ))}
        </div>
      </div>

      {selected && (
        <ReactorDetailModal card={selected} onClose={() => setSelected(null)} />
      )}
    </>
  )
}
```

Add missing import at top of file:
```tsx
import React, { useState } from 'react'
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ReactorGrid.tsx
git commit -m "[M7] Add ReactorGrid component — 18-slot grid with detail modal"
```

---

### Task B3: Gantt timeline component

**Files:**
- Create: `frontend/src/pages/ExperimentTimeline.tsx`

Pure CSS Gantt: each experiment is a horizontal bar sized by (days_running / max_days) × 100%. Colored by status. Filtered entries only.

- [ ] **Step 1: Create `ExperimentTimeline.tsx`**

```tsx
// frontend/src/pages/ExperimentTimeline.tsx
import type { GanttEntry } from '@/api/dashboard'
import { useNavigate } from 'react-router-dom'

const STATUS_BAR: Record<string, string> = {
  ONGOING: 'bg-status-ongoing',
  COMPLETED: 'bg-status-completed',
  CANCELLED: 'bg-status-cancelled bg-opacity-50',
}

export function ExperimentTimeline({ entries }: { entries: GanttEntry[] }) {
  const navigate = useNavigate()

  if (entries.length === 0) {
    return <p className="text-sm text-ink-muted text-center py-8">No experiments to display</p>
  }

  const maxDays = Math.max(...entries.map((e) => e.days_running ?? 1), 1)

  return (
    <div className="space-y-1 overflow-x-auto">
      <div className="min-w-[400px]">
        {entries.map((entry) => {
          const pct = Math.max(((entry.days_running ?? 1) / maxDays) * 100, 1)
          const barColor = STATUS_BAR[entry.status] ?? 'bg-surface-overlay'

          return (
            <div
              key={entry.experiment_db_id}
              className="flex items-center gap-2 py-0.5 group cursor-pointer"
              onClick={() => navigate(`/experiments/${entry.experiment_id}`)}
              title={`${entry.experiment_id} — Day ${entry.days_running ?? 0}`}
            >
              {/* Label */}
              <span className="text-xs font-mono-data text-ink-secondary w-32 shrink-0 truncate group-hover:text-ink-primary transition-colors">
                {entry.experiment_id}
              </span>

              {/* Bar */}
              <div className="flex-1 h-4 bg-surface-overlay rounded overflow-hidden">
                <div
                  className={`h-full rounded transition-all duration-300 ${barColor}`}
                  style={{ width: `${pct}%` }}
                />
              </div>

              {/* Day count */}
              <span className="text-xs font-mono-data text-ink-muted w-12 text-right shrink-0">
                {entry.days_running ?? 0}d
              </span>
            </div>
          )
        })}

        {/* X-axis label */}
        <div className="flex items-center gap-2 mt-2 pt-2 border-t border-surface-border">
          <span className="text-2xs text-ink-muted w-32 shrink-0">Experiment</span>
          <div className="flex-1 flex justify-between">
            <span className="text-2xs text-ink-muted">0d</span>
            <span className="text-2xs text-ink-muted">{Math.round(maxDays / 2)}d</span>
            <span className="text-2xs text-ink-muted">{maxDays}d</span>
          </div>
          <span className="w-12" />
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ExperimentTimeline.tsx
git commit -m "[M7] Add ExperimentTimeline CSS Gantt component"
```

---

### Task B4: Activity feed component

**Files:**
- Create: `frontend/src/pages/ActivityFeed.tsx`

- [ ] **Step 1: Create `ActivityFeed.tsx`**

```tsx
// frontend/src/pages/ActivityFeed.tsx
import type { ActivityEntry } from '@/api/dashboard'
import { useNavigate } from 'react-router-dom'

const ACTION_LABELS: Record<string, string> = {
  create: 'Created',
  update: 'Updated',
  delete: 'Deleted',
}

const ACTION_COLORS: Record<string, string> = {
  create: 'text-status-ongoing',
  update: 'text-status-completed',
  delete: 'text-status-cancelled',
}

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export function ActivityFeed({ entries }: { entries: ActivityEntry[] }) {
  const navigate = useNavigate()

  if (entries.length === 0) {
    return <p className="text-sm text-ink-muted text-center py-8">No recent activity</p>
  }

  return (
    <ul className="divide-y divide-surface-border">
      {entries.map((entry) => (
        <li
          key={entry.id}
          className="flex items-start gap-3 py-2 group"
        >
          <span
            className={`text-xs font-semibold uppercase tracking-wider w-16 shrink-0 mt-0.5 ${ACTION_COLORS[entry.modification_type] ?? 'text-ink-muted'}`}
          >
            {ACTION_LABELS[entry.modification_type] ?? entry.modification_type}
          </span>

          <div className="flex-1 min-w-0">
            <p className="text-xs text-ink-secondary leading-snug">
              <span className="font-medium text-ink-primary">{entry.modified_table}</span>
              {entry.experiment_id && (
                <>
                  {' '}—{' '}
                  <button
                    onClick={() => navigate(`/experiments/${entry.experiment_id}`)}
                    className="text-brand-red hover:underline"
                  >
                    {entry.experiment_id}
                  </button>
                </>
              )}
            </p>
            {entry.modified_by && (
              <p className="text-2xs text-ink-muted mt-0.5">{entry.modified_by}</p>
            )}
          </div>

          <span className="text-2xs text-ink-muted shrink-0 mt-0.5">{timeAgo(entry.created_at)}</span>
        </li>
      ))}
    </ul>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ActivityFeed.tsx
git commit -m "[M7] Add ActivityFeed component"
```

---

### Task B5: Dashboard filters component

**Files:**
- Create: `frontend/src/pages/DashboardFilters.tsx`

Filters are applied client-side. Chips for status (ONGOING / COMPLETED / CANCELLED) and experiment type (HPHT / Serum / Core Flood / Autoclave / Other). Date range: `dateFrom` / `dateTo` inputs. Parent passes current filter state and `onChange`.

- [ ] **Step 1: Create `DashboardFilters.tsx`**

```tsx
// frontend/src/pages/DashboardFilters.tsx
import { useId } from 'react'

export interface DashboardFilterState {
  statuses: string[]       // empty = all
  types: string[]          // empty = all
  dateFrom: string         // ISO date string or ''
  dateTo: string
}

const STATUS_OPTIONS = ['ONGOING', 'COMPLETED', 'CANCELLED']
const TYPE_OPTIONS = ['HPHT', 'Serum', 'Core Flood', 'Autoclave', 'Other']

function Chip({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={[
        'px-2.5 py-1 rounded text-xs font-medium border transition-colors',
        active
          ? 'bg-brand-red text-white border-brand-red'
          : 'text-ink-muted border-surface-border hover:border-ink-muted',
      ].join(' ')}
    >
      {label}
    </button>
  )
}

export function DashboardFilters({
  filters,
  onChange,
}: {
  filters: DashboardFilterState
  onChange: (f: DashboardFilterState) => void
}) {
  const fromId = useId()
  const toId = useId()

  function toggleStatus(s: string) {
    const next = filters.statuses.includes(s)
      ? filters.statuses.filter((x) => x !== s)
      : [...filters.statuses, s]
    onChange({ ...filters, statuses: next })
  }

  function toggleType(t: string) {
    const next = filters.types.includes(t)
      ? filters.types.filter((x) => x !== t)
      : [...filters.types, t]
    onChange({ ...filters, types: next })
  }

  const hasFilters =
    filters.statuses.length > 0 || filters.types.length > 0 || filters.dateFrom || filters.dateTo

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Status chips */}
      <div className="flex items-center gap-1.5">
        <span className="text-2xs text-ink-muted uppercase tracking-wider mr-1">Status</span>
        {STATUS_OPTIONS.map((s) => (
          <Chip
            key={s}
            label={s.charAt(0) + s.slice(1).toLowerCase()}
            active={filters.statuses.includes(s)}
            onClick={() => toggleStatus(s)}
          />
        ))}
      </div>

      {/* Type chips */}
      <div className="flex items-center gap-1.5">
        <span className="text-2xs text-ink-muted uppercase tracking-wider mr-1">Type</span>
        {TYPE_OPTIONS.map((t) => (
          <Chip key={t} label={t} active={filters.types.includes(t)} onClick={() => toggleType(t)} />
        ))}
      </div>

      {/* Date range */}
      <div className="flex items-center gap-1.5">
        <label htmlFor={fromId} className="text-2xs text-ink-muted uppercase tracking-wider">
          From
        </label>
        <input
          id={fromId}
          type="date"
          value={filters.dateFrom}
          onChange={(e) => onChange({ ...filters, dateFrom: e.target.value })}
          className="text-xs bg-surface-overlay border border-surface-border rounded px-2 py-0.5 text-ink-secondary focus:outline-none focus:border-ink-muted"
        />
        <label htmlFor={toId} className="text-2xs text-ink-muted uppercase tracking-wider">
          To
        </label>
        <input
          id={toId}
          type="date"
          value={filters.dateTo}
          onChange={(e) => onChange({ ...filters, dateTo: e.target.value })}
          className="text-xs bg-surface-overlay border border-surface-border rounded px-2 py-0.5 text-ink-secondary focus:outline-none focus:border-ink-muted"
        />
      </div>

      {/* Clear */}
      {hasFilters && (
        <button
          onClick={() => onChange({ statuses: [], types: [], dateFrom: '', dateTo: '' })}
          className="text-2xs text-ink-muted hover:text-ink-primary underline"
        >
          Clear filters
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/DashboardFilters.tsx
git commit -m "[M7] Add DashboardFilters component (status, type, date chips)"
```

---

### Task B6: Rebuild Dashboard.tsx — wire everything together

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Rewrite Dashboard.tsx**

```tsx
// frontend/src/pages/Dashboard.tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '@/api/dashboard'
import { MetricCard, Card, CardHeader, CardBody, PageSpinner } from '@/components/ui'
import { ReactorGrid } from './ReactorGrid'
import { ExperimentTimeline } from './ExperimentTimeline'
import { ActivityFeed } from './ActivityFeed'
import { DashboardFilters, type DashboardFilterState } from './DashboardFilters'
import type { GanttEntry } from '@/api/dashboard'

function applyFilters(entries: GanttEntry[], f: DashboardFilterState): GanttEntry[] {
  return entries.filter((e) => {
    if (f.statuses.length > 0 && !f.statuses.includes(e.status)) return false
    if (f.types.length > 0 && e.experiment_type && !f.types.includes(e.experiment_type)) return false
    if (f.dateFrom && e.started_at && e.started_at.slice(0, 10) < f.dateFrom) return false
    if (f.dateTo && e.started_at && e.started_at.slice(0, 10) > f.dateTo) return false
    return true
  })
}

export function DashboardPage() {
  const [filters, setFilters] = useState<DashboardFilterState>({
    statuses: [],
    types: [],
    dateFrom: '',
    dateTo: '',
  })

  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: dashboardApi.full,
    refetchInterval: 60_000,
  })

  const filteredTimeline = data ? applyFilters(data.timeline, filters) : []

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold text-ink-primary">Dashboard</h1>
          <p className="text-xs text-ink-muted mt-0.5">
            Reactor status and lab overview · Auto-refreshes every 60s
          </p>
        </div>
      </div>

      {/* Summary metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard
          label="Active Experiments"
          value={data?.summary.active_experiments ?? '—'}
        />
        <MetricCard
          label="Reactors In Use"
          value={data?.summary.reactors_in_use ?? '—'}
          unit={`/ ${16 + 2}`}
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

      {/* Filters */}
      <DashboardFilters filters={filters} onChange={setFilters} />

      {/* Reactor grid */}
      <Card padding="none">
        <CardHeader label="Reactor Status" />
        <CardBody>
          {isLoading && <PageSpinner />}
          {error && (
            <p className="text-sm text-red-400 py-4 text-center">Failed to load dashboard</p>
          )}
          {data && <ReactorGrid cards={data.reactors} />}
        </CardBody>
      </Card>

      {/* Gantt timeline */}
      <Card padding="none">
        <CardHeader label="Experiment Timeline">
          <span className="text-2xs text-ink-muted">
            {filteredTimeline.length} experiment{filteredTimeline.length !== 1 ? 's' : ''}
          </span>
        </CardHeader>
        <CardBody>
          {data && <ExperimentTimeline entries={filteredTimeline} />}
        </CardBody>
      </Card>

      {/* Activity feed */}
      <Card padding="none">
        <CardHeader label="Recent Activity" />
        <CardBody>
          {data && <ActivityFeed entries={data.recent_activity} />}
        </CardBody>
      </Card>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript + ESLint**

```bash
cd frontend
npx tsc --noEmit
npx eslint src/pages/Dashboard.tsx src/pages/ReactorGrid.tsx src/pages/ExperimentTimeline.tsx src/pages/ActivityFeed.tsx src/pages/DashboardFilters.tsx --ext .tsx
```
Expected: 0 errors, 0 warnings.

- [ ] **Step 3: Build to check production bundle**

```bash
npm run build
```
Expected: clean build.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx frontend/src/pages/ReactorGrid.tsx frontend/src/pages/ExperimentTimeline.tsx frontend/src/pages/ActivityFeed.tsx frontend/src/pages/DashboardFilters.tsx
git commit -m "[M7] Rebuild Dashboard page — reactor grid, Gantt, activity feed, filters"
```

---

## Chunk C — Documentation

### Task C1: User guide and API reference

**Files:**
- Create: `docs/user_guide/DASHBOARD.md`
- Modify: `docs/api/API_REFERENCE.md`

- [ ] **Step 1: Create `docs/user_guide/DASHBOARD.md`**

```markdown
# Dashboard User Guide

## Overview
The Dashboard provides a live overview of the lab's reactor status, experiment progress, and recent activity. It auto-refreshes every 60 seconds.

## Summary Metrics
Four metrics at the top of the page:
- **Active Experiments** — count of all ONGOING experiments
- **Reactors In Use** — count of reactors with an active experiment assigned
- **Completed This Month** — experiments marked COMPLETED since the first of the current month
- **Pending Results** — ONGOING experiments with no result recorded in the last 7 days

## Reactor Grid
Shows all 18 reactor slots:
- **R01–R16** — standard serum/HPHT/autoclave reactors
- **CF01–CF02** — core flood reactors

**Occupied slots** show: reactor label, experiment ID, sample ID, description (first note, truncated), experiment type, temperature, elapsed days.
**Empty slots** appear greyed out.

Click any occupied slot to open a **detail modal** with full card info and a link to the experiment's detail page.

## Experiment Timeline (Gantt)
Horizontal bar chart showing up to 100 experiments sorted by most recent start date. Bar width is proportional to experiment duration relative to the longest experiment displayed. Colors:
- Green — ONGOING
- Blue — COMPLETED
- Grey — CANCELLED

Click any bar to navigate to that experiment's detail page.

## Recent Activity Feed
Shows the last 20 entries from the modifications audit log: what was changed, in which table, by whom, and when. Click an experiment ID to jump to its detail page.

## Filters
Filter chips and date range apply to the **timeline** view:
- **Status chips** — ONGOING, COMPLETED, CANCELLED (multi-select; empty = all)
- **Type chips** — HPHT, Serum, Core Flood, Autoclave, Other (multi-select; empty = all)
- **Date range** — From / To (filters by experiment start date)

Filters are applied locally — no new API call is made when filters change.
```

- [ ] **Step 2: Add endpoint to `docs/api/API_REFERENCE.md`**

Add this section under the Dashboard endpoints:

```markdown
### GET /api/dashboard/

Returns all dashboard data in a single call.

**Auth:** Required

**Response:** `DashboardResponse`
```json
{
  "summary": {
    "active_experiments": 5,
    "reactors_in_use": 4,
    "completed_this_month": 2,
    "pending_results": 1
  },
  "reactors": [
    {
      "reactor_number": 5,
      "reactor_label": "R05",
      "experiment_id": "HPHT_MH_072",
      "experiment_db_id": 142,
      "status": "ONGOING",
      "experiment_type": "HPHT",
      "sample_id": "SMP-042",
      "description": "Baseline run with magnetite catalyst",
      "researcher": "MH",
      "started_at": "2026-03-01T09:00:00",
      "days_running": 18,
      "temperature_c": 200.0
    }
  ],
  "timeline": [ ... ],
  "recent_activity": [ ... ]
}
```
**Notes:** Only occupied reactor slots are returned; frontend renders all 18 fixed slots and marks empties as greyed out. Timeline limited to 100 most recent experiments. Activity limited to last 20 entries.
```

- [ ] **Step 3: Update `docs/working/plan.md` M7 section**

In `docs/working/plan.md`, under the M7 section, replace "Not Started" with completed chunk status.

- [ ] **Step 4: Commit docs**

```bash
git add docs/user_guide/DASHBOARD.md docs/api/API_REFERENCE.md docs/working/plan.md
git commit -m "[M7] Add dashboard user guide + API reference"
```

---

## Acceptance Criteria Checklist

Before sign-off, verify all M7 acceptance criteria:

- [ ] All 18 reactor slots render (16 R + 2 CF); empty slots are greyed out
- [ ] Occupied reactor cards show: reactor label, experiment ID, sample ID, description, type, temperature, elapsed days
- [ ] Click occupied card opens detail modal with full info + link to experiment page
- [ ] Summary metrics reflect real DB data
- [ ] Gantt timeline renders all 100 most recent experiments with correct proportional widths
- [ ] Activity feed shows last 20 ModificationsLog entries with relative timestamps
- [ ] Status + type filter chips filter the timeline correctly
- [ ] Date range filter works
- [ ] "Clear filters" resets all chips and date range
- [ ] Auto-refresh every 60s via React Query `refetchInterval` (no flicker)
- [ ] Single API call confirmed (`/api/dashboard/` only, no secondary calls)
- [ ] Performance test passes: <1000ms with 500-experiment dataset
- [ ] All API tests pass: `pytest tests/api/test_dashboard.py -v`
- [ ] TypeScript strict: 0 errors; ESLint: 0 warnings
- [ ] Production build: clean
- [ ] `docs/user_guide/DASHBOARD.md` written
- [ ] `docs/api/API_REFERENCE.md` updated
- [ ] `docs/working/plan.md` updated

---

## Quick Reference — Commands

```bash
# Run dashboard API tests
.venv/Scripts/python -m pytest tests/api/test_dashboard.py -v

# Run performance test only
.venv/Scripts/python -m pytest tests/api/test_dashboard.py::test_dashboard_performance_500_experiments -v -s

# Frontend type check
cd frontend && npx tsc --noEmit

# Frontend lint
cd frontend && npx eslint src/pages/ --ext .tsx

# Frontend build
cd frontend && npm run build

# Start backend (may need new port if stale process exists)
.venv/Scripts/uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
```
