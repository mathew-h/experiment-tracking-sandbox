# Wizard Description + Notes Retype Control (issue #122, PR-B0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the New Experiment wizard save its Step 1 text as the experiment's `description` note, and let a researcher change any note's type from the Notes tab within the scope the database allows, so the wizard-created experiments that lost their description since the 2026-09-23 deploy can be repaired by hand.

**Architecture:** Frontend only; no schema, backend or locked-file change. The wizard passes `note_type: 'description'` to the existing `experimentsApi.addNote` and refreshes the dashboard query on success. In `NotesTab.tsx` the read-only type `Badge` on each note becomes a native `<select>` whose options mirror the `ck_note_scope` CHECK constraint (experiment-level: `observation`/`description`; timepoint: `observation`/`modification`/`result_note`); changing it calls the existing `PATCH /experiments/{id}/notes/{note_id}` with `{ note_type }`, which already returns 422 on a scope violation, 409 on a second description, and writes one `ModificationsLog` row.

**Tech Stack:** React 18 + TypeScript strict + TanStack Query v5 + Tailwind (no hex literals, no inline styles); vitest + Testing Library + `@testing-library/user-event`; existing Axios client whose interceptor lifts FastAPI `detail` into `error.message`.

**Spec:** `docs/working/issues/07-notes-overhaul-phase-2.md`, section "PR-B0: wizard description + retype control", plus design decisions 7 and 8 in §3 of that file. The four gap decisions made in-session on 2026-09-24 (recorded here because the spec is silent): (1) the "(already set)" check excludes the note being retyped, so the description note itself reads "Description" and may be demoted to Observation; (2) a note's select is disabled while its own retype is in flight; (3) the two existing badge-span assertions in `TypedNotes.test.tsx` become assertions on select values; (4) the wizard test drives the real four-step wizard with the API modules mocked, because `index.tsx` does not export its mutation.

## Global Constraints

- Branch `fix/notes-entry-and-retype` off `develop` (`db85cf4`); PR base `develop` (`gh pr create --base develop`). Do NOT stack on `feat/notes-review-queue` (PR #123).
- Commit format `[#122] <imperative, <50 chars, no trailing period>` with `- Tests added: yes/no` / `- Docs updated: yes/no` lines and a final `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` line. Multi-line messages go through `git commit -F <scratchpad file>` (PowerShell here-strings break on embedded quotes).
- No schema change. No file under `backend/`, `database/`, or `alembic/` is touched.
- Nothing becomes required (design decision 4): a blank wizard description still writes no note.
- Frontend rules: functional components, props interfaces, React Query for all server state, Tailwind classes only, no hex literals, no `console.log`, ESLint zero new warnings.
- `frontend/package.json` and `package-lock.json` are not touched (no new dependency).
- Run frontend commands from `frontend/`: `npx vitest run <path>`, `npx eslint src --ext .ts,.tsx`, `npx tsc --noEmit`. Known baseline on `develop` (#106): 5 eslint problems and 3 tsc errors in `ResultsTab.columns.test.tsx` — those are not yours to fix and must not grow.
- Keep `aria-label="Note type"` on every retype select; tests and the PR-C timeline rely on it.
- Do not edit `docs/project_context/` directly; the PostToolUse hook copies any `docs/` edit made with the Edit/Write tools. A scripted doc edit must be followed by `python -c "from importlib import import_module; import_module('sync_docs_to_project_context').full_sync()"` run from `.claude/hooks/` — prefer the Edit tool.

## Review Focus

Inputs the spec implies but names no test for; each is pinned in the owning task.

1. **The description note's own select** — must show "Description" selected and enabled, not "Description (already set)" disabled; a researcher must be able to demote it to Observation. Pinned in Task 2.
2. **A rejected retype (409/422)** — the select must snap back to the note's real type (it is a controlled input bound to `n.note_type`, so no local state may hold the attempted value) and the server's `detail` must reach the toast. Pinned in Task 2.
3. **Wizard description containing only whitespace** — today `if (step1.note)` treats `"  "` as truthy and posts a blank note. The spec says blank ⇒ no note; the server's `_clean` is not applied on `POST notes`. Task 1 trims before the guard and pins it.
4. **A timepoint note whose experiment already has a description** — the timepoint menu must not gain a disabled "Description (already set)" entry; Description is simply absent. Pinned in Task 2.
5. **Retype to the note's current type** — a native `<select>` fires no `change` event when the value does not change, so no PATCH is sent; nothing to code, but the Task 2 implementation must not add an `onBlur`/`onClick` handler that would.

---

### Task 1: Type the wizard's description note and refresh the dashboard

**Files:**
- Modify: `frontend/src/pages/NewExperiment/index.tsx:131-134` (the addNote call) and `:188-189` (`onSuccess` invalidation)
- Create: `frontend/src/pages/NewExperiment/__tests__/NewExperiment.description.test.tsx`

**Interfaces:**
- Consumes: `experimentsApi.addNote(experimentId: string, text: string, opts: Omit<NoteCreate, 'note_text'> = {})` from `frontend/src/api/experiments.ts:353` — `opts` already accepts `{ note_type?: NoteType; result_id?: number }`.
- Produces: nothing other tasks depend on.

Background for the implementer: the wizard is four steps (`Step1BasicInfo` → `Step2Conditions` → `Step3Additives` → `Step4Review`). Step 1's "Next" is disabled until an experiment type is chosen AND the ID field is non-blank AND the debounced (300 ms) `useExperimentIdValidation` hook has resolved to `available` via `experimentsApi.checkExists`. Choosing a type triggers `experimentsApi.nextId`, which auto-fills the ID. Steps 2 and 3 have no gate when left empty. Step 4's button reads "Create Experiment". The page also renders `CopyFromExisting` (calls `experimentsApi.list`) and `SampleSelector` (calls `samplesApi.list`, only when opened). All of these must be mocked; none are under test.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/pages/NewExperiment/__tests__/NewExperiment.description.test.tsx`:

```tsx
/** Issue #122 PR-B0: the wizard's Step 1 text is the experiment's `description`
 *  note (design decision 7), and creating an experiment refreshes the dashboard
 *  so the new reactor card shows it without a reload. */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import { experimentsApi } from '@/api/experiments'
import { NewExperimentPage } from '../index'

const { mockNavigate } = vi.hoisted(() => ({ mockNavigate: vi.fn() }))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    nextId: vi.fn(() => Promise.resolve({ next_id: 'HPHT_900' })),
    checkExists: vi.fn(() => Promise.resolve({ exists: false })),
    list: vi.fn(() => Promise.resolve({ items: [], total: 0 })),
    create: vi.fn(() => Promise.resolve({ id: 42, experiment_id: 'HPHT_900' })),
    addNote: vi.fn(() => Promise.resolve({})),
    createReplicates: vi.fn(),
  },
}))

vi.mock('@/api/conditions', () => ({
  conditionsApi: {
    create: vi.fn(() => Promise.resolve({})),
    getByExperiment: vi.fn(),
  },
}))

vi.mock('@/api/chemicals', () => ({
  chemicalsApi: {
    listCompounds: vi.fn(() => Promise.resolve([])),
    listExperimentAdditives: vi.fn(() => Promise.resolve([])),
    upsertAdditive: vi.fn(),
  },
}))

vi.mock('@/api/samples', () => ({
  samplesApi: {
    list: vi.fn(() => Promise.resolve({ items: [], total: 0 })),
  },
}))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const utils = render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>{ui}</MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
  return { ...utils, qc }
}

/** Drive the four-step wizard to submission. `description` is typed into the
 *  Step 1 "Experiment Description (optional)" textarea when given. */
async function createExperiment(user: ReturnType<typeof userEvent.setup>, description?: string) {
  await user.selectOptions(screen.getByLabelText(/experiment type/i), 'HPHT')
  await waitFor(() =>
    expect((screen.getByLabelText(/^experiment id/i) as HTMLInputElement).value).toBe('HPHT_900'),
  )
  if (description !== undefined) {
    await user.type(screen.getByPlaceholderText(/describe the experiment/i), description)
  }
  const next1 = screen.getByRole('button', { name: /next: conditions/i })
  // Step 1's Next waits on the 300 ms debounced ID-availability check.
  await waitFor(() => expect(next1).not.toBeDisabled(), { timeout: 2000 })
  await user.click(next1)
  await user.click(screen.getByRole('button', { name: /next: additives/i }))
  await user.click(screen.getByRole('button', { name: /next: review/i }))
  await user.click(screen.getByRole('button', { name: /create experiment/i }))
  await waitFor(() => expect(experimentsApi.create).toHaveBeenCalled())
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('NewExperimentPage — description note', () => {
  it('saves the Step 1 description as a note typed description', async () => {
    const user = userEvent.setup()
    wrap(<NewExperimentPage />)
    await createExperiment(user, 'Baseline serpentinite run')
    await waitFor(() =>
      expect(experimentsApi.addNote).toHaveBeenCalledWith(
        'HPHT_900', 'Baseline serpentinite run', { note_type: 'description' },
      ),
    )
    expect(experimentsApi.addNote).toHaveBeenCalledTimes(1)
  })

  it('writes no note when the description is blank', async () => {
    const user = userEvent.setup()
    wrap(<NewExperimentPage />)
    await createExperiment(user)
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/experiments/HPHT_900'))
    expect(experimentsApi.addNote).not.toHaveBeenCalled()
  })

  it('writes no note when the description is only whitespace', async () => {
    const user = userEvent.setup()
    wrap(<NewExperimentPage />)
    await createExperiment(user, '   ')
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/experiments/HPHT_900'))
    expect(experimentsApi.addNote).not.toHaveBeenCalled()
  })

  it('invalidates the dashboard and experiments queries on success', async () => {
    const user = userEvent.setup()
    const { qc } = wrap(<NewExperimentPage />)
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    await createExperiment(user, 'Baseline serpentinite run')
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['dashboard'] }))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['experiments'] })
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npx vitest run src/pages/NewExperiment/__tests__/NewExperiment.description.test.tsx`

Expected: the first test FAILS on `toHaveBeenCalledWith` (addNote is called with two arguments, no `{ note_type }`); the whitespace test FAILS (addNote IS called with `'   '`); the invalidation test FAILS (`['dashboard']` never invalidated). The blank-description test PASSES already — that is fine, it pins existing behaviour.

If instead the suite fails before reaching an assertion (e.g. "Unable to find a label with the text of: /experiment type/i" or a missing mock method), fix the harness in the test file, not the component — the labels above were read from `Step1BasicInfo.tsx` (`label="Experiment Type *"`, `label="Experiment ID *"`, placeholder `Describe the experiment conditions…`), `Step2Conditions.tsx` (`Next: Additives →`), `Step3Additives.tsx` (`Next: Review →`) and `Step4Review.tsx` (`Create Experiment`).

- [ ] **Step 3: Make the change**

In `frontend/src/pages/NewExperiment/index.tsx`, replace lines 131-134:

```tsx
      // 2. Add condition note if provided
      if (step1.note) {
        await experimentsApi.addNote(exp.experiment_id, step1.note)
      }
```

with:

```tsx
      // 2. The Step 1 text is the experiment's description (issue #122, design
      //    decision 7). Every reader — reactor card, detail header, v_experiments —
      //    resolves the description by note_type, so an untyped note would be
      //    invisible as a description. Blank or whitespace writes no note.
      const description = step1.note.trim()
      if (description) {
        await experimentsApi.addNote(exp.experiment_id, description, { note_type: 'description' })
      }
```

Then in `onSuccess` (line 189), directly after `queryClient.invalidateQueries({ queryKey: ['experiments'] })`, add:

```tsx
      // The new experiment may occupy a reactor slot; its card shows the description.
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run src/pages/NewExperiment/__tests__/NewExperiment.description.test.tsx`
Expected: 4 passed.

Then run the whole NewExperiment folder to confirm nothing else moved: `npx vitest run src/pages/NewExperiment`
Expected: all passed (the existing `Step3Additives.test.tsx` is untouched).

- [ ] **Step 5: Lint and type-check the touched files**

Run: `npx eslint src/pages/NewExperiment --ext .ts,.tsx` → expected: no output (0 problems in this folder).
Run: `npx tsc --noEmit` → expected: only the 3 baseline errors in `ResultsTab.columns.test.tsx`.

- [ ] **Step 6: Commit**

Write the message to a scratchpad file, then:

```bash
git add frontend/src/pages/NewExperiment/index.tsx frontend/src/pages/NewExperiment/__tests__/NewExperiment.description.test.tsx
git commit -F <scratchpad>/msg1.txt
```

`msg1.txt`:
```
[#122] Type the wizard description note as description

- NewExperiment/index.tsx: addNote gets note_type 'description'; text is
  trimmed so whitespace writes no note; onSuccess invalidates ['dashboard']
- Tests added: yes (NewExperiment.description.test.tsx, 4)
- Docs updated: no

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 2: Retype control in the Notes tab

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/NotesTab.tsx` (imports `:3-5`, `typeBadgeVariant` `:14-18`, mutations after `resolveNote` `:59-66`, the badge at `:150`)
- Modify: `frontend/src/pages/ExperimentDetail/__tests__/TypedNotes.test.tsx` (`wrap` `:40-47`, the `NotesTab — typed notes` block `:141-184`)

**Interfaces:**
- Consumes: `experimentsApi.patchNote(experimentId: string, noteId: number, patch: NotePatch)` where `NotePatch = { note_text?: string; note_type?: NoteType; needs_review?: boolean }` (`frontend/src/api/experiments.ts:28-32, 358`); `NOTE_TYPE_LABELS: Record<NoteType, string>` and `NoteType` from `@/api/noteTypes`.
- Produces: a per-note `<select aria-label="Note type">` whose options are the scoped types. PR-C's timeline keeps this control.

Background: `NotesTab` receives every note on the experiment (experiment-level AND result-scoped — `ExperimentDetail/index.tsx` passes `experiment.notes`), renders newest-first (`[...notes].reverse()`), and already has add/edit/resolve/delete mutations plus a shared `invalidate()` for `['experiment', experimentId]`. The backend PATCH (`backend/api/routers/experiments.py::patch_note`) rejects `description` on a result-scoped note and `modification`/`result_note` on an experiment-level note with 422, and a second description with 409; the Axios interceptor puts that `detail` string in `error.message`, which is what the existing `onError` handlers toast.

- [ ] **Step 1: Update the two existing assertions and add the new tests**

In `frontend/src/pages/ExperimentDetail/__tests__/TypedNotes.test.tsx`:

(a) Replace the `wrap` helper (lines 40-47) so tests can spy on the query client:

```tsx
function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const utils = render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  )
  return { ...utils, qc }
}
```

(b) Add this helper directly below `wrap`:

```tsx
/** The value of every <option> in a select, in DOM order. */
const optionValues = (s: HTMLSelectElement) => Array.from(s.options).map((o) => o.value)
```

(c) Replace the test `'labels each note with its type and flags the review queue'` (lines 148-155) with:

```tsx
  it('labels each note with its type via a scoped select and flags the review queue', () => {
    wrap(<NotesTab experimentId="HPHT_001" notes={notes} />)
    // Feed is newest-first: id 3 (observation), id 2 (timepoint observation), id 1 (description).
    const selects = screen.getAllByLabelText('Note type') as HTMLSelectElement[]
    expect(selects.map((s) => s.value)).toEqual(['observation', 'observation', 'description'])
    expect(screen.getByText('Needs review')).toBeInTheDocument()
    expect(screen.getByText(/Review queue only \(1\)/)).toBeInTheDocument()
  })
```

(d) Append these tests inside the same `describe('NotesTab — typed notes', …)` block, after `'adding a note sends the chosen type…'`:

```tsx
  it('offers only the types valid for each note’s anchor (mirrors ck_note_scope)', () => {
    wrap(<NotesTab experimentId="HPHT_001" notes={notes} />)
    const [expLevel, timepoint, description] = screen.getAllByLabelText('Note type') as HTMLSelectElement[]
    expect(optionValues(expLevel)).toEqual(['observation', 'description'])
    expect(optionValues(timepoint)).toEqual(['observation', 'modification', 'result_note'])
    expect(optionValues(description)).toEqual(['observation', 'description'])
  })

  it('disables Description "(already set)" on other experiment-level notes but not on the description itself', () => {
    wrap(<NotesTab experimentId="HPHT_001" notes={notes} />)
    const [expLevel, timepoint, description] = screen.getAllByLabelText('Note type') as HTMLSelectElement[]
    const taken = within(expLevel).getByRole('option', { name: 'Description (already set)' }) as HTMLOptionElement
    expect(taken.disabled).toBe(true)
    const own = within(description).getByRole('option', { name: 'Description' }) as HTMLOptionElement
    expect(own.disabled).toBe(false)
    // A timepoint note never lists Description at all — not even disabled.
    expect(within(timepoint).queryByRole('option', { name: /description/i })).toBeNull()
  })

  it('retypes an experiment-level observation to Description through PATCH when none exists', async () => {
    const user = userEvent.setup()
    const { qc } = wrap(
      <NotesTab experimentId="HPHT_001" notes={[note({ id: 3, note_text: 'A plain observation' })]} />,
    )
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    const select = screen.getByLabelText('Note type') as HTMLSelectElement
    const desc = within(select).getByRole('option', { name: 'Description' }) as HTMLOptionElement
    expect(desc.disabled).toBe(false)
    await user.selectOptions(select, 'description')
    expect(experimentsApiModule.experimentsApi.patchNote).toHaveBeenCalledWith(
      'HPHT_001', 3, { note_type: 'description' },
    )
    // Retyping to/from description changes the reactor card, so the dashboard refetches too.
    await vi.waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['dashboard'] }))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['experiment', 'HPHT_001'] })
  })

  it('retypes a timepoint note to Modification through PATCH', async () => {
    const user = userEvent.setup()
    wrap(<NotesTab experimentId="HPHT_001" notes={[note({ id: 2, note_text: 'brine swapped', result_id: 5 })]} />)
    await user.selectOptions(screen.getByLabelText('Note type'), 'modification')
    expect(experimentsApiModule.experimentsApi.patchNote).toHaveBeenCalledWith(
      'HPHT_001', 2, { note_type: 'modification' },
    )
  })

  it('shows the server detail in a toast when a retype is rejected, and the select keeps the real type', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApiModule.experimentsApi.patchNote).mockRejectedValueOnce(
      new Error("Experiment 'HPHT_001' already has a description note."),
    )
    wrap(<NotesTab experimentId="HPHT_001" notes={[note({ id: 3, note_text: 'A plain observation' })]} />)
    const select = screen.getByLabelText('Note type') as HTMLSelectElement
    await user.selectOptions(select, 'description')
    expect(await screen.findByText(/already has a description note/)).toBeInTheDocument()
    // Controlled input bound to the note's stored type: no optimistic value survives the failure.
    expect(select.value).toBe('observation')
  })
```

- [ ] **Step 2: Run the file to verify the new tests fail**

Run (from `frontend/`): `npx vitest run src/pages/ExperimentDetail/__tests__/TypedNotes.test.tsx`

Expected: the rewritten `'labels each note…'` test and the five new tests FAIL with "Unable to find a label with the text of: Note type". The two `ResultsTab` tests, the review-filter test, the Mark-reviewed test, the add-note test and the two `AddResultsModal` tests still PASS.

- [ ] **Step 3: Implement the retype select**

In `frontend/src/pages/ExperimentDetail/NotesTab.tsx`:

(a) Delete the `typeBadgeVariant` function (lines 14-18). `Badge` stays imported — it still renders "Needs review".

(b) Add, directly below `ADDABLE_TYPES` (after line 12):

```tsx
/** Types a note may be retyped to, given its anchor — the UI mirror of the
 *  ck_note_scope CHECK (issue #122, design decision 8). The DB stays the
 *  authority: an invalid combination is still a 422 from PATCH. */
function retypeOptions(n: ExperimentNote): NoteType[] {
  return n.result_id == null
    ? ['observation', 'description']
    : ['observation', 'modification', 'result_note']
}
```

(c) Add a fourth mutation directly after `resolveNote` (after line 66):

```tsx
  const retypeNote = useMutation({
    mutationFn: ({ noteId, noteType }: { noteId: number; noteType: NoteType }) =>
      experimentsApi.patchNote(experimentId, noteId, { note_type: noteType }),
    onSuccess: (_data, { noteType }) => {
      invalidate()
      // To or from 'description' changes what the reactor card shows.
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      success('Note type changed', NOTE_TYPE_LABELS[noteType])
    },
    onError: (err: Error) => toastError('Failed to change note type', err.message),
  })
```

(d) Replace the badge at line 150:

```tsx
                <Badge variant={typeBadgeVariant(n.note_type)}>{NOTE_TYPE_LABELS[n.note_type]}</Badge>
```

with a select. Compute `descriptionHeldByOther` inline — it must exclude the note itself (Review Focus 1):

```tsx
                <select
                  aria-label="Note type"
                  value={n.note_type}
                  disabled={retypeNote.isPending && retypeNote.variables?.noteId === n.id}
                  onChange={(e) => retypeNote.mutate({ noteId: n.id, noteType: e.target.value as NoteType })}
                  className="text-xs px-2 py-1 border border-surface-border rounded bg-surface-raised text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50 disabled:opacity-40"
                >
                  {retypeOptions(n).map((t) => {
                    const taken =
                      t === 'description' &&
                      notes.some((m) => m.note_type === 'description' && m.id !== n.id)
                    return (
                      <option key={t} value={t} disabled={taken}>
                        {NOTE_TYPE_LABELS[t]}{taken ? ' (already set)' : ''}
                      </option>
                    )
                  })}
                </select>
```

Do not add `onBlur` or `onClick` handlers (Review Focus 5). Do not keep the attempted value in local state (Review Focus 2) — the select is bound to `n.note_type`, and the refetch after a successful PATCH is what moves it.

- [ ] **Step 4: Run the file to verify everything passes**

Run: `npx vitest run src/pages/ExperimentDetail/__tests__/TypedNotes.test.tsx`
Expected: 13 passed (8 existing incl. the rewritten one, +5 new).

Then the sibling suite that also renders `NotesTab`: `npx vitest run src/pages/ExperimentDetail/__tests__/NotesTab.buttons.test.tsx`
Expected: 3 passed, unchanged.

- [ ] **Step 5: Lint and type-check**

Run: `npx eslint src/pages/ExperimentDetail --ext .ts,.tsx` → expected: only the pre-existing #106 baseline problems (compare against `git stash`-free baseline by running the same command on `develop` if unsure: `git show develop:frontend/src/pages/ExperimentDetail/NotesTab.tsx` should be the only difference in this folder). A leftover unused `typeBadgeVariant` would appear here as `no-unused-vars` — remove it.
Run: `npx tsc --noEmit` → expected: only the 3 baseline errors in `ResultsTab.columns.test.tsx`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/NotesTab.tsx frontend/src/pages/ExperimentDetail/__tests__/TypedNotes.test.tsx
git commit -F <scratchpad>/msg2.txt
```

`msg2.txt`:
```
[#122] Add scoped retype select to the Notes tab

- NotesTab.tsx: the type badge becomes a <select aria-label="Note type">
  offering only the types ck_note_scope allows for the note's anchor;
  Description is disabled "(already set)" when another note holds it;
  PATCH {note_type}; invalidates ['experiment', id] and ['dashboard']
- Tests added: yes (TypedNotes.test.tsx +5, one assertion rewritten)
- Docs updated: no

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 3: Docs, issue-log, full frontend verification

**Files:**
- Modify: `docs/user_guide/USER_MANUAL.md` (the "Experiments" row in "Main Pages", `:28`; the "Common Tasks" table, `:49-60`)
- Modify: `docs/working/issue-log.md` (append one entry at the end)

**Interfaces:** none.

Use the Edit tool for `USER_MANUAL.md` so the PostToolUse hook copies it to `docs/project_context/`. `docs/working/` is excluded from the hook by design.

- [ ] **Step 1: Update the user manual**

In `docs/user_guide/USER_MANUAL.md`, change the Experiments row of the "Main Pages" table from:

```
| **Experiments** (`/experiments`) | List all experiments. Click an experiment to open its detail view with Conditions, Results, and Analysis tabs. |
```
to:
```
| **Experiments** (`/experiments`) | List all experiments. Click an experiment to open its detail view with Conditions, Results, Notes, and Analysis tabs. |
```

In the "Common Tasks" table, insert two rows after `| View all results for an experiment | Open an experiment → **Results** tab |`:

```
| Add or fix an experiment's description | Fill in "Experiment Description" in step 1 of **New Experiment**; it is saved as the experiment's Description note and shows on the reactor card and detail header. To fix one later, open the experiment → **Notes** tab → change the note's type to **Description** |
| Change a note's type | Open an experiment → **Notes** tab → use the type dropdown on the note. Experiment-level notes can be Observation or Description; notes on a timepoint can be Observation, Modification or Result note. Only one Description is allowed per experiment |
```

- [ ] **Step 2: Confirm the hook synced the manual**

Run (from the repo root): `git status --short docs/`
Expected: both `docs/user_guide/USER_MANUAL.md` and `docs/project_context/USER_MANUAL.md` show as modified. If the `project_context` copy is missing, run from `.claude/hooks/`: `python -c "import sync_docs_to_project_context as s; s.full_sync()"`.

- [ ] **Step 3: Full frontend verification**

From `frontend/`, run and record the counts (they go in the issue-log entry and the PR body):

```
npx vitest run
npx eslint src --ext .ts,.tsx
npx tsc --noEmit
```

Expected: vitest all files passed (develop baseline was 235 in 34 files on 2026-09-23; this branch adds 9 tests in 1 new file); eslint shows exactly the 5 baseline problems; tsc shows exactly the 3 baseline errors in `ResultsTab.columns.test.tsx`. If any count other than "tests passed" grew, that is a regression to fix before committing.

- [ ] **Step 4: Append the issue-log entry**

Append to `docs/working/issue-log.md` (replace the bracketed counts with the real ones from Step 3):

```markdown

## 2026-09-24 | issue #122 PR-B0 — Wizard description typed; Notes tab retype control (`fix/notes-entry-and-retype`)
- **Files changed:**
  - `frontend/src/pages/NewExperiment/index.tsx` — Step 1 text posted with `note_type: 'description'` (design decision 7); trimmed so whitespace writes no note; `onSuccess` also invalidates `['dashboard']`
  - `frontend/src/pages/ExperimentDetail/NotesTab.tsx` — the read-only type badge is now a `<select aria-label="Note type">` scoped to the note's anchor (experiment-level: Observation/Description; timepoint: Observation/Modification/Result note), mirroring `ck_note_scope`; Description disabled "(already set)" when another note holds it (the description note's own menu is not disabled); PATCH `{note_type}`; invalidates `['experiment', id]` and `['dashboard']`; server 422/409 `detail` shown in the toast
  - Tests: `NewExperiment/__tests__/NewExperiment.description.test.tsx` (4, new), `ExperimentDetail/__tests__/TypedNotes.test.tsx` (+5, one badge assertion rewritten to read the selects)
  - Docs: `docs/user_guide/USER_MANUAL.md` (Notes tab named; two Common Tasks rows)
- **Root cause (defect 1 of §1):** the wizard called `addNote` without `note_type`, so `NoteCreate` defaulted to `observation`; every reader since #118 PR3 resolves the description by `note_type = 'description'`, so wizard-created experiments showed no description on the reactor card, detail header or `v_experiments`. No backfill: the retype control is the fix-forward path (design decision 7).
- **Gap decisions (in-session, 2026-09-24):** the "(already set)" check excludes the note being retyped; a note's select is disabled while its own retype is in flight; the select is bound to the stored type so a rejected retype snaps back; no backend change — PATCH already enforces scope (422) and the one-description index (409) and writes the `ModificationsLog` row.
- **Verification:** `npx vitest run` → [N] passed in [F] files; `npx eslint src --ext .ts,.tsx` → 5 problems (#106 baseline); `npx tsc --noEmit` → 3 errors in `ResultsTab.columns.test.tsx` (baseline). Backend untouched — no pytest run needed for this branch. Chrome DevTools check of the wizard, Notes tab and dashboard card: see the PR body.
- **Tests added:** yes — 9. **Docs updated:** yes. **Decision logged:** no (decisions 7 and 8 were recorded in the phase-2 spec on 2026-09-24).
```

- [ ] **Step 5: Commit**

```bash
git add docs/user_guide/USER_MANUAL.md docs/project_context/USER_MANUAL.md docs/working/issue-log.md
git commit -F <scratchpad>/msg3.txt
```

`msg3.txt`:
```
[#122] Document Notes tab retype; log PR-B0

- USER_MANUAL.md: Notes tab named; description and retype tasks
- issue-log entry with verification counts
- Tests added: no
- Docs updated: yes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

## After the tasks (Conductor, not a subagent)

1. Chrome DevTools closed loop against the running app (`http://localhost:5173`, backend on 8000):
   the wizard with a description → new experiment's detail header shows it and the Notes tab lists it as Description; the dashboard card (if the experiment has a reactor slot) shows it without reload; in the Notes tab retype an observation ↔ description and confirm the toast, the badge-free select, and a 409 toast when a second description is attempted. Check the console for errors. Clean up any test experiment created in the dev DB (`DELETE /api/experiments/{id}` from the detail page).
2. Whole-branch review on the most capable model (`superpowers:requesting-code-review`).
3. Commit the plan file itself if not yet committed (`docs/superpowers/plans/` is tracked by convention).
4. `gh pr create --base develop` with: the spec section cited, the four gap decisions, verification counts, DevTools findings, and the required `🤖 Generated with [Claude Code](https://claude.com/claude-code)` footer.
