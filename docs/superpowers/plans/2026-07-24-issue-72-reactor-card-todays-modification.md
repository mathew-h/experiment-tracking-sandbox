# Issue #72 — Reactor Cards Show Today's Reactor Modification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the Reactor Modification text on each dashboard reactor card when (and only when) a modification was saved for the current UTC day for that card's experiment + reactor slot.

**Architecture:** The existing single dashboard call (`GET /api/dashboard/`) is enriched server-side: one batched query against `reactor_change_requests` keyed on `(experiment_id, reactor_label, sync_date == today UTC)` populates a new optional `todays_modification` field on `ReactorCardData`. The frontend adds the field to its TS type and renders a compact, line-clamped block in the occupied branch of `ReactorCard`. No new endpoints, no migration, no per-card fetches.

**Tech Stack:** FastAPI + SQLAlchemy 2.x select() + Pydantic v2 (backend), React 18 + TypeScript + Tailwind + vitest/@testing-library (frontend), pytest (backend tests).

## Global Constraints

- **Branch:** all work on `feat/issue-72-reactor-card-todays-modification` (already created off `develop`).
- **Commit format** (from `.claude/CLAUDE.md` §8): `[#72] <imperative description, <50 chars, no trailing period>` with body lines `- Tests added: yes/no` and `- Docs updated: yes/no`.
- **No N+1:** `GET /api/dashboard/` must remain a single call; the modification lookup is exactly ONE additional batched query. Never fetch per-card from the frontend.
- **"Current day" = UTC:** `now.date()` where `now = datetime.now(timezone.utc)` (already computed in `get_dashboard`). This matches the pop-out's save path (`todayISO()` is the UTC date). Do NOT convert to lab-local time — that is explicitly out of scope per the issue.
- **No migration, no model changes:** `database/models/` is locked; this feature only reads the existing `reactor_change_requests` table.
- **Key on BOTH `experiment_id` AND `reactor_label`:** a same-day row logged against the experiment under a different reactor slot must NOT appear on the card.
- **Card render rule:** if `todays_modification` is null, the card renders exactly as today — no label, no placeholder, no empty box. Applies to both ONGOING and QUEUED cards; never on empty slots.
- **Frontend rules:** Tailwind utility classes only, no inline styles, no hardcoded hex, no `console.log`. Do NOT touch `frontend/package.json` or `package-lock.json` — no new dependencies.
- **Locked components:** do not modify `database/models/`, `backend/services/bulk_uploads/`, `alembic/versions/`, or Firebase auth.
- **Test runner facts:** backend tests run against a real PostgreSQL test DB via fixtures `client` / `db_session` from `tests/conftest.py` (auth is dependency-overridden). Frontend tests run with `npx vitest run <file>` from `frontend/`.
- The `.claude/hooks/` PostToolUse hook auto-syncs any file written under `docs/` to `docs/project_context/` — write only the source doc, never the copy.

---

### Task 1: Backend — `todays_modification` on `ReactorCardData` + batched dashboard query + API docs

**Files:**
- Modify: `backend/api/schemas/dashboard.py` (add one field to `ReactorCardData`, ~line 58)
- Modify: `backend/api/routers/dashboard.py` (one import + one batched lookup block after the `reactor_cards` loop, ~line 188)
- Test: `tests/api/test_dashboard.py` (append new tests)
- Modify: `docs/api/API_REFERENCE.md` (`GET /api/dashboard/` response example + notes, ~lines 312–359)

**Interfaces:**
- Consumes: existing `ReactorChangeRequest` model (`database/models/notion_sync.py`) — columns `experiment_id` (String FK to `experiments.experiment_id`), `reactor_label` (String), `requested_change` (String), `sync_date` (Date). Unique on `(reactor_label, experiment_id, sync_date)`.
- Produces: `ReactorCardData.todays_modification: Optional[str] = None` in the `GET /api/dashboard/` JSON payload — Task 2's frontend type mirrors this exact field name.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_dashboard.py` (the file already has `import datetime` at the top — do not re-import):

```python
# ---------------------------------------------------------------------------
# Today's reactor modification on cards (issue #72)
# ---------------------------------------------------------------------------

def _utc_today() -> datetime.date:
    """The dashboard's definition of 'today' — UTC, matching the pop-out save path."""
    return datetime.datetime.now(datetime.timezone.utc).date()


def test_reactor_card_data_schema_todays_modification_defaults_none():
    from backend.api.schemas.dashboard import ReactorCardData
    r = ReactorCardData(reactor_number=5, reactor_label="R05")
    assert r.todays_modification is None


def test_reactor_card_shows_todays_modification(client, db_session):
    """A card whose experiment has a change request with sync_date == today (UTC)
    returns the requested_change text in todays_modification."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.notion_sync import ReactorChangeRequest
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="MOD_TODAY_001",
        experiment_number=72001,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(exp)
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="MOD_TODAY_001",
        reactor_number=4,
        experiment_type="HPHT",
    ))
    db_session.add(ReactorChangeRequest(
        reactor_label="R04",
        experiment_id="MOD_TODAY_001",
        requested_change="Swapped stir shaft; topped up catalyst",
        sync_date=_utc_today(),
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}
    assert "R04" in cards
    assert cards["R04"]["todays_modification"] == "Swapped stir shaft; topped up catalyst"


def test_reactor_card_prior_day_modification_not_shown(client, db_session):
    """A modification saved yesterday must NOT surface on the card."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.notion_sync import ReactorChangeRequest
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="MOD_YDAY_001",
        experiment_number=72002,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(exp)
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="MOD_YDAY_001",
        reactor_number=5,
        experiment_type="HPHT",
    ))
    db_session.add(ReactorChangeRequest(
        reactor_label="R05",
        experiment_id="MOD_YDAY_001",
        requested_change="Yesterday's note",
        sync_date=_utc_today() - datetime.timedelta(days=1),
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}
    assert "R05" in cards
    assert cards["R05"]["todays_modification"] is None


def test_todays_modification_keys_on_experiment_and_reactor_label(client, db_session):
    """Three cards: ONGOING with a today-mod, QUEUED with a today-mod, ONGOING without.
    Only the two with a matching (experiment_id, reactor_label, today) row are populated.
    A same-day row saved under a DIFFERENT reactor_label must not leak onto the card."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.notion_sync import ReactorChangeRequest
    from database.models.enums import ExperimentStatus

    specs = [
        ("MOD_KEY_ON", 72010, ExperimentStatus.ONGOING, 6),
        ("MOD_KEY_QU", 72011, ExperimentStatus.QUEUED, 7),
        ("MOD_KEY_NO", 72012, ExperimentStatus.ONGOING, 8),
        ("MOD_KEY_WRONG_SLOT", 72013, ExperimentStatus.ONGOING, 9),
    ]
    for exp_id, num, status, rn in specs:
        exp = Experiment(
            experiment_id=exp_id,
            experiment_number=num,
            status=status,
            created_at=datetime.datetime.utcnow(),
        )
        db_session.add(exp)
        db_session.flush()
        db_session.add(ExperimentalConditions(
            experiment_fk=exp.id,
            experiment_id=exp_id,
            reactor_number=rn,
            experiment_type="HPHT",
        ))
    db_session.add(ReactorChangeRequest(
        reactor_label="R06", experiment_id="MOD_KEY_ON",
        requested_change="ongoing mod", sync_date=_utc_today(),
    ))
    db_session.add(ReactorChangeRequest(
        reactor_label="R07", experiment_id="MOD_KEY_QU",
        requested_change="queued mod", sync_date=_utc_today(),
    ))
    # Saved today for MOD_KEY_WRONG_SLOT but under a reactor label it does NOT occupy:
    db_session.add(ReactorChangeRequest(
        reactor_label="R01", experiment_id="MOD_KEY_WRONG_SLOT",
        requested_change="wrong slot mod", sync_date=_utc_today(),
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}
    assert cards["R06"]["todays_modification"] == "ongoing mod"
    assert cards["R07"]["todays_modification"] == "queued mod"
    assert cards["R08"]["todays_modification"] is None
    assert cards["R09"]["todays_modification"] is None, (
        "A same-day row under a different reactor_label must not appear on this card"
    )


def test_dashboard_modification_lookup_is_single_batched_query(client, db_session):
    """The enrichment must add exactly ONE query touching reactor_change_requests,
    regardless of how many cards are occupied (no per-card N+1)."""
    import sqlalchemy
    from sqlalchemy.engine import Engine
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.notion_sync import ReactorChangeRequest
    from database.models.enums import ExperimentStatus

    for i, rn in enumerate((10, 11, 12)):
        exp = Experiment(
            experiment_id=f"MOD_BATCH_{rn}",
            experiment_number=72100 + i,
            status=ExperimentStatus.ONGOING,
            created_at=datetime.datetime.utcnow(),
        )
        db_session.add(exp)
        db_session.flush()
        db_session.add(ExperimentalConditions(
            experiment_fk=exp.id, experiment_id=exp.experiment_id,
            reactor_number=rn, experiment_type="HPHT",
        ))
        db_session.add(ReactorChangeRequest(
            reactor_label=f"R{rn:02d}", experiment_id=exp.experiment_id,
            requested_change=f"mod {rn}", sync_date=_utc_today(),
        ))
    db_session.commit()

    statements: list[str] = []

    def counter(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sqlalchemy.event.listen(Engine, "before_cursor_execute", counter)
    try:
        resp = client.get("/api/dashboard/")
    finally:
        sqlalchemy.event.remove(Engine, "before_cursor_execute", counter)

    assert resp.status_code == 200
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}
    assert cards["R10"]["todays_modification"] == "mod 10"
    assert cards["R12"]["todays_modification"] == "mod 12"
    cr_queries = [s for s in statements if "reactor_change_requests" in s]
    assert len(cr_queries) == 1, (
        f"Expected exactly 1 batched change-request query, got {len(cr_queries)}"
    )
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run (from project root):
```bash
.venv/Scripts/python -m pytest tests/api/test_dashboard.py -v -k "todays_modification or modification"
```
Expected: `test_reactor_card_data_schema_todays_modification_defaults_none` FAILS with Pydantic `AttributeError`/`ValidationError` (no such field); the integration tests FAIL with `KeyError: 'todays_modification'`.

- [ ] **Step 3: Add the schema field**

In `backend/api/schemas/dashboard.py`, inside `ReactorCardData` (after the `vendor` field, ~line 58), add:

```python
    todays_modification: Optional[str] = None  # requested_change saved today (UTC) for this experiment + reactor slot; None if none
```

- [ ] **Step 4: Add the batched lookup in the router**

In `backend/api/routers/dashboard.py`:

1. Add to the model imports at the top (after the `database.models.enums` import, ~line 10):

```python
from database.models.notion_sync import ReactorChangeRequest
```

2. Insert immediately after the `reactor_cards` build loop ends (after the `reactor_cards.append(ReactorCardData(...))` loop, before the `# ── 3. Gantt timeline` comment, ~line 188):

```python
    # ── 2b. Today's reactor modification per card (issue #72) ─────────────
    # One batched query keyed on (experiment_id, reactor_label) — keeps the
    # "no N+1" contract of this endpoint. "Today" is UTC, matching the
    # pop-out's save path (todayISO() is the UTC date).
    today = now.date()
    card_exp_ids = [c.experiment_id for c in reactor_cards if c.experiment_id]
    if card_exp_ids:
        mod_rows = db.execute(
            select(
                ReactorChangeRequest.experiment_id,
                ReactorChangeRequest.reactor_label,
                ReactorChangeRequest.requested_change,
            ).where(
                ReactorChangeRequest.experiment_id.in_(card_exp_ids),
                ReactorChangeRequest.sync_date == today,
            )
        ).all()
        mods = {(r.experiment_id, r.reactor_label): r.requested_change for r in mod_rows}
        for c in reactor_cards:
            c.todays_modification = mods.get((c.experiment_id, c.reactor_label))
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run:
```bash
.venv/Scripts/python -m pytest tests/api/test_dashboard.py -v -k "todays_modification or modification"
```
Expected: all 5 new tests PASS.

- [ ] **Step 6: Run the full dashboard test file (regression)**

Run:
```bash
.venv/Scripts/python -m pytest tests/api/test_dashboard.py -v
```
Expected: ALL tests pass (the pre-existing ones prove the response shape is otherwise unchanged).

- [ ] **Step 7: Update the API reference**

In `docs/api/API_REFERENCE.md`, in the `GET /api/dashboard/` response example, add one line to the reactor card object (after `"temperature_c": 200.0` — add a trailing comma to that line):

```json
      "temperature_c": 200.0,
      "todays_modification": "Swapped stir shaft; topped up catalyst"
```

And add one bullet to the **Notes** list under the example:

```markdown
- `todays_modification` is the `requested_change` of a reactor modification saved for the current UTC day for this card's `(experiment_id, reactor_label)`; `null` if none was saved today. Populated by one batched query — the endpoint remains a single call.
```

Do not edit `docs/project_context/` — the hook syncs it.

- [ ] **Step 8: Commit**

```bash
git add backend/api/schemas/dashboard.py backend/api/routers/dashboard.py tests/api/test_dashboard.py docs/api/API_REFERENCE.md docs/project_context/API_REFERENCE.md
git commit -m "[#72] Add todays_modification to reactor cards

- One batched reactor_change_requests query keyed on (experiment_id, reactor_label, today UTC)
- Tests added: yes
- Docs updated: yes"
```

(If the hook-synced copy has a different path under `docs/project_context/`, `git status` after Step 7 shows the exact file — add whatever it produced.)

---

### Task 2: Frontend — TS type + `ReactorCard` render block + component test

**Files:**
- Modify: `frontend/src/api/dashboard.ts` (add one field to `ReactorCardData` interface, ~line 38)
- Modify: `frontend/src/pages/ReactorGrid.tsx` (one conditional block in the occupied branch of `ReactorCard`, ~line 218)
- Test: Create `frontend/src/pages/__tests__/ReactorGrid.test.tsx`

**Interfaces:**
- Consumes: the backend field from Task 1 — `todays_modification` (string or null) on each element of `DashboardData.reactors`.
- Produces: nothing consumed by later tasks (this is the final task).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/__tests__/ReactorGrid.test.tsx`:

```tsx
import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import type { ReactorCardData } from '@/api/dashboard'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    patchStatus: vi.fn(),
    patch: vi.fn(),
    getRecentChangeRequests: vi.fn(),
    createChangeRequest: vi.fn(),
  },
}))

import { ReactorGrid } from '../ReactorGrid'

function makeCard(overrides: Partial<ReactorCardData> = {}): ReactorCardData {
  return {
    reactor_number: 5,
    reactor_label: 'R05',
    experiment_id: 'HPHT_MH_072',
    experiment_db_id: 142,
    status: 'ONGOING',
    experiment_type: 'HPHT',
    sample_id: null,
    description: null,
    researcher: null,
    started_at: null,
    days_running: 3,
    temperature_c: 200,
    volume_mL: null,
    material: null,
    vendor: null,
    todays_modification: null,
    ...overrides,
  }
}

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

describe('ReactorCard — todays_modification (issue #72)', () => {
  it('renders the modification text with the "Modified today:" label when set', () => {
    renderGrid([makeCard({ todays_modification: 'Swapped stir shaft' })])
    expect(screen.getByText('Modified today:')).toBeInTheDocument()
    expect(screen.getByText(/Swapped stir shaft/)).toBeInTheDocument()
  })

  it('renders no modification block when todays_modification is null', () => {
    renderGrid([makeCard({ todays_modification: null })])
    expect(screen.queryByText('Modified today:')).toBeNull()
  })

  it('exposes the full text via the title attribute for hover', () => {
    const long =
      'A very long modification text that will be line-clamped on the card face but fully visible on hover'
    renderGrid([makeCard({ todays_modification: long })])
    const block = screen.getByTitle(long)
    expect(block).toHaveTextContent('Modified today:')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`):
```bash
npx vitest run src/pages/__tests__/ReactorGrid.test.tsx
```
Expected: FAIL — first the TS type lacks `todays_modification` (test 1 and 3 fail with "Unable to find an element"; the `makeCard` object literal may also produce a TS error in editors, vitest itself runs via esbuild without type-checking).

- [ ] **Step 3: Add the field to the TS interface**

In `frontend/src/api/dashboard.ts`, inside `export interface ReactorCardData` (after `vendor: string | null`, ~line 38), add:

```ts
  todays_modification: string | null
```

- [ ] **Step 4: Add the render block to `ReactorCard`**

In `frontend/src/pages/ReactorGrid.tsx`, inside the `occupied` branch of `ReactorCard` — immediately after the `{card!.description && (...)}` block (~line 218) and before the `<div className="flex items-center gap-3 pt-0.5">` temperature/day row — insert:

```tsx
          {card!.todays_modification && (
            <p
              className="text-xs text-ink-secondary line-clamp-2 leading-snug"
              title={card!.todays_modification}
            >
              <span className="text-ink-muted">Modified today:</span>{' '}
              {card!.todays_modification}
            </p>
          )}
```

Note: this block renders for any occupied card (ONGOING or QUEUED) — no status gate. Empty slots take the other branch and can never show it.

- [ ] **Step 5: Run the test to verify it passes**

Run (from `frontend/`):
```bash
npx vitest run src/pages/__tests__/ReactorGrid.test.tsx
```
Expected: 3 tests PASS.

- [ ] **Step 6: Full frontend verification**

Run (from `frontend/`):
```bash
npx vitest run
npx tsc --noEmit
npx eslint src --ext .ts,.tsx
```
Expected: all vitest suites pass; tsc clean; eslint reports only the 5 known pre-existing errors in files this branch never touched (none in `ReactorGrid.tsx`, `dashboard.ts`, or the new test file).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/dashboard.ts frontend/src/pages/ReactorGrid.tsx frontend/src/pages/__tests__/ReactorGrid.test.tsx
git commit -m "[#72] Render today's modification on reactor cards

- Line-clamped block with title hover, occupied cards only
- Tests added: yes
- Docs updated: no"
```

---

## Acceptance Criteria Traceability

| Issue criterion | Covered by |
|---|---|
| Card with today's mod shows the text | Task 1 `test_reactor_card_shows_todays_modification` + Task 2 test 1 |
| No mod → card identical to current behavior | Task 1 keying test (R08 None) + Task 2 test 2; pre-existing dashboard tests pass unchanged |
| Prior-day mod not shown | Task 1 `test_reactor_card_prior_day_modification_not_shown` |
| Save in pop-out + reload shows on card | ~~`['dashboard']` query already invalidated on save (pre-existing)~~ **Plan premise was false** (final review finding): `crMutation.onSuccess` did not invalidate `['dashboard']` — fixed post-review by adding the one-line invalidation, matching the sibling mutations. Backend read path covered by Task 1 tests |
| Works for ONGOING and QUEUED; never empty slots | Task 1 keying test (QUEUED card) + Task 2 render placement (occupied branch only) |
| Long text line-clamped with title hover | Task 2 render block (`line-clamp-2`, `title`) + Task 2 test 3 |
| Single call, one batched lookup, no per-card queries | Task 1 `test_dashboard_modification_lookup_is_single_batched_query` |
