# Editable Experiment ID — New + Existing Experiments

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to set a custom experiment ID in the New Experiment form (Step 1) and rename an existing experiment's ID from the detail page header, with real-time availability feedback and a new `/exists` endpoint.

**Architecture:** Three independent layers — backend schema + endpoints, a shared frontend validation hook, then two UI sites (Step 1 form + Detail header). Backend first (TDD), then frontend. No schema migration required; `experiment_id` is already an untyped `String` column.

**Tech Stack:** FastAPI / SQLAlchemy / PostgreSQL, React 18, React Query (`@tanstack/react-query`), TypeScript, Tailwind.

---

## File Map

| File | Change |
|------|--------|
| `backend/api/schemas/experiments.py` | Add `experiment_id` field to `ExperimentUpdate` |
| `backend/api/routers/experiments.py` | Add `GET /{experiment_id}/exists`; update `update_experiment` to handle rename |
| `tests/api/test_experiments.py` | New test cases for `/exists` and rename PATCH |
| `frontend/src/api/experiments.ts` | Add `checkExists`; expand `patch` signature |
| `frontend/src/hooks/useExperimentIdValidation.ts` | **Create** debounced ID availability hook |
| `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx` | Remove `readOnly`; wire validation hook |
| `frontend/src/pages/ExperimentDetail/index.tsx` | Add inline-edit pencil + rename mutation |
| `docs/api/API_REFERENCE.md` | Document new endpoint + updated PATCH schema |

---

## Task 1 — Backend schema: add `experiment_id` to `ExperimentUpdate`

**Files:**
- Modify: `backend/api/schemas/experiments.py:19-24`
- Test: `tests/api/test_experiments.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_experiments.py — add after existing patch test

def test_patch_rename_success(client, db_session):
    _make_experiment(db_session, "RENAME_SRC_001", 9010)
    resp = client.patch("/api/experiments/RENAME_SRC_001", json={"experiment_id": "RENAME_DST_001"})
    assert resp.status_code == 200
    assert resp.json()["experiment_id"] == "RENAME_DST_001"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd C:\Users\MathewHearl\Documents\0x_Software\database_sandbox\experiment_tracking_sandbox
.venv/Scripts/pytest tests/api/test_experiments.py::test_patch_rename_success -v
```

Expected: FAIL — the PATCH returns 200 but `experiment_id` in the response is still `RENAME_SRC_001` because the field is not in the schema.

- [ ] **Step 3: Add `experiment_id` to `ExperimentUpdate`**

In `backend/api/schemas/experiments.py`, replace the `ExperimentUpdate` class (lines 19-24):

```python
class ExperimentUpdate(BaseModel):
    experiment_id: Optional[str] = Field(None, min_length=1, max_length=100)
    sample_id: Optional[str] = None
    researcher: Optional[str] = None
    date: Optional[datetime] = None
    status: Optional[ExperimentStatus] = None
```

Add `Field` to the import at line 4:
```python
from pydantic import BaseModel, ConfigDict, Field
```

- [ ] **Step 4: Run test — still fails (handler doesn't rename yet)**

```bash
.venv/Scripts/pytest tests/api/test_experiments.py::test_patch_rename_success -v
```

Expected: FAIL with `experiment_id` still `RENAME_SRC_001`. Good — the schema change alone isn't enough; Task 2 fixes the handler.

- [ ] **Step 5: Commit**

```bash
git add backend/api/schemas/experiments.py tests/api/test_experiments.py
git commit -m "[#27] add experiment_id to ExperimentUpdate schema

- Tests added: yes
- Docs updated: no"
```

---

## Task 2 — Backend handler: rename logic + `/exists` endpoint

**Files:**
- Modify: `backend/api/routers/experiments.py`
- Test: `tests/api/test_experiments.py`

- [ ] **Step 1: Write all failing tests first**

Append to `tests/api/test_experiments.py`:

```python
# --- #27: /exists endpoint ---

def test_exists_returns_true_for_known_id(client, db_session):
    _make_experiment(db_session, "EXISTS_001", 9020)
    resp = client.get("/api/experiments/EXISTS_001/exists")
    assert resp.status_code == 200
    assert resp.json() == {"exists": True}


def test_exists_returns_false_for_unknown_id(client):
    resp = client.get("/api/experiments/DOES_NOT_EXIST_XYZ/exists")
    assert resp.status_code == 200
    assert resp.json() == {"exists": False}


# --- #27: rename via PATCH ---

def test_patch_rename_conflict(client, db_session):
    _make_experiment(db_session, "CONFLICT_SRC_001", 9030)
    _make_experiment(db_session, "CONFLICT_DST_001", 9031)
    resp = client.patch(
        "/api/experiments/CONFLICT_SRC_001",
        json={"experiment_id": "CONFLICT_DST_001"},
    )
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


def test_patch_rename_same_id_is_noop(client, db_session):
    _make_experiment(db_session, "SAME_ID_001", 9032)
    resp = client.patch("/api/experiments/SAME_ID_001", json={"experiment_id": "SAME_ID_001"})
    assert resp.status_code == 200
    assert resp.json()["experiment_id"] == "SAME_ID_001"


def test_patch_rename_logs_modification(client, db_session):
    from database.models.experiments import ModificationsLog
    from sqlalchemy import select as sa_select
    _make_experiment(db_session, "LOG_SRC_001", 9033)
    client.patch("/api/experiments/LOG_SRC_001", json={"experiment_id": "LOG_DST_001"})
    log = db_session.execute(
        sa_select(ModificationsLog)
        .where(ModificationsLog.modified_table == "experiments")
        .order_by(ModificationsLog.id.desc())
    ).scalar_one_or_none()
    assert log is not None
    assert log.old_values == {"experiment_id": "LOG_SRC_001"}
    assert log.new_values == {"experiment_id": "LOG_DST_001"}


def test_patch_rename_strips_whitespace(client, db_session):
    _make_experiment(db_session, "STRIP_SRC_001", 9034)
    resp = client.patch("/api/experiments/STRIP_SRC_001", json={"experiment_id": "  STRIP_DST_001  "})
    assert resp.status_code == 200
    assert resp.json()["experiment_id"] == "STRIP_DST_001"
```

- [ ] **Step 2: Run all new tests to confirm they all fail**

```bash
.venv/Scripts/pytest tests/api/test_experiments.py -k "exists or rename or conflict or noop or logs_mod or strips" -v
```

Expected: all FAIL.

- [ ] **Step 3: Add the `/exists` endpoint to the router**

In `backend/api/routers/experiments.py`, add this route **before** the `GET /{experiment_id}` route (currently at line 400). Place it right after the `PATCH /{experiment_id}/background-ammonium` handler (line 397):

```python
@router.get("/{experiment_id}/exists")
def check_experiment_id_exists(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> dict:
    """Return whether an experiment_id string is already in use."""
    exists = db.execute(
        select(Experiment.id).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    return {"exists": exists is not None}
```

- [ ] **Step 4: Update `update_experiment` to handle rename**

Replace the entire `update_experiment` function (lines 475-492) with:

```python
@router.patch("/{experiment_id}", response_model=ExperimentResponse)
def update_experiment(
    experiment_id: str,
    payload: ExperimentUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentResponse:
    """Update mutable fields on an experiment. If experiment_id is provided and differs
    from the path param, treats it as a rename: checks uniqueness, updates
    ExperimentalConditions.experiment_id, and writes a ModificationsLog entry."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    data = payload.model_dump(exclude_unset=True)
    new_id = data.pop("experiment_id", None)

    for field, value in data.items():
        setattr(exp, field, value)

    if new_id is not None:
        new_id = new_id.strip()
        if new_id != experiment_id:
            conflict = db.execute(
                select(Experiment.id).where(Experiment.experiment_id == new_id)
            ).scalar_one_or_none()
            if conflict is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Experiment ID '{new_id}' already exists",
                )
            exp.experiment_id = new_id
            # Keep denormalized string in conditions in sync so additives endpoints work
            cond = db.execute(
                select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
            ).scalar_one_or_none()
            if cond is not None:
                cond.experiment_id = new_id
            db.add(ModificationsLog(
                experiment_id=new_id,
                experiment_fk=exp.id,
                modified_by=current_user.uid,
                modification_type="update",
                modified_table="experiments",
                old_values={"experiment_id": experiment_id},
                new_values={"experiment_id": new_id},
            ))

    db.commit()
    db.refresh(exp)
    return ExperimentResponse.model_validate(exp)
```

- [ ] **Step 5: Run all new tests**

```bash
.venv/Scripts/pytest tests/api/test_experiments.py -v
```

Expected: all PASS (including the previously written `test_patch_rename_success`).

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/experiments.py tests/api/test_experiments.py
git commit -m "[#27] add /exists endpoint and rename logic to PATCH

- Tests added: yes
- Docs updated: no"
```

---

## Task 3 — Frontend API: `checkExists` + expand `patch` signature

**Files:**
- Modify: `frontend/src/api/experiments.ts`

No new tests for this task — it's a type-level change that the TypeScript compiler validates.

- [ ] **Step 1: Add `checkExists` to `experimentsApi` and expand `patch` payload type**

In `frontend/src/api/experiments.ts`, make two changes:

1. Update the `patch` function signature (line 106-108):

```typescript
  patch: (
    experimentId: string,
    payload: {
      status?: string
      researcher?: string
      date?: string
      experiment_id?: string
    },
  ) =>
    apiClient
      .patch<ExperimentDetail>(`/experiments/${experimentId}`, payload)
      .then((r) => r.data),
```

2. Add `checkExists` after the `nextId` function (after line 113):

```typescript
  checkExists: (experimentId: string) =>
    apiClient
      .get<{ exists: boolean }>(`/experiments/${encodeURIComponent(experimentId)}/exists`)
      .then((r) => r.data),
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend
npx tsc --noEmit
```

Expected: exit 0, no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/experiments.ts
git commit -m "[#27] expand experiments API: checkExists + patch experiment_id

- Tests added: no
- Docs updated: no"
```

---

## Task 4 — Frontend: `useExperimentIdValidation` hook

**Files:**
- Create: `frontend/src/hooks/useExperimentIdValidation.ts`

- [ ] **Step 1: Create the hook**

```typescript
// frontend/src/hooks/useExperimentIdValidation.ts
import { useState, useEffect } from 'react'
import { experimentsApi } from '@/api/experiments'

export type IdValidationStatus = 'idle' | 'checking' | 'available' | 'taken' | 'error'

export interface IdValidationState {
  status: IdValidationStatus
  message: string
}

/**
 * Debounced hook that checks whether an experiment ID is available via
 * GET /api/experiments/{id}/exists.
 *
 * @param value       The current input value to validate.
 * @param currentId   The existing ID on the record being edited. When value
 *                    equals currentId the hook returns 'available' immediately
 *                    so the "Save" button stays enabled without an API call.
 */
export function useExperimentIdValidation(
  value: string,
  currentId?: string,
): IdValidationState {
  const [state, setState] = useState<IdValidationState>({ status: 'idle', message: '' })

  useEffect(() => {
    const trimmed = value.trim()

    if (!trimmed) {
      setState({ status: 'idle', message: '' })
      return
    }

    if (currentId !== undefined && trimmed === currentId) {
      setState({ status: 'available', message: 'Current ID' })
      return
    }

    setState({ status: 'checking', message: '' })

    const timer = setTimeout(async () => {
      try {
        const { exists } = await experimentsApi.checkExists(trimmed)
        setState(
          exists
            ? { status: 'taken', message: `'${trimmed}' is already in use` }
            : { status: 'available', message: 'Available' },
        )
      } catch {
        setState({ status: 'error', message: 'Could not validate ID' })
      }
    }, 300)

    return () => clearTimeout(timer)
  }, [value, currentId])

  return state
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend
npx tsc --noEmit
```

Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useExperimentIdValidation.ts
git commit -m "[#27] add useExperimentIdValidation hook

- Tests added: no
- Docs updated: no"
```

---

## Task 5 — Frontend: Step 1 editable experiment ID

**Files:**
- Modify: `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx`

- [ ] **Step 1: Rewrite `Step1BasicInfo.tsx`**

Replace the entire file content:

```tsx
import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { Input, Select, Button, SampleSelector } from '@/components/ui'
import { useExperimentIdValidation } from '@/hooks/useExperimentIdValidation'
import type { ExperimentType } from './fieldVisibility'

export interface Step1Data {
  experimentType: ExperimentType | ''
  experimentId: string
  sampleId: string
  date: string
  status: string
  note: string
}

interface Props {
  data: Step1Data
  onChange: (patch: Partial<Step1Data>) => void
  onNext: () => void
}

const TYPE_OPTIONS = [
  { value: 'Serum', label: 'Serum' },
  { value: 'HPHT', label: 'HPHT' },
  { value: 'Autoclave', label: 'Autoclave' },
  { value: 'Core Flood', label: 'Core Flood' },
]
const STATUS_OPTIONS = [
  { value: 'ONGOING', label: 'Ongoing' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'CANCELLED', label: 'Cancelled' },
]

/** Step 1 of new experiment wizard: experiment ID, type, researcher, sample, and notes. */
export function Step1BasicInfo({ data, onChange, onNext }: Props) {
  const { data: nextIdData, isFetching: loadingId } = useQuery({
    queryKey: ['next-id', data.experimentType],
    queryFn: () => experimentsApi.nextId(data.experimentType),
    enabled: Boolean(data.experimentType),
  })

  useEffect(() => {
    if (nextIdData?.next_id) onChange({ experimentId: nextIdData.next_id })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nextIdData])

  const idValidation = useExperimentIdValidation(data.experimentId)

  const idRightElement =
    idValidation.status === 'checking' ? (
      <span className="text-xs text-ink-muted animate-pulse">…</span>
    ) : idValidation.status === 'available' ? (
      <span className="text-xs text-status-success">✓</span>
    ) : null

  const canProceed =
    Boolean(data.experimentType) &&
    Boolean(data.experimentId.trim()) &&
    idValidation.status !== 'taken' &&
    idValidation.status !== 'checking'

  return (
    <div className="space-y-4">
      <Select
        label="Experiment Type *"
        options={TYPE_OPTIONS}
        placeholder="Select type…"
        value={data.experimentType}
        onChange={(e) =>
          onChange({ experimentType: e.target.value as ExperimentType, experimentId: '' })
        }
      />
      <Input
        label="Experiment ID *"
        value={loadingId ? '' : data.experimentId}
        placeholder={loadingId ? 'Loading…' : undefined}
        onChange={(e) => onChange({ experimentId: e.target.value })}
        error={idValidation.status === 'taken' ? idValidation.message : undefined}
        hint={
          idValidation.status !== 'taken'
            ? 'Auto-generated. Edit to use a custom ID (e.g., HPHT_100-2, HPHT_100_Desorption).'
            : undefined
        }
        rightElement={idRightElement}
        disabled={loadingId}
      />
      <SampleSelector value={data.sampleId} onChange={(id) => onChange({ sampleId: id })} />
      <div className="grid grid-cols-2 gap-3">
        <Input
          label="Date"
          type="date"
          value={data.date}
          onChange={(e) => onChange({ date: e.target.value })}
        />
        <Select
          label="Status"
          options={STATUS_OPTIONS}
          value={data.status}
          onChange={(e) => onChange({ status: e.target.value })}
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-ink-secondary mb-1">
          Experiment Description (optional)
        </label>
        <textarea
          className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary placeholder-ink-muted focus:outline-none focus:ring-1 focus:ring-brand-red/50 resize-none"
          rows={3}
          placeholder="Describe the experiment conditions…"
          value={data.note}
          onChange={(e) => onChange({ note: e.target.value })}
        />
      </div>
      <div className="flex justify-end pt-2">
        <Button variant="primary" disabled={!canProceed} onClick={onNext}>
          Next: Conditions →
        </Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend
npx tsc --noEmit
```

Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/NewExperiment/Step1BasicInfo.tsx
git commit -m "[#27] make experiment ID editable in Step 1 with live validation

- Tests added: no
- Docs updated: no"
```

---

## Task 6 — Frontend: Experiment Detail header inline rename

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/index.tsx`

- [ ] **Step 1: Rewrite `ExperimentDetail/index.tsx`**

Replace the entire file:

```tsx
import { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { conditionsApi } from '@/api/conditions'
import { StatusBadge, Button, Input, PageSpinner, useToast } from '@/components/ui'
import { useExperimentIdValidation } from '@/hooks/useExperimentIdValidation'
import { ConditionsTab } from './ConditionsTab'
import { ResultsTab } from './ResultsTab'
import { NotesTab } from './NotesTab'
import { ModificationsTab } from './ModificationsTab'
import { AnalysisTab } from './AnalysisTab'

const TABS = ['Conditions', 'Results', 'Notes', 'Analysis', 'Entry Logs'] as const
type Tab = typeof TABS[number]

/** Full experiment detail page with tabbed navigation (Results, Conditions, Analysis, Notes, Modifications). */
export function ExperimentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()
  const [activeTab, setActiveTab] = useState<Tab>('Conditions')
  const [editingId, setEditingId] = useState(false)
  const [idDraft, setIdDraft] = useState('')

  const { data: experiment, isLoading, error } = useQuery({
    queryKey: ['experiment', id],
    queryFn: () => experimentsApi.get(id!),
    enabled: Boolean(id),
  })

  const { data: conditions } = useQuery({
    queryKey: ['conditions', id],
    queryFn: () => conditionsApi.getByExperiment(id!),
    enabled: Boolean(id),
    retry: false,
  })

  const renameValidation = useExperimentIdValidation(idDraft, experiment?.experiment_id)

  const renameMutation = useMutation({
    mutationFn: (newId: string) => experimentsApi.patch(id!, { experiment_id: newId }),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['experiment'] })
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
      success('Experiment renamed')
      setEditingId(false)
      navigate(`/experiments/${updated.experiment_id}`, { replace: true })
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      if (detail?.includes('already exists')) {
        toastError('ID conflict', detail)
      } else {
        toastError('Rename failed', String(err))
      }
      setEditingId(false)
    },
  })

  function startEdit() {
    setIdDraft(experiment!.experiment_id)
    setEditingId(true)
  }

  function confirmRename() {
    const trimmed = idDraft.trim()
    if (trimmed && trimmed !== experiment!.experiment_id) {
      renameMutation.mutate(trimmed)
    } else {
      setEditingId(false)
    }
  }

  if (isLoading) return <PageSpinner />
  if (error || !experiment) return <p className="text-red-400 text-sm p-6">Experiment not found</p>

  const idRightElement =
    renameValidation.status === 'checking' ? (
      <span className="text-xs text-ink-muted animate-pulse">…</span>
    ) : renameValidation.status === 'available' ? (
      <span className="text-xs text-status-success">✓</span>
    ) : null

  return (
    <div className="space-y-4">
      {/* Breadcrumb */}
      <div>
        <p className="text-xs text-ink-muted mb-1">
          <Link to="/experiments" className="hover:text-ink-secondary">Experiments</Link>
          <span className="mx-1.5">›</span>
          <span className="font-mono-data">{experiment.experiment_id}</span>
        </p>

        {editingId ? (
          <div className="flex items-center gap-2">
            <Input
              value={idDraft}
              onChange={(e) => setIdDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') confirmRename()
                if (e.key === 'Escape') setEditingId(false)
              }}
              error={renameValidation.status === 'taken' ? renameValidation.message : undefined}
              rightElement={idRightElement}
              className="font-mono-data"
              // eslint-disable-next-line jsx-a11y/no-autofocus
              autoFocus
            />
            <Button
              variant="primary"
              size="sm"
              disabled={
                renameValidation.status === 'taken' ||
                renameValidation.status === 'checking' ||
                !idDraft.trim()
              }
              onClick={confirmRename}
            >
              Save
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setEditingId(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-ink-primary font-mono-data">
              {experiment.experiment_id}
            </h1>
            <button
              onClick={startEdit}
              className="text-ink-muted hover:text-ink-secondary transition-colors text-sm leading-none"
              title="Rename experiment"
              aria-label="Rename experiment"
            >
              ✎
            </button>
            <StatusBadge status={experiment.status} />
            {conditions?.experiment_type && (
              <span className="text-xs text-ink-muted">{conditions.experiment_type}</span>
            )}
          </div>
        )}

        <p className="text-xs text-ink-muted mt-0.5">
          #{experiment.experiment_number}
          {experiment.researcher && ` · ${experiment.researcher}`}
          {experiment.date && ` · ${experiment.date.slice(0, 10)}`}
          {experiment.sample_id && ` · Sample: ${experiment.sample_id}`}
          {conditions?.reactor_number != null && ` · Reactor ${conditions.reactor_number}`}
        </p>
      </div>

      {/* Quick actions */}
      <div className="flex gap-2">
        <Button variant="ghost" size="sm" onClick={() => navigate('/experiments/new')}>
          + New Experiment
        </Button>
      </div>

      {/* Tab bar */}
      <div className="border-b border-surface-border flex gap-0">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm border-b-2 transition-colors ${
              activeTab === tab
                ? 'border-brand-red text-ink-primary'
                : 'border-transparent text-ink-muted hover:text-ink-secondary'
            }`}
          >
            {tab}
            {tab === 'Notes' && experiment.notes.length > 0 && (
              <span className="ml-1.5 text-[10px] bg-surface-raised rounded px-1">
                {experiment.notes.length}
              </span>
            )}
            {tab === 'Entry Logs' && experiment.modifications.length > 0 && (
              <span className="ml-1.5 text-[10px] bg-surface-raised rounded px-1">
                {experiment.modifications.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="bg-surface-card border border-surface-border rounded-lg overflow-hidden">
        {activeTab === 'Conditions' && (
          <ConditionsTab conditions={conditions ?? null} experimentId={id!} experimentFk={experiment.id} />
        )}
        {activeTab === 'Results' && <ResultsTab experimentId={id!} experimentFk={experiment.id} />}
        {activeTab === 'Notes' && (
          <NotesTab experimentId={id!} notes={experiment.notes} />
        )}
        {activeTab === 'Entry Logs' && (
          <ModificationsTab modifications={experiment.modifications} />
        )}
        {activeTab === 'Analysis' && <AnalysisTab experimentId={id!} />}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend
npx tsc --noEmit
```

Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/index.tsx
git commit -m "[#27] add inline rename to experiment detail header

- Tests added: no
- Docs updated: no"
```

---

## Task 7 — Docs: Update API reference

**Files:**
- Modify: `docs/api/API_REFERENCE.md`

- [ ] **Step 1: Find the experiments section of the API reference**

```bash
grep -n "experiment" docs/api/API_REFERENCE.md | head -30
```

- [ ] **Step 2: Add `/exists` endpoint documentation**

Find the block documenting `GET /api/experiments/{experiment_id}` and add the `/exists` entry directly before it:

```markdown
#### `GET /api/experiments/{experiment_id}/exists`

Check whether an experiment ID string is already in use.

**Auth:** Required (Firebase token)

**Path params:**
- `experiment_id` — the string to check

**Response `200`:**
```json
{ "exists": true }
```
or
```json
{ "exists": false }
```

**Usage:** Called by the frontend on a 300 ms debounce while the user types a custom ID, to show real-time availability feedback without submitting the form.
```

- [ ] **Step 3: Update the PATCH documentation to include `experiment_id`**

Find the `PATCH /api/experiments/{experiment_id}` section and update the request body to include:

```markdown
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `experiment_id` | string | No | Rename: must be unique; max 100 chars; whitespace stripped |
| `status` | string | No | `ONGOING` \| `COMPLETED` \| `CANCELLED` |
| `researcher` | string | No | |
| `date` | ISO datetime | No | |
| `sample_id` | string | No | |

**409 Conflict:** returned when `experiment_id` is provided and already belongs to another experiment.

**Side effects on rename:** `ExperimentalConditions.experiment_id` is updated to the new value; a `ModificationsLog` entry is written recording the old and new IDs.
```

- [ ] **Step 4: Commit**

```bash
git add docs/api/API_REFERENCE.md
git commit -m "[#27] document /exists endpoint and updated PATCH schema

- Tests added: no
- Docs updated: yes"
```

---

## Self-Review Against Spec

**Spec coverage check:**

| Requirement | Task |
|-------------|------|
| New experiment form: editable ID field | Task 5 |
| Auto-populated default from `next-id` retained | Task 5 — `useEffect` on `nextIdData` unchanged |
| Helper text under ID field | Task 5 — `hint` prop |
| Debounced validation on input | Task 4 — 300 ms `setTimeout` |
| Inline validation: green check / red warning | Tasks 5 & 6 — `rightElement` + `error` |
| 409 conflict handling on submit (existing safety net) | Already in `create_experiment` handler — no change needed |
| PATCH accepts `experiment_id` | Tasks 1 & 2 |
| Uniqueness check on rename | Task 2 |
| 409 on conflict | Task 2 |
| `ModificationsLog` entry on rename | Task 2 |
| `GET /exists` endpoint | Task 2 |
| Detail page: click to rename inline | Task 6 |
| On 409: show toast "already exists" | Task 6 |
| On success: redirect to new URL + invalidate cache | Task 6 |
| Validation: not empty | Tasks 4 & 5 (`disabled` when blank) |
| Validation: strip whitespace | Task 2 backend + Task 4 hook `.trim()` |
| Validation: unique | Tasks 2 & 4 |
| Validation: max 100 chars | Task 1 — `Field(max_length=100)` |
| No format validation | Hooks accept any non-empty string |
| API reference updated | Task 7 |

**Placeholder scan:** No TBDs, no "similar to above" references, no steps without code.

**Type consistency:** `useExperimentIdValidation` returns `IdValidationState.status` — used as `idValidation.status` in Tasks 5 and `renameValidation.status` in Task 6. `experimentsApi.checkExists` returns `{ exists: boolean }` — consumed in Task 4 hook as `const { exists } = await experimentsApi.checkExists(trimmed)`. `patch` payload type updated in Task 3, consumed in Task 6 as `{ experiment_id: newId }`. All consistent.
