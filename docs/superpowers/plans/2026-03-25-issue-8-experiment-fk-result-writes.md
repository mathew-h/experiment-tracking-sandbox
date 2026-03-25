# Issue #8: Enforce experiment_fk Integer PK on Result Writes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every result-write path passes `experiments.id` (integer PK) as `experiment_fk`, never the string `experiment_id` URL param — enforced at the type level, schema level, router level, and component level.

**Architecture:** Two identifiers exist: `experiment_id` (string label in URLs, e.g. `"HPHT_001"`) and `experiments.id` (integer PK, stored as `experiment_fk` on child tables). The bug is passing the string where the integer is required. Fix is structural: typed interfaces force `number`, the router validates FK existence before insert, and the new `AddResultModal` component accepts `experimentPk: number` (not `experimentStringId`) to make the wrong call structurally impossible.

**Tech Stack:** Python 3.11 / FastAPI / Pydantic v2 / SQLAlchemy 2.x / pytest / React 18 / TypeScript strict / TanStack Query v5 / Vitest / React Testing Library

---

## Status Legend

- ✅ Already implemented in commit `1379675` (branch `fix/issue-8-experiment-fk-result-writes`)
- 🔲 Not yet done — implement as part of this plan

---

## File Map

| File | Status | Responsibility |
|------|--------|----------------|
| `backend/api/schemas/results.py` | ✅→🔲 | `ResultCreate.experiment_fk` Field description + `strict=True` hardening |
| `backend/api/routers/results.py` | ✅ | FK existence check in `create_result` |
| `frontend/src/api/results.ts` | ✅ | Typed `ResultCreate`/`ScalarCreate`; `createScalar`; contract comment |
| `frontend/src/components/experiments/AddResultModal.tsx` | ✅ | Form modal; `experimentPk: number` prop |
| `frontend/src/pages/ExperimentDetail.tsx` | ✅ | Wires modal with `experiment.id` (integer); call-site comment |
| `tests/api/test_results.py` | 🔲 | **Append** 4 new tests: reject-invalid-fk, reject-string-as-fk, numeric-coercion-boundary |
| `tests/api/test_schemas.py` | 🔲 | **Append** 4 new tests: `ResultCreate` requires integer fk; field description present |
| `frontend/vitest.config.ts` | 🔲 | Vitest + jsdom + @testing-library setup |
| `frontend/src/test/setup.ts` | 🔲 | jest-dom matchers import |
| `frontend/src/api/results.test.ts` | 🔲 | TypeScript interface shape assertions |
| `frontend/src/components/experiments/AddResultModal.test.tsx` | 🔲 | Render, form interaction, submit |

---

## Pydantic v2 Coercion Note (Read Before Starting)

Pydantic v2 silently coerces valid numeric strings to integers by default.
This means `{"experiment_fk": "42"}` passes validation and becomes `{"experiment_fk": 42}`.
This is NOT the bug in this issue (the bug is passing `"HPHT_001"` — a non-numeric string — as fk),
but it is a latent correctness gap: a caller who passes a numeric string would bypass the type system
silently.

**Task 1 (below) adds `ConfigDict(strict=True)` to `ResultCreate` to close this gap.** With strict
mode, `"42"` is also rejected → 422. This is a safe change for an API endpoint (JSON numbers are
always integers, not strings).

---

## Task 1: Harden ResultCreate with strict mode

**Files:**
- Modify: `backend/api/schemas/results.py`

The existing implementation uses a plain `int` field. Pydantic v2 will coerce `"42"` → `42`
by default. Adding `ConfigDict(strict=True)` to `ResultCreate` ensures the API rejects any
string — numeric or otherwise — for `experiment_fk`, making the type contract airtight.

- [ ] **Step 1.1: Verify current state**

  Read `backend/api/schemas/results.py`. Confirm:
  - `experiment_fk` has `Field(description="FK to experiments.id (integer PK)...")` ✓
  - `ResultCreate` does NOT yet have `model_config = ConfigDict(strict=True)`

- [ ] **Step 1.2: Add strict mode to ResultCreate**

  Modify `backend/api/schemas/results.py`:

  ```python
  from pydantic import BaseModel, ConfigDict, Field

  class ResultCreate(BaseModel):
      model_config = ConfigDict(strict=True)

      # experiment_fk must be experiments.id (the integer primary key), NOT the
      # human-readable experiment_id string (e.g. "HPHT_001").  Resolve the full
      # Experiment object from the API first, then pass experiment.id here.
      experiment_fk: int = Field(
          description="FK to experiments.id (integer PK). Never pass the string experiment_id."
      )
      time_post_reaction_days: Optional[float] = None
      time_post_reaction_bucket_days: Optional[float] = None
      cumulative_time_post_reaction_days: Optional[float] = None
      is_primary_timepoint_result: bool = True
      description: str
  ```

  **Note:** `strict=True` only applies to this model. Do not add it to `ScalarCreate`,
  `ICPCreate`, or other schemas unless explicitly required — it can break existing callers.

- [ ] **Step 1.3: Run existing results router test to confirm no regression**

  ```bash
  pytest tests/api/test_results.py -v
  ```

  Expected: All 3 existing tests (`test_list_results_by_experiment`, `test_create_result`,
  `test_create_scalar_triggers_calculation`) still pass. The existing `test_create_result`
  sends `"experiment_fk": exp.id` (already an integer) → unaffected by strict mode.

- [ ] **Step 1.4: Commit the strict-mode hardening**

  ```bash
  git add backend/api/schemas/results.py
  git commit -m "[#8] Add strict=True to ResultCreate — reject numeric string coercion"
  ```

---

## Task 2: Verify rest of existing implementation is correct

**Files:** All other ✅ files — read-only verification.

- [ ] **Step 2.1: Confirm router FK guard**

  Read `backend/api/routers/results.py`, `create_result` function. Verify:
  - `exp = db.get(Experiment, payload.experiment_fk)` is called before `ExperimentalResults(...)`
  - `HTTPException(status_code=404, ...)` raised if `exp is None`
  - `log.info(...)` records `experiment_fk` and `result_id`

- [ ] **Step 2.2: Confirm frontend contract**

  Read `frontend/src/api/results.ts`. Verify:
  - `ResultCreate` interface has `experiment_fk: number` (required, not optional, not `string | number`)
  - `createResult(payload: ResultCreate)` — typed payload, not `Partial<ExperimentResult>`
  - File-level JSDoc block explains the string vs integer contract with correct/wrong examples

- [ ] **Step 2.3: Confirm modal prop type**

  Read `frontend/src/components/experiments/AddResultModal.tsx`. Verify:
  - `Props.experimentPk: number` (the integer PK prop)
  - Mutation sends `experiment_fk: experimentPk` (integer), not `experimentStringId`
  - Top-of-file comment explains why `experimentPk` must be the integer PK

- [ ] **Step 2.4: Confirm page wiring**

  Read `frontend/src/pages/ExperimentDetail.tsx`. Verify:
  - `<AddResultModal experimentPk={experiment.id} ...>` where `experiment` comes from `useQuery`
  - NOT `experimentPk={id}` where `id` is the URL string from `useParams`
  - Call-site comment explains the distinction

---

## Task 3: Backend — schema tests

**Files:**
- Modify: `tests/api/test_schemas.py` — **APPEND** to end of existing file (do not overwrite)

The file already has tests for `ExperimentCreate`, `ConditionsCreate`, `ScalarCreate`, and
`CompoundResponse`. Add the `ResultCreate` tests below all existing tests.

- [ ] **Step 3.1: Write the new ResultCreate schema tests**

  Open `tests/api/test_schemas.py`. At the **end of the file**, add:

  ```python
  from backend.api.schemas.results import ResultCreate


  def test_result_create_requires_integer_fk():
      """experiment_fk must be a strict integer; non-numeric strings must be rejected."""
      # "HPHT_001" can never be parsed as int → ValidationError regardless of strict mode
      with pytest.raises(ValidationError):
          ResultCreate(experiment_fk="HPHT_001", description="Day 7")


  def test_result_create_rejects_numeric_string_fk():
      """With strict=True, even a numeric string like '42' must be rejected (no coercion)."""
      with pytest.raises(ValidationError):
          ResultCreate(experiment_fk="42", description="Day 7")


  def test_result_create_valid_integer_fk():
      """A real integer must be accepted."""
      r = ResultCreate(experiment_fk=42, description="Day 7")
      assert r.experiment_fk == 42
      assert isinstance(r.experiment_fk, int)


  def test_result_create_fk_field_has_description():
      """experiment_fk Field must carry a description explaining the integer PK contract."""
      field_info = ResultCreate.model_fields["experiment_fk"]
      assert field_info.description is not None
      # The description should name the integer PK concept
      desc_lower = field_info.description.lower()
      assert "integer" in desc_lower or "pk" in desc_lower


  def test_result_create_missing_description_fails():
      """description is required — omitting it raises ValidationError."""
      with pytest.raises(ValidationError):
          ResultCreate(experiment_fk=1)
  ```

  **Import note:** `pytest` and `ValidationError` are already imported at the top of the file.
  `ResultCreate` import goes after the existing imports.

- [ ] **Step 3.2: Run new tests in isolation**

  ```bash
  pytest tests/api/test_schemas.py \
    -k "test_result_create" \
    -v
  ```

  Expected: All 5 new tests PASS.

  Failure guide:
  - `test_result_create_rejects_numeric_string_fk` FAILS → `ConfigDict(strict=True)` not added yet — go back to Task 1, Step 1.2
  - `test_result_create_fk_field_has_description` FAILS → `Field(description=...)` missing — check schema

- [ ] **Step 3.3: Run full schema test file (no regressions)**

  ```bash
  pytest tests/api/test_schemas.py -v
  ```

  Expected: All existing tests (4) + new tests (5) = 9 total, all pass.

- [ ] **Step 3.4: Commit schema tests**

  ```bash
  git add tests/api/test_schemas.py
  git commit -m "[#8] Add ResultCreate schema tests — strict int, field description"
  ```

---

## Task 4: Backend — router tests for FK rejection

**Files:**
- Modify: `tests/api/test_results.py` — **APPEND** to end of existing file

The file currently has 59 lines with 3 tests (`test_list_results_by_experiment`,
`test_create_result`, `test_create_scalar_triggers_calculation`) and a `_seed(db)` helper.
The existing `test_create_result` (line 30) already verifies the happy path with a valid
integer fk. Do not duplicate it — skip the happy-path test below and only add the failure tests.

- [ ] **Step 4.1: Write FK rejection tests**

  Open `tests/api/test_results.py`. At the **end of the file**, add:

  ```python
  # ── Issue #8: experiment_fk must be experiments.id (integer PK) ──────────────


  def test_create_result_rejects_nonexistent_fk(client):
      """POST /api/results with an experiment_fk that has no matching row → 404.

      This catches the case where a developer accidentally passes a valid integer
      but one that references nothing (e.g. passes 1 when the actual PK is 42).
      """
      payload = {
          "experiment_fk": 999999,  # no experiment with this integer PK
          "description": "Should fail",
          "is_primary_timepoint_result": False,
      }
      resp = client.post("/api/results", json=payload)
      assert resp.status_code == 404
      # The error message should include the bad PK value to guide the caller
      assert "999999" in resp.json()["detail"]


  def test_create_result_rejects_nonnumeric_string_fk(client):
      """POST /api/results with experiment_fk as a non-numeric string → 422.

      "HPHT_001" cannot be parsed as int even without strict mode, so this
      verifies the baseline rejection behavior.
      """
      payload = {
          "experiment_fk": "HPHT_001",  # the string experiment_id — wrong field
          "description": "Should fail",
      }
      resp = client.post("/api/results", json=payload)
      assert resp.status_code == 422


  def test_create_result_rejects_numeric_string_fk(client):
      """POST /api/results with experiment_fk as a numeric string → 422.

      With ConfigDict(strict=True) on ResultCreate, "42" must be rejected (no coercion).
      Without strict=True this would return 201 — the test fails and tells you to add it.
      """
      payload = {
          "experiment_fk": "42",  # a numeric string — should be rejected by strict mode
          "description": "Should fail",
      }
      resp = client.post("/api/results", json=payload)
      assert resp.status_code == 422


  def test_create_result_404_message_guides_caller(client):
      """404 detail message must mention 'experiment' and the bad PK value."""
      payload = {"experiment_fk": 888888, "description": "x"}
      resp = client.post("/api/results", json=payload)
      assert resp.status_code == 404
      detail = resp.json()["detail"].lower()
      assert "experiment" in detail
      assert "888888" in resp.json()["detail"]
  ```

- [ ] **Step 4.2: Run new tests only**

  ```bash
  pytest tests/api/test_results.py \
    -k "rejects or guides" \
    -v
  ```

  Expected: All 4 new tests PASS.

  Failure guide:
  - `test_create_result_rejects_nonexistent_fk` FAILS with 201 → router guard missing in `create_result`
  - `test_create_result_rejects_numeric_string_fk` FAILS with 201 → `strict=True` not set on `ResultCreate` — go back to Task 1
  - `test_create_result_rejects_nonnumeric_string_fk` FAILS with 201 → Pydantic not validating type at all (very unexpected)

- [ ] **Step 4.3: Run full results test file (no regressions)**

  ```bash
  pytest tests/api/test_results.py -v
  ```

  Expected: All 3 existing + 4 new = 7 total, all pass.

- [ ] **Step 4.4: Run entire API test suite**

  ```bash
  pytest tests/api/ -v
  ```

  Expected: All pass. No regressions from the strict-mode or router change.

- [ ] **Step 4.5: Commit router tests**

  ```bash
  git add tests/api/test_results.py
  git commit -m "[#8] Add router tests — FK guard returns 404 / 422 on bad fk"
  ```

---

## Task 5: Frontend — Vitest setup

**Files:**
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Modify: `frontend/package.json` (add test script)

The frontend has `vitest ^1.1.0` and `@testing-library/react ^14.1.2` installed as
devDependencies but no vitest config exists yet. `frontend/tsconfig.json` already
includes `"vitest/globals"` in its `types` array — no tsconfig change needed.

- [ ] **Step 5.1: Create vitest config**

  Create `frontend/vitest.config.ts`:

  ```typescript
  import { defineConfig } from 'vitest/config'
  import react from '@vitejs/plugin-react'
  import path from 'path'

  export default defineConfig({
    plugins: [react()],
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      globals: true,
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
  })
  ```

- [ ] **Step 5.2: Create test setup file**

  Create `frontend/src/test/setup.ts`:

  ```typescript
  import '@testing-library/jest-dom'
  ```

- [ ] **Step 5.3: Add test scripts to package.json**

  In `frontend/package.json`, add to the `"scripts"` object:

  ```json
  "test": "vitest run",
  "test:watch": "vitest"
  ```

- [ ] **Step 5.4: Smoke-check the config**

  ```bash
  cd frontend && npx vitest run
  ```

  Expected: exits with "No test files found" (not an error/crash). If it throws, fix the config.

- [ ] **Step 5.5: Commit vitest setup**

  ```bash
  git add frontend/vitest.config.ts frontend/src/test/setup.ts frontend/package.json
  git commit -m "[#8] Add vitest + jsdom setup for frontend tests"
  ```

---

## Task 6: Frontend — API type contract test

**Files:**
- Create: `frontend/src/api/results.test.ts`

TypeScript types are erased at runtime. These tests:
1. Verify runtime shape of exported objects (`resultsApi.createResult` is a function, etc.)
2. Use TypeScript type assignments that would cause `tsc --noEmit` to fail if the types are wrong
   (so `tsc` is the primary enforcement mechanism — the test file is the spec)

- [ ] **Step 6.1: Write API contract tests**

  Create `frontend/src/api/results.test.ts`:

  ```typescript
  import { describe, it, expect, vi } from 'vitest'
  import type { ResultCreate, ScalarCreate } from './results'

  // ── Compile-time shape assertions ─────────────────────────────────────────────
  // These assignments compile only if the types are correct. If experiment_fk
  // were typed as string | number or were optional, the strict-mode tsc would
  // still flag places where a string is passed. The real guard is `tsc --noEmit`.

  const _validCreate: ResultCreate = {
    experiment_fk: 42,    // integer PK ✓
    description: 'Day 7',
  }

  const _withOptionals: ResultCreate = {
    experiment_fk: 1,
    description: 'Day 14',
    time_post_reaction_days: 14,
    is_primary_timepoint_result: false,
  }

  // ScalarCreate links to result_id — must NOT have experiment_fk
  const _validScalar: ScalarCreate = {
    result_id: 5,
    final_ph: 7.2,
  }

  // ── Runtime assertions ────────────────────────────────────────────────────────

  describe('ResultCreate shape', () => {
    it('experiment_fk is a number', () => {
      expect(typeof _validCreate.experiment_fk).toBe('number')
    })

    it('experiment_fk is required (no undefined default)', () => {
      expect(_validCreate.experiment_fk).toBe(42)
    })

    it('optional fields are absent when not set', () => {
      expect(_validCreate.time_post_reaction_days).toBeUndefined()
      expect(_validCreate.is_primary_timepoint_result).toBeUndefined()
    })
  })

  describe('ScalarCreate shape', () => {
    it('links via result_id, not experiment_fk', () => {
      expect(_validScalar.result_id).toBe(5)
      expect('experiment_fk' in _validScalar).toBe(false)
    })
  })

  describe('resultsApi exports', () => {
    it('exports createResult and createScalar as functions', async () => {
      const { resultsApi } = await import('./results')
      expect(typeof resultsApi.createResult).toBe('function')
      expect(typeof resultsApi.createScalar).toBe('function')
    })
  })
  ```

- [ ] **Step 6.2: Run TypeScript type-check first**

  ```bash
  cd frontend && npx tsc --noEmit
  ```

  Expected: Zero errors. Any error mentioning `experiment_fk` type mismatch means `results.ts` needs fixing.

- [ ] **Step 6.3: Run API tests**

  ```bash
  cd frontend && npx vitest run src/api/results.test.ts
  ```

  Expected: All pass.

- [ ] **Step 6.4: Commit**

  ```bash
  git add frontend/src/api/results.test.ts
  git commit -m "[#8] Add frontend API contract tests for ResultCreate/ScalarCreate"
  ```

---

## Task 7: Frontend — AddResultModal component test

**Files:**
- Create: `frontend/src/components/experiments/AddResultModal.test.tsx`

These tests verify the component's behavior: renders, validates, submits with the correct
integer FK, handles errors. The core test is `calls createResult with integer experiment_fk`
— this directly verifies the bug cannot recur.

- [ ] **Step 7.1: Write component tests**

  Create `frontend/src/components/experiments/AddResultModal.test.tsx`:

  ```typescript
  import { describe, it, expect, vi, beforeEach } from 'vitest'
  import { render, screen, fireEvent, waitFor } from '@testing-library/react'
  import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
  import { AddResultModal } from './AddResultModal'
  import * as resultsModule from '@/api/results'

  // Stub response used by multiple tests
  const STUB_RESULT: resultsModule.ExperimentResult = {
    id: 99,
    experiment_fk: 42,
    description: 'Test',
    time_post_reaction_days: null,
    time_post_reaction_bucket_days: null,
    cumulative_time_post_reaction_days: null,
    is_primary_timepoint_result: true,
    created_at: new Date().toISOString(),
  }

  function renderModal(props: Partial<React.ComponentProps<typeof AddResultModal>> = {}) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    return render(
      <QueryClientProvider client={qc}>
        <AddResultModal
          experimentPk={42}
          experimentStringId="HPHT_001"
          open={true}
          onClose={vi.fn()}
          {...props}
        />
      </QueryClientProvider>
    )
  }

  describe('AddResultModal', () => {
    beforeEach(() => {
      vi.restoreAllMocks()
    })

    it('renders title and form fields when open', () => {
      renderModal()
      expect(screen.getByText('Add Result Timepoint')).toBeInTheDocument()
      expect(screen.getByLabelText(/description/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/days post-reaction/i)).toBeInTheDocument()
    })

    it('does not render when closed', () => {
      renderModal({ open: false })
      expect(screen.queryByText('Add Result Timepoint')).not.toBeInTheDocument()
    })

    it('requires description — shows error when submit clicked with empty description', async () => {
      renderModal()
      fireEvent.click(screen.getByText('Save Timepoint'))
      await waitFor(() => {
        expect(screen.getByText('Description is required')).toBeInTheDocument()
      })
    })

    it('sends experiment_fk as the INTEGER prop value — never the string experimentStringId', async () => {
      // THE CORE CONTRACT TEST.
      // experimentPk=42 (integer), experimentStringId="HPHT_001" (string).
      // The payload must send experiment_fk=42, not "HPHT_001".
      const mockCreate = vi.spyOn(resultsModule.resultsApi, 'createResult')
        .mockResolvedValue(STUB_RESULT)

      renderModal({ experimentPk: 42, experimentStringId: 'HPHT_001' })
      fireEvent.change(screen.getByLabelText(/description/i), {
        target: { value: 'Day 7 sampling' },
      })
      fireEvent.click(screen.getByText('Save Timepoint'))

      await waitFor(() => expect(mockCreate).toHaveBeenCalledOnce())

      const payload = mockCreate.mock.calls[0][0]
      expect(payload.experiment_fk).toBe(42)                  // integer ✓
      expect(typeof payload.experiment_fk).toBe('number')     // not string ✓
      expect(payload.experiment_fk).not.toBe('HPHT_001')      // not the URL string ✓
      expect(payload.description).toBe('Day 7 sampling')
    })

    it('calls onClose after successful submit', async () => {
      const onClose = vi.fn()
      vi.spyOn(resultsModule.resultsApi, 'createResult').mockResolvedValue(STUB_RESULT)

      renderModal({ onClose })
      fireEvent.change(screen.getByLabelText(/description/i), { target: { value: 'Day 1' } })
      fireEvent.click(screen.getByText('Save Timepoint'))

      await waitFor(() => expect(onClose).toHaveBeenCalled())
    })

    it('shows API error message on failure', async () => {
      vi.spyOn(resultsModule.resultsApi, 'createResult')
        .mockRejectedValue(new Error('Experiment with id=42 not found'))

      renderModal()
      fireEvent.change(screen.getByLabelText(/description/i), { target: { value: 'Bad call' } })
      fireEvent.click(screen.getByText('Save Timepoint'))

      await waitFor(() => {
        expect(screen.getByText(/experiment with id=42 not found/i)).toBeInTheDocument()
      })
    })

    it('calls onClose when Cancel is clicked (no submit)', () => {
      const onClose = vi.fn()
      renderModal({ onClose })
      fireEvent.click(screen.getByText('Cancel'))
      expect(onClose).toHaveBeenCalled()
    })

    it('validates days-post-reaction as a number when provided', async () => {
      renderModal()
      fireEvent.change(screen.getByLabelText(/description/i), { target: { value: 'Day x' } })
      fireEvent.change(screen.getByLabelText(/days post-reaction/i), {
        target: { value: 'not-a-number' },
      })
      fireEvent.click(screen.getByText('Save Timepoint'))
      await waitFor(() => {
        expect(screen.getByText('Must be a number')).toBeInTheDocument()
      })
    })
  })
  ```

  **`React` import note:** `React.ComponentProps` requires `import React from 'react'` or
  use `import type { ComponentProps } from 'react'` and replace `React.ComponentProps` with
  `ComponentProps`.

- [ ] **Step 7.2: Run component tests**

  ```bash
  cd frontend && npx vitest run src/components/experiments/AddResultModal.test.tsx
  ```

  Expected: All 7 tests pass.

  Common failure modes:
  | Error | Cause | Fix |
  |-------|-------|-----|
  | `Unable to find label "Description"` | `Input` label text or `htmlFor` mismatch | Use `getByPlaceholderText(/description/i)` as fallback; check `Input.tsx` label rendering |
  | `Unable to find label "Days Post-Reaction"` | Same as above | Use `getByPlaceholderText(/e.g. 7/i)` as fallback |
  | `createResult not called` | Modal closes before mutation fires | Verify `onSuccess` is wired to `onClose` after mutation resolves |
  | `Cannot find module '@/api/results'` | `vitest.config.ts` `@` alias missing | Confirm `resolve.alias` is in vitest config |

- [ ] **Step 7.3: Run full frontend test suite**

  ```bash
  cd frontend && npx vitest run
  ```

  Expected: All tests across all files pass.

- [ ] **Step 7.4: TypeScript strict check**

  ```bash
  cd frontend && npx tsc --noEmit
  ```

  Expected: Zero errors.

- [ ] **Step 7.5: Lint**

  ```bash
  cd frontend && npx eslint src --ext .ts,.tsx --max-warnings 0
  ```

  Expected: Zero warnings.

- [ ] **Step 7.6: Commit component tests**

  ```bash
  git add frontend/src/components/experiments/AddResultModal.test.tsx
  git commit -m "[#8] Add AddResultModal tests — 7 cases, verifies integer fk contract"
  ```

---

## Task 8: Full regression pass and sign-off

- [ ] **Step 8.1: Run all backend tests**

  ```bash
  pytest tests/api/ -v
  ```

  Expected: All pass (should be at minimum 7 results tests + 9 schema tests + all others).

- [ ] **Step 8.2: Run all frontend tests + type check + lint**

  ```bash
  cd frontend && npx vitest run && npx tsc --noEmit && npx eslint src --ext .ts,.tsx --max-warnings 0
  ```

  Expected: All pass.

- [ ] **Step 8.3: Acceptance criteria checklist**

  Verify every item from the issue is satisfied:

  - [ ] `ResultCreate.experiment_fk` has `Field(description=...)` naming `experiments.id` (integer PK)
  - [ ] `ResultCreate` has `ConfigDict(strict=True)` — numeric strings also rejected
  - [ ] `src/api/results.ts` `createResult` typed with `experiment_fk: number` (required, not string, not optional)
  - [ ] `AddResultModal` prop is `experimentPk: number`; mutation sends that integer as `experiment_fk`
  - [ ] Call site in `ExperimentDetail` passes `experiment.id` (integer from query result), not `id` (URL string from `useParams`)
  - [ ] Comment at call site explains the distinction
  - [ ] `POST /api/results` returns `404` when `experiment_fk` has no matching experiment
  - [ ] `POST /api/results` returns `422` for non-numeric string fk
  - [ ] `POST /api/results` returns `422` for numeric string fk (strict mode)
  - [ ] All new tests pass; no regressions

- [ ] **Step 8.4: Run `/complete-task` or create PR**

  ```bash
  gh pr create \
    --title "[#8] Enforce experiment_fk integer PK on all result writes" \
    --body "Fixes #8. Plan: docs/superpowers/plans/2026-03-25-issue-8-experiment-fk-result-writes.md" \
    --base feature/m4-react-shell
  ```

---

## What Could Go Wrong

| Risk | How to Detect | Fix |
|------|---------------|-----|
| `ConfigDict(strict=True)` on `ResultCreate` breaks an existing caller | `test_create_result` (existing) fails after Task 1 | Existing test already passes integer correctly — shouldn't break. If it does, check the test payload type. |
| `test_create_result_rejects_numeric_string_fk` fails with 201 | Strict mode not applied | Go back to Task 1 Step 1.2, add `model_config = ConfigDict(strict=True)` |
| `getByLabelText` doesn't find form fields | Test error: "Unable to find a label with the text..." | Check `Input` component: `label` prop renders `<label htmlFor={id}>` linked to `<input id={id}>`. Use `getByPlaceholderText` as fallback |
| `vi.spyOn` on imported module doesn't intercept calls | Test: `mockCreate` has 0 calls | Ensure `resultsModule.resultsApi.createResult` is spied before render; confirm module uses named export not default |
| `time_post_reaction_bucket_days` null causes unique constraint error on second insert | 500 on second POST with same timepoint | The `is_primary_timepoint_result=True` + null bucket should be fine; constraint is `unique per experiment+bucket` where null != null in SQL |
| Vitest can't find `jsdom` | Config error on test run | Run `cd frontend && npm install` — jsdom ships with vitest, no separate install needed |
| `@testing-library/jest-dom` matchers not available | `toBeInTheDocument is not a function` | Confirm `frontend/src/test/setup.ts` is referenced in `vitest.config.ts` setupFiles |
