# Issue #29 — Additive Silent Failure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface a user-readable error when a Step 3 additive row has a typed compound name with no resolved `compound_id`, blocking form advancement and preventing silent data loss.

**Architecture:** All changes are in the frontend wizard. `Step3Additives.tsx` gains per-row error state and a `handleNext` validator; `RowEditor` receives an `error` prop it displays inline on the compound input. No backend changes required.

**Tech Stack:** React 18, React Query (`@tanstack/react-query`), Vitest + Testing Library (`@testing-library/react`, `@testing-library/user-event`), Tailwind CSS.

---

## Root Cause

`Step3Additives` passes `onNext` directly to the "Next: Review →" button with no validation. A row with `compound_name` set but `compound_id: null` (user typed a name, never selected from the dropdown) advances to Step 4 silently. On final submission in `index.tsx` line 160, `if (row.compound_id && row.amount)` skips the row — additive dropped with no feedback.

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `frontend/src/pages/NewExperiment/__tests__/Step3Additives.test.tsx` | **Create** | Unit tests for the validation behavior |
| `frontend/src/pages/NewExperiment/Step3Additives.tsx` | **Modify** | Add `rowErrors` state, `handleNext` validator, error display on compound input, `useToast` import |
| `frontend/src/pages/NewExperiment/index.tsx` | **No change** | Validation in Step 3 prevents the silent-skip path; existing mutation `onError` handles API failures |
| `frontend/src/api/chemicals.ts` | **No change** | `addAdditive` already propagates Axios errors; interceptor in `client.ts` extracts `detail` |

---

## Task 1: Write failing tests

**Files:**
- Create: `frontend/src/pages/NewExperiment/__tests__/Step3Additives.test.tsx`

- [ ] **Step 1.1 — Create the test file**

```tsx
// frontend/src/pages/NewExperiment/__tests__/Step3Additives.test.tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import { Step3Additives, generateId, type AdditiveRow } from '../Step3Additives'

vi.mock('@/api/chemicals', () => ({
  chemicalsApi: {
    listCompounds: vi.fn(() => Promise.resolve([])),
  },
}))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
  )
}

function makeRow(overrides: Partial<AdditiveRow> = {}): AdditiveRow {
  return { id: generateId(), compound_id: null, compound_name: '', amount: '', unit: 'g', ...overrides }
}

describe('Step3Additives validation', () => {
  it('calls onNext when all rows have compound_id', async () => {
    const onNext = vi.fn()
    const rows = [makeRow({ compound_id: 1, compound_name: 'Magnetite', amount: '5' })]
    wrap(<Step3Additives rows={rows} onChange={vi.fn()} onBack={vi.fn()} onNext={onNext} />)

    await userEvent.click(screen.getByRole('button', { name: /next/i }))

    expect(onNext).toHaveBeenCalledOnce()
  })

  it('calls onNext when rows is empty', async () => {
    const onNext = vi.fn()
    wrap(<Step3Additives rows={[]} onChange={vi.fn()} onBack={vi.fn()} onNext={onNext} />)

    await userEvent.click(screen.getByRole('button', { name: /next/i }))

    expect(onNext).toHaveBeenCalledOnce()
  })

  it('blocks onNext when a row has compound_name but no compound_id', async () => {
    const onNext = vi.fn()
    const rows = [makeRow({ compound_name: 'Unknown Stuff', amount: '5' })]
    wrap(<Step3Additives rows={rows} onChange={vi.fn()} onBack={vi.fn()} onNext={onNext} />)

    await userEvent.click(screen.getByRole('button', { name: /next/i }))

    expect(onNext).not.toHaveBeenCalled()
  })

  it('shows inline error on unresolved compound row', async () => {
    const rows = [makeRow({ compound_name: 'Unknown Stuff', amount: '5' })]
    wrap(<Step3Additives rows={rows} onChange={vi.fn()} onBack={vi.fn()} onNext={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /next/i }))

    expect(screen.getByText(/compound not found/i)).toBeInTheDocument()
  })

  it('fires an error toast when a row has unresolved compound_name', async () => {
    const rows = [makeRow({ compound_name: 'Unknown Stuff', amount: '5' })]
    wrap(<Step3Additives rows={rows} onChange={vi.fn()} onBack={vi.fn()} onNext={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /next/i }))

    await waitFor(() => {
      expect(screen.getByText(/resolve all compound names/i)).toBeInTheDocument()
    })
  })

  it('does not show inline error on a row with empty compound_name', async () => {
    const onNext = vi.fn()
    // Row with amount but no compound_name — valid (will be skipped at submission)
    const rows = [makeRow({ amount: '5' })]
    wrap(<Step3Additives rows={rows} onChange={vi.fn()} onBack={vi.fn()} onNext={onNext} />)

    await userEvent.click(screen.getByRole('button', { name: /next/i }))

    expect(onNext).toHaveBeenCalledOnce()
    expect(screen.queryByText(/compound not found/i)).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 1.2 — Run the tests to confirm they fail**

Run from `frontend/` directory:
```bash
npx vitest run src/pages/NewExperiment/__tests__/Step3Additives.test.tsx
```

Expected output: 4–5 test failures along the lines of `AssertionError: expected [Function] to be called once` and missing DOM elements. The "calls onNext when all rows have compound_id" and "calls onNext when rows is empty" tests may already pass because `onNext` is called unconditionally today — that is expected and fine.

---

## Task 2: Implement validation in Step3Additives

**Files:**
- Modify: `frontend/src/pages/NewExperiment/Step3Additives.tsx`

- [ ] **Step 2.1 — Add `useToast` to the import and `error` to `RowEditorProps`**

Replace the imports block and `RowEditorProps` interface:

```tsx
import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { chemicalsApi, type Compound } from '@/api/chemicals'
import { Input, Select, Button, useToast } from '@/components/ui'
import { CompoundFormModal } from '@/components/CompoundFormModal'
```

And update `RowEditorProps`:

```tsx
interface RowEditorProps {
  row: AdditiveRow
  onPatch: (patch: Partial<AdditiveRow>) => void
  onRemove: () => void
  error?: string
}
```

- [ ] **Step 2.2 — Add inline error display to the compound input in `RowEditor`**

Replace the entire compound input `<div className="flex-1 relative">` block (lines 84–122 in the original). The key changes are: conditional border/bg classes on the `<input>` and an error `<p>` below it.

```tsx
<div className="flex-1 relative">
  <label className="block text-xs font-medium text-ink-secondary mb-1">Chemical</label>
  <input
    ref={inputRef}
    className={[
      'w-full bg-surface-input border rounded px-2 py-1.5 text-sm text-ink-primary',
      'focus:outline-none focus:ring-1',
      error
        ? 'border-red-500 bg-red-500/5 focus:ring-red-500/50'
        : 'border-surface-border hover:border-ink-muted focus:ring-brand-red/50',
    ].join(' ')}
    placeholder="Search compounds…"
    value={query}
    onChange={handleInputChange}
    onFocus={() => setDropdownOpen(true)}
    onBlur={() => setTimeout(() => setDropdownOpen(false), 150)}
    autoComplete="off"
  />
  {error && <p className="text-xs text-red-400 mt-0.5">{error}</p>}
  {dropdownOpen && (query.length >= 1) && (
    <div className="absolute z-10 left-0 right-0 top-full mt-0.5 bg-surface-raised border border-surface-border rounded shadow-lg max-h-48 overflow-y-auto">
      {results.map((c) => (
        <button
          key={c.id}
          type="button"
          className="w-full text-left px-3 py-1.5 text-sm text-ink-primary hover:bg-surface-border/30 flex items-center gap-2"
          onMouseDown={() => selectCompound(c)}
        >
          <span>{c.name}</span>
          {c.formula && <span className="text-xs text-ink-muted font-mono-data">{c.formula}</span>}
        </button>
      ))}
      {!hasExactMatch && query.trim().length >= 2 && (
        <button
          type="button"
          className="w-full text-left px-3 py-1.5 text-sm text-brand-red hover:bg-surface-border/30 border-t border-surface-border/50"
          onMouseDown={openCreate}
        >
          Create "{query.trim()}"
        </button>
      )}
      {results.length === 0 && query.trim().length < 2 && (
        <p className="px-3 py-2 text-xs text-ink-muted">Type to search…</p>
      )}
    </div>
  )}
</div>
```

- [ ] **Step 2.3 — Replace `Step3Additives` body with validated version**

Replace the entire `Step3Additives` function (lines 161–202):

```tsx
/** Step 3 of new experiment wizard: chemical additives table with compound typeahead picker. */
export function Step3Additives({ rows, onChange, onBack, onNext }: Props) {
  const { error: toastError } = useToast()
  const [rowErrors, setRowErrors] = useState<Record<string, string | null>>({})

  const addRow = () =>
    onChange([...rows, { id: generateId(), compound_id: null, compound_name: '', amount: '', unit: 'g' }])

  const removeRow = (i: number) => onChange(rows.filter((_, idx) => idx !== i))

  const patchRow = (i: number, patch: Partial<AdditiveRow>) => {
    const rowId = rows[i].id
    // Clear error when compound resolves or the input is fully cleared
    if (patch.compound_id != null || patch.compound_name === '') {
      setRowErrors((prev) => ({ ...prev, [rowId]: null }))
    }
    const updated = rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r))
    if (patch.compound_id != null) {
      const newCompoundId = patch.compound_id
      const deduped = updated.filter((r, idx) => idx === i || r.compound_id !== newCompoundId)
      onChange(deduped)
    } else {
      onChange(updated)
    }
  }

  const handleNext = () => {
    const errors: Record<string, string | null> = {}
    let hasError = false
    for (const row of rows) {
      if (row.compound_name && !row.compound_id) {
        errors[row.id] = 'Compound not found. Add it to the chemical inventory first.'
        hasError = true
      }
    }
    if (hasError) {
      setRowErrors(errors)
      toastError('Cannot advance', 'Resolve all compound names before continuing.')
      return
    }
    onNext()
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-ink-muted">Add chemical additives. Leave empty if none.</p>

      {rows.map((row, i) => (
        <RowEditor
          key={row.id}
          row={row}
          onPatch={(patch) => patchRow(i, patch)}
          onRemove={() => removeRow(i)}
          error={rowErrors[row.id] ?? undefined}
        />
      ))}

      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={addRow} type="button">+ Add additive</Button>
        {rows.length === 0 && <span className="text-xs text-ink-muted">No additives (valid)</span>}
      </div>

      <div className="flex justify-between pt-2">
        <Button variant="ghost" onClick={onBack} type="button">← Back</Button>
        <Button variant="primary" onClick={handleNext} type="button">Next: Review →</Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2.4 — Run the tests to confirm they pass**

```bash
npx vitest run src/pages/NewExperiment/__tests__/Step3Additives.test.tsx
```

Expected output: all 6 tests pass. If `"fires an error toast"` fails, check that the toast title text (`"Cannot advance"`) or message (`"Resolve all compound names before continuing."`) matches what the test searches for.

- [ ] **Step 2.5 — Run the full frontend test suite to confirm no regressions**

```bash
npx vitest run
```

Expected: all pre-existing tests pass (ConditionsTab, NotesTab, AddResultModal).

- [ ] **Step 2.6 — Lint check**

```bash
npx eslint src/pages/NewExperiment/Step3Additives.tsx src/pages/NewExperiment/__tests__/Step3Additives.test.tsx --ext .ts,.tsx
```

Expected: 0 errors, 0 warnings.

- [ ] **Step 2.7 — Commit**

```bash
git add frontend/src/pages/NewExperiment/Step3Additives.tsx \
        frontend/src/pages/NewExperiment/__tests__/Step3Additives.test.tsx
git commit -m "$(cat <<'EOF'
[#29] surface error for unresolved additive compound name

- Add rowErrors state to Step3Additives; validate on Next click
- Block form advancement when compound_name set but compound_id null
- Show inline error on compound input and fire toast.error
- Clear per-row error when compound resolves or input is cleared
- Tests added: yes
- Docs updated: no
EOF
)"
```

---

## Self-Review

### Spec coverage check

| Requirement | Covered by |
|------------|-----------|
| `toast.error` fires for unknown compound | Task 2 `handleNext` + test "fires an error toast" |
| Offending row stays populated + inline field error | Task 2 `rowErrors` state + RowEditor `error` prop; test "shows inline error" |
| Form does not navigate away | Task 2 early `return` in `handleNext`; test "blocks onNext" |
| Valid compound after correction submits successfully | Test "calls onNext when all rows have compound_id" |
| No console errors | ESLint step 2.6 |
| Valid compound names unaffected | Tests "calls onNext when all rows…" and "calls onNext when rows is empty" |

### Placeholder scan

None found — all steps include exact code.

### Type consistency

- `AdditiveRow` interface: unchanged (`compound_id: number | null`, `compound_name: string`). Used consistently across test `makeRow` helper and implementation.
- `RowEditorProps.error?: string` added in Step 2.1 and consumed in Steps 2.2 and 2.3.
- `rowErrors: Record<string, string | null>` — key is `row.id` (string UUID) throughout.
- `useToast().error` is typed `(title: string, message?: string) => void` — called correctly in `handleNext`.
