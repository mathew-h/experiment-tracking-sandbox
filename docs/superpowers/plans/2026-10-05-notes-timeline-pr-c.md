# Notes Timeline + Description Editing (issue #122, PR-C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Notes tab shows every note on an experiment in one chronological timeline with the badges the Results tab and `/notes/review` already use, a composer that can write all four note types with a valid anchor, and a header description that is edited in place — and the experiments list item calls the description `description`.

**Architecture:** Pure frontend plus one field rename. A shared `NoteBadge` replaces the per-page badge logic. `NotesTab` is split into a timeline (sort helper in `notesTimeline.ts`) and a `NoteComposer` whose anchor rules are a data table mirroring `ck_note_scope`. The header gets a `DescriptionEditor` component that PATCHes the existing `description` note or POSTs a new one. No endpoint changes; the `T+N` chip comes from the existing results query. `ExperimentListItem.condition_note` becomes `description` end to end.

**Tech Stack:** React 18 + TypeScript strict + TanStack Query v5 + Tailwind (frontend); FastAPI + Pydantic v2 (one schema field); vitest + Testing Library; pytest against `experiments_test`.

**Spec:** `docs/working/issues/07-notes-overhaul-phase-2.md` §4 "PR-C" (plus §2 gates and §3 settled decisions). The gap calls below were made by the Conductor on 2026-10-05 because Mat was not available mid-session; they are listed in the PR body for review.

## Gap calls (Conductor, 2026-10-05)

1. **NoteBadge** renders the full `NOTE_TYPE_LABELS` text; variant `modification → warning + dot`, `description → info`, others `default` (what `/notes/review` already did). The Results tab's expanded-row `NoteLine` consumes it and drops its redundant " · Label" suffix; the collapsed row's MOD/NOTE flags are row summaries, not note badges, and stay.
2. **Timeline sort key** = `event_date` (parsed as *local midnight*) else `created_at`; newest first; ties → higher id first. A pure, exported helper.
3. **`T+N` chip** needs days the note does not carry; the tab fetches `['experiment-results', id]` (the Results tab's key) and maps `result_id → time_post_reaction_days`. Unknown result → `T+?`. No API change.
4. **Retype select stays** (PR-B0 control, `aria-label="Note type"`, options from `retypeOptions()`), moved to the row's right-hand controls and always visible; `NoteBadge` is the visible label.
5. **Composer anchors** mirror `ck_note_scope`: description → no anchor; result_note → timepoint required; modification → timepoint OR date, the date input enabled only when no timepoint is chosen and defaulting to the lab's today; observation → optional timepoint, never a date. Timepoint and date are mutually exclusive in the UI. Server detail text appears in a toast *and* inline under the composer.
6. **Lab-today helper** moves from `ReactorGrid.tsx` to `frontend/src/utils/labDate.ts` (`labTodayISO`), shared by the card and the composer.
7. **Description editor** is its own component; blank or unchanged text cannot be saved; there is no delete from the header (delete the note in the Notes tab).
8. **Timeline edit stays text-only.** PATCH already supports `event_date`; editing the date chip is deferred.

## Global Constraints

- Branch `feat/notes-timeline` off `develop`; PR base `develop` (`gh pr create --base develop`).
- Commit format `[#122] <imperative, <50 chars>` + `- Tests added:` / `- Docs updated:` lines + `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Multi-line messages via `git commit -F <scratchpad file>`.
- No schema change, no migration, no file under `database/models/` or `backend/services/bulk_uploads/` is touched, no new package. Nothing becomes required (decision 4).
- Frontend: functional components with props interfaces, React Query for all server state, Tailwind classes only, no hex literals, no `console.log`, no inline styles.
- Run frontend commands from `frontend/`: `npx vitest run <path>`, `npx eslint src --ext .ts,.tsx`, `npx tsc --noEmit`. Baseline (#106): eslint 5 problems, tsc 3 errors all in `ResultsTab.columns.test.tsx`. Nothing new may be added to either.
- Backend: `.venv/Scripts/pytest.exe` from the repo root; **one pytest process at a time**; never include root-level `tests/test_*.py` in the same invocation as `tests/api`.
- Doc edits go through the Edit/Write tools (the `project_context` sync hook fires on them); after any scripted doc edit call `sync_docs_to_project_context.full_sync()`.
- Every claim in a DONE report must be backed by a command the implementer actually ran, with its output quoted.

## Review Focus

1. **A note whose `result_id` is not in the results list** (result deleted, or the list still loading) — the timeline must render `T+?`, never crash or hide the note. Pinned in Task 5.
2. **Switching the composer type from Modification (date filled) to Observation** — the date must be cleared so an observation never posts `event_date`. Pinned in Task 6.
3. **Saving an unchanged description** — Save must be disabled so no no-op PATCH (and no spurious `ModificationsLog` row) is sent. Pinned in Task 7.
4. **Type filter and review-only filter together** — the timeline shows the intersection, not either set. Pinned in Task 5.
5. **`event_date` absent (`undefined`) versus `null`** — the TS type is optional; the sort helper and chips must treat a missing key exactly like `null`. Pinned in Task 5 (test notes built without the key).

---

### Task 1: Shared `NoteBadge`; Results tab and review page consume it

**Files:**
- Create: `frontend/src/components/experiments/NoteBadge.tsx`
- Create: `frontend/src/components/experiments/NoteBadge.test.tsx`
- Modify: `frontend/src/pages/ExperimentDetail/ResultsTab.tsx:1-8,33-48`
- Modify: `frontend/src/pages/NotesReview.tsx:25-29,265`
- Modify: `frontend/src/pages/ExperimentDetail/__tests__/TypedNotes.test.tsx:123-142`

**Interfaces:**
- Produces: `NoteBadge({ type: NoteType; className?: string })` rendering `<Badge data-testid="note-badge">`; `noteBadgeVariant(type): 'default' | 'warning' | 'info'`. Tasks 5 and 6 import `NoteBadge` from `@/components/experiments/NoteBadge`.

- [ ] **Step 1: Write the failing test**

`frontend/src/components/experiments/NoteBadge.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { NoteBadge, noteBadgeVariant } from './NoteBadge'

describe('NoteBadge', () => {
  it('renders the full type label', () => {
    render(<NoteBadge type="result_note" />)
    expect(screen.getByTestId('note-badge')).toHaveTextContent('Result note')
  })

  it('maps types to the variants /notes/review used', () => {
    expect(noteBadgeVariant('modification')).toBe('warning')
    expect(noteBadgeVariant('description')).toBe('info')
    expect(noteBadgeVariant('observation')).toBe('default')
    expect(noteBadgeVariant('result_note')).toBe('default')
  })

  it('only a modification carries the status dot', () => {
    const { container, rerender } = render(<NoteBadge type="modification" />)
    expect(container.querySelector('.rounded-full')).not.toBeNull()
    rerender(<NoteBadge type="observation" />)
    expect(container.querySelector('.rounded-full')).toBeNull()
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run (from `frontend/`): `npx vitest run src/components/experiments/NoteBadge.test.tsx`
Expected: FAIL — cannot resolve `./NoteBadge`.

- [ ] **Step 3: Write the component**

`frontend/src/components/experiments/NoteBadge.tsx`:

```tsx
import { Badge } from '@/components/ui'
import { NOTE_TYPE_LABELS, type NoteType } from '@/api/noteTypes'

interface NoteBadgeProps {
  type: NoteType
  className?: string
}

/** Colour for a note type. 'modification' keeps the warning colour (and the
 *  dot) researchers know from the Results tab's MOD flag; 'description' is
 *  the one-per-experiment summary, so it stands out as info. */
export function noteBadgeVariant(type: NoteType): 'default' | 'warning' | 'info' {
  if (type === 'modification') return 'warning'
  if (type === 'description') return 'info'
  return 'default'
}

/** The one badge for a note's type (issue #122 PR-C). Used by the Notes
 *  timeline, the Results tab's expanded row and /notes/review, so the three
 *  cannot disagree on colour or wording. */
export function NoteBadge({ type, className }: NoteBadgeProps) {
  return (
    <span data-testid="note-badge" className="inline-flex">
      <Badge variant={noteBadgeVariant(type)} dot={type === 'modification'} className={className}>
        {NOTE_TYPE_LABELS[type]}
      </Badge>
    </span>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run src/components/experiments/NoteBadge.test.tsx`
Expected: 3 passed.

- [ ] **Step 5: Consume it in the Results tab**

In `frontend/src/pages/ExperimentDetail/ResultsTab.tsx`:

Replace line 4 `import { NOTE_TYPE_LABELS } from '@/api/noteTypes'` with
`import { NoteBadge } from '@/components/experiments/NoteBadge'` (the labels import becomes unused).

Replace the `NoteLine` function (lines 33–48) with:

```tsx
/** One typed note on a timepoint (issue #118). The badge is the shared
 *  NoteBadge (issue #122 PR-C) so this row, the Notes timeline and
 *  /notes/review all label a note the same way. */
function NoteLine({ note }: { note: ExperimentNote }) {
  return (
    <li className="text-xs flex items-start gap-2">
      <NoteBadge type={note.note_type} />
      <span className="text-ink-primary">
        {note.note_text}
        {note.needs_review && <span className="text-status-error"> · needs review</span>}
      </span>
    </li>
  )
}
```

`Badge` stays imported — the collapsed row (lines ~275–278) still uses it for ICP/XRD/MOD/NOTE.

- [ ] **Step 6: Consume it on the review page**

In `frontend/src/pages/NotesReview.tsx`:

Delete the `typeBadgeVariant` function (lines 25–29). Add the import
`import { NoteBadge } from '@/components/experiments/NoteBadge'` after the `noteTypes` import.
Replace the cell at line 265:

```tsx
                <Td><NoteBadge type={n.note_type} /></Td>
```

Then run `npx tsc --noEmit` and `npx eslint src/pages/NotesReview.tsx`; if `Badge` is now unused in this file, remove it from the `@/components/ui` import list (it is used elsewhere in the file only if `grep -n "<Badge" src/pages/NotesReview.tsx` still prints a line).

- [ ] **Step 7: Update the Results tab expectation**

In `frontend/src/pages/ExperimentDetail/__tests__/TypedNotes.test.tsx`, in the test
`'lists every typed note with its label in the expanded row'`, replace

```tsx
    expect(within(panel).getByText(/· Modification/)).toBeInTheDocument()
    expect(within(panel).getByText(/· Observation/)).toBeInTheDocument()
```

with

```tsx
    const badges = within(panel).getAllByTestId('note-badge').map((b) => b.textContent)
    expect(badges).toEqual(['Modification', 'Observation'])
```

- [ ] **Step 8: Run the affected suites**

Run: `npx vitest run src/components/experiments src/pages/ExperimentDetail/__tests__/TypedNotes.test.tsx src/pages/__tests__/NotesReview.test.tsx`
Expected: all pass. Then `npx tsc --noEmit` (3 baseline errors only) and `npx eslint src --ext .ts,.tsx` (5 baseline problems only).

- [ ] **Step 9: Commit**

```
[#122] Add shared NoteBadge for Results tab and review

- One badge component for a note's type; ResultsTab NoteLine and
  NotesReview consume it (replaces typeBadgeVariant)
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 2: `labTodayISO` shared helper

**Files:**
- Create: `frontend/src/utils/labDate.ts`
- Create: `frontend/src/utils/__tests__/labDate.test.ts`
- Modify: `frontend/src/pages/ReactorGrid.tsx:8-14,285`

**Interfaces:**
- Produces: `labTodayISO(now?: Date): string` (YYYY-MM-DD in America/New_York) and `LAB_TZ`. Task 6 imports `labTodayISO` from `@/utils/labDate`.

- [ ] **Step 1: Write the failing test**

`frontend/src/utils/__tests__/labDate.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { labTodayISO, LAB_TZ } from '../labDate'

describe('labTodayISO', () => {
  it('is the lab calendar day, which can differ from the UTC date', () => {
    // 02:30Z on 6 Oct is still the evening of 5 Oct in New York (EDT, UTC-4).
    expect(labTodayISO(new Date('2026-10-06T02:30:00Z'))).toBe('2026-10-05')
  })

  it('formats YYYY-MM-DD with zero padding', () => {
    expect(labTodayISO(new Date('2026-01-05T12:00:00Z'))).toBe('2026-01-05')
  })

  it('names the lab zone the server uses', () => {
    expect(LAB_TZ).toBe('America/New_York')
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx vitest run src/utils/__tests__/labDate.test.ts`
Expected: FAIL — cannot resolve `../labDate`.

- [ ] **Step 3: Write the helper**

`frontend/src/utils/labDate.ts`:

```ts
/** The lab's time zone. "Today" for a dated note is the lab's calendar day,
 *  not UTC and not the browser's zone (Mat, 2026-10-05). The server uses the
 *  same zone (`LAB_TZ` in backend/api/routers/dashboard.py) for the reactor
 *  card's "modified today" line. */
export const LAB_TZ = 'America/New_York'

/** Today as YYYY-MM-DD in the lab's time zone. `now` is injectable for tests. */
export function labTodayISO(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: LAB_TZ, year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(now)
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run src/utils/__tests__/labDate.test.ts`
Expected: 3 passed.

- [ ] **Step 5: Point ReactorGrid at it**

In `frontend/src/pages/ReactorGrid.tsx`: delete the local `todayISO` function and its doc comment (lines 8–14); add `import { labTodayISO } from '@/utils/labDate'` beside the other imports; change line 285 from `useState(todayISO)` to `useState(() => labTodayISO())`.

- [ ] **Step 6: Verify**

Run: `npx vitest run src/pages/__tests__/ReactorGrid.test.tsx src/pages/__tests__/Dashboard.test.tsx`
Expected: all pass (the test `'defaults the Modification date input to today in America/New_York…'` still passes). `npx tsc --noEmit` → baseline only.

- [ ] **Step 7: Commit**

```
[#122] Extract labTodayISO into utils/labDate

- ReactorGrid imports the shared helper; the Notes composer (next)
  uses the same definition of "today"
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 3: Backend rename `condition_note` → `description` on the list item

**Files:**
- Modify: `backend/api/schemas/experiments.py:64-65`
- Modify: `backend/api/routers/experiments.py:96-98`
- Modify: `tests/api/test_schemas.py:37`
- Modify: `tests/api/test_results_typed_notes.py:85-93`
- Modify: `tests/api/test_notes.py:64-66`
- Modify: `tests/api/test_experiments.py` (append one test)
- Modify: `docs/api/API_REFERENCE.md:69,439`
- Modify: `.claude/rules/MODELS.md:220`

**Interfaces:**
- Produces: `ExperimentListItem.description: Optional[str]` in the JSON of `GET /api/experiments`. Task 4 renames the TS side to match.

- [ ] **Step 1: Write the failing tests**

In `tests/api/test_results_typed_notes.py`, replace the test at lines 85–93 with:

```python
def test_list_item_description_is_the_typed_description(client, db_session):
    exp = _exp(db_session, "RTN_004", 7304)
    _note(db_session, exp, "an older observation")
    _note(db_session, exp, "the description", note_type=NoteType.description)
    db_session.commit()
    resp = client.get("/api/experiments?search=RTN_004")
    assert resp.status_code == 200
    item = next(i for i in resp.json()["items"] if i["experiment_id"] == "RTN_004")
    assert item["description"] == "the description"
    # Issue #122 PR-C: the field is called what it is; the old name is gone.
    assert "condition_note" not in item
```

Append to `tests/api/test_experiments.py` (it already has `client`/`db_session` fixtures from `tests/api/conftest.py`; add the three model imports at the top of the file if they are not already there — `from database.models.enums import ExperimentStatus, NoteType`, `from database.models.experiments import Experiment, ExperimentNotes`):

```python
def test_list_item_without_description_note_has_null_description(client, db_session):
    """Issue #122 PR-C: `description` is None (not missing) when the experiment
    has no 'description' note, so the UI can render the "Add description" state."""
    exp = Experiment(experiment_id="LIST_DESC_001", experiment_number=7401, status=ExperimentStatus.ONGOING)
    db_session.add(exp)
    db_session.flush()
    db_session.add(ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id,
                                   note_text="just an observation", note_type=NoteType.observation))
    db_session.commit()
    resp = client.get("/api/experiments?search=LIST_DESC_001")
    assert resp.status_code == 200
    item = next(i for i in resp.json()["items"] if i["experiment_id"] == "LIST_DESC_001")
    assert "description" in item
    assert item["description"] is None
```

In `tests/api/test_schemas.py` line 37 change `condition_note=None` to `description=None`.

In `tests/api/test_notes.py` lines 64–66 rename the function and docstring:

```python
def test_patch_description_note_is_editable(client, db_session):
    """The description note must be editable — no special read-only treatment."""
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/pytest.exe tests/api/test_results_typed_notes.py tests/api/test_experiments.py tests/api/test_schemas.py -q -k "description or additives_summary"`
Expected: the two list-item tests FAIL on `KeyError: 'description'` / `assert "condition_note" not in item`; the schema test FAILS with a Pydantic unexpected-field error only if `extra='forbid'` is set (it is not — it will pass; that is fine).

- [ ] **Step 3: Rename the field**

`backend/api/schemas/experiments.py` lines 64–65:

```python
    # The note typed 'description' (Experiment.description hybrid, issue #118).
    # Renamed from `condition_note` in issue #122 PR-C.
    description: Optional[str] = None
```

`backend/api/routers/experiments.py` lines 96–98:

```python
    # Issue #118 PR3: the description is the note typed 'description'
    # (Experiment.description hybrid), no longer the lowest-id note.
    # Issue #122 PR-C: exposed as `description` (was `condition_note`).
    item_data["description"] = exp.description
```

(`item_data` is built from `Experiment.__table__.columns`, so the hybrid is not picked up automatically — this explicit line is what populates it.)

- [ ] **Step 4: Run the API suites**

Run: `.venv/Scripts/pytest.exe tests/api/test_results_typed_notes.py tests/api/test_experiments.py tests/api/test_schemas.py tests/api/test_notes.py -q`
Expected: all pass.

- [ ] **Step 5: Docs**

`docs/api/API_REFERENCE.md` line 69: change `` `condition_note` `` to `` `description` ``.
Line 439: change `` `condition_note` on the experiments list `` to `` `description` on the experiments list (renamed from `condition_note` in #122 PR-C) ``.
`.claude/rules/MODELS.md` line 220: change `` (`condition_note`, the `description` filter) `` to `` (the list item's `description` field — renamed from `condition_note` in #122 PR-C — and the `description` filter) ``.
Use the Edit tool for all three so the `project_context` hook copies them.

- [ ] **Step 6: Confirm the old name is gone from the backend**

Run (repo root, Git Bash): `grep -rn "condition_note" backend/ docs/api/ .claude/rules/ tests/`
Expected: no output.

- [ ] **Step 7: Commit**

```
[#122] Rename list item condition_note to description

- ExperimentListItem.description is the typed description note;
  router, tests, API reference and MODELS.md updated
- Tests added: yes
- Docs updated: yes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 4: Frontend rename `condition_note` → `description`

**Files:**
- Modify: `frontend/src/api/experiments.ts:99`
- Modify: `frontend/src/pages/ExperimentList.tsx:367`
- Modify: `frontend/src/pages/__tests__/ExperimentList.test.tsx:37,214,271,313,380,500` (+ one new test)

**Interfaces:**
- Consumes: Task 3's JSON field `description`.
- Produces: `ExperimentListItem.description: string | null`.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/pages/__tests__/ExperimentList.test.tsx` (inside a new `describe` at the end of the file; it reuses the file's `wrapper`, `makeItems`, `queryClient`):

```tsx
describe('ExperimentListPage — issue #122 PR-C: the Description column reads `description`', () => {
  it('renders the description text, and a dash when there is none', async () => {
    const [withDesc, without] = makeItems(0, 2)
    vi.mocked(experimentsApi.list).mockResolvedValue({
      items: [{ ...withDesc, description: 'Pyrite + Cu catalyst, 90 °C' }, { ...without, description: null }],
      total: 2, skip: 0, limit: 25,
    })
    render(<ExperimentListPage />, { wrapper })
    expect(await screen.findByText('Pyrite + Cu catalyst, 90 °C')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })
})
```

Also replace every `condition_note: null` in the file (lines 37, 214, 271, 313, 380, 500) with `description: null`.

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/pages/__tests__/ExperimentList.test.tsx`
Expected: the new test FAILS (text not found — the column still reads `condition_note`); `npx tsc --noEmit` reports `description` is not a known property on `ExperimentListItem`.

- [ ] **Step 3: Rename**

`frontend/src/api/experiments.ts` line 99:

```ts
  /** The note typed 'description' (issue #118); renamed from condition_note in #122 PR-C. */
  description: string | null
```

`frontend/src/pages/ExperimentList.tsx` line 367: `{exp.condition_note ?? …}` → `{exp.description ?? …}`.

- [ ] **Step 4: Verify**

Run: `npx vitest run src/pages/__tests__/ExperimentList.test.tsx` → all pass. `npx tsc --noEmit` → baseline only.
Run (repo root): `grep -rn "condition_note" frontend/src` → no output.

- [ ] **Step 5: Commit**

```
[#122] Read description on the experiments list item

- TS type, ExperimentList column and tests follow the API rename
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 5: Notes timeline — sort helper, chips, type filter

**Files:**
- Create: `frontend/src/pages/ExperimentDetail/notesTimeline.ts`
- Create: `frontend/src/pages/ExperimentDetail/__tests__/notesTimeline.test.ts`
- Rewrite: `frontend/src/pages/ExperimentDetail/NotesTab.tsx`
- Modify: `frontend/src/pages/ExperimentDetail/__tests__/TypedNotes.test.tsx` (beforeEach; one test's order; new describe)
- Modify: `frontend/src/pages/ExperimentDetail/__tests__/NotesTab.buttons.test.tsx:8-14`

**Interfaces:**
- Consumes: `NoteBadge` (Task 1).
- Produces: `sortTimeline(notes: ExperimentNote[]): ExperimentNote[]`, `timelineKey(n): number`, `timepointLabel(days: number | null | undefined): string` from `./notesTimeline`. `NotesTab` keeps its props `{ experimentId: string; notes: ExperimentNote[] }` and now runs `useQuery(['experiment-results', experimentId])`; Task 6 reads `results` and `hasDescription` from this component.

- [ ] **Step 1: Write the failing helper tests**

`frontend/src/pages/ExperimentDetail/__tests__/notesTimeline.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import type { ExperimentNote } from '@/api/experiments'
import { sortTimeline, timelineKey, timepointLabel } from '../notesTimeline'

/** Built WITHOUT an event_date key on purpose: the TS field is optional and
 *  a missing key must behave exactly like null (Review Focus 5). */
function note(partial: Partial<ExperimentNote> & { id: number }): ExperimentNote {
  return {
    note_text: 'x', note_type: 'observation', result_id: null, created_by: null,
    needs_review: false, created_at: '2026-04-01T12:00:00Z', updated_at: null, ...partial,
  }
}

describe('sortTimeline', () => {
  it('orders by event_date when set, else created_at, newest first', () => {
    const out = sortTimeline([
      note({ id: 1, created_at: '2026-09-01T10:00:00Z' }),
      note({ id: 2, note_type: 'modification', event_date: '2026-09-20', created_at: '2026-08-01T10:00:00Z' }),
      note({ id: 3, created_at: '2026-09-10T10:00:00Z' }),
    ])
    expect(out.map((n) => n.id)).toEqual([2, 3, 1])
  })

  it('breaks ties on id, newest first, and does not mutate its input', () => {
    const input = [note({ id: 4 }), note({ id: 9 }), note({ id: 6 })]
    const out = sortTimeline(input)
    expect(out.map((n) => n.id)).toEqual([9, 6, 4])
    expect(input.map((n) => n.id)).toEqual([4, 9, 6])
  })

  it('treats event_date: null like a missing key', () => {
    const out = sortTimeline([
      note({ id: 1, event_date: null, created_at: '2026-09-01T10:00:00Z' }),
      note({ id: 2, created_at: '2026-09-02T10:00:00Z' }),
    ])
    expect(out.map((n) => n.id)).toEqual([2, 1])
  })
})

describe('timelineKey', () => {
  it('a dated note keys at local midnight of its lab calendar day', () => {
    expect(timelineKey(note({ id: 1, event_date: '2026-09-20' }))).toBe(new Date(2026, 8, 20).getTime())
  })
  it('an undated note keys at the instant it was created', () => {
    expect(timelineKey(note({ id: 1, created_at: '2026-04-01T12:00:00Z' }))).toBe(Date.parse('2026-04-01T12:00:00Z'))
  })
})

describe('timepointLabel', () => {
  it('formats known days and falls back to T+? for unknown', () => {
    expect(timepointLabel(7)).toBe('T+7')
    expect(timepointLabel(0.5)).toBe('T+0.5')
    expect(timepointLabel(null)).toBe('T+?')
    expect(timepointLabel(undefined)).toBe('T+?')
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/pages/ExperimentDetail/__tests__/notesTimeline.test.ts`
Expected: FAIL — cannot resolve `../notesTimeline`.

- [ ] **Step 3: Write the helper module**

`frontend/src/pages/ExperimentDetail/notesTimeline.ts`:

```ts
import type { ExperimentNote } from '@/api/experiments'

/** Sort key for the Notes timeline (issue #122 PR-C): COALESCE(event_date,
 *  created_at). A dated note sorts at local midnight of its lab calendar day
 *  (the date is a day, not an instant); everything else at the instant it was
 *  written. A missing event_date key behaves like null. */
export function timelineKey(n: ExperimentNote): number {
  if (n.event_date) {
    const [y, m, d] = n.event_date.split('-').map(Number)
    return new Date(y, m - 1, d).getTime()
  }
  return new Date(n.created_at).getTime()
}

/** Newest first; equal keys → higher id first. Returns a new array. */
export function sortTimeline(notes: ExperimentNote[]): ExperimentNote[] {
  return [...notes].sort((a, b) => timelineKey(b) - timelineKey(a) || b.id - a.id)
}

/** `T+7` for a result-scoped note whose result is known; `T+?` when the
 *  results list has not loaded or no longer contains that result. */
export function timepointLabel(days: number | null | undefined): string {
  return days == null ? 'T+?' : `T+${days}`
}
```

- [ ] **Step 4: Run the helper tests**

Run: `npx vitest run src/pages/ExperimentDetail/__tests__/notesTimeline.test.ts`
Expected: 6 passed.

- [ ] **Step 5: Write the failing timeline tests**

In `frontend/src/pages/ExperimentDetail/__tests__/TypedNotes.test.tsx`:

(a) Replace the `beforeEach` (lines 96–98) with:

```tsx
beforeEach(() => {
  vi.clearAllMocks()
  // The Notes tab now reads the results list for its T+N chips (issue #122 PR-C).
  vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([])
})
```

(b) In the test `'a date-anchored note offers Modification (and Description) but a bare experiment-level note does not'`, the timeline now puts the dated note (2026-09-24) before the bare one (created 2026-04-01). Replace

```tsx
    const [bare, dated] = screen.getAllByLabelText('Note type') as HTMLSelectElement[]
    // feed is newest-first: id 8 (bare) then id 7 (dated)
```

with

```tsx
    const [dated, bare] = screen.getAllByLabelText('Note type') as HTMLSelectElement[]
    // Timeline order is COALESCE(event_date, created_at) newest-first (PR-C):
    // id 7 (dated 2026-09-24) precedes id 8 (created 2026-04-01).
```

(c) Append a new describe block at the end of the file:

```tsx
describe('NotesTab — timeline (issue #122 PR-C)', () => {
  const rowIds = () => screen.getAllByTestId(/^note-row-/).map((el) => Number(el.dataset.noteId))

  it('mixes experiment-level and timepoint notes in one list, newest first by COALESCE(event_date, created_at)', () => {
    wrap(<NotesTab experimentId="HPHT_001" notes={[
      note({ id: 1, note_text: 'oldest', created_at: '2026-09-01T10:00:00Z' }),
      note({ id: 2, note_text: 'dated mod', note_type: 'modification', event_date: '2026-09-20', created_at: '2026-08-01T10:00:00Z' }),
      note({ id: 3, note_text: 'on a result', result_id: 5, created_at: '2026-09-10T10:00:00Z' }),
    ]} />)
    expect(rowIds()).toEqual([2, 3, 1])
    expect(screen.getAllByTestId('note-badge').map((b) => b.textContent)).toEqual(['Modification', 'Observation', 'Observation'])
  })

  it('shows a T+N chip for a result-scoped note and a date chip for a dated one, and neither on a bare note', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, id: 5, time_post_reaction_days: 7 },
    ])
    wrap(<NotesTab experimentId="HPHT_001" notes={[
      note({ id: 3, note_text: 'on a result', result_id: 5 }),
      note({ id: 2, note_text: 'dated mod', note_type: 'modification', event_date: '2026-09-20' }),
      note({ id: 1, note_text: 'bare' }),
    ]} />)
    expect(await screen.findByLabelText('Timepoint')).toHaveTextContent('T+7')
    expect(screen.getByLabelText('Event date')).toHaveTextContent('2026-09-20')
    expect(screen.getAllByLabelText('Timepoint')).toHaveLength(1)
    expect(screen.getAllByLabelText('Event date')).toHaveLength(1)
  })

  it('renders T+? when the note’s result is not in the results list (Review Focus 1)', async () => {
    wrap(<NotesTab experimentId="HPHT_001" notes={[note({ id: 3, note_text: 'orphan', result_id: 999 })]} />)
    expect(await screen.findByLabelText('Timepoint')).toHaveTextContent('T+?')
    expect(screen.getByText('orphan')).toBeInTheDocument()
  })

  it('the type filter narrows the timeline and combines with review-only (Review Focus 4)', async () => {
    const user = userEvent.setup()
    wrap(<NotesTab experimentId="HPHT_001" notes={[
      note({ id: 1, note_text: 'obs reviewed' }),
      note({ id: 2, note_text: 'obs queued', needs_review: true }),
      note({ id: 3, note_text: 'mod queued', note_type: 'modification', result_id: 5, needs_review: true }),
    ]} />)
    await user.selectOptions(screen.getByLabelText('Filter by type'), 'observation')
    expect(screen.queryByText('mod queued')).not.toBeInTheDocument()
    expect(screen.getByText('obs reviewed')).toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: /review queue only/i }))
    expect(screen.queryByText('obs reviewed')).not.toBeInTheDocument()
    expect(screen.getByText('obs queued')).toBeInTheDocument()
    expect(screen.queryByText('mod queued')).not.toBeInTheDocument()
  })

  it('shows the author on each row', () => {
    wrap(<NotesTab experimentId="HPHT_001" notes={[note({ id: 1, note_text: 'x', created_by: 'mhearl@addisenergy.com' })]} />)
    expect(screen.getByText(/mhearl@addisenergy\.com/)).toBeInTheDocument()
  })
})
```

(d) In `frontend/src/pages/ExperimentDetail/__tests__/NotesTab.buttons.test.tsx` lines 8–14, add `getResults` to the mock:

```tsx
vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    addNote: vi.fn(),
    patchNote: vi.fn(),
    deleteNote: vi.fn(() => Promise.resolve()),
    getResults: vi.fn(() => Promise.resolve([])),
  },
}))
```

- [ ] **Step 6: Run to verify the new tests fail**

Run: `npx vitest run src/pages/ExperimentDetail/__tests__/TypedNotes.test.tsx`
Expected: the five new tests FAIL (no `note-row-*` test ids, no `Timepoint`/`Event date` labels, no `Filter by type`); the re-ordered dated/bare test FAILS until the sort lands.

- [ ] **Step 7: Rewrite `NotesTab.tsx`**

Replace the whole file with the following. The composer block (textarea + Type select + Add Note) is the existing code carried over verbatim; Task 6 replaces it.

```tsx
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { experimentsApi, type ExperimentNote } from '@/api/experiments'
import { NOTE_TYPE_LABELS, type NoteType } from '@/api/noteTypes'
import { Badge, Button, ConfirmModal, useToast } from '@/components/ui'
import { NoteBadge } from '@/components/experiments/NoteBadge'
import { sortTimeline, timepointLabel } from './notesTimeline'

interface Props { experimentId: string; notes: ExperimentNote[] }

/** Types a researcher can pick when writing an experiment-level note here.
 *  'modification' and 'result_note' are scoped to a timepoint and are written
 *  from the Results tab (Add Results), not from this feed. */
const ADDABLE_TYPES: NoteType[] = ['observation', 'description']

/** Every type, in the order the timeline's type filter lists them. */
const ALL_TYPES: NoteType[] = ['description', 'modification', 'observation', 'result_note']

/** Types a note may be retyped to, given its anchor — the UI mirror of the
 *  ck_note_scope CHECK (issue #122, decisions 1 and 8). A result anchors
 *  modification and result_note; an event_date anchors modification only;
 *  description is experiment-level. The DB stays the authority (422 on PATCH). */
function retypeOptions(n: ExperimentNote): NoteType[] {
  if (n.result_id != null) return ['observation', 'modification', 'result_note']
  if (n.event_date != null) return ['observation', 'modification', 'description']
  return ['observation', 'description']
}

const CHIP = 'font-mono-data'

/** Notes tab (issue #118, #122 PR-C): one chronological timeline of every
 *  note on the experiment — experiment-level and timepoint-scoped mixed —
 *  with inline add, edit, retype, delete, and the review queue for rows the
 *  backfill could not place with certainty. */
export function NotesTab({ experimentId, notes }: Props) {
  const [text, setText] = useState('')
  const [newType, setNewType] = useState<NoteType>('observation')
  const [reviewOnly, setReviewOnly] = useState(false)
  const [typeFilter, setTypeFilter] = useState<NoteType | 'all'>('all')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editText, setEditText] = useState('')
  const [deleteNoteId, setDeleteNoteId] = useState<number | null>(null)
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()

  const hasDescription = notes.some((n) => n.note_type === 'description')
  const reviewCount = notes.filter((n) => n.needs_review).length
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] })

  /** Days per result id, so a result-scoped note can show its T+N chip. Shares
   *  the Results tab's query key, so an Add Results save refreshes both. */
  const { data: results } = useQuery({
    queryKey: ['experiment-results', experimentId],
    queryFn: () => experimentsApi.getResults(experimentId),
  })
  const daysByResult = useMemo(() => {
    const m = new Map<number, number | null>()
    for (const r of results ?? []) m.set(r.id, r.time_post_reaction_days)
    return m
  }, [results])

  const addNote = useMutation({
    mutationFn: () => experimentsApi.addNote(experimentId, text, { note_type: newType }),
    onSuccess: () => {
      invalidate()
      success('Note added')
      setText('')
      setNewType('observation')
    },
    onError: (err: Error) => toastError('Failed to add note', err.message),
  })

  const editNote = useMutation({
    mutationFn: ({ noteId, newText }: { noteId: number; newText: string }) =>
      experimentsApi.patchNote(experimentId, noteId, { note_text: newText }),
    onSuccess: () => {
      invalidate()
      success('Note updated')
      setEditingId(null)
      setEditText('')
    },
    onError: (err: Error) => toastError('Failed to update note', err.message),
  })

  const resolveNote = useMutation({
    mutationFn: (noteId: number) => experimentsApi.patchNote(experimentId, noteId, { needs_review: false }),
    onSuccess: () => {
      invalidate()
      success('Marked as reviewed')
    },
    onError: (err: Error) => toastError('Failed to mark reviewed', err.message),
  })

  const retypeNote = useMutation({
    mutationFn: ({ noteId, noteType }: { noteId: number; noteType: NoteType }) =>
      experimentsApi.patchNote(experimentId, noteId, { note_type: noteType }),
    onSuccess: (_data, { noteType }) => {
      success('Note type changed', NOTE_TYPE_LABELS[noteType])
      // Returned so the row stays pending (and shows the chosen type) until the
      // refetch lands. To or from 'description' changes the reactor card and
      // the experiments list's Description column as well as this page.
      return Promise.all([
        invalidate(),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['experiments'] }),
      ])
    },
    onError: (err: Error) => toastError('Failed to change note type', err.message),
  })

  const deleteNote = useMutation({
    mutationFn: (noteId: number) => experimentsApi.deleteNote(experimentId, noteId),
    onSuccess: () => {
      invalidate()
      success('Note deleted')
      setDeleteNoteId(null)
    },
    onError: (err: Error) => toastError('Failed to delete note', err.message),
  })

  const startEdit = (note: ExperimentNote) => {
    setEditingId(note.id)
    setEditText(note.note_text ?? '')
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditText('')
  }

  const isEdited = (note: ExperimentNote) =>
    note.updated_at != null && note.updated_at !== note.created_at

  const visible = useMemo(
    () => sortTimeline(notes).filter(
      (n) => (!reviewOnly || n.needs_review) && (typeFilter === 'all' || n.note_type === typeFilter),
    ),
    [notes, reviewOnly, typeFilter],
  )

  return (
    <div className="p-4 space-y-4">
      {/* Add note */}
      <div className="space-y-2">
        <textarea
          className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary placeholder-ink-muted focus:outline-none focus:ring-1 focus:ring-brand-red/50 resize-none"
          rows={3}
          placeholder="Add a note…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="flex items-center gap-2">
          <label htmlFor="new-note-type" className="text-xs text-ink-secondary">Type</label>
          <select
            id="new-note-type"
            value={newType}
            onChange={(e) => setNewType(e.target.value as NoteType)}
            className="text-xs px-2 py-1 border border-surface-border rounded bg-surface-raised text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50"
          >
            {ADDABLE_TYPES.map((t) => (
              <option key={t} value={t} disabled={t === 'description' && hasDescription}>
                {NOTE_TYPE_LABELS[t]}{t === 'description' && hasDescription ? ' (already set)' : ''}
              </option>
            ))}
          </select>
          <Button variant="primary" size="sm" disabled={!text.trim()} loading={addNote.isPending}
            onClick={() => addNote.mutate()}>
            Add Note
          </Button>
        </div>
      </div>

      {/* Filters */}
      {notes.length > 0 && (
        <div className="flex flex-wrap items-center gap-4 text-xs text-ink-secondary">
          <label className="flex items-center gap-2">
            <span>Show</span>
            <select
              aria-label="Filter by type"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as NoteType | 'all')}
              className="text-xs px-2 py-1 border border-surface-border rounded bg-surface-raised text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50"
            >
              <option value="all">All types</option>
              {ALL_TYPES.map((t) => (
                <option key={t} value={t}>{NOTE_TYPE_LABELS[t]}</option>
              ))}
            </select>
          </label>
          {reviewCount > 0 && (
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={reviewOnly}
                onChange={(e) => setReviewOnly(e.target.checked)}
              />
              Review queue only ({reviewCount})
            </label>
          )}
        </div>
      )}

      {/* Timeline */}
      <div className="space-y-3">
        {notes.length === 0 && <p className="text-sm text-ink-muted">No notes yet</p>}
        {notes.length > 0 && visible.length === 0 && (
          <p className="text-sm text-ink-muted">
            {reviewOnly ? 'Nothing left to review' : 'No notes of this type'}
          </p>
        )}
        {visible.map((n, i) => {
          const isRetyping = retypeNote.isPending && retypeNote.variables?.noteId === n.id
          return (
          <div
            key={n.id}
            data-testid={`note-row-${n.id}`}
            data-note-id={n.id}
            className={`text-xs border-b border-surface-border pb-3 group ${i === visible.length - 1 ? 'border-b-0' : ''}`}
          >
            <div className="flex items-start justify-between gap-2 mb-0.5">
              <div className="flex items-center gap-1.5 flex-wrap">
                <NoteBadge type={n.note_type} />
                {n.result_id != null && (
                  <span aria-label="Timepoint" className="inline-flex">
                    <Badge className={CHIP}>{timepointLabel(daysByResult.get(n.result_id))}</Badge>
                  </span>
                )}
                {n.event_date && (
                  <span aria-label="Event date" className="inline-flex">
                    <Badge className={CHIP}>{n.event_date}</Badge>
                  </span>
                )}
                {n.needs_review && (
                  <Badge variant="error" dot>Needs review</Badge>
                )}
                {isEdited(n) && (
                  <span className="text-[10px] text-ink-muted italic">(edited)</span>
                )}
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <select
                  aria-label="Note type"
                  value={isRetyping ? retypeNote.variables!.noteType : n.note_type}
                  disabled={isRetyping}
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
                {editingId !== n.id && (
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 max-sm:opacity-100 transition-opacity">
                    {n.needs_review && (
                      <Button
                        variant="ghost"
                        size="xs"
                        aria-label="Mark reviewed"
                        loading={resolveNote.isPending && resolveNote.variables === n.id}
                        onClick={() => resolveNote.mutate(n.id)}
                      >
                        Mark reviewed
                      </Button>
                    )}
                    {/* Edit */}
                    <button
                      type="button"
                      aria-label="Edit note"
                      onClick={() => startEdit(n)}
                      className="p-1 rounded text-ink-secondary hover:text-ink-primary hover:bg-surface-overlay transition-colors"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round"
                          d="M11.5 2.5a1.414 1.414 0 012 2L5 13H3v-2L11.5 2.5z" />
                      </svg>
                    </button>
                    {/* Delete */}
                    <button
                      type="button"
                      aria-label="Delete note"
                      onClick={() => setDeleteNoteId(n.id)}
                      className="p-1 rounded text-ink-secondary hover:text-red-400 hover:bg-surface-overlay transition-colors"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round"
                          d="M3 4h10M6 4V2h4v2M5 4v9a1 1 0 001 1h4a1 1 0 001-1V4" />
                      </svg>
                    </button>
                  </div>
                )}
              </div>
            </div>

            {editingId === n.id ? (
              <div className="space-y-1.5 mt-1">
                <textarea
                  className="w-full bg-surface-input border border-surface-border rounded px-2 py-1.5 text-sm text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50 resize-none"
                  rows={3}
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  autoFocus
                />
                <div className="flex gap-2">
                  <Button
                    variant="primary"
                    size="xs"
                    disabled={!editText.trim()}
                    loading={editNote.isPending}
                    onClick={() => editNote.mutate({ noteId: n.id, newText: editText })}
                  >
                    Save
                  </Button>
                  <Button variant="ghost" size="xs" onClick={cancelEdit}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <p className="text-ink-secondary leading-relaxed whitespace-pre-wrap">{n.note_text}</p>
                <p className="text-ink-muted mt-0.5 font-mono-data">
                  {new Date(n.created_at).toLocaleString()}
                  {n.created_by && ` · ${n.created_by}`}
                </p>
              </>
            )}
          </div>
          )
        })}
      </div>

      {/* Delete note confirmation */}
      <ConfirmModal
        open={deleteNoteId !== null}
        onClose={() => setDeleteNoteId(null)}
        onConfirm={() => { if (deleteNoteId !== null) deleteNote.mutate(deleteNoteId) }}
        loading={deleteNote.isPending}
        title="Delete note?"
        description="This note will be permanently deleted and cannot be recovered."
        confirmLabel="Delete"
        danger
      />
    </div>
  )
}
```

Note: `Badge` takes `className` but not `aria-label` in its props, which is why each chip is wrapped in a labelled `<span>`. The tests query by label text and `toHaveTextContent`.

- [ ] **Step 8: Run the Notes suites**

Run: `npx vitest run src/pages/ExperimentDetail/__tests__/TypedNotes.test.tsx src/pages/ExperimentDetail/__tests__/NotesTab.buttons.test.tsx src/pages/ExperimentDetail/__tests__/notesTimeline.test.ts`
Expected: all pass, including every pre-existing `NotesTab — typed notes` test (the select is still `aria-label="Note type"` with the same options).
Then `npx tsc --noEmit` and `npx eslint src --ext .ts,.tsx` → baseline only.

- [ ] **Step 9: Commit**

```
[#122] Make the Notes tab one chronological timeline

- Sort by COALESCE(event_date, created_at) newest first; NoteBadge,
  T+N and date chips, type filter; retype select kept as the control
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 6: `NoteComposer` — all four types with a valid anchor

**Files:**
- Create: `frontend/src/pages/ExperimentDetail/NoteComposer.tsx`
- Create: `frontend/src/pages/ExperimentDetail/__tests__/NoteComposer.test.tsx`
- Modify: `frontend/src/pages/ExperimentDetail/NotesTab.tsx` (remove the inline composer; render `NoteComposer`)
- Modify: `frontend/src/pages/ExperimentDetail/__tests__/TypedNotes.test.tsx` (one existing test's expectation stays valid — see Step 7)

**Interfaces:**
- Consumes: `labTodayISO` (Task 2), `timepointLabel` (Task 5), `results` and `hasDescription` from `NotesTab` (Task 5).
- Produces: `NoteComposer({ experimentId: string; hasDescription: boolean; results: ResultWithFlags[] | undefined })`. Its anchor controls are labelled **"At timepoint"** and **"On date"** (not "Timepoint"/"Date") so they never collide with the timeline chips' `aria-label="Timepoint"` / `"Event date"` in queries; pure exports `ANCHOR_RULE`, `anchorProblem(type, resultId, eventDate): string | null`, `composerPayload(type, resultId, eventDate): Omit<NoteCreate, 'note_text'>`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/pages/ExperimentDetail/__tests__/NoteComposer.test.tsx`:

```tsx
/** Issue #122 PR-C: the Notes composer writes every note type with an anchor
 *  that ck_note_scope accepts, and refuses the rest before any request. */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import type { ResultWithFlags } from '@/api/experiments'
import * as experimentsApiModule from '@/api/experiments'
import { labTodayISO } from '@/utils/labDate'
import { NoteComposer, anchorProblem, composerPayload } from '../NoteComposer'

vi.mock('@/api/experiments', async () => {
  const actual = await vi.importActual<typeof import('@/api/experiments')>('@/api/experiments')
  return { ...actual, experimentsApi: { addNote: vi.fn(() => Promise.resolve({})) } }
})

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return { ...render(<QueryClientProvider client={qc}><ToastProvider>{ui}</ToastProvider></QueryClientProvider>), qc }
}

const result = (id: number, days: number | null): ResultWithFlags => ({
  id, experiment_fk: 10, time_post_reaction_days: days, time_post_reaction_bucket_days: days,
  cumulative_time_post_reaction_days: days, is_primary_timepoint_result: true, description: 'legacy',
  created_at: '2026-04-01T00:00:00Z', has_scalar: false, has_icp: false, has_modification_note: false,
  notes: [], brine_modification_description: null, grams_per_ton_yield: null, h2_concentration: null,
  h2_grams_per_ton_yield: null, h2_micromoles: null, gross_ammonium_concentration_mM: null,
  background_ammonium_concentration_mM: null, final_conductivity_mS_cm: null, final_ph: null,
  scalar_measurement_date: null, ferrous_iron_yield_h2_pct: null, ferrous_iron_yield_nh3_pct: null,
  nmr_run_date: null, icp_run_date: null, gc_run_date: null, xrd_run_date: null,
})
const RESULTS = [result(5, 7), result(6, 14)]
const addNote = () => vi.mocked(experimentsApiModule.experimentsApi.addNote)

beforeEach(() => vi.clearAllMocks())

describe('anchorProblem / composerPayload (pure)', () => {
  it('mirrors ck_note_scope', () => {
    expect(anchorProblem('description', null, null)).toBeNull()
    expect(anchorProblem('description', 5, null)).toMatch(/description/i)
    expect(anchorProblem('result_note', null, null)).toMatch(/timepoint/i)
    expect(anchorProblem('result_note', 5, null)).toBeNull()
    expect(anchorProblem('modification', null, null)).toMatch(/timepoint or a date/i)
    expect(anchorProblem('modification', 5, null)).toBeNull()
    expect(anchorProblem('modification', null, '2026-10-05')).toBeNull()
    expect(anchorProblem('observation', null, null)).toBeNull()
    expect(anchorProblem('observation', 5, null)).toBeNull()
    expect(anchorProblem('observation', null, '2026-10-05')).toMatch(/modification/i)
  })

  it('sends only the anchor keys that apply', () => {
    expect(composerPayload('observation', null, null)).toEqual({ note_type: 'observation' })
    expect(composerPayload('observation', 5, null)).toEqual({ note_type: 'observation', result_id: 5 })
    expect(composerPayload('modification', null, '2026-10-05')).toEqual({ note_type: 'modification', event_date: '2026-10-05' })
    // A result-anchored modification never also sends the date (Gap call 5).
    expect(composerPayload('modification', 5, '2026-10-05')).toEqual({ note_type: 'modification', result_id: 5 })
    expect(composerPayload('description', null, null)).toEqual({ note_type: 'description' })
  })
})

describe('NoteComposer', () => {
  it('a result note cannot be sent until a timepoint is chosen, then posts result_id', async () => {
    const user = userEvent.setup()
    wrap(<NoteComposer experimentId="HPHT_001" hasDescription={false} results={RESULTS} />)
    await user.type(screen.getByPlaceholderText(/add a note/i), 'pH probe drifted')
    await user.selectOptions(screen.getByLabelText('Type'), 'result_note')
    const add = screen.getByRole('button', { name: /add note/i })
    expect(add).toBeDisabled()
    expect(screen.getByText(/needs a timepoint/i)).toBeInTheDocument()
    const tp = screen.getByLabelText('At timepoint') as HTMLSelectElement
    expect(within(tp).getAllByRole('option').map((o) => o.textContent)).toEqual(['Choose…', 'T+7', 'T+14'])
    await user.selectOptions(tp, '6')
    expect(add).toBeEnabled()
    await user.click(add)
    expect(addNote()).toHaveBeenCalledWith('HPHT_001', 'pH probe drifted', { note_type: 'result_note', result_id: 6 })
  })

  it('a modification with no timepoint defaults its date to the lab’s today and posts event_date', async () => {
    const user = userEvent.setup()
    wrap(<NoteComposer experimentId="HPHT_001" hasDescription={false} results={RESULTS} />)
    await user.type(screen.getByPlaceholderText(/add a note/i), 'swapped stir bar')
    await user.selectOptions(screen.getByLabelText('Type'), 'modification')
    const date = screen.getByLabelText('On date') as HTMLInputElement
    expect(date.value).toBe(labTodayISO())
    expect(date).toBeEnabled()
    await user.click(screen.getByRole('button', { name: /add note/i }))
    expect(addNote()).toHaveBeenCalledWith('HPHT_001', 'swapped stir bar', { note_type: 'modification', event_date: labTodayISO() })
  })

  it('choosing a timepoint for a modification clears and disables the date; the payload carries result_id only', async () => {
    const user = userEvent.setup()
    wrap(<NoteComposer experimentId="HPHT_001" hasDescription={false} results={RESULTS} />)
    await user.type(screen.getByPlaceholderText(/add a note/i), 'brine replaced')
    await user.selectOptions(screen.getByLabelText('Type'), 'modification')
    await user.selectOptions(screen.getByLabelText('At timepoint'), '5')
    const date = screen.getByLabelText('On date') as HTMLInputElement
    expect(date.value).toBe('')
    expect(date).toBeDisabled()
    await user.click(screen.getByRole('button', { name: /add note/i }))
    expect(addNote()).toHaveBeenCalledWith('HPHT_001', 'brine replaced', { note_type: 'modification', result_id: 5 })
  })

  it('switching from Modification back to Observation drops the date so no event_date is sent (Review Focus 2)', async () => {
    const user = userEvent.setup()
    wrap(<NoteComposer experimentId="HPHT_001" hasDescription={false} results={RESULTS} />)
    await user.type(screen.getByPlaceholderText(/add a note/i), 'cloudy')
    await user.selectOptions(screen.getByLabelText('Type'), 'modification')
    expect((screen.getByLabelText('On date') as HTMLInputElement).value).toBe(labTodayISO())
    await user.selectOptions(screen.getByLabelText('Type'), 'observation')
    expect(screen.queryByLabelText('On date')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /add note/i }))
    expect(addNote()).toHaveBeenCalledWith('HPHT_001', 'cloudy', { note_type: 'observation' })
  })

  it('Description hides both anchor controls and posts no anchor; it is disabled once one exists', async () => {
    const user = userEvent.setup()
    const { unmount } = wrap(<NoteComposer experimentId="HPHT_001" hasDescription={false} results={RESULTS} />)
    await user.type(screen.getByPlaceholderText(/add a note/i), 'Pyrite + Cu, 90 °C')
    await user.selectOptions(screen.getByLabelText('Type'), 'description')
    expect(screen.queryByLabelText('At timepoint')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('On date')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /add note/i }))
    expect(addNote()).toHaveBeenCalledWith('HPHT_001', 'Pyrite + Cu, 90 °C', { note_type: 'description' })
    unmount()
    wrap(<NoteComposer experimentId="HPHT_001" hasDescription results={RESULTS} />)
    const opt = within(screen.getByLabelText('Type')).getByRole('option', { name: /description/i }) as HTMLOptionElement
    expect(opt.disabled).toBe(true)
  })

  it('shows the server’s detail verbatim inline and in a toast when the POST is rejected', async () => {
    const user = userEvent.setup()
    addNote().mockRejectedValueOnce(new Error("Experiment 'HPHT_001' already has a description note."))
    wrap(<NoteComposer experimentId="HPHT_001" hasDescription={false} results={RESULTS} />)
    await user.type(screen.getByPlaceholderText(/add a note/i), 'dup')
    await user.selectOptions(screen.getByLabelText('Type'), 'description')
    await user.click(screen.getByRole('button', { name: /add note/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent("Experiment 'HPHT_001' already has a description note.")
    // The draft survives so the researcher can fix and resend.
    expect((screen.getByPlaceholderText(/add a note/i) as HTMLTextAreaElement).value).toBe('dup')
  })

  it('a successful add refreshes the experiment, the experiments list and the dashboard', async () => {
    const user = userEvent.setup()
    const { qc } = wrap(<NoteComposer experimentId="HPHT_001" hasDescription={false} results={RESULTS} />)
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    await user.type(screen.getByPlaceholderText(/add a note/i), 'x')
    await user.click(screen.getByRole('button', { name: /add note/i }))
    await vi.waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['experiment', 'HPHT_001'] }))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['experiments'] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['dashboard'] })
    expect((screen.getByPlaceholderText(/add a note/i) as HTMLTextAreaElement).value).toBe('')
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/pages/ExperimentDetail/__tests__/NoteComposer.test.tsx`
Expected: FAIL — cannot resolve `../NoteComposer`.

- [ ] **Step 3: Write the component**

`frontend/src/pages/ExperimentDetail/NoteComposer.tsx`:

```tsx
import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { experimentsApi, type NoteCreate, type ResultWithFlags } from '@/api/experiments'
import { NOTE_TYPE_LABELS, type NoteType } from '@/api/noteTypes'
import { Button, useToast } from '@/components/ui'
import { labTodayISO } from '@/utils/labDate'
import { timepointLabel } from './notesTimeline'

interface Props {
  experimentId: string
  /** True when the experiment already has its one 'description' note. */
  hasDescription: boolean
  /** The experiment's results, for the timepoint select. Undefined while loading. */
  results: ResultWithFlags[] | undefined
}

/** Types the composer offers, in menu order. */
const COMPOSER_TYPES: NoteType[] = ['observation', 'modification', 'result_note', 'description']

export type AnchorRule = 'none' | 'optional' | 'result' | 'result_or_date'

/** The UI mirror of ck_note_scope (issue #122, decisions 1 and 8):
 *  description ⇒ no anchor; result_note ⇒ a result; modification ⇒ a result OR
 *  a date; observation ⇒ an optional result and never a date. The DB stays
 *  the authority — its 422/409 is shown verbatim when it disagrees. */
export const ANCHOR_RULE: Record<NoteType, AnchorRule> = {
  description: 'none',
  observation: 'optional',
  result_note: 'result',
  modification: 'result_or_date',
}

/** Why the current type/anchor combination cannot be sent, or null when it can. */
export function anchorProblem(type: NoteType, resultId: number | null, eventDate: string | null): string | null {
  switch (ANCHOR_RULE[type]) {
    case 'none':
      return resultId != null || eventDate ? 'A description is not tied to a timepoint or a date.' : null
    case 'result':
      return resultId == null ? 'A result note needs a timepoint.' : null
    case 'result_or_date':
      return resultId == null && !eventDate ? 'A modification needs a timepoint or a date.' : null
    case 'optional':
      return eventDate ? 'Only a modification can carry a date.' : null
  }
}

/** The body for POST /experiments/{id}/notes — only the anchor keys that
 *  apply. A result-anchored modification never also sends the date. */
export function composerPayload(type: NoteType, resultId: number | null, eventDate: string | null): Omit<NoteCreate, 'note_text'> {
  const body: Omit<NoteCreate, 'note_text'> = { note_type: type }
  if (resultId != null) body.result_id = resultId
  if (type === 'modification' && resultId == null && eventDate) body.event_date = eventDate
  return body
}

const SELECT = 'text-xs px-2 py-1 border border-surface-border rounded bg-surface-raised text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50 disabled:opacity-40'

/** The Notes tab's composer (issue #122 PR-C): writes any of the four note
 *  types through POST /notes with a timepoint OR a date anchor, validated to
 *  the ck_note_scope rule before the request is sent. */
export function NoteComposer({ experimentId, hasDescription, results }: Props) {
  const [text, setText] = useState('')
  const [type, setType] = useState<NoteType>('observation')
  const [resultId, setResultId] = useState<number | null>(null)
  const [eventDate, setEventDate] = useState<string | null>(null)
  const [serverError, setServerError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()

  const rule = ANCHOR_RULE[type]
  const showTimepoint = rule !== 'none'
  const showDate = rule === 'result_or_date'
  const dateEnabled = showDate && resultId == null
  const problem = anchorProblem(type, resultId, eventDate)

  const timepoints = useMemo(
    () => [...(results ?? [])].sort(
      (a, b) => (a.time_post_reaction_days ?? Infinity) - (b.time_post_reaction_days ?? Infinity) || a.id - b.id,
    ),
    [results],
  )

  const changeType = (next: NoteType) => {
    setType(next)
    setServerError(null)
    const nextRule = ANCHOR_RULE[next]
    if (nextRule === 'none') {
      setResultId(null)
      setEventDate(null)
    } else if (nextRule === 'result_or_date') {
      if (resultId == null && !eventDate) setEventDate(labTodayISO())
    } else {
      setEventDate(null)
    }
  }

  const changeTimepoint = (value: string) => {
    const id = value === '' ? null : Number(value)
    setResultId(id)
    setServerError(null)
    if (id != null) setEventDate(null)
    else if (rule === 'result_or_date') setEventDate(labTodayISO())
  }

  const addNote = useMutation({
    mutationFn: () => experimentsApi.addNote(experimentId, text, composerPayload(type, resultId, eventDate)),
    onSuccess: () => {
      success('Note added')
      setText('')
      setType('observation')
      setResultId(null)
      setEventDate(null)
      setServerError(null)
      // A new description changes the reactor card and the experiments list too.
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] }),
        queryClient.invalidateQueries({ queryKey: ['experiments'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      ])
    },
    onError: (err: Error) => {
      // apiClient copies FastAPI's `detail` into message: the 422/409 text, verbatim.
      setServerError(err.message)
      toastError('Failed to add note', err.message)
    },
  })

  return (
    <div className="space-y-2" data-testid="note-composer">
      <textarea
        className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary placeholder-ink-muted focus:outline-none focus:ring-1 focus:ring-brand-red/50 resize-none"
        rows={3}
        placeholder="Add a note…"
        value={text}
        onChange={(e) => { setText(e.target.value); setServerError(null) }}
      />
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="new-note-type" className="text-xs text-ink-secondary">Type</label>
        <select id="new-note-type" value={type} onChange={(e) => changeType(e.target.value as NoteType)} className={SELECT}>
          {COMPOSER_TYPES.map((t) => (
            <option key={t} value={t} disabled={t === 'description' && hasDescription}>
              {NOTE_TYPE_LABELS[t]}{t === 'description' && hasDescription ? ' (already set)' : ''}
            </option>
          ))}
        </select>
        {showTimepoint && (
          <>
            <label htmlFor="new-note-timepoint" className="text-xs text-ink-secondary">At timepoint</label>
            <select id="new-note-timepoint" value={resultId ?? ''} onChange={(e) => changeTimepoint(e.target.value)} className={SELECT}>
              <option value="">{rule === 'result' ? 'Choose…' : 'None'}</option>
              {timepoints.map((r) => (
                <option key={r.id} value={r.id}>{timepointLabel(r.time_post_reaction_days)}</option>
              ))}
            </select>
          </>
        )}
        {showDate && (
          <>
            <label htmlFor="new-note-date" className="text-xs text-ink-secondary">On date</label>
            <input
              id="new-note-date"
              type="date"
              value={eventDate ?? ''}
              disabled={!dateEnabled}
              onChange={(e) => { setEventDate(e.target.value || null); setServerError(null) }}
              className={`${SELECT} font-mono-data`}
            />
          </>
        )}
        <Button
          variant="primary"
          size="sm"
          disabled={!text.trim() || problem != null}
          loading={addNote.isPending}
          onClick={() => addNote.mutate()}
        >
          Add Note
        </Button>
      </div>
      {problem && <p className="text-xs text-ink-muted">{problem}</p>}
      {serverError && <p role="alert" className="text-xs text-status-error">{serverError}</p>}
    </div>
  )
}
```

- [ ] **Step 4: Run the composer tests**

Run: `npx vitest run src/pages/ExperimentDetail/__tests__/NoteComposer.test.tsx`
Expected: 9 passed.

- [ ] **Step 5: Swap it into `NotesTab.tsx`**

In `frontend/src/pages/ExperimentDetail/NotesTab.tsx` (as written in Task 5):
- Delete the `ADDABLE_TYPES` constant and its doc comment.
- Delete the `text` / `newType` `useState` lines and the `addNote` mutation.
- Delete the whole `{/* Add note */} <div className="space-y-2">…</div>` block.
- Add `import { NoteComposer } from './NoteComposer'`.
- Render `<NoteComposer experimentId={experimentId} hasDescription={hasDescription} results={results} />` where the block was.
- `useMutation` stays imported (edit/resolve/retype/delete still use it).

- [ ] **Step 6: Run every Notes suite**

Run: `npx vitest run src/pages/ExperimentDetail/__tests__/`
Expected: all pass. The pre-existing test `'adding a note sends the chosen type, and a second description is not offered'` still passes through `NotesTab`: the `Type` label and the `Add Note` button are unchanged and `composerPayload('observation', null, null)` is `{ note_type: 'observation' }`.
Then `npx tsc --noEmit` and `npx eslint src --ext .ts,.tsx` → baseline only.

- [ ] **Step 7: Commit**

```
[#122] Add Notes composer with timepoint or date anchor

- All four types via POST /notes; anchor rules mirror ck_note_scope
  client-side; server 422/409 shown verbatim inline and in a toast
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 7: Header description — click to edit, "Add description" when absent

**Files:**
- Create: `frontend/src/pages/ExperimentDetail/DescriptionEditor.tsx`
- Create: `frontend/src/pages/ExperimentDetail/__tests__/DescriptionEdit.test.tsx`
- Modify: `frontend/src/pages/ExperimentDetail/index.tsx:13-14,313-318`

**Interfaces:**
- Produces: `DescriptionEditor({ experimentId: string; note: ExperimentNote | undefined })`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/pages/ExperimentDetail/__tests__/DescriptionEdit.test.tsx`:

```tsx
/** Issue #122 PR-C: the header description is the 'description' note, edited
 *  in place; a description-less experiment gets one from here. */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '@/components/ui'
import type { ExperimentDetail, ExperimentNote } from '@/api/experiments'
import * as experimentsApiModule from '@/api/experiments'
import { DescriptionEditor } from '../DescriptionEditor'
import { ExperimentDetailPage } from '../index'

vi.mock('@/api/experiments', async () => {
  const actual = await vi.importActual<typeof import('@/api/experiments')>('@/api/experiments')
  return {
    ...actual,
    experimentsApi: {
      get: vi.fn(),
      patch: vi.fn(),
      getReplicateGroup: vi.fn(() => Promise.resolve({ base_experiment_id: 'SERUM_050', parent: null, members: [] })),
      getGroup: vi.fn(() => Promise.reject(new Error('404'))),
      getResults: vi.fn(() => Promise.resolve([])),
      getRollup: vi.fn(),
      getDeleteImpact: vi.fn(),
      delete: vi.fn(),
      addNote: vi.fn(() => Promise.resolve({})),
      patchNote: vi.fn(() => Promise.resolve({ data: {} })),
    },
  }
})
vi.mock('@/api/conditions', () => ({
  conditionsApi: { getByExperiment: vi.fn().mockRejectedValue(new Error('none')) },
}))

const api = () => experimentsApiModule.experimentsApi

const DESC: ExperimentNote = {
  id: 41, note_text: 'Pyrite + Cu, 90 °C', note_type: 'description', result_id: null,
  created_by: null, needs_review: false, created_at: '2026-07-01T00:00:00Z', updated_at: null,
}

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } } })
  const utils = render(
    <MemoryRouter initialEntries={['/experiments/SERUM_050']}>
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <Routes>
            <Route path="/experiments/:id" element={ui} />
            <Route path="/experiments" element={<div>Experiments List</div>} />
          </Routes>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
  return { ...utils, qc }
}

beforeEach(() => vi.clearAllMocks())

describe('DescriptionEditor', () => {
  it('offers "Add description" when the experiment has none, and POSTs a description note', async () => {
    const user = userEvent.setup()
    const { qc } = wrap(<DescriptionEditor experimentId="SERUM_050" note={undefined} />)
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    await user.click(screen.getByRole('button', { name: /add description/i }))
    await user.type(screen.getByLabelText('Description'), 'Serum, Ni catalyst')
    await user.click(screen.getByRole('button', { name: /^save$/i }))
    expect(api().addNote).toHaveBeenCalledWith('SERUM_050', 'Serum, Ni catalyst', { note_type: 'description' })
    await vi.waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['experiment', 'SERUM_050'] }))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['experiments'] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['dashboard'] })
  })

  it('clicking the description opens the editor pre-filled, and Save PATCHes note_text on that note', async () => {
    const user = userEvent.setup()
    wrap(<DescriptionEditor experimentId="SERUM_050" note={DESC} />)
    await user.click(screen.getByRole('button', { name: /edit description/i }))
    const box = screen.getByLabelText('Description') as HTMLTextAreaElement
    expect(box.value).toBe('Pyrite + Cu, 90 °C')
    await user.clear(box)
    await user.type(box, 'Pyrite + Cu, 120 °C')
    await user.click(screen.getByRole('button', { name: /^save$/i }))
    expect(api().patchNote).toHaveBeenCalledWith('SERUM_050', 41, { note_text: 'Pyrite + Cu, 120 °C' })
    expect(api().addNote).not.toHaveBeenCalled()
  })

  it('Save is disabled for blank text and for unchanged text (Review Focus 3)', async () => {
    const user = userEvent.setup()
    wrap(<DescriptionEditor experimentId="SERUM_050" note={DESC} />)
    await user.click(screen.getByRole('button', { name: /edit description/i }))
    const save = screen.getByRole('button', { name: /^save$/i })
    expect(save).toBeDisabled()
    const box = screen.getByLabelText('Description')
    await user.clear(box)
    expect(save).toBeDisabled()
    await user.type(box, '   ')
    expect(save).toBeDisabled()
    await user.type(box, 'changed')
    expect(save).toBeEnabled()
    expect(api().patchNote).not.toHaveBeenCalled()
  })

  it('Escape cancels without a request; Ctrl+Enter saves', async () => {
    const user = userEvent.setup()
    wrap(<DescriptionEditor experimentId="SERUM_050" note={DESC} />)
    await user.click(screen.getByRole('button', { name: /edit description/i }))
    await user.type(screen.getByLabelText('Description'), ' more')
    await user.keyboard('{Escape}')
    expect(screen.queryByLabelText('Description')).not.toBeInTheDocument()
    expect(api().patchNote).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /edit description/i })).toHaveTextContent('Pyrite + Cu, 90 °C')

    await user.click(screen.getByRole('button', { name: /edit description/i }))
    await user.type(screen.getByLabelText('Description'), ' more')
    await user.keyboard('{Control>}{Enter}{/Control}')
    expect(api().patchNote).toHaveBeenCalledWith('SERUM_050', 41, { note_text: 'Pyrite + Cu, 90 °C more' })
  })

  it('a rejected save shows the server detail in a toast and stays in edit mode', async () => {
    const user = userEvent.setup()
    vi.mocked(api().patchNote).mockRejectedValueOnce(new Error('Note 41 not found'))
    wrap(<DescriptionEditor experimentId="SERUM_050" note={DESC} />)
    await user.click(screen.getByRole('button', { name: /edit description/i }))
    await user.type(screen.getByLabelText('Description'), '!')
    await user.click(screen.getByRole('button', { name: /^save$/i }))
    expect(await screen.findByText(/Note 41 not found/)).toBeInTheDocument()
    expect(screen.getByLabelText('Description')).toBeInTheDocument()
  })
})

describe('ExperimentDetailPage header wiring', () => {
  const BASE: ExperimentDetail = {
    id: 5, experiment_id: 'SERUM_050', experiment_number: 150, status: 'ONGOING',
    researcher: null, date: null, sample_id: null, base_experiment_id: null,
    parent_experiment_fk: null, replicate_label: null, is_outlier: false,
    id_timepoint_days: null, created_at: '2026-07-01T00:00:00Z', updated_at: null,
    conditions: null, notes: [], modifications: [],
  }

  it('shows "Add description" when the detail has no description note', async () => {
    vi.mocked(api().get).mockResolvedValue(BASE)
    wrap(<ExperimentDetailPage />)
    expect(await screen.findByRole('button', { name: /add description/i })).toBeInTheDocument()
  })

  it('renders the description note as the editable header text', async () => {
    vi.mocked(api().get).mockResolvedValue({ ...BASE, notes: [DESC] })
    wrap(<ExperimentDetailPage />)
    expect(await screen.findByRole('button', { name: /edit description/i })).toHaveTextContent('Pyrite + Cu, 90 °C')
    expect(screen.queryByRole('button', { name: /add description/i })).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/pages/ExperimentDetail/__tests__/DescriptionEdit.test.tsx`
Expected: FAIL — cannot resolve `../DescriptionEditor`.

- [ ] **Step 3: Write the component**

`frontend/src/pages/ExperimentDetail/DescriptionEditor.tsx`:

```tsx
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { experimentsApi, type ExperimentNote } from '@/api/experiments'
import { Button, useToast } from '@/components/ui'

interface Props {
  experimentId: string
  /** The experiment's 'description' note, or undefined when it has none. */
  note: ExperimentNote | undefined
}

/** The header description (issue #122 PR-C): the note typed 'description',
 *  edited in place. Saving PATCHes the existing note or POSTs a new one — this
 *  is how a description-less experiment gets one from its page. The reactor
 *  card and the experiments list read the same note, so both refetch. Blank
 *  or unchanged text cannot be saved; deleting is done in the Notes tab. */
export function DescriptionEditor({ experimentId, note }: Props) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()

  const save = useMutation({
    mutationFn: (text: string) =>
      note
        ? experimentsApi.patchNote(experimentId, note.id, { note_text: text })
        : experimentsApi.addNote(experimentId, text, { note_type: 'description' }),
    onSuccess: () => {
      success(note ? 'Description updated' : 'Description added')
      setEditing(false)
      setDraft('')
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] }),
        queryClient.invalidateQueries({ queryKey: ['experiments'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      ])
    },
    onError: (err: Error) => toastError('Failed to save description', err.message),
  })

  const start = () => {
    setDraft(note?.note_text ?? '')
    setEditing(true)
  }
  const cancel = () => {
    setEditing(false)
    setDraft('')
  }
  const trimmed = draft.trim()
  const canSave = trimmed.length > 0 && trimmed !== (note?.note_text ?? '').trim()

  if (editing) {
    return (
      <div className="mt-1 space-y-1.5 max-w-2xl" data-testid="description-editor">
        <textarea
          aria-label="Description"
          className="w-full bg-surface-input border border-surface-border rounded px-2 py-1.5 text-sm text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50 resize-none"
          rows={3}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') cancel()
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && canSave) save.mutate(trimmed)
          }}
          autoFocus
        />
        <div className="flex gap-2">
          <Button variant="primary" size="xs" disabled={!canSave} loading={save.isPending} onClick={() => save.mutate(trimmed)}>
            Save
          </Button>
          <Button variant="ghost" size="xs" onClick={cancel}>Cancel</Button>
        </div>
      </div>
    )
  }

  if (!note) {
    return (
      <Button variant="ghost" size="xs" className="mt-1 -ml-2" onClick={start}>
        Add description
      </Button>
    )
  }

  return (
    <button
      type="button"
      aria-label="Edit description"
      title="Click to edit"
      onClick={start}
      data-testid="experiment-description"
      className="mt-1 block text-left text-sm text-ink-secondary hover:text-ink-primary rounded -mx-1 px-1 hover:bg-surface-overlay/60 transition-colors whitespace-pre-wrap"
    >
      {note.note_text}
    </button>
  )
}
```

- [ ] **Step 4: Wire the header**

In `frontend/src/pages/ExperimentDetail/index.tsx`: add `import { DescriptionEditor } from './DescriptionEditor'` beside the `NotesTab` import (line 13), and replace lines 313–318

```tsx
        {/* Issue #118: the description is the note typed 'description'. */}
        {descriptionNote && (
          <p className="text-sm text-ink-secondary mt-1" data-testid="experiment-description">
            {descriptionNote.note_text}
          </p>
        )}
```

with

```tsx
        {/* Issue #118: the description is the note typed 'description';
            issue #122 PR-C: edited in place, or added when missing. */}
        <DescriptionEditor experimentId={id!} note={descriptionNote} />
```

- [ ] **Step 5: Run the tests**

Run: `npx vitest run src/pages/ExperimentDetail/__tests__/`
Expected: all pass (the `DescriptionEdit` file: 7 passed). `npx tsc --noEmit` and `npx eslint src --ext .ts,.tsx` → baseline only.

- [ ] **Step 6: Commit**

```
[#122] Edit the header description in place

- DescriptionEditor PATCHes the description note or POSTs one when
  missing; "Add description" when absent; refreshes list + dashboard
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

### Task 8: Docs, full verification, issue-log, spec status

**Files:**
- Modify: `docs/user_guide/USER_MANUAL.md:59-61`
- Modify: `docs/working/issues/07-notes-overhaul-phase-2.md` (§1 table, PR-C row)
- Modify: `docs/working/issue-log.md` (append)

(The API reference and MODELS.md were updated in Task 3.)

- [ ] **Step 1: User manual**

In `docs/user_guide/USER_MANUAL.md`, replace the two rows at lines 60–61 with these three (Edit tool, so the hook syncs):

```markdown
| Add or fix an experiment's description | Fill in "Experiment Description" in step 1 of **New Experiment**; it is saved as the experiment's Description note and shows on the reactor card and detail header. Later, open the experiment and click the description under its ID to edit it in place — or click **Add description** if it has none. Only one Description is allowed per experiment |
| Read or write notes on an experiment | Open an experiment → **Notes** tab. Every note — experiment-level and timepoint-scoped — is one timeline, newest first, each with a type badge, a `T+N` chip (on a timepoint) or a date chip (a dated modification), and its author. Filter by type or "Review queue only". To add one, pick a type: an Observation may name a timepoint; a Result note must; a Modification needs a timepoint **or** a date (defaults to today); a Description has neither |
| Change a note's type | Open an experiment → **Notes** tab → use the type dropdown on the note. Experiment-level notes can be Observation or Description; notes on a timepoint can be Observation, Modification or Result note; a dated note can be Observation, Modification or Description. Only one Description is allowed per experiment |
```

- [ ] **Step 2: Spec status**

In `docs/working/issues/07-notes-overhaul-phase-2.md` §1 table, change the PR-C row's State cell from `Next.` to `In review (PR #<n>, 2026-10-05).` once the PR number is known (the Conductor fills `<n>` after `gh pr create`).

- [ ] **Step 3: Full verification (one process each)**

Backend (repo root):
```
.venv/Scripts/pytest.exe tests/models tests/views tests/api tests/test_icp_handling.py tests/services tests/regression tests/data_migrations -q
```
Expected: 0 failed; count ≥ 1,427 (1,426 on develop + the new test in `test_experiments.py`). If `experiments_test` is stale, reset it per memory `experiments-test-reset-needs-schema-grant` first.

Frontend (`frontend/`):
```
npx vitest run
npx eslint src --ext .ts,.tsx
npx tsc --noEmit
```
Expected: vitest 0 failed (264 on develop + ~30 new); eslint exactly the 5 baseline problems; tsc exactly the 3 baseline errors in `ResultsTab.columns.test.tsx`.

Acceptance grep (repo root, Git Bash):
```
grep -rn "condition_note" backend/ frontend/src docs/api/ docs/project_context/api/ .claude/rules/ tests/
grep -rn "typeBadgeVariant" frontend/src
```
Expected: both empty.

- [ ] **Step 4: Issue-log entry**

Append to `docs/working/issue-log.md`, filling the counts from Step 3:

```markdown
## 2026-10-05 | issue #122 PR-C — Unified notes timeline + description editing (`feat/notes-timeline`)
- **Files changed:**
  - `frontend/src/components/experiments/NoteBadge.tsx` (new) — the one badge for a note's type; `ResultsTab.tsx` (`NoteLine`) and `NotesReview.tsx` consume it (`typeBadgeVariant` deleted).
  - `frontend/src/utils/labDate.ts` (new) — `labTodayISO()` / `LAB_TZ`, extracted from `ReactorGrid.tsx`.
  - `frontend/src/pages/ExperimentDetail/notesTimeline.ts` (new) — `sortTimeline` (COALESCE(event_date, created_at) newest first, id tiebreak), `timelineKey`, `timepointLabel`.
  - `frontend/src/pages/ExperimentDetail/NotesTab.tsx` — one chronological timeline of every note (experiment-level and timepoint-scoped); `NoteBadge`, `T+N` chip (days from the shared `['experiment-results', id]` query; `T+?` if unknown), date chip, author, needs-review marker + Mark reviewed, the PR-B0 retype select (now always visible in the row's right-hand controls), edit, delete; type filter + the existing review-only checkbox.
  - `frontend/src/pages/ExperimentDetail/NoteComposer.tsx` (new) — all four types via `POST /notes`; `ANCHOR_RULE` / `anchorProblem` / `composerPayload` mirror `ck_note_scope`; timepoint select or date picker (modification only; defaults to the lab's today when no timepoint); server 422/409 shown verbatim inline and in a toast.
  - `frontend/src/pages/ExperimentDetail/DescriptionEditor.tsx` (new) + `index.tsx` — header description is click-to-edit (PATCH `note_text`) or "Add description" (POST a `description` note); invalidates `['experiment', id]`, `['experiments']`, `['dashboard']`.
  - `backend/api/schemas/experiments.py`, `backend/api/routers/experiments.py`, `frontend/src/api/experiments.ts`, `frontend/src/pages/ExperimentList.tsx` — `ExperimentListItem.condition_note` → `description`.
  - Tests: `NoteBadge.test.tsx`, `labDate.test.ts`, `notesTimeline.test.ts`, `NoteComposer.test.tsx`, `DescriptionEdit.test.tsx` (new); `TypedNotes.test.tsx`, `NotesTab.buttons.test.tsx`, `ExperimentList.test.tsx`, `tests/api/test_results_typed_notes.py`, `tests/api/test_experiments.py`, `tests/api/test_schemas.py`, `tests/api/test_notes.py` updated.
  - Docs: `docs/api/API_REFERENCE.md`, `.claude/rules/MODELS.md`, `docs/user_guide/USER_MANUAL.md`, spec §1 table, this entry.
- **Why:** after PR-B a modification can be anchored to a result or a date, so the Notes tab had to show both kinds in one place, with the same badge the Results tab and `/notes/review` use; the composer had to be able to write every type the schema allows (the old one offered only Observation/Description); and the header description — read by the reactor card and the experiments list — needed an edit path so the 118 description-less experiments on the mirror can get one without the wizard.
- **Gap calls (Conductor, 2026-10-05; for Mat's review):** see `docs/superpowers/plans/2026-10-05-notes-timeline-pr-c.md` "Gap calls" — sort key parses `event_date` as local midnight; `T+N` comes from the results query (no API change); the retype select remains the control beside the badge; timepoint and date are mutually exclusive in the composer; the date editor on an existing note is deferred (PATCH supports it).
- **Verification (full suite, fresh `experiments_test`):**
  - Backend: `.venv/Scripts/pytest.exe tests/models tests/views tests/api tests/test_icp_handling.py tests/services tests/regression tests/data_migrations -q` → **<N> passed, 0 failed**.
  - Frontend: `npx vitest run` → **<N> passed, <F> files, 0 failed**; `npx eslint src --ext .ts,.tsx` → 5 problems (#106 baseline); `npx tsc --noEmit` → 3 errors in `ResultsTab.columns.test.tsx` (baseline).
  - `grep -rn "condition_note" backend/ frontend/src docs/api/ .claude/rules/ tests/` → empty.
  - Chrome DevTools check on `http://localhost:5173` (dev DB = 2026-09-23 mirror + 020 + 021): timeline, composer (each type), header edit — see PR body.
- **Tests added:** yes. **Docs updated:** yes.
```

- [ ] **Step 5: Commit**

```
[#122] Document the notes timeline and header edit

- USER_MANUAL rows, spec §1 status, issue-log entry with counts
- Tests added: no
- Docs updated: yes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

## After the tasks (Conductor, not a subagent)

1. Whole-branch review on the most capable model; fix wave if needed.
2. Chrome DevTools closed loop on `http://localhost:5173` (signed in): open an experiment with dated and result-scoped notes (e.g. one touched by 021 — `SELECT experiment_id FROM experiment_notes WHERE created_by='migrate_change_requests_021' LIMIT 5` via the read-only psql in `docs/PSQL_ACCESS.md`), check the timeline order and chips, the retype select, the type filter; create one note of each type through the composer (and clean them up); edit the header description on one experiment and add one on a description-less experiment (and revert); watch the console and network tabs for errors.
3. `gh pr create --base develop` with the gap calls, the verification counts, the pre-authorization citations (none needed — no schema, no parser), and the DevTools checklist in the body; then fill the PR number into the spec §1 row (Task 8 Step 2) in a final small commit.

## Self-review

- **Spec coverage:** timeline (T5), NoteBadge shared across three consumers (T1), `T+N`/date chips, author, review marker, retype select, edit, delete (T5), filters (T5), composer with four types and anchor validation + verbatim server error (T6), header click-to-edit / Add description with the three invalidations (T7), `condition_note` rename across schema/TS/list/tests/API reference (T3, T4), Results tab unchanged except NoteBadge (T1), tests named in §4: `TypedNotes.test.tsx` (T1, T5), `NotesTab.buttons.test.tsx` (T5), `DescriptionEdit.test.tsx` (T7), `ExperimentList.test.tsx` (T4), `tests/api/test_experiments.py` (T3). Docs §7 items that PR-C owns: API reference (T3), MODELS.md (T3), USER_MANUAL (T8), issue-log (T8).
- **Placeholders:** none; the only `<n>` / `<N>` are values the Conductor fills from command output in Task 8.
- **Type consistency:** `NoteBadge({ type })`, `labTodayISO(now?)`, `sortTimeline`/`timelineKey`/`timepointLabel`, `NoteComposer({ experimentId, hasDescription, results })`, `anchorProblem(type, resultId, eventDate)`, `composerPayload(...)`, `DescriptionEditor({ experimentId, note })` are used with the same names and shapes in every task that references them. `ExperimentListItem.description` is the same name in Pydantic and TS.
- **Review Focus:** 1 → T5 test "renders T+? …"; 2 → T6 test "switching from Modification back to Observation …"; 3 → T7 test "Save is disabled for blank text and for unchanged text"; 4 → T5 test "the type filter narrows the timeline and combines with review-only"; 5 → T5 helper tests build notes without an `event_date` key and one with `null`.
