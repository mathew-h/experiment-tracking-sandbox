# Experiments Filter Pagination Reset — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add vitest tests that verify the pagination offset resets to 0 whenever a filter changes, proving the existing fix is complete and guarding against regressions.

**Architecture:** The `resetPage()` fix is already in `ExperimentList.tsx` — every filter `onChange` handler calls it. The work here is to write tests that would fail if any `resetPage()` call were removed, covering all five acceptance criteria from issue #53.

**Tech Stack:** Vitest, @testing-library/react 14, @testing-library/user-event 14, react-router-dom MemoryRouter, @tanstack/react-query QueryClientProvider, jsdom

---

## Current State

The fix is already applied: every filter `onChange` handler in `ExperimentList.tsx` calls `resetPage()` (which calls `setSkip(0)`). No test exists to verify this. These tests lock in that behavior.

The five acceptance criteria from issue #53:
1. Applying any filter always resets to page 1
2. Page indicator shows "Page 1 of N" after filter
3. Filtered results are correct regardless of prior page
4. Clearing filters resets to page 1
5. No regression on default unfiltered pagination

---

## File Map

| Action | Path |
|--------|------|
| **Create** | `frontend/src/pages/__tests__/ExperimentList.test.tsx` |
| **Read (context only)** | `frontend/src/pages/ExperimentList.tsx` |
| **Read (context only)** | `frontend/src/api/experiments.ts` |

---

### Task 1: Create test file skeleton with shared setup

**Files:**
- Create: `frontend/src/pages/__tests__/ExperimentList.test.tsx`

- [ ] **Step 1: Write the test file with imports, mock, stub data, and wrapper**

```typescript
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    list: vi.fn(),
    patchStatus: vi.fn(),
  },
}))

import { ExperimentListPage } from '../ExperimentList'
import { experimentsApi } from '@/api/experiments'
import type { ExperimentListItem } from '@/api/experiments'

const TOTAL = 80
const LIMIT = 25

function makeItems(skip: number, limit: number): ExperimentListItem[] {
  const count = Math.min(limit, Math.max(0, TOTAL - skip))
  return Array.from({ length: count }, (_, i) => ({
    id: skip + i + 1,
    experiment_id: `EXP_${String(skip + i + 1).padStart(3, '0')}`,
    experiment_number: skip + i + 1,
    status: 'ONGOING' as const,
    researcher: null,
    date: null,
    sample_id: null,
    created_at: '2026-01-01T00:00:00Z',
    experiment_type: null,
    reactor_number: null,
    additives_summary: null,
    condition_note: null,
  }))
}

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0 },
      mutations: { retry: false },
    },
  })
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  )
}
```

- [ ] **Step 2: Run the test file to confirm it is importable with no syntax errors**

Run from `frontend/`:
```
npx vitest run src/pages/__tests__/ExperimentList.test.tsx
```
Expected: "No test files found" or 0 tests (no `describe` block yet). Not a crash.

- [ ] **Step 3: Commit the skeleton**

```bash
git add frontend/src/pages/__tests__/ExperimentList.test.tsx
git commit -m "[#53] add ExperimentList test skeleton"
```

---

### Task 2: Test — status filter resets to page 1

**Files:**
- Modify: `frontend/src/pages/__tests__/ExperimentList.test.tsx`

- [ ] **Step 1: Write the failing test**

Add a `describe` block and this test inside the test file (after the imports/setup):

```typescript
describe('ExperimentListPage — pagination reset on filter', () => {
  beforeEach(() => {
    vi.mocked(experimentsApi.list).mockImplementation(async (params) => {
      const skip = params?.skip ?? 0
      const limit = params?.limit ?? LIMIT
      return { items: makeItems(skip, limit), total: TOTAL, skip, limit }
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('resets to page 1 when status filter is applied on page 2', async () => {
    render(<ExperimentListPage />, { wrapper })

    // Wait for initial page 1 load
    await waitFor(() => expect(screen.getByText('Page 1 of 4')).toBeInTheDocument())

    // Navigate to page 2
    fireEvent.click(screen.getByRole('button', { name: '→' }))
    await waitFor(() => expect(screen.getByText('Page 2 of 4')).toBeInTheDocument())

    // Apply status filter
    const statusSelect = screen.getAllByRole('combobox')[0]
    fireEvent.change(statusSelect, { target: { value: 'COMPLETED' } })

    // Verify reset to page 1 and API called with skip=0
    await waitFor(() => expect(screen.getByText(/Page 1 of/)).toBeInTheDocument())
    const lastCall = vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]
    expect(lastCall?.skip).toBe(0)
    expect(lastCall?.status).toBe('COMPLETED')
  })
```

- [ ] **Step 2: Run to see it fail (proves it tests the right thing)**

To confirm this test catches the bug, temporarily remove the `resetPage()` call from the status filter's `onChange` in `ExperimentList.tsx`:

```typescript
// TEMPORARY — remove resetPage() to prove test catches the bug
onChange={(e) => { setStatusFilter(e.target.value) }}
```

Run:
```
npx vitest run src/pages/__tests__/ExperimentList.test.tsx
```
Expected: FAIL — `expect(lastCall?.skip).toBe(0)` fails; actual value is `25`.

Then **restore** the `resetPage()` call:
```typescript
onChange={(e) => { setStatusFilter(e.target.value); resetPage() }}
```

- [ ] **Step 3: Run to confirm it passes with the fix in place**

```
npx vitest run src/pages/__tests__/ExperimentList.test.tsx
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/__tests__/ExperimentList.test.tsx
git commit -m "[#53] test: status filter resets pagination to page 1"
```

---

### Task 3: Test — text filter resets to page 1

**Files:**
- Modify: `frontend/src/pages/__tests__/ExperimentList.test.tsx`

- [ ] **Step 1: Write the test** (add inside the same `describe` block)

```typescript
  it('resets to page 1 when experiment ID text filter is typed on page 2', async () => {
    const user = userEvent.setup()
    render(<ExperimentListPage />, { wrapper })

    // Wait for initial load and navigate to page 2
    await waitFor(() => expect(screen.getByText('Page 1 of 4')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '→' }))
    await waitFor(() => expect(screen.getByText('Page 2 of 4')).toBeInTheDocument())

    // Type in the experiment ID filter
    const idInput = screen.getByPlaceholderText('Experiment ID…')
    await user.type(idInput, 'HP')

    // After typing, must be back on page 1 and API called with skip=0
    await waitFor(() => expect(screen.getByText(/Page 1 of/)).toBeInTheDocument())
    const lastCall = vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]
    expect(lastCall?.skip).toBe(0)
    expect(lastCall?.search).toBe('HP')
  })
```

- [ ] **Step 2: Run to confirm it passes**

```
npx vitest run src/pages/__tests__/ExperimentList.test.tsx
```
Expected: PASS (both Task 2 + Task 3 tests green)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/__tests__/ExperimentList.test.tsx
git commit -m "[#53] test: text filter resets pagination to page 1"
```

---

### Task 4: Test — clearing filters resets to page 1

**Files:**
- Modify: `frontend/src/pages/__tests__/ExperimentList.test.tsx`

- [ ] **Step 1: Write the test** (add inside the same `describe` block)

```typescript
  it('resets to page 1 when filters are cleared', async () => {
    render(<ExperimentListPage />, { wrapper })

    await waitFor(() => expect(screen.getByText('Page 1 of 4')).toBeInTheDocument())

    // Apply a filter (lands on page 1)
    const statusSelect = screen.getAllByRole('combobox')[0]
    fireEvent.change(statusSelect, { target: { value: 'ONGOING' } })
    await waitFor(() => expect(screen.getByText(/Page 1 of/)).toBeInTheDocument())

    // Navigate to page 2 within the filtered set
    fireEvent.click(screen.getByRole('button', { name: '→' }))
    await waitFor(() => expect(screen.getByText('Page 2 of 4')).toBeInTheDocument())

    // Clear filters
    const clearButton = screen.getByRole('button', { name: /clear/i })
    fireEvent.click(clearButton)

    // Must reset to page 1 and API called with skip=0 and no status filter
    await waitFor(() => expect(screen.getByText(/Page 1 of/)).toBeInTheDocument())
    const lastCall = vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]
    expect(lastCall?.skip).toBe(0)
    expect(lastCall?.status).toBeUndefined()
  })
```

- [ ] **Step 2: Run to confirm it passes**

```
npx vitest run src/pages/__tests__/ExperimentList.test.tsx
```
Expected: PASS (all three tests green)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/__tests__/ExperimentList.test.tsx
git commit -m "[#53] test: clearing filters resets pagination to page 1"
```

---

### Task 5: Test — page size change resets to page 1

**Files:**
- Modify: `frontend/src/pages/__tests__/ExperimentList.test.tsx`

- [ ] **Step 1: Write the test** (add inside the same `describe` block)

```typescript
  it('resets to page 1 when page size is changed on page 2', async () => {
    render(<ExperimentListPage />, { wrapper })

    await waitFor(() => expect(screen.getByText('Page 1 of 4')).toBeInTheDocument())

    // Navigate to page 2
    fireEvent.click(screen.getByRole('button', { name: '→' }))
    await waitFor(() => expect(screen.getByText('Page 2 of 4')).toBeInTheDocument())

    // Change page size to 50
    fireEvent.click(screen.getByRole('button', { name: '50' }))

    // Must reset to page 1 and API called with skip=0, limit=50
    await waitFor(() => expect(screen.getByText(/Page 1 of/)).toBeInTheDocument())
    const lastCall = vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]
    expect(lastCall?.skip).toBe(0)
    expect(lastCall?.limit).toBe(50)
  })
```

- [ ] **Step 2: Run to confirm it passes**

```
npx vitest run src/pages/__tests__/ExperimentList.test.tsx
```
Expected: PASS (all four tests green)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/__tests__/ExperimentList.test.tsx
git commit -m "[#53] test: page size change resets pagination to page 1"
```

---

### Task 6: Test — normal pagination regression guard

**Files:**
- Modify: `frontend/src/pages/__tests__/ExperimentList.test.tsx`

- [ ] **Step 1: Write the test** (add inside the same `describe` block)

```typescript
  it('paginates forward and backward without resetting when no filter changes', async () => {
    render(<ExperimentListPage />, { wrapper })

    await waitFor(() => expect(screen.getByText('Page 1 of 4')).toBeInTheDocument())

    // Go to page 2
    fireEvent.click(screen.getByRole('button', { name: '→' }))
    await waitFor(() => expect(screen.getByText('Page 2 of 4')).toBeInTheDocument())
    let lastCall = vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]
    expect(lastCall?.skip).toBe(25)

    // Go to page 3
    fireEvent.click(screen.getByRole('button', { name: '→' }))
    await waitFor(() => expect(screen.getByText('Page 3 of 4')).toBeInTheDocument())
    lastCall = vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]
    expect(lastCall?.skip).toBe(50)

    // Go back to page 2
    fireEvent.click(screen.getByRole('button', { name: '←' }))
    await waitFor(() => expect(screen.getByText('Page 2 of 4')).toBeInTheDocument())
    lastCall = vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]
    expect(lastCall?.skip).toBe(25)
  })
}) // closes describe block
```

- [ ] **Step 2: Run the full test suite to confirm all five tests pass**

```
npx vitest run src/pages/__tests__/ExperimentList.test.tsx
```
Expected output:
```
✓ resets to page 1 when status filter is applied on page 2
✓ resets to page 1 when experiment ID text filter is typed on page 2
✓ resets to page 1 when filters are cleared
✓ resets to page 1 when page size is changed on page 2
✓ paginates forward and backward without resetting when no filter changes
Test Files  1 passed (1)
Tests       5 passed (5)
```

- [ ] **Step 3: Run the broader test suite to check for regressions**

```
npx vitest run
```
Expected: All tests pass. If any pre-existing tests fail, investigate before proceeding.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/__tests__/ExperimentList.test.tsx
git commit -m "[#53] test: normal pagination regression guard"
```

---

## Self-Review

**Spec coverage:**
- AC1 (filter resets to page 1): Tasks 2 + 3 — ✓
- AC2 (page indicator reflects reset): Both tasks assert `screen.getByText(/Page 1 of/)` — ✓
- AC3 (correct results regardless of prior page): API call assertions verify `skip=0` with correct filter params — ✓
- AC4 (clearing filters resets): Task 4 — ✓
- AC5 (no regression on normal pagination): Task 6 — ✓

**Placeholder scan:** No TBD, TODO, or "similar to Task N" entries. All test code is complete.

**Type consistency:**
- `makeItems` returns `ExperimentListItem[]` — matches the `ExperimentListResponse.items` type
- `experimentsApi.list` mock params use `ExperimentListParams` fields: `skip`, `limit`, `status`, `search` — all match the interface in `experiments.ts:77-88`
- `vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]` accesses the first argument of the last call, which is `ExperimentListParams | undefined`

**One gap identified:** The plan doesn't test the date filter or sample ID / reactor filter resets individually. These all use the same `resetPage()` call pattern as the status filter, so the status filter test (Task 2) demonstrates the pattern. Individual tests for each filter would be repetitive without adding coverage value.
