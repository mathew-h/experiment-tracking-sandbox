# Bulk-Upload Preview-First UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the New Experiments bulk upload preview-first — a dropped file always runs a dry run and opens a review modal showing the create/rename/overwrite plan, and the only path that writes is a Commit button that replays the previewed plan hash.

**Architecture:** A wrapper component (`NewExperimentsUploadRow`) owns the two-phase state and both mutations, exactly as the existing `ActlabsUploadRow` wraps `UploadRow` for its conflict flow. `UploadRow` itself gains one optional prop (`onUploadSuccess`) so a dry run's real-looking counts never render as a completed upload. Plan rendering is a pure presentational component (`UploadPlanPanel`) inside a modal (`UploadPlanModal`) whose body already scrolls, so an 80-rename plan needs no layout surgery.

**Tech Stack:** React 18 + TypeScript (strict), TanStack Query v5, Tailwind (brand tokens only), vitest + @testing-library/react, Playwright for E2E.

**Spec:** `docs/superpowers/specs/2026-07-29-issue-100-bulk-upload-preview-ui-design.md` — read it before Task 1.

## Global Constraints

- **No backend change.** No file under `backend/`, `database/`, or `alembic/` is touched. Items 1–5 of issue #100 already shipped everything needed server-side.
- **Never hardcode hex values in components** — use brand tokens (`status-*`, `surface-*`, `ink-*`). Per `frontend/CLAUDE.md`.
- **No inline styles** — Tailwind utility classes only.
- **No `console.log`** in committed code.
- **No `useEffect` + `useState` for data fetching** — React Query only.
- **Never start or stop the Vite dev server or uvicorn.** Assume both are already running (Vite on 5173 or 5174, API on 8000). If unreachable, report to the user.
- **Do not add any npm dependency.** If one seems necessary, stop and escalate — `package.json` and `package-lock.json` must always be committed together (`.claude/CLAUDE.md` §5).
- **Commit format:** `[#100] <imperative description under 50 chars>` followed by `- Tests added: yes/no` and `- Docs updated: yes/no`.
- **Run tests from `frontend/`:** `npx vitest run <path>`. Type-check with `npx tsc --noEmit`.
- **`tsconfig.json` sets `isolatedModules: true` and `strict: true`.** Import types with a separate `import type { … }` statement rather than mixing them into a value import — the pattern `DeleteExperimentModal.test.tsx:13-14` already uses. Where this plan's code samples mix them (e.g. `import { UploadPlanModal, PlanModalView }`), split them.
- **Pre-existing lint baseline:** `npx eslint src --ext .ts,.tsx` reports **5 errors on files this work does not touch** (`CompoundFormModal.tsx:41,57`, `ConditionsTab.buttons.test.tsx:61,83`, `NotesTab.buttons.test.tsx:50`). Do not fix them; do not add new ones.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `frontend/src/api/bulkUploads.ts` | modify | TS mirror of the plan schema; `dryRun`/`planHash` options on `uploadNewExperiments` |
| `frontend/src/api/__tests__/bulkUploads.plan.test.ts` | create | Asserts the form fields actually sent |
| `frontend/src/components/bulkUploads/UploadPlanPanel.tsx` | create | Pure plan renderer — sections, counts, truncation, field diffs |
| `frontend/src/components/bulkUploads/UploadPlanPanel.test.tsx` | create | Panel behaviour |
| `frontend/src/components/bulkUploads/UploadPlanModal.tsx` | create | Review surface — 3 views, commit gating, re-arm checkbox |
| `frontend/src/components/bulkUploads/UploadPlanModal.test.tsx` | create | Modal behaviour |
| `frontend/src/pages/BulkUploadRow.tsx` | modify | One new optional prop, `onUploadSuccess` |
| `frontend/src/pages/NewExperimentsUploadRow.tsx` | create | State owner: preview mutation, commit mutation, stale detection |
| `frontend/src/pages/__tests__/NewExperimentsUploadRow.test.tsx` | create | Two-phase flow behaviour |
| `frontend/src/pages/BulkUploads.tsx` | modify | Swap the wrapper in for the New Experiments row |
| `frontend/e2e/journeys/02-bulk-upload-experiments.spec.ts` | modify | Walk the modal instead of expecting immediate badges |
| `docs/user_guide/BULK_UPLOADS.md` | modify | Document preview-first in section 5 |

Component tests are co-located (matching `components/experiments/DeleteExperimentModal.test.tsx`); page and api tests live in `__tests__/` (matching `pages/__tests__/BulkUploads.test.tsx`).

---

### Task 1: Plan types and API client options

**Files:**
- Modify: `frontend/src/api/bulkUploads.ts:3-11` (extend `BulkUploadResult`), `:87-89` (`uploadNewExperiments`)
- Test: `frontend/src/api/__tests__/bulkUploads.plan.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `UploadPlan`, `PlanCreate`, `PlanRename`, `PlanOverwrite`, `PlanSkip`, `PlanConflict`, `PlanFieldChange` (all exported types); `bulkUploadsApi.uploadNewExperiments(file: File, opts?: { dryRun?: boolean; planHash?: string }): Promise<BulkUploadResult>`; `BulkUploadResult.plan?: UploadPlan | null`, `.plan_hash?: string | null`, `.dry_run?: boolean`.

**Why the new fields are optional:** the other 12 endpoints return `plan: null` and no `plan_hash`, and existing test mocks build `BulkUploadResult` literals. Required fields would break their compile for no benefit.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/__tests__/bulkUploads.plan.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

import { bulkUploadsApi } from '../bulkUploads'
import { apiClient } from '../client'

function sentForm(): FormData {
  return vi.mocked(apiClient.post).mock.calls[0][1] as FormData
}

describe('uploadNewExperiments — dry-run and plan-hash options', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.post).mockResolvedValue({ data: { created: 0, updated: 0, skipped: 0, errors: [], warnings: [], feedbacks: [], message: '' } })
  })

  const file = new File(['x'], 'exp.xlsx')

  it('sends no dry_run or plan_hash field by default', async () => {
    await bulkUploadsApi.uploadNewExperiments(file)
    const fd = sentForm()
    expect(fd.get('file')).toBe(file)
    expect(fd.get('dry_run')).toBeNull()
    expect(fd.get('plan_hash')).toBeNull()
  })

  it('sends dry_run=true when previewing', async () => {
    await bulkUploadsApi.uploadNewExperiments(file, { dryRun: true })
    expect(sentForm().get('dry_run')).toBe('true')
  })

  it('sends the plan hash on a real submit without dry_run', async () => {
    await bulkUploadsApi.uploadNewExperiments(file, { planHash: 'abc123' })
    const fd = sentForm()
    expect(fd.get('plan_hash')).toBe('abc123')
    expect(fd.get('dry_run')).toBeNull()
  })

  it('posts to the new-experiments endpoint', async () => {
    await bulkUploadsApi.uploadNewExperiments(file, { dryRun: true })
    expect(vi.mocked(apiClient.post).mock.calls[0][0]).toBe('/bulk-uploads/new-experiments')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run from `frontend/`: `npx vitest run src/api/__tests__/bulkUploads.plan.test.ts`
Expected: the `dryRun` and `planHash` tests FAIL — `uploadNewExperiments` currently takes only `(file)` and appends nothing, so `fd.get('dry_run')` is `null`.

- [ ] **Step 3: Add the plan types**

Insert after the `BulkUploadResult` interface in `frontend/src/api/bulkUploads.ts`:

```ts
// ─── Upload plan (issue #100 items 2, 6-9) ───────────────────────────────────
// Mirrors backend/api/schemas/bulk_upload.py. Currently populated only by the
// new-experiments endpoint; every other upload type returns plan: null.

export interface PlanFieldChange {
  field: string
  old: unknown
  new: unknown
}

export interface PlanCreate {
  row: number
  experiment_id: string
  parent_id: string | null
  copied_from: string | null
}

export interface PlanRename {
  row: number
  from_id: string
  to_id: string
}

export interface PlanOverwrite {
  row: number
  experiment_id: string
  fields_changed: PlanFieldChange[]
}

export interface PlanSkip {
  row: number
  experiment_id: string | null
  reason: string
}

export interface PlanConflict {
  row: number
  kind: string
  detail: string
}

export interface UploadPlan {
  creates: PlanCreate[]
  renames: PlanRename[]
  overwrites: PlanOverwrite[]
  skips: PlanSkip[]
  conflicts: PlanConflict[]
  counts: Record<string, number>
}
```

Then add these three optional fields to `BulkUploadResult` (after `message: string`):

```ts
  /** True when the server rolled back instead of committing. */
  dry_run?: boolean
  /** Structured plan — new-experiments only; null elsewhere. */
  plan?: UploadPlan | null
  /** sha256 of the plan; replay it on commit to prove the plan is unchanged. */
  plan_hash?: string | null
```

- [ ] **Step 4: Add the options parameter**

Replace `uploadNewExperiments` in `frontend/src/api/bulkUploads.ts:87-89`:

```ts
  // Card 5 — New Experiments. Preview-first: the UI always calls this with
  // { dryRun: true } first, then replays the returned plan_hash to commit
  // (issue #100 items 5-6).
  uploadNewExperiments: (
    file: File,
    opts: { dryRun?: boolean; planHash?: string } = {},
  ) => {
    const fd = fileForm(file)
    if (opts.dryRun) fd.append('dry_run', 'true')
    if (opts.planHash) fd.append('plan_hash', opts.planHash)
    return post<BulkUploadResult>('/bulk-uploads/new-experiments', fd)
  },
```

- [ ] **Step 5: Run tests and type-check**

Run: `npx vitest run src/api/__tests__/bulkUploads.plan.test.ts` — Expected: 4 passed.
Run: `npx tsc --noEmit` — Expected: no output (clean). The default `= {}` keeps the existing single-argument call in `BulkUploads.tsx:265` compiling.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/bulkUploads.ts frontend/src/api/__tests__/bulkUploads.plan.test.ts
git commit -m "[#100] Add plan types and dry-run options to API client

- Tests added: yes
- Docs updated: no"
```

---

### Task 2: UploadPlanPanel

**Files:**
- Create: `frontend/src/components/bulkUploads/UploadPlanPanel.tsx`
- Test: `frontend/src/components/bulkUploads/UploadPlanPanel.test.tsx`

**Interfaces:**
- Consumes: `UploadPlan` from `@/api/bulkUploads` (Task 1).
- Produces: `UploadPlanPanel({ plan }: { plan: UploadPlan })` — default export not used; named export only.

**Design notes:** Sections render in a fixed order with conflicts expanded and everything else collapsed (item 7). Empty sections are omitted entirely. Truncation is 10 rows, looser than the 5 used in `BulkUploadRow.tsx:199` because a modal has more room. The chevron is defined locally rather than imported from `pages/BulkUploadRow.tsx` — a `components/` file must not depend on `pages/`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/bulkUploads/UploadPlanPanel.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UploadPlan } from '@/api/bulkUploads'
import { UploadPlanPanel } from './UploadPlanPanel'

const EMPTY: UploadPlan = {
  creates: [], renames: [], overwrites: [], skips: [], conflicts: [], counts: {},
}

function renameN(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    row: i + 2,
    from_id: `SERUM_catalyst_${String(i + 1).padStart(3, '0')}`,
    to_id: `SERUM_Catalyst_${String(i + 1).padStart(3, '0')}a-t7`,
  }))
}

describe('UploadPlanPanel', () => {
  it('omits empty sections and reports a no-op plan', () => {
    render(<UploadPlanPanel plan={EMPTY} />)
    expect(screen.getByText(/no changes/i)).toBeInTheDocument()
    expect(screen.queryByText(/0 creates/)).not.toBeInTheDocument()
  })

  it('puts the count in each section header and pluralises it', () => {
    render(<UploadPlanPanel plan={{ ...EMPTY, renames: renameN(3), creates: [{ row: 9, experiment_id: 'HPHT_001', parent_id: null, copied_from: null }] }} />)
    expect(screen.getByRole('button', { name: /3 renames/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /1 create$/ })).toBeInTheDocument()
  })

  it('expands conflicts by default and collapses creates', () => {
    render(<UploadPlanPanel plan={{
      ...EMPTY,
      conflicts: [{ row: 4, kind: 'rename_without_overwrite', detail: "old_experiment_id='SERUM_003a' provided but overwrite is not TRUE" }],
      creates: [{ row: 9, experiment_id: 'HPHT_001', parent_id: null, copied_from: null }],
    }} />)
    expect(screen.getByText(/overwrite is not TRUE/)).toBeInTheDocument()
    expect(screen.queryByText('HPHT_001')).not.toBeInTheDocument()
  })

  it('reveals a collapsed section when its header is clicked', async () => {
    render(<UploadPlanPanel plan={{ ...EMPTY, creates: [{ row: 9, experiment_id: 'HPHT_001', parent_id: null, copied_from: null }] }} />)
    await userEvent.click(screen.getByRole('button', { name: /1 create/ }))
    expect(screen.getByText(/HPHT_001/)).toBeInTheDocument()
  })

  it('renders an overwrite field diff with both old and new values', async () => {
    render(<UploadPlanPanel plan={{
      ...EMPTY,
      overwrites: [{ row: 3, experiment_id: 'SERUM_001a', fields_changed: [{ field: 'initial_ph', old: 4, new: 9 }] }],
    }} />)
    await userEvent.click(screen.getByRole('button', { name: /1 overwrite/ }))
    expect(screen.getByText('initial_ph:')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
    expect(screen.getByText('9')).toBeInTheDocument()
  })

  it('renders an empty old value as (empty) rather than blank', async () => {
    render(<UploadPlanPanel plan={{
      ...EMPTY,
      overwrites: [{ row: 3, experiment_id: 'SERUM_001a', fields_changed: [{ field: 'researcher', old: null, new: 'MH' }] }],
    }} />)
    await userEvent.click(screen.getByRole('button', { name: /1 overwrite/ }))
    expect(screen.getByText('(empty)')).toBeInTheDocument()
  })

  it('truncates a long section at 10 rows and reveals the rest on demand', async () => {
    render(<UploadPlanPanel plan={{ ...EMPTY, renames: renameN(80) }} />)
    await userEvent.click(screen.getByRole('button', { name: /80 renames/ }))
    expect(screen.getByText(/SERUM_Catalyst_010a-t7/)).toBeInTheDocument()
    expect(screen.queryByText(/SERUM_Catalyst_011a-t7/)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Show 70 more/ }))
    expect(screen.getByText(/SERUM_Catalyst_080a-t7/)).toBeInTheDocument()
  })

  it('orders sections conflicts, renames, overwrites, creates, skips', () => {
    render(<UploadPlanPanel plan={{
      ...EMPTY,
      conflicts: [{ row: 1, kind: 'k', detail: 'd' }],
      renames: renameN(1),
      overwrites: [{ row: 3, experiment_id: 'X_002', fields_changed: [] }],
      creates: [{ row: 4, experiment_id: 'X_003', parent_id: null, copied_from: null }],
      skips: [{ row: 5, experiment_id: null, reason: 'blank experiment_id' }],
    }} />)
    const headers = screen.getAllByRole('button').map((b) => b.textContent ?? '')
    expect(headers[0]).toMatch(/conflict/)
    expect(headers[1]).toMatch(/rename/)
    expect(headers[2]).toMatch(/overwrite/)
    expect(headers[3]).toMatch(/create/)
    expect(headers[4]).toMatch(/skip/)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/components/bulkUploads/UploadPlanPanel.test.tsx`
Expected: FAIL — "Failed to resolve import ./UploadPlanPanel".

- [ ] **Step 3: Write the component**

Create `frontend/src/components/bulkUploads/UploadPlanPanel.tsx`:

```tsx
import { useState } from 'react'
import type { UploadPlan } from '@/api/bulkUploads'

/** Rows shown per section before the "Show N more" toggle. Looser than the 5 used
 *  in BulkUploadRow because the plan renders in a modal with room to scroll. */
const TRUNCATE_AT = 10

type SectionKey = 'conflicts' | 'renames' | 'overwrites' | 'creates' | 'skips'

interface SectionMeta {
  key: SectionKey
  singular: string
  plural: string
  /** Brand status tokens only — never raw hex (frontend/CLAUDE.md). */
  box: string
  heading: string
  defaultOpen: boolean
}

// Fixed order. Conflicts first and expanded, everything else collapsed (issue #100 item 7).
const SECTIONS: SectionMeta[] = [
  { key: 'conflicts', singular: 'conflict', plural: 'conflicts',
    box: 'bg-status-error/5 border-status-error/25', heading: 'text-status-error', defaultOpen: true },
  { key: 'renames', singular: 'rename', plural: 'renames',
    box: 'bg-status-info/5 border-status-info/25', heading: 'text-status-info', defaultOpen: false },
  { key: 'overwrites', singular: 'overwrite', plural: 'overwrites',
    box: 'bg-status-warning/5 border-status-warning/25', heading: 'text-status-warning', defaultOpen: false },
  { key: 'creates', singular: 'create', plural: 'creates',
    box: 'bg-status-success/5 border-status-success/25', heading: 'text-status-success', defaultOpen: false },
  { key: 'skips', singular: 'skip', plural: 'skips',
    box: 'bg-surface-raised border-surface-border', heading: 'text-ink-muted', defaultOpen: false },
]

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width={14} height={14} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
      className={`text-ink-muted transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}

/** Renders a plan value for display. `null`/`undefined`/`''` all read as (empty) so a
 *  field being cleared is visible rather than looking like a rendering bug. */
function fmtValue(v: unknown): string {
  if (v === null || v === undefined || v === '') return '(empty)'
  return String(v)
}

function Line({ children }: { children: React.ReactNode }) {
  return <div className="text-2xs font-mono-data text-ink-secondary leading-relaxed">{children}</div>
}

function RowNo({ row }: { row: number }) {
  return <span className="text-ink-muted">Row {row}</span>
}

function sectionRows(plan: UploadPlan, key: SectionKey): React.ReactNode[] {
  switch (key) {
    case 'conflicts':
      return plan.conflicts.map((c, i) => (
        <Line key={i}>
          <RowNo row={c.row} /> <span className="text-status-error">[{c.kind}]</span> {c.detail}
        </Line>
      ))
    case 'renames':
      return plan.renames.map((r, i) => (
        <Line key={i}>
          <RowNo row={r.row} /> {r.from_id} <span className="text-status-info">→</span>{' '}
          <span className="font-semibold text-ink-primary">{r.to_id}</span>
        </Line>
      ))
    case 'overwrites':
      return plan.overwrites.map((o, i) => (
        <div key={i} className="space-y-0.5">
          <Line>
            <RowNo row={o.row} />{' '}
            <span className="font-semibold text-ink-primary">{o.experiment_id}</span>
          </Line>
          {o.fields_changed.length === 0 ? (
            <Line><span className="pl-4 text-ink-muted">no field changes</span></Line>
          ) : (
            o.fields_changed.map((f, j) => (
              <Line key={j}>
                <span className="pl-4 text-ink-muted">{f.field}:</span>{' '}
                <span className="line-through text-ink-muted">{fmtValue(f.old)}</span>{' '}
                <span className="text-status-warning">→</span>{' '}
                <span className="font-semibold text-ink-primary">{fmtValue(f.new)}</span>
              </Line>
            ))
          )}
        </div>
      ))
    case 'creates':
      return plan.creates.map((c, i) => (
        <Line key={i}>
          <RowNo row={c.row} />{' '}
          <span className="font-semibold text-ink-primary">{c.experiment_id}</span>
          {c.parent_id && <span className="text-ink-muted"> · parent {c.parent_id}</span>}
          {c.copied_from && <span className="text-ink-muted"> · copied from {c.copied_from}</span>}
        </Line>
      ))
    case 'skips':
      return plan.skips.map((s, i) => (
        <Line key={i}>
          <RowNo row={s.row} /> {s.experiment_id ?? '(no ID)'} — {s.reason}
        </Line>
      ))
  }
}

function PlanSection({ meta, rows }: { meta: SectionMeta; rows: React.ReactNode[] }) {
  const [open, setOpen] = useState(meta.defaultOpen)
  const [showAll, setShowAll] = useState(false)
  const count = rows.length
  const visible = showAll ? rows : rows.slice(0, TRUNCATE_AT)
  const hidden = count - visible.length

  return (
    <div className={`rounded border ${meta.box}`}>
      <button
        className="w-full flex items-center justify-between px-3 py-2 text-left"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className={`text-xs font-medium ${meta.heading}`}>
          {count} {count === 1 ? meta.singular : meta.plural}
        </span>
        <Chevron open={open} />
      </button>
      {open && (
        <div className="px-3 pb-2 space-y-1">
          {visible}
          {hidden > 0 && (
            <button
              className="text-2xs text-ink-muted underline hover:text-ink-secondary"
              onClick={() => setShowAll(true)}
            >
              Show {hidden} more
            </button>
          )}
          {showAll && count > TRUNCATE_AT && (
            <button
              className="text-2xs text-ink-muted underline hover:text-ink-secondary"
              onClick={() => setShowAll(false)}
            >
              Show less
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export interface UploadPlanPanelProps {
  plan: UploadPlan
}

/** Renders an UploadPlan as grouped, colour-coded sections with counts in the headers
 *  (issue #100 items 7-8). Presentational only — knows nothing about committing. */
export function UploadPlanPanel({ plan }: UploadPlanPanelProps) {
  const sections = SECTIONS
    .map((meta) => ({ meta, rows: sectionRows(plan, meta.key) }))
    .filter((s) => s.rows.length > 0)

  if (sections.length === 0) {
    return <p className="text-xs text-ink-muted">This file would make no changes.</p>
  }

  return (
    <div className="space-y-2">
      {sections.map(({ meta, rows }) => (
        <PlanSection key={meta.key} meta={meta} rows={rows} />
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Run tests and type-check**

Run: `npx vitest run src/components/bulkUploads/UploadPlanPanel.test.tsx` — Expected: 8 passed.
Run: `npx tsc --noEmit` — Expected: clean.

If the "1 create$" name matcher fails because the accessible name includes the chevron, relax it to `/^1 create/` — do not change the component to satisfy the test.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/bulkUploads/UploadPlanPanel.tsx frontend/src/components/bulkUploads/UploadPlanPanel.test.tsx
git commit -m "[#100] Add upload plan panel component

- Tests added: yes
- Docs updated: no"
```

---

### Task 3: UploadPlanModal

**Files:**
- Create: `frontend/src/components/bulkUploads/UploadPlanModal.tsx`
- Test: `frontend/src/components/bulkUploads/UploadPlanModal.test.tsx`

**Interfaces:**
- Consumes: `UploadPlanPanel` (Task 2); `BulkUploadResult` from `@/api/bulkUploads` (Task 1); `Modal`, `Button`, `Badge` from `@/components/ui`.
- Produces:
  ```ts
  export type PlanModalView = 'review' | 'stale' | 'done'
  export interface UploadPlanModalProps {
    open: boolean
    view: PlanModalView
    result: BulkUploadResult
    committing: boolean
    onCommit: () => void
    onClose: () => void
  }
  export function UploadPlanModal(props: UploadPlanModalProps): JSX.Element
  ```

**Design notes:** The re-arm checkbox is local state. It is reset by the **parent remounting the modal with `key={result.plan_hash}`** (Task 5) rather than a `useEffect` that calls `setState` — the repo's ESLint config carries a `react-hooks/set-state-in-effect` rule and a remount is the cleaner reset anyway. `Commit` is disabled when conflicts exist **regardless** of the checkbox: the conflict gate always wins.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/bulkUploads/UploadPlanModal.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { BulkUploadResult, UploadPlan } from '@/api/bulkUploads'
import { UploadPlanModal, PlanModalView } from './UploadPlanModal'

const EMPTY_PLAN: UploadPlan = {
  creates: [], renames: [], overwrites: [], skips: [], conflicts: [], counts: {},
}

function result(over: Partial<BulkUploadResult> = {}, plan: Partial<UploadPlan> = {}): BulkUploadResult {
  return {
    created: 0, updated: 0, skipped: 0, errors: [], warnings: [], feedbacks: [],
    message: '', dry_run: true, plan: { ...EMPTY_PLAN, ...plan }, plan_hash: 'h1',
    ...over,
  }
}

function renderModal(view: PlanModalView, res: BulkUploadResult, committing = false) {
  const onCommit = vi.fn()
  const onClose = vi.fn()
  render(
    <UploadPlanModal open view={view} result={res} committing={committing} onCommit={onCommit} onClose={onClose} />,
  )
  return { onCommit, onClose }
}

const THREE_CREATES = {
  creates: [
    { row: 2, experiment_id: 'HPHT_001', parent_id: null, copied_from: null },
    { row: 3, experiment_id: 'HPHT_002', parent_id: null, copied_from: null },
    { row: 4, experiment_id: 'HPHT_003', parent_id: null, copied_from: null },
  ],
}

describe('UploadPlanModal — review', () => {
  it('says nothing has been written yet', () => {
    renderModal('review', result({}, THREE_CREATES))
    expect(screen.getByText(/Nothing has been written yet/i)).toBeInTheDocument()
  })

  it('counts creates, renames and overwrites on the commit button but not skips', () => {
    renderModal('review', result({}, {
      ...THREE_CREATES,
      renames: [{ row: 5, from_id: 'A_001', to_id: 'A_001a' }],
      skips: [{ row: 6, experiment_id: null, reason: 'blank experiment_id' }],
    }))
    expect(screen.getByRole('button', { name: /Commit 4 changes/ })).toBeEnabled()
  })

  it('commits when the button is clicked', async () => {
    const { onCommit } = renderModal('review', result({}, THREE_CREATES))
    await userEvent.click(screen.getByRole('button', { name: /Commit 3 changes/ }))
    expect(onCommit).toHaveBeenCalledTimes(1)
  })

  it('disables commit entirely while conflicts are present and says why', () => {
    renderModal('review', result({}, {
      ...THREE_CREATES,
      conflicts: [{ row: 4, kind: 'rename_without_overwrite', detail: 'overwrite is not TRUE' }],
    }))
    expect(screen.getByRole('button', { name: /Commit/ })).toBeDisabled()
    expect(screen.getByText(/1 conflict must be fixed/i)).toBeInTheDocument()
  })

  it('shows a spinner label and blocks commit while committing', () => {
    renderModal('review', result({}, THREE_CREATES), true)
    expect(screen.getByRole('button', { name: /Committing/ })).toBeDisabled()
  })
})

describe('UploadPlanModal — stale', () => {
  const stale = () => result({ dry_run: false, plan_hash: 'h2', errors: ['Plan changed since preview: previewed plan hash \'h1\' does not match'] }, THREE_CREATES)

  it('says nothing was applied and keeps commit disabled until re-armed', () => {
    renderModal('stale', stale())
    expect(screen.getByText(/Nothing was applied/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Commit/ })).toBeDisabled()
  })

  it('surfaces the server reason for the rejection', () => {
    renderModal('stale', stale())
    expect(screen.getByText(/does not match/)).toBeInTheDocument()
  })

  it('arms commit once the researcher confirms they reviewed the new plan', async () => {
    renderModal('stale', stale())
    await userEvent.click(screen.getByRole('checkbox', { name: /reviewed the updated plan/i }))
    expect(screen.getByRole('button', { name: /Commit 3 changes/ })).toBeEnabled()
  })

  it('keeps commit disabled when the new plan has conflicts even after re-arming', async () => {
    renderModal('stale', result(
      { dry_run: false, plan_hash: 'h2', errors: ['Row 4: [chain_rename_conflict] target already exists'] },
      { ...THREE_CREATES, conflicts: [{ row: 4, kind: 'chain_rename_conflict', detail: 'target already exists' }] },
    ))
    await userEvent.click(screen.getByRole('checkbox', { name: /reviewed the updated plan/i }))
    expect(screen.getByRole('button', { name: /Commit/ })).toBeDisabled()
  })
})

describe('UploadPlanModal — done', () => {
  const done = result({
    created: 8, updated: 2, skipped: 1, dry_run: false,
    errors: ['Row 12: invalid status "RUNNING"'],
    warnings: ['Row 3: reactor 4 already occupied'],
  }, THREE_CREATES)

  it('reports the committed counts', () => {
    renderModal('done', done)
    expect(screen.getByText('Created: 8')).toBeInTheDocument()
    expect(screen.getByText('Updated: 2')).toBeInTheDocument()
    expect(screen.getByText('Skipped: 1')).toBeInTheDocument()
  })

  it('lists parser row errors and warnings from a successful commit', () => {
    renderModal('done', done)
    expect(screen.getByText(/invalid status/)).toBeInTheDocument()
    expect(screen.getByText(/already occupied/)).toBeInTheDocument()
  })

  it('offers only Close — no second commit', () => {
    renderModal('done', done)
    expect(screen.getByRole('button', { name: /Close/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Commit/ })).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/components/bulkUploads/UploadPlanModal.test.tsx`
Expected: FAIL — "Failed to resolve import ./UploadPlanModal".

- [ ] **Step 3: Write the component**

Create `frontend/src/components/bulkUploads/UploadPlanModal.tsx`:

```tsx
import { useState } from 'react'
import { Modal, Button, Badge } from '@/components/ui'
import { UploadPlanPanel } from './UploadPlanPanel'
import type { BulkUploadResult } from '@/api/bulkUploads'

export type PlanModalView = 'review' | 'stale' | 'done'

export interface UploadPlanModalProps {
  open: boolean
  view: PlanModalView
  /** The previewed, rejected, or committed response. Carries a non-null plan. */
  result: BulkUploadResult
  committing: boolean
  onCommit: () => void
  onClose: () => void
}

/** Review surface for a bulk-upload plan (issue #100 items 6-9).
 *
 *  Three views: `review` (preview a dry run), `stale` (the server refused the commit
 *  because the plan changed — requires explicit re-arming), and `done` (committed).
 *
 *  The re-arm checkbox is local state and is reset by the PARENT remounting this
 *  component with `key={result.plan_hash}` on every new response — not by an effect. */
export function UploadPlanModal({ open, view, result, committing, onCommit, onClose }: UploadPlanModalProps) {
  const [reviewed, setReviewed] = useState(false)
  const plan = result.plan

  const conflicts = plan?.conflicts.length ?? 0
  const changeCount = plan
    ? plan.creates.length + plan.renames.length + plan.overwrites.length
    : 0

  // The conflict gate always wins — re-arming a stale plan cannot override it.
  const commitDisabled = conflicts > 0 || (view === 'stale' && !reviewed) || committing

  const footer = view === 'done' ? (
    <Button variant="secondary" onClick={onClose}>Close</Button>
  ) : (
    <>
      {conflicts > 0 && (
        <span className="text-2xs text-status-error mr-auto max-w-md leading-relaxed">
          {conflicts} conflict{conflicts !== 1 ? 's' : ''} must be fixed in the workbook
          before this file can be committed — nothing will be applied until then.
        </span>
      )}
      <Button variant="ghost" onClick={onClose} disabled={committing}>Cancel</Button>
      <Button variant="primary" onClick={onCommit} disabled={commitDisabled} loading={committing}>
        {committing ? 'Committing…' : `Commit ${changeCount} change${changeCount !== 1 ? 's' : ''}`}
      </Button>
    </>
  )

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={view === 'done' ? 'Upload complete' : 'Review upload plan'}
      description={
        view === 'done'
          ? undefined
          : 'Nothing has been written yet. Review what this file would do, then commit.'
      }
      size="xl"
      footer={footer}
    >
      {view === 'stale' && (
        <div className="mb-3 p-3 rounded border bg-status-warning/10 border-status-warning/30 space-y-2">
          <p className="text-xs font-medium text-status-warning">
            Nothing was applied — the plan changed since you previewed it.
          </p>
          {result.errors.map((e, i) => (
            <p key={i} className="text-2xs text-ink-secondary leading-relaxed">{e}</p>
          ))}
          <label className="flex items-center gap-2 cursor-pointer select-none pt-1">
            <input
              type="checkbox"
              className="w-3.5 h-3.5 rounded accent-red-500"
              checked={reviewed}
              onChange={(e) => setReviewed(e.target.checked)}
            />
            <span className="text-xs text-ink-secondary">I&apos;ve reviewed the updated plan</span>
          </label>
        </div>
      )}

      {view === 'done' ? (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Badge variant="success">Created: {result.created}</Badge>
            <Badge variant="default">Updated: {result.updated}</Badge>
            <Badge variant="warning">Skipped: {result.skipped}</Badge>
          </div>
          {result.errors.length > 0 && (
            <div className="p-3 rounded bg-status-error/5 border border-status-error/20 space-y-1">
              {result.errors.map((e, i) => (
                <p key={i} className="text-2xs text-status-error font-mono-data">{e}</p>
              ))}
            </div>
          )}
          {result.warnings.length > 0 && (
            <div className="p-3 rounded bg-status-warning/5 border border-status-warning/20 space-y-1">
              {result.warnings.map((w, i) => (
                <p key={i} className="text-2xs text-status-warning">{w}</p>
              ))}
            </div>
          )}
        </div>
      ) : (
        plan && <UploadPlanPanel plan={plan} />
      )}
    </Modal>
  )
}
```

- [ ] **Step 4: Run tests and type-check**

Run: `npx vitest run src/components/bulkUploads/UploadPlanModal.test.tsx` — Expected: 12 passed.
Run: `npx tsc --noEmit` — Expected: clean.

Note: the checkbox is matched by `getByRole('checkbox', { name: /reviewed the updated plan/i })`, which relies on the `<label>` wrapping the input. If that lookup fails, use `screen.getByLabelText(/reviewed the updated plan/i)` — do not add an `aria-label` duplicating the visible text.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/bulkUploads/UploadPlanModal.tsx frontend/src/components/bulkUploads/UploadPlanModal.test.tsx
git commit -m "[#100] Add upload plan review modal

- Tests added: yes
- Docs updated: no"
```

---

### Task 4: `onUploadSuccess` override on UploadRow

**Files:**
- Modify: `frontend/src/pages/BulkUploadRow.tsx:33-53` (props interface), `:63-77` (destructuring), `:83-97` (mutation)
- Test: `frontend/src/pages/__tests__/BulkUploadRow.delegation.test.tsx` (create)

**Interfaces:**
- Consumes: `BulkUploadResult`, `ConflictCheckResult` (already imported in the file).
- Produces: `UploadRowProps.onUploadSuccess?: (data: BulkUploadResult | ConflictCheckResult) => void`.

**Why this exists:** a dry run returns **real** counts — the parser creates, updates and flushes before the router rolls back. Without this override, dropping a file for preview would badge "Created: 5" and toast "Upload complete — 5 created" for an upload that persisted nothing.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/__tests__/BulkUploadRow.delegation.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import type { BulkUploadResult } from '@/api/bulkUploads'
import { UploadRow } from '../BulkUploadRow'

const DRY_RUN: BulkUploadResult = {
  created: 5, updated: 2, skipped: 0, errors: [], warnings: [], feedbacks: [],
  message: '[DRY RUN] 5 created, 2 updated, 0 skipped', dry_run: true,
  plan: { creates: [], renames: [], overwrites: [], skips: [], conflicts: [], counts: {} },
  plan_hash: 'h1',
}

function renderRow(onUploadSuccess?: (d: BulkUploadResult) => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <UploadRow
          id="t" title="Test Upload" description="d" accept=".xlsx"
          uploadFn={() => Promise.resolve(DRY_RUN)}
          onUploadSuccess={onUploadSuccess}
          isOpen onToggle={vi.fn()}
        />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

async function dropFile() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  await userEvent.upload(input, new File(['x'], 'f.xlsx'))
}

describe('UploadRow — onUploadSuccess override', () => {
  it('renders its own result badges when no override is supplied', async () => {
    renderRow()
    await dropFile()
    await waitFor(() => expect(screen.getByText('Created: 5')).toBeInTheDocument())
  })

  it('delegates and renders no result summary when an override is supplied', async () => {
    const onUploadSuccess = vi.fn()
    renderRow(onUploadSuccess)
    await dropFile()
    await waitFor(() => expect(onUploadSuccess).toHaveBeenCalledWith(DRY_RUN))
    expect(screen.queryByText('Created: 5')).not.toBeInTheDocument()
    expect(screen.queryByText(/Uploaded/)).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/pages/__tests__/BulkUploadRow.delegation.test.tsx`
Expected: the first test PASSES (existing behaviour), the second FAILS — `onUploadSuccess` is not a prop, so the row still sets its own result and "Created: 5" is present.

- [ ] **Step 3: Add the prop**

In `frontend/src/pages/BulkUploadRow.tsx`, add to `UploadRowProps` immediately after the existing `onUploadError` declaration (line 50):

```ts
  /** Override success handling; defaults to setting the row's own result summary and
   *  toasting. Two-phase rows (New Experiments) supply this so a dry run's real-looking
   *  counts are never rendered as a completed upload. Mirrors `onUploadError`. */
  onUploadSuccess?: (data: BulkUploadResult | ConflictCheckResult) => void
```

Add `onUploadSuccess,` to the destructured parameter list (after `onUploadError,` on line 72).

Replace the mutation's `onSuccess` (lines 85-92) with:

```ts
    onSuccess: (data) => {
      if (onUploadSuccess) {
        onUploadSuccess(data)
        return
      }
      setResult(data)
      if (isBulkUploadResult(data)) {
        success(`Upload complete — ${data.created} created, ${data.updated} updated`)
      } else {
        success(data.message)
      }
    },
```

- [ ] **Step 4: Run tests and type-check**

Run: `npx vitest run src/pages/__tests__/BulkUploadRow.delegation.test.tsx` — Expected: 2 passed.
Run: `npx vitest run src/pages/__tests__/BulkUploads.test.tsx` — Expected: still passing, unchanged. This is the regression proof that the other 12 rows are untouched.
Run: `npx tsc --noEmit` — Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/BulkUploadRow.tsx frontend/src/pages/__tests__/BulkUploadRow.delegation.test.tsx
git commit -m "[#100] Allow UploadRow to delegate success handling

- Tests added: yes
- Docs updated: no"
```

---

### Task 5: NewExperimentsUploadRow

**Files:**
- Create: `frontend/src/pages/NewExperimentsUploadRow.tsx`
- Test: `frontend/src/pages/__tests__/NewExperimentsUploadRow.test.tsx`

**Interfaces:**
- Consumes: `UploadRow` + its `onUploadSuccess` prop (Task 4); `UploadPlanModal`, `PlanModalView` (Task 3); `bulkUploadsApi.uploadNewExperiments(file, opts)` (Task 1).
- Produces:
  ```ts
  export interface NewExperimentsUploadRowProps {
    isOpen: boolean
    onToggle: () => void
    prominent?: boolean
    topContent?: React.ReactNode
  }
  export function NewExperimentsUploadRow(props: NewExperimentsUploadRowProps): JSX.Element
  ```

**Critical logic — the rejection discriminator.** The endpoint returns HTTP 200 for success, gate rejection, *and* parser crash. The test must be structural:

```ts
const rejected = data.plan.conflicts.length > 0 || data.plan_hash !== vars.planHash
```

**Do not test on `errors.length > 0`.** The success path returns the parser's own row-level errors alongside a real commit (`backend/api/routers/bulk_uploads.py:211`), so a file that committed 8 rows and errored on 2 has non-empty `errors` *and* a non-null plan — testing on `errors` would tell the researcher "nothing was applied" about an upload that applied 8 rows.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/__tests__/NewExperimentsUploadRow.test.tsx`:

```tsx
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'

vi.mock('@/api/bulkUploads', () => ({
  bulkUploadsApi: { uploadNewExperiments: vi.fn(), downloadTemplate: vi.fn() },
  isConflictCheckResult: () => false,
}))

import { NewExperimentsUploadRow } from '../NewExperimentsUploadRow'
import { bulkUploadsApi } from '@/api/bulkUploads'
import type { BulkUploadResult, UploadPlan } from '@/api/bulkUploads'

const PLAN: UploadPlan = {
  creates: [
    { row: 2, experiment_id: 'HPHT_001', parent_id: null, copied_from: null },
    { row: 3, experiment_id: 'HPHT_002', parent_id: null, copied_from: null },
  ],
  renames: [], overwrites: [], skips: [], conflicts: [], counts: {},
}

function res(over: Partial<BulkUploadResult> = {}, plan: UploadPlan | null = PLAN): BulkUploadResult {
  return {
    created: 0, updated: 0, skipped: 0, errors: [], warnings: [], feedbacks: [],
    message: '', dry_run: true, plan, plan_hash: 'hash-1', ...over,
  }
}

let client: QueryClient

function renderRow() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <NewExperimentsUploadRow isOpen onToggle={vi.fn()} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

async function dropFile() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  await userEvent.upload(input, new File(['x'], 'exp.xlsx'))
}

const mockUpload = () => vi.mocked(bulkUploadsApi.uploadNewExperiments)

beforeEach(() => { vi.clearAllMocks() })

describe('NewExperimentsUploadRow — preview phase', () => {
  it('previews with dry_run and never commits on a file drop', async () => {
    mockUpload().mockResolvedValue(res())
    renderRow()
    await dropFile()
    await waitFor(() => expect(mockUpload()).toHaveBeenCalledTimes(1))
    expect(mockUpload()).toHaveBeenCalledWith(expect.any(File), { dryRun: true })
  })

  it('opens the review modal showing the plan', async () => {
    mockUpload().mockResolvedValue(res())
    renderRow()
    await dropFile()
    await waitFor(() => expect(screen.getByText(/Review upload plan/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /Commit 2 changes/ })).toBeEnabled()
  })

  it('does not open the modal when the parser crashed and returned no plan', async () => {
    mockUpload().mockResolvedValue(res({ errors: ['Missing experiments sheet'], message: 'Upload failed' }, null))
    renderRow()
    await dropFile()
    await waitFor(() => expect(screen.getByText(/Missing experiments sheet/)).toBeInTheDocument())
    expect(screen.queryByText(/Review upload plan/i)).not.toBeInTheDocument()
  })
})

describe('NewExperimentsUploadRow — commit phase', () => {
  it('replays the previewed plan hash and omits dry_run', async () => {
    mockUpload().mockResolvedValue(res())
    renderRow()
    await dropFile()
    await waitFor(() => screen.getByRole('button', { name: /Commit 2 changes/ }))

    mockUpload().mockResolvedValue(res({ created: 2, dry_run: false, plan_hash: 'hash-1' }))
    await userEvent.click(screen.getByRole('button', { name: /Commit 2 changes/ }))

    await waitFor(() => expect(mockUpload()).toHaveBeenCalledTimes(2))
    expect(mockUpload()).toHaveBeenLastCalledWith(expect.any(File), { planHash: 'hash-1' })
  })

  it('shows the committed counts and invalidates the next-ID chips', async () => {
    mockUpload().mockResolvedValue(res())
    renderRow()
    await dropFile()
    await waitFor(() => screen.getByRole('button', { name: /Commit 2 changes/ }))

    const spy = vi.spyOn(client, 'invalidateQueries')
    mockUpload().mockResolvedValue(res({ created: 2, updated: 0, dry_run: false, plan_hash: 'hash-1' }))
    await userEvent.click(screen.getByRole('button', { name: /Commit 2 changes/ }))

    await waitFor(() => expect(screen.getByText(/Upload complete/i)).toBeInTheDocument())
    expect(screen.getByText('Created: 2')).toBeInTheDocument()
    expect(spy).toHaveBeenCalledWith({ queryKey: ['nextIds'] })
  })

  it('treats a committed upload with parser row errors as done, not stale', async () => {
    mockUpload().mockResolvedValue(res())
    renderRow()
    await dropFile()
    await waitFor(() => screen.getByRole('button', { name: /Commit 2 changes/ }))

    // 8 rows committed, 2 rows errored — plan_hash unchanged, no conflicts.
    mockUpload().mockResolvedValue(res({
      created: 8, updated: 0, skipped: 0, dry_run: false, plan_hash: 'hash-1',
      errors: ['Row 12: invalid status "RUNNING"'],
    }))
    await userEvent.click(screen.getByRole('button', { name: /Commit 2 changes/ }))

    await waitFor(() => expect(screen.getByText(/Upload complete/i)).toBeInTheDocument())
    expect(screen.getByText('Created: 8')).toBeInTheDocument()
    expect(screen.queryByText(/Nothing was applied/i)).not.toBeInTheDocument()
  })
})

describe('NewExperimentsUploadRow — stale plan', () => {
  it('shows the stale view when the returned hash differs from the previewed one', async () => {
    mockUpload().mockResolvedValue(res())
    renderRow()
    await dropFile()
    await waitFor(() => screen.getByRole('button', { name: /Commit 2 changes/ }))

    mockUpload().mockResolvedValue(res({
      dry_run: false, plan_hash: 'hash-2',
      errors: ["Plan changed since preview: previewed plan hash 'hash-1' does not match this file's plan 'hash-2'"],
    }))
    await userEvent.click(screen.getByRole('button', { name: /Commit 2 changes/ }))

    await waitFor(() => expect(screen.getByText(/Nothing was applied/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /Commit/ })).toBeDisabled()
  })

  it('shows the stale view when the fresh plan has conflicts', async () => {
    mockUpload().mockResolvedValue(res())
    renderRow()
    await dropFile()
    await waitFor(() => screen.getByRole('button', { name: /Commit 2 changes/ }))

    mockUpload().mockResolvedValue(res({
      dry_run: false, plan_hash: 'hash-1',
      errors: ['Row 4: [chain_rename_conflict] target already exists'],
    }, { ...PLAN, conflicts: [{ row: 4, kind: 'chain_rename_conflict', detail: 'target already exists' }] }))
    await userEvent.click(screen.getByRole('button', { name: /Commit 2 changes/ }))

    await waitFor(() => expect(screen.getByText(/Nothing was applied/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /Commit/ })).toBeDisabled()
  })

  it('re-arms commit only after the researcher confirms the new plan', async () => {
    mockUpload().mockResolvedValue(res())
    renderRow()
    await dropFile()
    await waitFor(() => screen.getByRole('button', { name: /Commit 2 changes/ }))

    mockUpload().mockResolvedValue(res({ dry_run: false, plan_hash: 'hash-2', errors: ['Plan changed since preview'] }))
    await userEvent.click(screen.getByRole('button', { name: /Commit 2 changes/ }))
    await waitFor(() => screen.getByText(/Nothing was applied/i))

    await userEvent.click(screen.getByRole('checkbox', { name: /reviewed the updated plan/i }))
    expect(screen.getByRole('button', { name: /Commit 2 changes/ })).toBeEnabled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/pages/__tests__/NewExperimentsUploadRow.test.tsx`
Expected: FAIL — "Failed to resolve import ../NewExperimentsUploadRow".

- [ ] **Step 3: Write the component**

Create `frontend/src/pages/NewExperimentsUploadRow.tsx`:

```tsx
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/components/ui'
import { UploadRow } from './BulkUploadRow'
import { UploadPlanModal, PlanModalView } from '@/components/bulkUploads/UploadPlanModal'
import { bulkUploadsApi } from '@/api/bulkUploads'
import type { BulkUploadResult, ConflictCheckResult } from '@/api/bulkUploads'

const HELP_TEXT =
  'Dropping a file previews it — nothing is written until you review the plan and press Commit. ' +
  "Use the template for correct column formatting. The file must have an 'experiments' sheet; a 'conditions' sheet is optional. " +
  'Replicates: write a lowercase letter after the number (SERUM_001a, _001b, _001c) — the bare SERUM_001 (or SERUM_001-0) is replicate 0, the group parent. ' +
  'Replicate timepoints are separate vials: encode the sample day in the ID with -t<days> (SERUM_001a-t0, SERUM_001a-t7, decimals allowed like -t0.5). ' +
  'The day is locked to the ID for all results. ' +
  'To rename experiments, fill old_experiment_id AND set overwrite=TRUE — the preview will tell you if a rename would instead create a duplicate.'

export interface NewExperimentsUploadRowProps {
  isOpen: boolean
  onToggle: () => void
  /** Larger header treatment — passed through to UploadRow */
  prominent?: boolean
  /** Next-ID chips, rendered inside the expanded panel */
  topContent?: React.ReactNode
}

/** Two-phase New Experiments upload (issue #100 items 6-9).
 *
 *  A dropped file ALWAYS previews via `dry_run=true`; the only path that writes is the
 *  Commit button in the review modal, which replays the previewed `plan_hash` so a
 *  workbook or database edited in between is refused rather than applied. */
export function NewExperimentsUploadRow({
  isOpen,
  onToggle,
  prominent = false,
  topContent,
}: NewExperimentsUploadRowProps) {
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<BulkUploadResult | null>(null)
  const [view, setView] = useState<PlanModalView>('review')
  const { success, error: toastError } = useToast()
  const queryClient = useQueryClient()

  const close = () => {
    setFile(null)
    setResult(null)
    setView('review')
  }

  /** A 200 with errors and no plan is the parser-crash path
   *  (backend/api/routers/bulk_uploads.py:189) — there is nothing to review. */
  const handlePreview = (data: BulkUploadResult | ConflictCheckResult) => {
    const res = data as BulkUploadResult
    if (!res.plan) {
      toastError('Preview failed', res.errors[0] ?? res.message)
      setFile(null)
      return
    }
    setResult(res)
    setView('review')
  }

  const commitMutation = useMutation({
    mutationFn: ({ f, planHash }: { f: File; planHash: string }) =>
      bulkUploadsApi.uploadNewExperiments(f, { planHash }),
    onSuccess: (data, vars) => {
      if (!data.plan) {
        toastError('Upload failed', data.errors[0] ?? data.message)
        close()
        return
      }
      setResult(data)

      // Structural test, mirroring the only two things that populate the server's
      // plan gate. NOT `errors.length > 0` — a successful commit also returns the
      // parser's own row errors, so that would report "nothing applied" for an
      // upload that applied most of the file.
      const rejected = data.plan.conflicts.length > 0 || data.plan_hash !== vars.planHash
      if (rejected) {
        setView('stale')
        return
      }

      setView('done')
      success(`Upload complete — ${data.created} created, ${data.updated} updated`)
      // Creating experiments moves the next-ID chips (staleTime 60s).
      queryClient.invalidateQueries({ queryKey: ['nextIds'] })
    },
    onError: (err: Error) => {
      // Keep the modal on its current view so the reviewed plan is not lost.
      toastError('Upload failed', err.message)
    },
  })

  return (
    <>
      <UploadRow
        id="new-experiments"
        title="New Experiments"
        description="Bulk-create experiments from a structured Excel template — previews before writing"
        helpText={HELP_TEXT}
        accept=".xlsx,.xls"
        uploadFn={(f) => {
          setFile(f)
          return bulkUploadsApi.uploadNewExperiments(f, { dryRun: true })
        }}
        onUploadSuccess={handlePreview}
        templateType="new-experiments"
        topContent={topContent}
        prominent={prominent}
        isOpen={isOpen}
        onToggle={onToggle}
      />
      {result?.plan && (
        <UploadPlanModal
          // Remounting on a new hash resets the modal's re-arm checkbox.
          key={result.plan_hash ?? 'no-hash'}
          open
          view={view}
          result={result}
          committing={commitMutation.isPending}
          onCommit={() => {
            if (file && result.plan_hash) {
              commitMutation.mutate({ f: file, planHash: result.plan_hash })
            }
          }}
          onClose={close}
        />
      )}
    </>
  )
}
```

- [ ] **Step 4: Run tests and type-check**

Run: `npx vitest run src/pages/__tests__/NewExperimentsUploadRow.test.tsx` — Expected: 9 passed.
Run: `npx tsc --noEmit` — Expected: clean.

If the "shows the stale view when the fresh plan has conflicts" test fails because the modal did not remount (same `plan_hash`), that is a genuine finding, not a test bug: the re-arm checkbox would carry over. Fix it by keying on `` `${result.plan_hash}-${view}` `` and note the change.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/NewExperimentsUploadRow.tsx frontend/src/pages/__tests__/NewExperimentsUploadRow.test.tsx
git commit -m "[#100] Add preview-first New Experiments upload row

- Tests added: yes
- Docs updated: no"
```

---

### Task 6: Wire into the page, fix E2E, update the user guide

**Files:**
- Modify: `frontend/src/pages/BulkUploads.tsx:1-6` (imports), `:258-271` (the New Experiments row)
- Modify: `frontend/e2e/journeys/02-bulk-upload-experiments.spec.ts`
- Modify: `docs/user_guide/BULK_UPLOADS.md` (section 5, line 135)

**Interfaces:**
- Consumes: `NewExperimentsUploadRow` (Task 5).
- Produces: nothing for later tasks.

- [ ] **Step 1: Swap the row in**

In `frontend/src/pages/BulkUploads.tsx`, add to the imports after line 6:

```ts
import { NewExperimentsUploadRow } from './NewExperimentsUploadRow'
```

Replace the whole `{/* 4 — New Experiments */}` block (lines 258-271) with:

```tsx
        {/* 4 — New Experiments — preview-first (issue #100 items 6-9) */}
        <NewExperimentsUploadRow
          topContent={<NextIdChips data={nextIds} />}
          prominent
          isOpen={isOpen('new-experiments')}
          onToggle={() => toggle('new-experiments')}
        />
```

The title, description and help text now live in `NewExperimentsUploadRow`, matching how `ActlabsUploadRow` owns its own copy.

- [ ] **Step 2: Run the full frontend suite**

Run from `frontend/`: `npx vitest run`
Expected: every test passes. `src/pages/__tests__/BulkUploads.test.tsx` must pass **unchanged** — that is the proof the other 12 rows still commit in one shot.

Run: `npx tsc --noEmit` — Expected: clean.
Run: `npx eslint src --ext .ts,.tsx` — Expected: exactly the 5 pre-existing errors listed in Global Constraints, none in new files.

- [ ] **Step 3: Fix the E2E spec**

`frontend/e2e/journeys/02-bulk-upload-experiments.spec.ts:26` waits for `Created:` badges immediately after the drop. With preview-first that never appears until the plan is committed. Replace the file body from the `setInputFiles` line onward:

```ts
  const fileInput = card.locator('input[type="file"]')
  await fileInput.setInputFiles(SAMPLE_FILE)

  // Preview-first: the drop opens a review modal and writes nothing yet (issue #100)
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('Review upload plan')).toBeVisible({ timeout: 15_000 })
  await expect(dialog.getByText(/Nothing has been written yet/i)).toBeVisible()

  // No conflicts in the sample template, so commit is available
  const commit = dialog.getByRole('button', { name: /^Commit \d+ change/ })
  await expect(commit).toBeEnabled()
  await commit.click()

  // Committed — the modal reports the real counts
  await expect(dialog.getByText('Upload complete')).toBeVisible({ timeout: 15_000 })
  await expect(dialog.getByText(/Created: \d+/)).toBeVisible()
})
```

Do **not** run the Playwright suite as part of this task — it needs the dev server, a Firebase login, and it writes real rows. Leave it for the manual verification step and report that it was not run.

- [ ] **Step 4: Update the user guide**

In `docs/user_guide/BULK_UPLOADS.md`, read section `## 5 — New Experiments` (from line 135) and add a subsection immediately under its heading, matching the surrounding tone and heading depth:

```markdown
### Preview before it writes

Dropping a file here does not change anything. It runs the upload against the database
and then rolls it back, so what you get is a **plan**: every experiment that would be
created, every rename, every field that would be overwritten (with its current value
next to the new one), and every row that would be skipped. Nothing is written until you
press **Commit**.

If the plan contains a conflict — most commonly an `old_experiment_id` filled in without
`overwrite=TRUE`, which would silently create a duplicate instead of renaming — Commit is
disabled and the whole file is refused. Fix the workbook and drop it again.

Between previewing and committing, the plan is pinned by a fingerprint. If the workbook
changes on disk, or another researcher edits one of the experiments the plan would
overwrite, the commit is refused and you are shown the new plan to review before you can
proceed.
```

The `PostToolUse` hook copies the file to `docs/project_context/` automatically — do not write there directly.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/BulkUploads.tsx frontend/e2e/journeys/02-bulk-upload-experiments.spec.ts docs/user_guide/BULK_UPLOADS.md docs/project_context/BULK_UPLOADS.md
git commit -m "[#100] Make New Experiments upload preview-first

- Wires the preview row into the page, fixes the E2E journey
- Tests added: yes (E2E rewritten; unit tests in prior tasks)
- Docs updated: yes"
```

---

## Manual Verification (required before merge)

Automated tests do not cover this — the issue-log entries for #99 record two real defects (a 4×`404` burst and wrong pluralisation) that a 152-test suite missed and only a manual walkthrough caught.

Vite and uvicorn are assumed already running. **Never start or stop either.** If unreachable, report to the user and stop.

Using the Chrome DevTools MCP against `http://localhost:5173/bulk-uploads`:

- [ ] Drop `docs/sample_data/new_experiments_template.xlsx`. Confirm the modal opens, the plan lists the creates, and **no** experiment appears in the database yet (check `/experiments` in another tab, or the network trace showing only one POST).
- [ ] Confirm the network request carried `dry_run=true`.
- [ ] Press Commit. Confirm a second POST carries `plan_hash` and no `dry_run`, the modal switches to "Upload complete", and the counts are real.
- [ ] Confirm the Next-ID chips advanced after the commit without a page reload.
- [ ] Build a workbook with `old_experiment_id` filled and `overwrite` blank. Confirm the conflict section is expanded, Commit is disabled with the reason shown, and no rows were written.
- [ ] Check the console for errors across all of the above. Zero expected.
- [ ] Delete any experiments created during verification, and report what was created and removed.

## Self-Review Notes

Checked against the spec: every one of items 6–9 maps to a task (6 → Tasks 1/5/6, 7 → Task 2, 8 → Task 2, 9 → Task 3). Decisions D1–D4 are implemented in Tasks 6, 3, 3, and 3 respectively. The rejection discriminator correction from the spec review is pinned by a named test in Task 5. Type names are consistent across tasks: `UploadPlan`, `PlanModalView`, `onUploadSuccess`, `uploadNewExperiments(file, opts)`.
