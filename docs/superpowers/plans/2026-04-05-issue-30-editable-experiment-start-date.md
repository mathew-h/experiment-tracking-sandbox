# Issue #30 — Editable Experiment Start Date Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the experiment start date (`Experiment.date`) inline-editable on the detail page and reactor dashboard modal, with audit logging and correct elapsed-day calculations.

**Architecture:** The `Experiment.date` field and `PATCH /api/experiments/{id}` endpoint already exist and work end-to-end — no migration or schema change needed. The backend needs two targeted changes: (1) write a `ModificationsLog` entry when `date` is patched, and (2) fix the dashboard router to use `Experiment.date` (with `created_at` fallback) instead of `created_at` for `started_at` and `days_running`. The frontend adds a click-to-edit date input in two places: the ExperimentDetail header and the ReactorDetailModal.

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend), React 18/TypeScript/React Query/Tailwind (frontend), pytest (backend tests), PostgreSQL

---

## Codebase Facts (Resolved Clarifications)

| Question | Answer |
|----------|--------|
| Date fields on Experiment | `date: DateTime(timezone=True)` nullable; `created_at: DateTime` not-null auto-set; no `start_date` or `run_date` |
| PATCH handles `date`? | Yes — `ExperimentUpdate.date: Optional[datetime]` exists; handler applies it via `setattr` |
| ModificationsLog for date? | **Missing** — handler only logs `experiment_id` renames; all other field patches are unlogged |
| Dashboard `started_at` maps to | `Experiment.created_at` (wrong!) — must be changed to `Experiment.date ∥ Experiment.created_at` |
| `v_experiments` view | Does **not** exist — no action needed |
| Frontend detail date display | `ExperimentDetail/index.tsx:151` — plain string interpolation in metadata `<p>` |
| Dashboard modal date display | `ReactorGrid.tsx:299-306` — read-only `<dd>` element |

---

## File Map

| File | Change |
|------|--------|
| `backend/api/routers/experiments.py` | Add ModificationsLog entry when `date` is patched (lines 506–561) |
| `backend/api/routers/dashboard.py` | Select `Experiment.date`; use `date ∥ created_at` for `started_at` + `days_running` in reactor cards and Gantt (lines 115–211) |
| `tests/api/test_experiments.py` | Add 3 tests: patch date success, patch date invalid, patch date logs modification |
| `tests/api/test_dashboard.py` | Add 1 test: dashboard `started_at` reflects patched date |
| `frontend/src/pages/ExperimentDetail/index.tsx` | Add `editingDate`/`dateDraft` state, `dateMutation`, `confirmDate()`, inline `<input type="date">` replacing plain text at line 151 |
| `frontend/src/pages/ReactorGrid.tsx` | Add date-edit state + mutation to `ReactorDetailModal`; replace read-only "Started" row with editable version |

---

## Task 1: Backend tests — PATCH date and ModificationsLog

**Files:**
- Modify: `tests/api/test_experiments.py`

- [ ] **Step 1: Append the three failing tests**

Add to the bottom of `tests/api/test_experiments.py`:

```python
def test_patch_experiment_date(client, db_session):
    """PATCH with a valid ISO date string updates the experiment's date field."""
    _make_experiment(db_session, "DATE_PATCH_001", 9020)
    resp = client.patch(
        "/api/experiments/DATE_PATCH_001",
        json={"date": "2026-03-15T00:00:00"},
    )
    assert resp.status_code == 200
    assert resp.json()["date"] is not None
    assert "2026-03-15" in resp.json()["date"]


def test_patch_experiment_date_invalid(client, db_session):
    """PATCH with a non-datetime string returns 422."""
    _make_experiment(db_session, "DATE_INVALID_001", 9021)
    resp = client.patch(
        "/api/experiments/DATE_INVALID_001",
        json={"date": "not-a-date"},
    )
    assert resp.status_code == 422


def test_patch_date_logs_modification(client, db_session):
    """Patching date writes a ModificationsLog row with old and new values."""
    from database.models.experiments import ModificationsLog
    exp = _make_experiment(db_session, "DATE_LOG_001", 9022)
    old_date = "2026-01-01T00:00:00"
    new_date = "2026-03-15T00:00:00"

    # Set an initial date so old_values is non-null
    client.patch(f"/api/experiments/{exp.experiment_id}", json={"date": old_date})
    db_session.expire_all()

    client.patch(f"/api/experiments/{exp.experiment_id}", json={"date": new_date})
    db_session.expire_all()

    log_entry = (
        db_session.query(ModificationsLog)
        .filter(
            ModificationsLog.experiment_id == "DATE_LOG_001",
            ModificationsLog.modified_table == "experiments",
        )
        .order_by(ModificationsLog.id.desc())
        .first()
    )
    assert log_entry is not None
    assert log_entry.modification_type == "update"
    assert log_entry.new_values is not None
    assert "date" in log_entry.new_values
    assert "2026-03-15" in log_entry.new_values["date"]
```

- [ ] **Step 2: Run the tests to verify they fail**

```
pytest tests/api/test_experiments.py::test_patch_experiment_date tests/api/test_experiments.py::test_patch_experiment_date_invalid tests/api/test_experiments.py::test_patch_date_logs_modification -v
```

Expected: `test_patch_experiment_date` PASSES (field already works), `test_patch_experiment_date_invalid` PASSES (Pydantic already validates), `test_patch_date_logs_modification` FAILS with `AssertionError: assert log_entry is not None`

---

## Task 2: Backend implementation — ModificationsLog for date patch

**Files:**
- Modify: `backend/api/routers/experiments.py:506–561`

- [ ] **Step 1: Read the existing PATCH handler**

Open `backend/api/routers/experiments.py` at line 490 and confirm the handler body matches what follows before editing.

- [ ] **Step 2: Add old-date capture and ModificationsLog write**

Replace the block starting at line 506 (the `data = payload...` lines through the closing `db.commit()`) with:

```python
    data = payload.model_dump(exclude_unset=True)
    new_id = data.pop("experiment_id", None)
    old_date = exp.date  # capture before mutation

    for field, value in data.items():
        setattr(exp, field, value)

    if "date" in data:
        db.add(ModificationsLog(
            experiment_id=exp.experiment_id if new_id is None else new_id,
            experiment_fk=exp.id,
            modified_by=current_user.uid,
            modification_type="update",
            modified_table="experiments",
            old_values={"date": old_date.isoformat() if old_date else None},
            new_values={"date": data["date"].isoformat() if data["date"] else None},
        ))
        log.info("experiment_date_updated", experiment_id=exp.experiment_id, user=current_user.uid)
```

The existing `if new_id is not None:` rename block and `db.commit()` / `db.refresh(exp)` / `return` lines remain unchanged after this block.

- [ ] **Step 3: Run the failing test to confirm it now passes**

```
pytest tests/api/test_experiments.py::test_patch_date_logs_modification -v
```

Expected: PASS

- [ ] **Step 4: Run the full experiment test suite**

```
pytest tests/api/test_experiments.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/experiments.py tests/api/test_experiments.py
git commit -m "[#30] log ModificationsLog entry on experiment date patch

- Tests added: yes
- Docs updated: no"
```

---

## Task 3: Backend test — dashboard started_at reflects patched date

**Files:**
- Modify: `tests/api/test_dashboard.py`

- [ ] **Step 1: Add the failing integration test**

Add to `tests/api/test_dashboard.py`:

```python
def test_dashboard_started_at_reflects_patched_date(client, db_session):
    """After PATCHing Experiment.date, dashboard reactor card started_at reflects the new value."""
    from database.models.experiments import Experiment, ExperimentalConditions
    from database.models.enums import ExperimentStatus, ExperimentType
    import datetime

    # Create experiment with reactor_number so it appears on dashboard
    exp = Experiment(
        experiment_id="DASH_DATE_001",
        experiment_number=7001,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(exp)
    db_session.flush()

    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="DASH_DATE_001",
        reactor_number=99,
        experiment_type=ExperimentType.Serum,
    )
    db_session.add(cond)
    db_session.commit()

    # Patch experiment date
    new_date = "2026-01-10T00:00:00"
    patch_resp = client.patch(
        "/api/experiments/DASH_DATE_001",
        json={"date": new_date},
    )
    assert patch_resp.status_code == 200

    # Dashboard should reflect Experiment.date in started_at, not created_at
    dash_resp = client.get("/api/dashboard/")
    assert dash_resp.status_code == 200
    reactors = dash_resp.json()["reactors"]
    card = next((r for r in reactors if r["experiment_id"] == "DASH_DATE_001"), None)
    assert card is not None
    assert card["started_at"] is not None
    assert "2026-01-10" in card["started_at"]
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/api/test_dashboard.py::test_dashboard_started_at_reflects_patched_date -v
```

Expected: FAIL — `started_at` will contain the `created_at` timestamp, not `2026-01-10`

---

## Task 4: Backend implementation — dashboard uses Experiment.date

**Files:**
- Modify: `backend/api/routers/dashboard.py:115–211`

- [ ] **Step 1: Add Experiment.date to the reactor cards query select**

In the `select(...)` block starting at line 115, add `Experiment.date` as the 8th item (after `Experiment.created_at`):

```python
    reactor_rows = db.execute(
        select(
            ExperimentalConditions.reactor_number,
            Experiment.id,
            Experiment.experiment_id,
            Experiment.status,
            Experiment.sample_id,
            Experiment.researcher,
            Experiment.created_at,
            Experiment.date,                          # ← add this line
            ExperimentalConditions.temperature_c,
            ExperimentalConditions.experiment_type,
            note_sq.c.note_text.label("description"),
        )
```

- [ ] **Step 2: Use date-or-created_at for days_running and started_at in reactor cards**

In the reactor card build loop (around line 150–162), replace:

```python
        days = (now - row.created_at).days if row.created_at else None
```

with:

```python
        start = row.date or row.created_at
        days = (now - start).days if start else None
```

And replace:

```python
            started_at=row.created_at,
```

with:

```python
            started_at=start,
```

- [ ] **Step 3: Add Experiment.date to the Gantt query select**

In the Gantt `select(...)` block starting around line 171, add `Experiment.date` after `Experiment.created_at`:

```python
    gantt_rows = db.execute(
        select(
            Experiment.id,
            Experiment.experiment_id,
            Experiment.status,
            Experiment.sample_id,
            Experiment.researcher,
            Experiment.created_at,
            Experiment.date,          # ← add this line
            Experiment.updated_at,
            ExperimentalConditions.experiment_type,
        )
```

- [ ] **Step 4: Use date-or-created_at for Gantt started_at and days_running**

In the Gantt build loop (around line 196–208), replace:

```python
        days = None
        if row.created_at:
            end = ended_at or now
            days = (end - row.created_at).days
        timeline.append(GanttEntry(
            ...
            started_at=row.created_at,
```

with:

```python
        start = row.date or row.created_at
        days = None
        if start:
            end = ended_at or now
            days = (end - start).days
        timeline.append(GanttEntry(
            ...
            started_at=start,
```

- [ ] **Step 5: Run the failing test to confirm it passes**

```
pytest tests/api/test_dashboard.py::test_dashboard_started_at_reflects_patched_date -v
```

Expected: PASS

- [ ] **Step 6: Run the full dashboard test suite**

```
pytest tests/api/test_dashboard.py -v
```

Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add backend/api/routers/dashboard.py tests/api/test_dashboard.py
git commit -m "[#30] use Experiment.date (with created_at fallback) for dashboard started_at

- Tests added: yes
- Docs updated: no"
```

---

## Task 5: Frontend — inline date edit on ExperimentDetail page

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/index.tsx`

**Context:** The date is currently displayed on line 151 as a concatenated string inside a `<p>` tag. No edit affordance exists. The ID rename pattern (lines 24–75) is the model to follow.

- [ ] **Step 1: Add editingDate state, dateDraft state, and dateMutation**

After the existing `renameMutation` block (around line 61), add:

```tsx
  const [editingDate, setEditingDate] = useState(false)
  const [dateDraft, setDateDraft] = useState('')

  const dateMutation = useMutation({
    mutationFn: (newDate: string) => experimentsApi.patch(id!, { date: newDate }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiment', id] })
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
      success('Start date updated')
      setEditingDate(false)
    },
    onError: () => {
      toastError('Update failed', 'Could not save start date')
      setEditingDate(false)
    },
  })

  function startDateEdit() {
    setDateDraft(experiment!.date?.slice(0, 10) ?? '')
    setEditingDate(true)
  }

  function confirmDate() {
    const trimmed = dateDraft.trim()
    if (trimmed) {
      dateMutation.mutate(`${trimmed}T00:00:00`)
    } else {
      setEditingDate(false)
    }
  }
```

- [ ] **Step 2: Replace the date display in the metadata paragraph**

The metadata `<p>` at line 148–154 currently includes:
```tsx
{experiment.date && ` · ${experiment.date.slice(0, 10)}`}
```

Replace that entire line with an inline editable segment. The full updated `<p>` block:

```tsx
        <p className="text-xs text-ink-muted mt-0.5">
          #{experiment.experiment_number}
          {experiment.researcher && ` · ${experiment.researcher}`}
          {editingDate ? (
            <>
              {' · '}
              <input
                type="date"
                value={dateDraft}
                onChange={(e) => setDateDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') confirmDate()
                  if (e.key === 'Escape') setEditingDate(false)
                }}
                className="font-mono-data border border-surface-border rounded px-1 bg-surface-raised text-ink-primary"
                // eslint-disable-next-line jsx-a11y/no-autofocus
                autoFocus
              />
              <button
                onClick={confirmDate}
                disabled={dateMutation.isPending}
                className="ml-1 text-status-success hover:opacity-80"
                title="Save date"
              >
                ✓
              </button>
              <button
                onClick={() => setEditingDate(false)}
                className="ml-1 text-ink-muted hover:text-ink-secondary"
                title="Cancel"
              >
                ✗
              </button>
            </>
          ) : (
            <button
              onClick={startDateEdit}
              className="text-ink-muted hover:text-ink-secondary transition-colors"
              title="Edit start date"
            >
              {experiment.date
                ? ` · ${experiment.date.slice(0, 10)}`
                : ' · Set start date'}
            </button>
          )}
          {experiment.sample_id && ` · Sample: ${experiment.sample_id}`}
          {conditions?.reactor_number != null && ` · Reactor ${conditions.reactor_number}`}
        </p>
```

- [ ] **Step 3: Manually verify in browser**

With the dev server running on `http://localhost:5173`:
1. Navigate to any experiment detail page
2. Click the date field (or "Set start date" if unset) — a `<input type="date">` should appear
3. Set a date, press Enter or click ✓ — toast "Start date updated" should appear and the header should reflect the new date
4. Click the date field again, press Escape — should revert with no API call
5. Open DevTools > Network — confirm a single `PATCH /api/experiments/{id}` request with `{"date": "..."}` body

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/index.tsx
git commit -m "[#30] add inline date edit to ExperimentDetail header

- Tests added: no
- Docs updated: no"
```

---

## Task 6: Frontend — inline date edit in ReactorDetailModal

**Files:**
- Modify: `frontend/src/pages/ReactorGrid.tsx:232–361`

**Context:** `ReactorDetailModal` is a function component starting at line 232. It currently only uses `useNavigate`. The "Started" row at lines 299–306 is read-only.

- [ ] **Step 1: Extend ReactorDetailModal with date-edit state, queryClient, and useToast**

Replace the current component signature and hook line at lines 232–239:

```tsx
function ReactorDetailModal({
  card,
  onClose,
}: {
  card: ReactorCardData
  onClose: () => void
}) {
  const navigate = useNavigate()
```

with:

```tsx
function ReactorDetailModal({
  card,
  onClose,
}: {
  card: ReactorCardData
  onClose: () => void
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()
  const [editingDate, setEditingDate] = useState(false)
  const [dateDraft, setDateDraft] = useState('')

  const dateMutation = useMutation({
    mutationFn: (newDate: string) =>
      experimentsApi.patch(card.experiment_id!, { date: newDate }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      success('Start date updated')
      setEditingDate(false)
    },
    onError: () => {
      toastError('Update failed', 'Could not save start date')
      setEditingDate(false)
    },
  })

  function startDateEdit() {
    setDateDraft(card.started_at?.slice(0, 10) ?? '')
    setEditingDate(true)
  }

  function confirmDate() {
    const trimmed = dateDraft.trim()
    if (trimmed) {
      dateMutation.mutate(`${trimmed}T00:00:00`)
    } else {
      setEditingDate(false)
    }
  }
```

- [ ] **Step 2: Add useToast to the UI import**

At line 4 in `ReactorGrid.tsx`:

```tsx
import { Card } from '@/components/ui'
```

change to:

```tsx
import { Card, useToast } from '@/components/ui'
```

- [ ] **Step 3: Replace the read-only "Started" row with an editable one**

Replace lines 299–306:

```tsx
          {card.started_at && (
            <div className="flex gap-2">
              <dt className="text-ink-muted w-28 shrink-0">Started</dt>
              <dd className="font-mono-data text-ink-secondary">
                {card.started_at.slice(0, 10)}
              </dd>
            </div>
          )}
```

with:

```tsx
          <div className="flex gap-2 items-center">
            <dt className="text-ink-muted w-28 shrink-0">Started</dt>
            <dd className="font-mono-data text-ink-secondary flex items-center gap-1">
              {editingDate ? (
                <>
                  <input
                    type="date"
                    value={dateDraft}
                    onChange={(e) => setDateDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') confirmDate()
                      if (e.key === 'Escape') setEditingDate(false)
                    }}
                    className="font-mono-data border border-surface-border rounded px-1 bg-surface-raised text-ink-primary text-sm"
                    // eslint-disable-next-line jsx-a11y/no-autofocus
                    autoFocus
                  />
                  <button
                    onClick={confirmDate}
                    disabled={dateMutation.isPending}
                    className="text-status-success hover:opacity-80 text-sm"
                    title="Save date"
                  >
                    ✓
                  </button>
                  <button
                    onClick={() => setEditingDate(false)}
                    className="text-ink-muted hover:text-ink-secondary text-sm"
                    title="Cancel"
                  >
                    ✗
                  </button>
                </>
              ) : (
                <>
                  <span>{card.started_at ? card.started_at.slice(0, 10) : '—'}</span>
                  <button
                    onClick={startDateEdit}
                    className="text-ink-muted hover:text-ink-secondary transition-colors text-sm leading-none"
                    title="Edit start date"
                    aria-label="Edit start date"
                  >
                    ✎
                  </button>
                </>
              )}
            </dd>
          </div>
```

- [ ] **Step 4: Manually verify in browser**

With the dev server running:
1. Navigate to the Dashboard (`/dashboard`)
2. Click any occupied reactor card — the modal opens
3. Next to "Started", click the ✎ pencil icon — a date input should appear
4. Set a new date, press Enter or click ✓ — toast "Start date updated" appears; after modal re-opens `started_at` shows the new date
5. Test cancel: click ✎, change date, press Escape — revert, no API call

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ReactorGrid.tsx
git commit -m "[#30] add inline date edit to ReactorDetailModal

- Tests added: no
- Docs updated: no"
```

---

## Task 7: Run full backend test suite and close

- [ ] **Step 1: Run all API tests**

```
pytest tests/api/ -v
```

Expected: all PASS

- [ ] **Step 2: Verify acceptance criteria checklist**

| Criterion | Verified by |
|-----------|-------------|
| Detail header renders date as click-to-edit | Manual (Task 5 Step 3) |
| Dashboard modal renders date as click-to-edit | Manual (Task 6 Step 4) |
| Confirming edit calls PATCH, updates display without reload | Manual + network tab |
| ModificationsLog entry written with old/new date | `test_patch_date_logs_modification` |
| Gantt / elapsed-day counter reflects updated date | `test_dashboard_started_at_reflects_patched_date` |
| `created_at` not overwritten | `test_patch_experiment_date` — response still has `created_at` unchanged |
| Cancelling reverts, no API call | Manual |
| `v_experiments` view — N/A | View does not exist; `Experiment.date` is the canonical column |

- [ ] **Step 3: Commit final notes and close issue**

```bash
git add .
git commit -m "[#30] editable experiment start date — implementation complete

- Tests added: yes
- Docs updated: no"
```

---

## Self-Review

**Spec coverage check:**
- Inline edit on detail page header ✓ (Task 5)
- Inline edit on dashboard modal ✓ (Task 6)
- PATCH call on confirm ✓ (already works via `experimentsApi.patch`)
- Query cache invalidation on success ✓ (Tasks 5 + 6)
- Toast on success ✓ (Tasks 5 + 6)
- ModificationsLog entry ✓ (Task 2)
- Gantt / elapsed days reflect updated date ✓ (Task 4)
- `created_at` not affected ✓ (no model change)
- Cancel reverts without API call ✓ (Tasks 5 + 6 — setEditingDate(false) without mutate)
- `v_experiments` audit — ✓ (view does not exist; noted)

**Placeholder scan:** No TBD/TODO, all code shown in full. ✓

**Type consistency:**
- `dateMutation.mutate(string)` — mutationFn receives `string`, sends `{ date: string }` via `experimentsApi.patch` — consistent ✓
- `card.started_at` is `string | null` in `ReactorCardData` — `.slice(0, 10)` is safe after null guard ✓
- `experiment.date` is `string | null` in `ExperimentDetail` — `.slice(0, 10)` guarded ✓
