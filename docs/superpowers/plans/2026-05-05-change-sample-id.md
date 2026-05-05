# Change Sample ID on Existing Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to reassign the rock sample on an existing experiment from the Experiment Detail page, triggering a full recalculation of `total_ferrous_iron_g` (conditions) and `ferrous_iron_yield_*` (scalar results).

**Architecture:** The `PATCH /api/experiments/{experiment_id}` endpoint already accepts `sample_id` in its Pydantic schema (`ExperimentUpdate`) but does nothing special when it changes. We extend the handler to validate the new sample exists, then call `recalculate()` on conditions and all scalar result rows in the same transaction. The frontend adds an inline editor in `ExperimentDetail/index.tsx` that reuses the existing `SampleSelector` component, auto-saves on selection, and shows a confirmation toast mentioning that calculations were re-run.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Pydantic v2, React 18, TanStack Query v5, Tailwind CSS

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `backend/api/routers/experiments.py` | Modify | Pop `sample_id` before generic loop; validate sample exists; call `recalculate` on conditions then scalars; write `ModificationsLog` |
| `tests/api/test_experiments.py` | Modify | 6 new tests: valid change, 404 on bad sample, no conditions no crash, recalculate called on conditions, recalculate called on scalars, audit log written |
| `frontend/src/api/experiments.ts` | Modify | Add `sample_id?: string` to `patch()` payload type |
| `frontend/src/pages/ExperimentDetail/index.tsx` | Modify | Add `editingSampleId` state, `sampleMutation`, inline `SampleSelector` editor below the subtitle |

No new files. No schema migration. No new packages. `ExperimentUpdate` already has `sample_id: Optional[str] = None`.

---

## Task 1: Write the failing backend tests

**Files:**
- Modify: `tests/api/test_experiments.py`

These tests must be written **before** the implementation. Tests 2, 4, 5, and 6 fail against the current code. Tests 1 and 3 are green from the start and serve as regression anchors.

- [ ] **Step 1: Add the 6 new test functions at the end of `tests/api/test_experiments.py`**

Append this block after the last existing test (`test_get_change_requests_experiment_not_found`):

```python
# ============================================================
# Issue #57: Change sample_id on existing experiment
# ============================================================

def _make_sample(db, sample_id: str):
    """Create a minimal SampleInfo row."""
    from database.models.samples import SampleInfo
    s = SampleInfo(sample_id=sample_id)
    db.add(s)
    db.flush()
    return s


def test_patch_sample_id_to_valid_sample(client, db_session):
    """PATCH with a valid sample_id updates the field and returns 200."""
    _make_sample(db_session, "SAMPLE_VALID_001")
    _make_experiment(db_session, "SAMPLETEST_001", 9700)
    db_session.commit()

    resp = client.patch(
        "/api/experiments/SAMPLETEST_001",
        json={"sample_id": "SAMPLE_VALID_001"},
    )
    assert resp.status_code == 200
    assert resp.json()["sample_id"] == "SAMPLE_VALID_001"


def test_patch_sample_id_nonexistent_returns_404(client, db_session):
    """PATCH with a sample_id that does not exist in SampleInfo returns 404."""
    _make_experiment(db_session, "SAMPLETEST_002", 9701)
    db_session.commit()

    resp = client.patch(
        "/api/experiments/SAMPLETEST_002",
        json={"sample_id": "GHOST_SAMPLE_XYZ"},
    )
    assert resp.status_code == 404
    assert "GHOST_SAMPLE_XYZ" in resp.json()["detail"]


def test_patch_sample_id_no_conditions_no_crash(client, db_session):
    """Experiment with no conditions row: PATCH sample_id succeeds, no crash."""
    _make_sample(db_session, "SAMPLE_NOCOND_001")
    _make_experiment(db_session, "SAMPLETEST_003", 9702)
    db_session.commit()

    resp = client.patch(
        "/api/experiments/SAMPLETEST_003",
        json={"sample_id": "SAMPLE_NOCOND_001"},
    )
    assert resp.status_code == 200
    assert resp.json()["sample_id"] == "SAMPLE_NOCOND_001"


def test_patch_sample_id_calls_recalculate_on_conditions(client, db_session):
    """recalculate is called with the ExperimentalConditions instance."""
    from unittest.mock import patch as mock_patch
    from database.models.samples import SampleInfo
    from database.models.conditions import ExperimentalConditions

    _make_sample(db_session, "SAMPLE_COND_001")
    exp = _make_experiment(db_session, "SAMPLETEST_004", 9703)
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id=exp.experiment_id,
        rock_mass_g=100.0,
    )
    db_session.add(cond)
    db_session.commit()

    with mock_patch("backend.api.routers.experiments.recalculate") as mock_recalc:
        resp = client.patch(
            "/api/experiments/SAMPLETEST_004",
            json={"sample_id": "SAMPLE_COND_001"},
        )

    assert resp.status_code == 200
    called_types = [type(call_args[0][0]) for call_args in mock_recalc.call_args_list]
    assert ExperimentalConditions in called_types


def test_patch_sample_id_calls_recalculate_on_scalars(client, db_session):
    """recalculate is called with each ScalarResults instance."""
    from unittest.mock import patch as mock_patch
    from database.models.samples import SampleInfo
    from database.models.conditions import ExperimentalConditions
    from database.models.results import ExperimentalResults, ScalarResults

    _make_sample(db_session, "SAMPLE_SCALAR_001")
    exp = _make_experiment(db_session, "SAMPLETEST_005", 9704)
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id=exp.experiment_id,
    )
    db_session.add(cond)
    db_session.flush()
    result = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=1.0,
        time_post_reaction_bucket_days=1.0,
        cumulative_time_post_reaction_days=1.0,
        is_primary_timepoint_result=True,
        description="T1",
    )
    db_session.add(result)
    db_session.flush()
    scalar = ScalarResults(result_id=result.id)
    db_session.add(scalar)
    db_session.commit()

    with mock_patch("backend.api.routers.experiments.recalculate") as mock_recalc:
        resp = client.patch(
            "/api/experiments/SAMPLETEST_005",
            json={"sample_id": "SAMPLE_SCALAR_001"},
        )

    assert resp.status_code == 200
    called_types = [type(call_args[0][0]) for call_args in mock_recalc.call_args_list]
    assert ScalarResults in called_types


def test_patch_sample_id_logs_modification(client, db_session):
    """Changing sample_id writes a ModificationsLog entry."""
    from database.models.experiments import ModificationsLog
    from sqlalchemy import select as sa_select

    _make_sample(db_session, "SAMPLE_LOG_001")
    exp = _make_experiment(db_session, "SAMPLETEST_006", 9705)
    exp.sample_id = "OLD_SAMPLE"
    db_session.commit()

    client.patch(
        "/api/experiments/SAMPLETEST_006",
        json={"sample_id": "SAMPLE_LOG_001"},
    )

    log = db_session.execute(
        sa_select(ModificationsLog)
        .where(ModificationsLog.experiment_id == "SAMPLETEST_006")
        .where(ModificationsLog.modified_table == "experiments")
        .order_by(ModificationsLog.id.desc())
    ).scalar_one_or_none()
    assert log is not None
    assert log.old_values == {"sample_id": "OLD_SAMPLE"}
    assert log.new_values == {"sample_id": "SAMPLE_LOG_001"}
```

- [ ] **Step 2: Run the new tests to confirm they fail (as expected)**

```bash
cd C:\Users\MathewHearl\Documents\0x_Software\database_sandbox\experiment_tracking_sandbox
.venv\Scripts\pytest tests/api/test_experiments.py -k "SAMPLETEST" -v
```

Expected: `test_patch_sample_id_nonexistent_returns_404` → FAIL (gets 500, expects 404).
`test_patch_sample_id_calls_recalculate_on_conditions` → FAIL (mock not called).
`test_patch_sample_id_calls_recalculate_on_scalars` → FAIL (mock not called).
`test_patch_sample_id_logs_modification` → FAIL (no log written).
The other two should PASS (already works via setattr loop).

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/api/test_experiments.py
git commit -m "[#57] add failing tests for sample_id change endpoint

- Tests added: yes
- Docs updated: no"
```

---

## Task 2: Backend implementation — extend update_experiment

**Files:**
- Modify: `backend/api/routers/experiments.py`

Two changes: (1) add `SampleInfo` to imports, (2) extend `update_experiment` to handle `sample_id` specially.

- [ ] **Step 1: Add `SampleInfo` import**

In `backend/api/routers/experiments.py`, the existing model imports are grouped at the top. Add `SampleInfo` after the existing model imports:

Find this line:
```python
from database.models.notion_sync import ReactorChangeRequest
```

Add immediately after it:
```python
from database.models.samples import SampleInfo
```

- [ ] **Step 2: Extend `update_experiment` to validate, recalculate, and log**

In `update_experiment` (starts at line 515), find this block:

```python
    data = payload.model_dump(exclude_unset=True)
    new_id = data.pop("experiment_id", None)
    old_date = exp.date  # capture before mutation

    for field, value in data.items():
        setattr(exp, field, value)
```

Replace it with:

```python
    data = payload.model_dump(exclude_unset=True)
    new_id = data.pop("experiment_id", None)
    new_sample_id = data.pop("sample_id", None)
    old_date = exp.date  # capture before mutation

    for field, value in data.items():
        setattr(exp, field, value)
```

Then find the block that begins `if new_id is not None:` and ends just before `db.commit()`:

```python
            log.info("experiment_renamed", old_id=experiment_id, new_id=new_id, user=current_user.uid)

    db.commit()
```

Replace that closing section with:

```python
            log.info("experiment_renamed", old_id=experiment_id, new_id=new_id, user=current_user.uid)

    if new_sample_id is not None:
        sample = db.get(SampleInfo, new_sample_id)
        if sample is None:
            raise HTTPException(status_code=404, detail=f"Sample '{new_sample_id}' not found")
        old_sample_id = exp.sample_id
        exp.sample_id = new_sample_id
        db.flush()
        cond = db.execute(
            select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
        ).scalar_one_or_none()
        if cond is not None:
            recalculate(cond, db)
            db.flush()
        result_ids = db.execute(
            select(ExperimentalResults.id).where(ExperimentalResults.experiment_fk == exp.id)
        ).scalars().all()
        scalars = db.execute(
            select(ScalarResults).where(ScalarResults.result_id.in_(result_ids))
        ).scalars().all()
        for scalar in scalars:
            recalculate(scalar, db)
        db.add(ModificationsLog(
            experiment_id=exp.experiment_id,
            experiment_fk=exp.id,
            modified_by=current_user.uid,
            modification_type="update",
            modified_table="experiments",
            old_values={"sample_id": old_sample_id},
            new_values={"sample_id": new_sample_id},
        ))
        log.info("experiment_sample_updated", experiment_id=exp.experiment_id, new_sample_id=new_sample_id, user=current_user.uid)

    db.commit()
```

- [ ] **Step 3: Run the new tests — they should all pass**

```bash
.venv\Scripts\pytest tests/api/test_experiments.py -k "SAMPLETEST" -v
```

Expected: all 6 pass.

- [ ] **Step 4: Run the full experiment test suite to confirm no regressions**

```bash
.venv\Scripts\pytest tests/api/test_experiments.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the implementation**

```bash
git add backend/api/routers/experiments.py
git commit -m "[#57] extend PATCH experiments to validate sample and recalculate

- Validates new sample_id exists (404 if not)
- Calls recalculate on conditions, then all scalar results
- Writes ModificationsLog entry for sample_id changes
- Tests added: yes
- Docs updated: no"
```

---

## Task 3: Frontend API — add sample_id to patch payload

**Files:**
- Modify: `frontend/src/api/experiments.ts`

- [ ] **Step 1: Add `sample_id` to the `patch()` payload type**

In `frontend/src/api/experiments.ts`, find the `patch` method definition (around line 120):

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
```

Replace it with:

```typescript
  patch: (
    experimentId: string,
    payload: {
      status?: string
      researcher?: string
      date?: string
      experiment_id?: string
      sample_id?: string
    },
  ) =>
```

- [ ] **Step 2: Verify TypeScript compiles without errors**

```bash
cd frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/experiments.ts
git commit -m "[#57] add sample_id to experiments patch payload type

- Tests added: no
- Docs updated: no"
```

---

## Task 4: Frontend UI — inline sample ID editor

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/index.tsx`

The goal is to make the `Sample: XXX` text in the subtitle clickable, which opens a `SampleSelector` in a small block below the subtitle row. Selecting a sample auto-saves via mutation and closes the editor. A Cancel button exits without saving.

- [ ] **Step 1: Add imports and state**

In `frontend/src/pages/ExperimentDetail/index.tsx`, find the existing import for `SampleSelector` — it is NOT yet imported. Add it.

Find:
```typescript
import { StatusBadge, Button, Input, PageSpinner, useToast } from '@/components/ui'
```

Replace with:
```typescript
import { StatusBadge, Button, Input, PageSpinner, useToast } from '@/components/ui'
import { SampleSelector } from '@/components/ui/SampleSelector'
```

Then find the existing state declarations (around line 25):
```typescript
  const [editingDate, setEditingDate] = useState(false)
  const [dateDraft, setDateDraft] = useState('')
```

Add immediately after:
```typescript
  const [editingSampleId, setEditingSampleId] = useState(false)
```

- [ ] **Step 2: Add the sampleMutation**

Find the existing `dateMutation` declaration (around line 66):
```typescript
  const dateMutation = useMutation({
```

Add a new mutation block immediately after the `dateMutation` closing brace:
```typescript
  const sampleMutation = useMutation({
    mutationFn: (newSampleId: string) =>
      experimentsApi.patch(id!, { sample_id: newSampleId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiment', id] })
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
      success('Sample updated — calculations re-run')
      setEditingSampleId(false)
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      toastError('Sample change failed', detail ?? String(err))
      setEditingSampleId(false)
    },
  })
```

- [ ] **Step 3: Replace the read-only sample display with an editable version**

In the subtitle `<p>` tag (around line 178), find:
```typescript
          {experiment.sample_id && ` · Sample: ${experiment.sample_id}`}
```

Replace with:
```typescript
          {!editingSampleId && (
            <button
              onClick={() => setEditingSampleId(true)}
              className="text-ink-muted hover:text-ink-secondary transition-colors"
              title="Change sample"
            >
              {experiment.sample_id
                ? ` · Sample: ${experiment.sample_id}`
                : ' · Assign sample'}
            </button>
          )}
```

- [ ] **Step 4: Add the inline editor block below the subtitle paragraph**

Find the closing `</p>` of the subtitle paragraph (the one that contains `#{experiment.experiment_number}`). It ends just before:
```typescript
        </p>
      </div>

      {/* Quick actions */}
```

Add the inline editor block between `</p>` and `</div>`:

```typescript
        </p>

        {/* Inline sample ID editor */}
        {editingSampleId && (
          <div className="flex items-start gap-2 mt-1">
            <div className="w-64">
              <SampleSelector
                value={experiment.sample_id ?? ''}
                onChange={(newSampleId) => {
                  if (newSampleId && newSampleId !== experiment.sample_id) {
                    sampleMutation.mutate(newSampleId)
                  }
                }}
              />
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="mt-5"
              onClick={() => setEditingSampleId(false)}
              disabled={sampleMutation.isPending}
            >
              Cancel
            </Button>
          </div>
        )}
      </div>
```

Remove the old standalone `</div>` that was closing the header section (since we moved it inside).

- [ ] **Step 5: Verify TypeScript compiles without errors**

```bash
cd frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 6: Run ESLint on changed files**

```bash
npx eslint src/pages/ExperimentDetail/index.tsx src/api/experiments.ts --ext .ts,.tsx
```

Expected: zero warnings or errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/index.tsx
git commit -m "[#57] add inline sample ID editor to experiment detail

- Reuses SampleSelector; auto-saves on selection
- Success toast confirms calculations re-run
- Tests added: no
- Docs updated: no"
```

---

## Self-Review Checklist

### Spec coverage

| Requirement | Task |
|-------------|------|
| User can change sample ID from Experiment Detail view | Task 4 |
| `SampleSelector` reused, no new widget | Task 4 (imports existing component) |
| `total_ferrous_iron_g` updates after save | Task 2 (recalculate on conditions) |
| `ferrous_iron_yield_h2_pct` and `ferrous_iron_yield_nh3_pct` update | Task 2 (recalculate on scalars after conditions flush) |
| Non-existent sample_id → 404, no commit | Task 2 (raise HTTPException before setattr) |
| Sample with no FeO → NULL propagation (not error) | Inherits from existing `recalculate_conditions` logic |
| Audit log written | Task 2 (ModificationsLog) + Task 1 Test 6 |
| HPHT_112 can be re-pointed via UI | Resolved as side-effect (no special code needed) |
| On success: invalidate query, show toast mentioning calc re-run | Task 4 (onSuccess callback) |
| On error: toast, revert | Task 4 (onError callback + setEditingSampleId(false)) |
| On cancel / Escape: revert to read-only | Task 4 (Cancel button) |

### Placeholder scan
No TBD, TODO, or "similar to" references in the plan. All code blocks are complete.

### Type consistency
- `sampleMutation.mutate(newSampleId)` — `newSampleId: string` matches `mutationFn: (newSampleId: string) =>` ✓
- `experimentsApi.patch(id!, { sample_id: newSampleId })` — `sample_id?: string` added to payload type in Task 3 ✓
- `db.get(SampleInfo, new_sample_id)` — `SampleInfo` imported from `database.models.samples` in Task 2 ✓
- `ExperimentalConditions` already imported in the router ✓
- `ExperimentalResults`, `ScalarResults` already imported in the router ✓
- `recalculate` already imported from `backend.services.calculations.registry` ✓

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-05-change-sample-id.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — execute tasks in this session using the executing-plans skill, batch execution with checkpoints

Which approach?
