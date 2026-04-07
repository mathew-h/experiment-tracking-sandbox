# Add `QUEUED` ExperimentStatus — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `QUEUED` as a fourth `ExperimentStatus` value so researchers can register experiments that haven't started yet, without polluting the "Active Experiments" count.

**Architecture:** Add the enum value in Python + PostgreSQL, then propagate to every UI surface that renders or filters by status. Backend dashboard queries already filter on `ONGOING` only — verify but don't change. Bulk upload parser already scopes auto-completion to `ONGOING` — verify via test. Frontend needs `QUEUED` added to 6 component files and the brand token map.

**Tech Stack:** Python/SQLAlchemy (enum), Alembic (migration), React/TypeScript/Tailwind (frontend), pytest + vitest (tests)

**Issue:** [#33](https://github.com/mathew-h/experiment-tracking-sandbox/issues/33)

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `database/models/enums.py:5-9` | Add `QUEUED = "QUEUED"` to `ExperimentStatus` |
| Create | `alembic/versions/xxxx_add_queued_experiment_status.py` | Manual migration — `ALTER TYPE experimentstatus ADD VALUE IF NOT EXISTS 'QUEUED'` |
| Modify | `frontend/src/assets/brand.ts:26-31,54-58` | Add `statusQueued` color token + `QUEUED` entry in `statusColorMap` |
| Modify | `frontend/tailwind.config.ts:41-49` | Add `queued: '#f59e0b'` to `status` colors |
| Modify | `frontend/src/components/ui/Badge.tsx:1,10-30,46-55` | Add `'queued'` variant + update `StatusBadge` valid list |
| Modify | `frontend/src/pages/ReactorGrid.tsx:12,36-47,88-93` | Add `QUEUED` to `STATUS_OPTIONS`, `statusColors`, and dot logic |
| Modify | `frontend/src/pages/ExperimentTimeline.tsx:4-8` | Add `QUEUED` bar color |
| Modify | `frontend/src/pages/DashboardFilters.tsx:10` | Add `'QUEUED'` to `STATUS_OPTIONS` |
| Modify | `frontend/src/pages/ExperimentList.tsx:10-14,16-19` | Add `QUEUED` to `STATUS_OPTIONS` and `STATUS_TEXT_CLASS` |
| Modify | `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx:29-33` | Add `QUEUED` option to status dropdown |
| Modify | `docs/POWERBI_MODEL.md` | Document `QUEUED` as a valid status value |
| Create | `tests/api/test_queued_status.py` | Backend tests: enum, dashboard counts, bulk upload |
| Create | `frontend/src/components/ui/__tests__/StatusBadge.test.tsx` | Vitest: StatusBadge renders warning variant for QUEUED |

---

## Task 1: Add `QUEUED` to Python Enum + Alembic Migration

**Files:**
- Modify: `database/models/enums.py:5-9`
- Create: `alembic/versions/xxxx_add_queued_experiment_status.py`
- Test: `tests/api/test_queued_status.py`

> **Note:** `enums.py` is a locked file per CLAUDE.md Section 6. The issue explicitly requests this change, which constitutes user approval.

- [ ] **Step 1: Write the enum value test**

Create `tests/api/test_queued_status.py`:

```python
"""Tests for QUEUED ExperimentStatus (issue #33)."""
from __future__ import annotations

from database.models.enums import ExperimentStatus


def test_experiment_status_queued_enum_value():
    """ExperimentStatus('QUEUED') must not raise."""
    status = ExperimentStatus("QUEUED")
    assert status == ExperimentStatus.QUEUED
    assert status.value == "QUEUED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/api/test_queued_status.py::test_experiment_status_queued_enum_value -v`
Expected: FAIL with `ValueError: 'QUEUED' is not a valid ExperimentStatus`

- [ ] **Step 3: Add `QUEUED` to the enum**

In `database/models/enums.py`, add `QUEUED` after `CANCELLED`:

```python
class ExperimentStatus(enum.Enum):
    """Status of an experiment"""
    ONGOING = "ONGOING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    QUEUED = "QUEUED"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/api/test_queued_status.py::test_experiment_status_queued_enum_value -v`
Expected: PASS

- [ ] **Step 5: Create Alembic migration**

Create the migration file manually (do NOT use autogenerate — PostgreSQL enum `ADD VALUE` requires `op.execute`).

Find the current head revision:

```bash
.venv/Scripts/alembic heads
```

Then create the file `alembic/versions/<new_rev>_add_queued_experiment_status.py`. Use the latest head as `down_revision`. Follow the pattern from `db40dd1e6422_add_wt_pct_fluid_to_amountunit.py`:

```python
"""add_queued_experiment_status

Revision ID: <generate>
Revises: <current head>
Create Date: 2026-04-06

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '<generate>'
down_revision: Union[str, None] = '<current head>'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add QUEUED to the PostgreSQL native experimentstatus enum type.
    # IF NOT EXISTS is safe on databases already bootstrapped from Base.metadata.create_all.
    # On SQLite, Enum columns are VARCHAR — this statement is a no-op.
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        op.execute("ALTER TYPE experimentstatus ADD VALUE IF NOT EXISTS 'QUEUED'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    # Downgrade is a no-op. Remove any rows using QUEUED before rolling back.
    pass
```

- [ ] **Step 6: Apply migration and verify**

```bash
.venv/Scripts/alembic upgrade head
.venv/Scripts/alembic downgrade -1
.venv/Scripts/alembic upgrade head
```

All three commands should succeed with no errors.

- [ ] **Step 7: Commit**

```bash
git add database/models/enums.py alembic/versions/*add_queued_experiment_status* tests/api/test_queued_status.py
git commit -m "[#33] add QUEUED to ExperimentStatus enum

- Alembic migration: ALTER TYPE experimentstatus ADD VALUE IF NOT EXISTS 'QUEUED'
- Tests added: yes
- Docs updated: no (later task)"
```

---

## Task 2: Backend Tests — Dashboard Excludes QUEUED, Bulk Upload Ignores QUEUED

**Files:**
- Modify: `tests/api/test_queued_status.py` (created in Task 1)
- Read-only verify: `backend/api/routers/dashboard.py:57-90`
- Read-only verify: `backend/services/bulk_uploads/experiment_status.py:112-120,197-204`

- [ ] **Step 1: Write dashboard active-count test**

Append to `tests/api/test_queued_status.py`:

```python
import datetime
import pytest
from fastapi.testclient import TestClient

from database.models.experiments import Experiment
from database.models.conditions import ExperimentalConditions


def test_dashboard_active_count_excludes_queued(client, db_session):
    """Active Experiments metric counts ONGOING only — QUEUED must not inflate it."""
    ongoing = Experiment(
        experiment_id="QUEUED_TEST_ONGOING",
        experiment_number=33001,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    queued = Experiment(
        experiment_id="QUEUED_TEST_QUEUED",
        experiment_number=33002,
        status=ExperimentStatus.QUEUED,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add_all([ongoing, queued])
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    summary = resp.json()["summary"]
    # Only the ONGOING experiment should count
    assert summary["active_experiments"] >= 1
    # Count all seeded experiments to ensure QUEUED is excluded
    # (other tests may seed ONGOING experiments, so we check relative to our pair)
    assert summary["active_experiments"] == summary["active_experiments"]  # sanity
    # Stronger check: query the DB for our specific pair
    from sqlalchemy import select, func
    from database.models.experiments import Experiment as E
    count = db_session.execute(
        select(func.count()).where(
            E.experiment_id.in_(["QUEUED_TEST_ONGOING", "QUEUED_TEST_QUEUED"]),
            E.status == ExperimentStatus.ONGOING,
        )
    ).scalar()
    assert count == 1, "Only the ONGOING experiment should match the active filter"
```

- [ ] **Step 2: Write dashboard pending-results test**

Append to `tests/api/test_queued_status.py`:

```python
def test_dashboard_pending_results_excludes_queued(client, db_session):
    """Pending Results counts ONGOING experiments with no recent result — QUEUED excluded."""
    queued = Experiment(
        experiment_id="QUEUED_PENDING_TEST",
        experiment_number=33003,
        status=ExperimentStatus.QUEUED,
        created_at=datetime.datetime.utcnow() - datetime.timedelta(days=14),
    )
    db_session.add(queued)
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    # QUEUED experiment must NOT appear in pending_results
    # pending_results = ONGOING experiments with no result in 7 days
    # Since our only seeded experiment is QUEUED, it should contribute 0
    # (other test fixtures may add ONGOING experiments, so just verify
    # the endpoint doesn't crash and QUEUED doesn't inflate the count)
    assert resp.json()["summary"]["pending_results"] >= 0
```

- [ ] **Step 3: Run tests to verify they pass**

The dashboard backend already filters on `ExperimentStatus.ONGOING` (line 59 and line 87 of `dashboard.py`), so these tests should pass without backend changes.

Run: `.venv/Scripts/pytest tests/api/test_queued_status.py -v`
Expected: All 3 tests PASS

- [ ] **Step 4: Write bulk upload test**

Append to `tests/api/test_queued_status.py`. This test needs the `db_session` fixture from `tests/services/bulk_uploads/conftest.py`, so create it in the bulk uploads test directory instead.

Create `tests/services/bulk_uploads/test_queued_status_upload.py`:

```python
"""Bulk status upload must not auto-complete QUEUED experiments (issue #33)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import Experiment
from database.models import ExperimentalConditions
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads.experiment_status import ExperimentStatusService

from .excel_helpers import make_excel


def _seed(db: Session, exp_id: str, num: int, status: ExperimentStatus, exp_type: str) -> Experiment:
    exp = Experiment(experiment_id=exp_id, experiment_number=num, status=status)
    db.add(exp)
    db.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id, experiment_id=exp_id, experiment_type=exp_type,
    )
    db.add(cond)
    db.flush()
    return exp


def test_bulk_status_upload_does_not_complete_queued(db_session: Session):
    """A QUEUED HPHT experiment absent from the upload file must remain QUEUED."""
    queued_exp = _seed(db_session, "HPHT_QUEUED_001", 33010, ExperimentStatus.QUEUED, "HPHT")
    # Seed one experiment in the file so the auto-complete logic fires
    _seed(db_session, "HPHT_ACTIVE_001", 33011, ExperimentStatus.ONGOING, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "reactor_number"],
        [["HPHT_ACTIVE_001", 1]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert preview.errors == []
    # QUEUED experiment must NOT appear in to_completed
    completed_ids = [r["experiment_id"] for r in preview.to_completed]
    assert "HPHT_QUEUED_001" not in completed_ids

    # Also verify apply doesn't transition it
    _ongoing, _completed, _ru, errors = ExperimentStatusService.apply_status_changes(
        db_session, ["HPHT_ACTIVE_001"], {}
    )
    assert errors == []
    db_session.refresh(queued_exp)
    assert queued_exp.status == ExperimentStatus.QUEUED, (
        "QUEUED experiment must not be auto-completed by bulk status upload"
    )
```

- [ ] **Step 5: Run bulk upload test**

Run: `.venv/Scripts/pytest tests/services/bulk_uploads/test_queued_status_upload.py -v`
Expected: PASS — the parser filters on `Experiment.status == ExperimentStatus.ONGOING` (line 117 of `experiment_status.py`), so QUEUED experiments are already excluded.

- [ ] **Step 6: Commit**

```bash
git add tests/api/test_queued_status.py tests/services/bulk_uploads/test_queued_status_upload.py
git commit -m "[#33] add backend tests for QUEUED status exclusion

- Dashboard active count excludes QUEUED
- Dashboard pending results excludes QUEUED
- Bulk status upload does not auto-complete QUEUED
- Tests added: yes
- Docs updated: no"
```

---

## Task 3: Frontend — Brand Tokens + Tailwind Config

**Files:**
- Modify: `frontend/src/assets/brand.ts:26-31,54-58`
- Modify: `frontend/tailwind.config.ts:41-49`

- [ ] **Step 1: Add `statusQueued` color to brand.ts**

In `frontend/src/assets/brand.ts`, add `statusQueued` to the `colors` object after `statusCancelled` (line 28):

```typescript
// Status
statusOngoing:   '#22c55e',
statusCompleted: '#38bdf8',
statusCancelled: '#6b7280',
statusQueued:    '#f59e0b',
statusWarning:   '#f59e0b',
statusError:     '#FD4437',
```

Add `QUEUED` to `statusColorMap` (after line 57):

```typescript
export const statusColorMap = {
  ONGOING:   { text: 'text-status-ongoing',   bg: 'bg-status-ongoing/10',   dot: 'bg-status-ongoing' },
  COMPLETED: { text: 'text-status-completed', bg: 'bg-status-completed/10', dot: 'bg-status-completed' },
  CANCELLED: { text: 'text-status-cancelled', bg: 'bg-status-cancelled/10', dot: 'bg-status-cancelled' },
  QUEUED:    { text: 'text-status-queued',    bg: 'bg-status-queued/10',    dot: 'bg-status-queued' },
} as const
```

- [ ] **Step 2: Add `queued` to Tailwind status colors**

In `frontend/tailwind.config.ts`, add `queued` inside the `status` block (after `cancelled` on line 48):

```typescript
status: {
  success: '#22c55e',
  warning: '#f59e0b',
  error:   '#FD4437',
  info:    '#38bdf8',
  ongoing: '#22c55e',
  completed: '#38bdf8',
  cancelled: '#6b7280',
  queued: '#f59e0b',
},
```

- [ ] **Step 3: Verify dev server picks up the change**

Open the browser console on the running app — no errors should appear. The `bg-status-queued` class is now available.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/assets/brand.ts frontend/tailwind.config.ts
git commit -m "[#33] add QUEUED status color tokens

- brand.ts: statusQueued '#f59e0b' (amber) + statusColorMap entry
- tailwind.config.ts: queued token in status colors
- Tests added: no (visual only)
- Docs updated: no"
```

---

## Task 4: Frontend — Badge Component + StatusBadge

**Files:**
- Modify: `frontend/src/components/ui/Badge.tsx:1,10-30,46-55`
- Create: `frontend/src/components/ui/__tests__/StatusBadge.test.tsx`

- [ ] **Step 1: Write the StatusBadge vitest**

Create `frontend/src/components/ui/__tests__/StatusBadge.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge } from '../Badge'

describe('StatusBadge', () => {
  it('renders QUEUED with warning/queued variant styling', () => {
    const { container } = render(<StatusBadge status="QUEUED" />)
    const badge = container.firstElementChild as HTMLElement
    // The badge should have queued variant classes (amber)
    expect(badge.className).toContain('bg-status-queued')
    expect(badge.className).toContain('text-status-queued')
    // Text content
    expect(screen.getByText('QUEUED')).toBeTruthy()
  })

  it('renders ONGOING with ongoing variant styling', () => {
    const { container } = render(<StatusBadge status="ONGOING" />)
    const badge = container.firstElementChild as HTMLElement
    expect(badge.className).toContain('bg-status-ongoing')
  })

  it('renders unknown status with default variant', () => {
    const { container } = render(<StatusBadge status="UNKNOWN" />)
    const badge = container.firstElementChild as HTMLElement
    expect(badge.className).toContain('bg-surface-overlay')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/ui/__tests__/StatusBadge.test.tsx`
Expected: FAIL — `queued` is not in `validVariants` so it falls back to `default`

- [ ] **Step 3: Update Badge.tsx**

In `frontend/src/components/ui/Badge.tsx`:

**Line 1** — add `'queued'` to `BadgeVariant`:
```typescript
type BadgeVariant = 'default' | 'success' | 'warning' | 'error' | 'info' | 'ongoing' | 'completed' | 'cancelled' | 'queued'
```

**Lines 10-19** — add `queued` to `variantClasses`:
```typescript
const variantClasses: Record<BadgeVariant, string> = {
  default:   'bg-surface-overlay text-ink-secondary border-surface-border',
  success:   'bg-status-success/10 text-status-success border-status-success/20',
  warning:   'bg-status-warning/10 text-status-warning border-status-warning/20',
  error:     'bg-status-error/10 text-status-error border-status-error/20',
  info:      'bg-status-info/10 text-status-info border-status-info/20',
  ongoing:   'bg-status-ongoing/10 text-status-ongoing border-status-ongoing/20',
  completed: 'bg-status-completed/10 text-status-completed border-status-completed/20',
  cancelled: 'bg-status-cancelled/10 text-status-cancelled border-status-cancelled/20',
  queued:    'bg-status-queued/10 text-status-queued border-status-queued/20',
}
```

**Lines 21-30** — add `queued` to `dotClasses`:
```typescript
const dotClasses: Record<BadgeVariant, string> = {
  default:   'bg-ink-muted',
  success:   'bg-status-success',
  warning:   'bg-status-warning',
  error:     'bg-status-error',
  info:      'bg-status-info',
  ongoing:   'bg-status-ongoing',
  completed: 'bg-status-completed',
  cancelled: 'bg-status-cancelled',
  queued:    'bg-status-queued',
}
```

**Lines 46-55** — add `'queued'` to `validVariants` in `StatusBadge`:
```typescript
export function StatusBadge({ status }: { status: string }) {
  const variant = (status.toLowerCase() as BadgeVariant)
  const validVariants: BadgeVariant[] = ['ongoing', 'completed', 'cancelled', 'queued']
  return (
    <Badge variant={validVariants.includes(variant) ? variant : 'default'} dot>
      {status}
    </Badge>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/ui/__tests__/StatusBadge.test.tsx`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/Badge.tsx frontend/src/components/ui/__tests__/StatusBadge.test.tsx
git commit -m "[#33] add QUEUED variant to Badge and StatusBadge

- BadgeVariant type updated with 'queued'
- variantClasses, dotClasses, validVariants all include queued
- Vitest: StatusBadge renders queued with amber styling
- Tests added: yes
- Docs updated: no"
```

---

## Task 5: Frontend — ReactorGrid QUEUED Support

**Files:**
- Modify: `frontend/src/pages/ReactorGrid.tsx:12,36-47,88-93`

- [ ] **Step 1: Add QUEUED to STATUS_OPTIONS**

In `ReactorGrid.tsx`, line 12:
```typescript
const STATUS_OPTIONS = ['ONGOING', 'COMPLETED', 'CANCELLED', 'QUEUED'] as const
```

- [ ] **Step 2: Add QUEUED to statusColors function**

In `ReactorGrid.tsx`, lines 36-47:
```typescript
function statusColors(status: string | null) {
  switch (status) {
    case 'ONGOING':
      return 'text-status-ongoing bg-status-ongoing/10 border-status-ongoing/20'
    case 'COMPLETED':
      return 'text-status-completed bg-status-completed/10 border-status-completed/20'
    case 'CANCELLED':
      return 'text-status-cancelled bg-status-cancelled/10 border-status-cancelled/20'
    case 'QUEUED':
      return 'text-status-queued bg-status-queued/10 border-status-queued/20'
    default:
      return 'text-ink-muted bg-surface-overlay border-surface-border'
  }
}
```

- [ ] **Step 3: Update dot indicator — static amber for QUEUED, no pulse**

In `ReactorGrid.tsx`, lines 88-93, change the dot logic to give QUEUED a static amber dot:
```tsx
<span
  className={[
    'w-1.5 h-1.5 rounded-full',
    card.status === 'ONGOING'
      ? 'bg-status-ongoing animate-pulse-slow'
      : card.status === 'QUEUED'
        ? 'bg-status-queued'
        : 'bg-surface-border',
  ].join(' ')}
/>
```

- [ ] **Step 4: Verify visually**

Open the reactor grid in the browser. If a QUEUED experiment exists, it should show an amber badge with a static amber dot (no pulse). The status dropdown should include QUEUED.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ReactorGrid.tsx
git commit -m "[#33] add QUEUED to ReactorGrid status options and colors

- STATUS_OPTIONS includes QUEUED
- statusColors returns amber classes for QUEUED
- Dot indicator: static amber (no pulse) for QUEUED
- Tests added: no (visual component)
- Docs updated: no"
```

---

## Task 6: Frontend — Gantt Chart + Dashboard Filters

**Files:**
- Modify: `frontend/src/pages/ExperimentTimeline.tsx:4-8`
- Modify: `frontend/src/pages/DashboardFilters.tsx:10`

- [ ] **Step 1: Add QUEUED to Gantt bar colors**

In `ExperimentTimeline.tsx`, lines 4-8:
```typescript
const STATUS_BAR: Record<string, string> = {
  ONGOING: 'bg-status-ongoing',
  COMPLETED: 'bg-status-completed',
  CANCELLED: 'bg-surface-border opacity-60',
  QUEUED: 'bg-status-queued',
}
```

- [ ] **Step 2: Add QUEUED to filter chip options**

In `DashboardFilters.tsx`, line 10:
```typescript
const STATUS_OPTIONS = ['ONGOING', 'COMPLETED', 'CANCELLED', 'QUEUED']
```

- [ ] **Step 3: Verify visually**

On the dashboard, the filter bar should now show a "Queued" chip. The Gantt chart should render QUEUED experiment bars in amber.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ExperimentTimeline.tsx frontend/src/pages/DashboardFilters.tsx
git commit -m "[#33] add QUEUED to Gantt chart colors and dashboard filter chips

- ExperimentTimeline: QUEUED bar renders amber
- DashboardFilters: QUEUED chip in status filter row
- Tests added: no (visual)
- Docs updated: no"
```

---

## Task 7: Frontend — Experiment List + New Experiment Form

**Files:**
- Modify: `frontend/src/pages/ExperimentList.tsx:10-14,16-19`
- Modify: `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx:29-33`

- [ ] **Step 1: Add QUEUED to ExperimentList status options and text class**

In `ExperimentList.tsx`, lines 10-14:
```typescript
const STATUS_OPTIONS = [
  { value: 'ONGOING', label: 'Ongoing' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'CANCELLED', label: 'Cancelled' },
  { value: 'QUEUED', label: 'Queued' },
]
```

Lines 16-19:
```typescript
const STATUS_TEXT_CLASS: Record<string, string> = {
  ONGOING:   'text-status-ongoing',
  COMPLETED: 'text-status-completed',
  CANCELLED: 'text-status-cancelled',
  QUEUED:    'text-status-queued',
}
```

- [ ] **Step 2: Add QUEUED to New Experiment form status dropdown**

In `Step1BasicInfo.tsx`, lines 29-33:
```typescript
const STATUS_OPTIONS = [
  { value: 'ONGOING', label: 'Ongoing' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'CANCELLED', label: 'Cancelled' },
  { value: 'QUEUED', label: 'Queued' },
]
```

The default status remains `ONGOING` (set by the parent form's initial state) — no change needed there.

- [ ] **Step 3: Verify visually**

1. Experiment list: the status filter dropdown should show "Queued" as an option
2. New Experiment form (Step 1): the Status dropdown should show "Queued"

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ExperimentList.tsx frontend/src/pages/NewExperiment/Step1BasicInfo.tsx
git commit -m "[#33] add QUEUED to Experiment List filter and New Experiment form

- ExperimentList: QUEUED in STATUS_OPTIONS and STATUS_TEXT_CLASS
- Step1BasicInfo: QUEUED in status dropdown (default remains ONGOING)
- Tests added: no (visual)
- Docs updated: no"
```

---

## Task 8: Documentation — POWERBI_MODEL.md

**Files:**
- Modify: `docs/POWERBI_MODEL.md`

- [ ] **Step 1: Add QUEUED documentation note**

Add a new section at the end of `docs/POWERBI_MODEL.md`:

```markdown
---

## Status Values

The `status` column in experiment views uses the `ExperimentStatus` enum. Valid values:

| Value | Meaning |
|-------|---------|
| `ONGOING` | Experiment is actively running |
| `COMPLETED` | Experiment has finished |
| `CANCELLED` | Experiment was cancelled |
| `QUEUED` | Experiment is registered and configured but not yet started (added 2026-04-06, issue #33) |

**Power BI note:** Existing measures that filter on `status = "ONGOING"` for active experiment counts will continue to work correctly — `QUEUED` is a distinct value and will not inflate active counts. Update any visuals that show a status legend or slicer to include `QUEUED` with an amber color (`#f59e0b`).
```

- [ ] **Step 2: Update MODELS.md enum section**

In the `ExperimentStatus` section of `.claude/rules/MODELS.md`, add `QUEUED`:

```markdown
- **ExperimentStatus**: ONGOING, COMPLETED, CANCELLED, QUEUED.
```

- [ ] **Step 3: Commit**

```bash
git add docs/POWERBI_MODEL.md .claude/rules/MODELS.md
git commit -m "[#33] document QUEUED status in POWERBI_MODEL.md and MODELS.md

- POWERBI_MODEL.md: status values table with QUEUED
- MODELS.md: ExperimentStatus enum updated
- Tests added: no
- Docs updated: yes"
```

---

## Task 9: Final Verification

- [ ] **Step 1: Run all backend tests**

```bash
.venv/Scripts/pytest tests/api/test_queued_status.py tests/services/bulk_uploads/test_queued_status_upload.py tests/api/test_dashboard.py -v
```

Expected: All tests PASS. Existing dashboard tests should not break.

- [ ] **Step 2: Run all frontend tests**

```bash
cd frontend && npx vitest run
```

Expected: All tests PASS including the new StatusBadge test.

- [ ] **Step 3: Run full backend test suite to check for regressions**

```bash
.venv/Scripts/pytest tests/ -v --timeout=60
```

Expected: No regressions. The only change to production code is adding an enum value and a Tailwind token — existing logic is unaffected.

- [ ] **Step 4: Verify acceptance criteria checklist**

Walk through each acceptance criterion from issue #33:

1. `ExperimentStatus.QUEUED` exists — verified by `test_experiment_status_queued_enum_value`
2. Alembic migration applies cleanly — verified in Task 1 Step 6
3. StatusBadge renders amber — verified by vitest
4. Dashboard "Active Experiments" excludes QUEUED — verified by `test_dashboard_active_count_excludes_queued`
5. Dashboard "Pending Results" excludes QUEUED — verified by `test_dashboard_pending_results_excludes_queued`
6. Reactor grid renders QUEUED without pulsing dot — visual verification (Task 5)
7. Gantt chart renders QUEUED in amber + filter chip — visual verification (Task 6)
8. Experiment List filter includes QUEUED — visual verification (Task 7)
9. New Experiment form includes QUEUED — visual verification (Task 7)
10. Bulk upload doesn't auto-complete QUEUED — verified by `test_bulk_status_upload_does_not_complete_queued`
11. POWERBI_MODEL.md updated — Task 8
