# Issue #24: Fix Invisible Edit/Delete Buttons for Additives and Notes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the invisible `opacity-0` edit/delete buttons on the Conditions (additives) and Notes tabs with accessible, WCAG AA–compliant action buttons — and add the missing delete functionality for notes end-to-end.

**Architecture:** Fix happens across four layers: (1) a new backend DELETE endpoint for notes, (2) the `experimentsApi` service function, (3) two React tab components updated in place, and (4) two new Playwright E2E test files. No new shared components are needed; the existing `ConfirmModal` covers deletion confirmation.

**Tech Stack:** FastAPI (Python), React 18, TypeScript, Tailwind CSS (brand tokens), React Query, Playwright.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/api/routers/experiments.py` | Add `DELETE /{experiment_id}/notes/{note_id}` endpoint |
| Modify | `frontend/src/api/experiments.ts` | Add `deleteNote` service function |
| Modify | `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx` | Fix additives edit/delete buttons |
| Modify | `frontend/src/pages/ExperimentDetail/NotesTab.tsx` | Fix notes edit button + add delete button |
| Create | `frontend/e2e/journeys/02-additives-crud.spec.ts` | E2E tests for additives edit/delete |
| Create | `frontend/e2e/journeys/03-notes-crud.spec.ts` | E2E tests for notes edit/delete |

---

## Task 1: Add backend DELETE endpoint for notes

**Files:**
- Modify: `backend/api/routers/experiments.py` (after line 644, after `patch_note`)

The `patch_note` endpoint (line 606) already shows the pattern. Follow it exactly: look up experiment by string ID, verify note belongs to that experiment, write a `ModificationsLog`, delete the note, return 204.

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_notes_delete.py`:

```python
"""Tests for DELETE /experiments/{experiment_id}/notes/{note_id}."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from backend.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _mock_user():
    user = MagicMock()
    user.email = "test@addisenergy.com"
    return user


def test_delete_note_returns_204(client):
    """DELETE /experiments/{id}/notes/{note_id} returns 204 on success."""
    mock_exp = MagicMock()
    mock_exp.id = 1
    mock_exp.experiment_id = "HPHT_001"

    mock_note = MagicMock()
    mock_note.id = 42
    mock_note.note_text = "Old note"
    mock_note.experiment_fk = 1

    with patch("backend.api.routers.experiments.verify_firebase_token", return_value=_mock_user()), \
         patch("backend.api.routers.experiments.get_db") as mock_db_dep:
        mock_db = MagicMock()
        mock_db_dep.return_value = mock_db

        # First execute: experiment lookup → returns mock_exp
        # Second execute: note lookup → returns mock_note
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [mock_exp, mock_note]

        response = client.delete(
            "/api/experiments/HPHT_001/notes/42",
            headers={"Authorization": "Bearer fake-token"},
        )

    assert response.status_code == 204


def test_delete_note_404_when_experiment_missing(client):
    """Returns 404 if the experiment does not exist."""
    with patch("backend.api.routers.experiments.verify_firebase_token", return_value=_mock_user()), \
         patch("backend.api.routers.experiments.get_db") as mock_db_dep:
        mock_db = MagicMock()
        mock_db_dep.return_value = mock_db
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        response = client.delete(
            "/api/experiments/MISSING/notes/1",
            headers={"Authorization": "Bearer fake-token"},
        )

    assert response.status_code == 404


def test_delete_note_404_when_note_missing(client):
    """Returns 404 if the note does not exist or belongs to a different experiment."""
    mock_exp = MagicMock()
    mock_exp.id = 1

    with patch("backend.api.routers.experiments.verify_firebase_token", return_value=_mock_user()), \
         patch("backend.api.routers.experiments.get_db") as mock_db_dep:
        mock_db = MagicMock()
        mock_db_dep.return_value = mock_db
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [mock_exp, None]

        response = client.delete(
            "/api/experiments/HPHT_001/notes/999",
            headers={"Authorization": "Bearer fake-token"},
        )

    assert response.status_code == 404
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
pytest tests/api/test_notes_delete.py -v
```

Expected: 3 failures — `404` because the route doesn't exist yet.

- [ ] **Step 3: Add the DELETE endpoint**

In `backend/api/routers/experiments.py`, append the following after line 644 (after the closing of `patch_note`):

```python
@router.delete("/{experiment_id}/notes/{note_id}", status_code=204)
def delete_note(
    experiment_id: str,
    note_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> None:
    """Delete a note. Writes a ModificationsLog entry then removes the row."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    note = db.execute(
        select(ExperimentNotes)
        .where(ExperimentNotes.id == note_id)
        .where(ExperimentNotes.experiment_fk == exp.id)
    ).scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    db.add(ModificationsLog(
        experiment_id=experiment_id,
        experiment_fk=exp.id,
        modified_by=current_user.email,
        modification_type="delete",
        modified_table="experiment_notes",
        old_values={"note_text": note.note_text},
        new_values=None,
    ))
    db.delete(note)
    db.commit()
    log.info("note_deleted", experiment_id=experiment_id, note_id=note_id)
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
pytest tests/api/test_notes_delete.py -v
```

Expected: 3 passing.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/experiments.py tests/api/test_notes_delete.py
git commit -m "[#24] add DELETE /experiments/{id}/notes/{note_id} endpoint

- Tests added: yes
- Docs updated: no"
```

---

## Task 2: Add deleteNote to the frontend API service

**Files:**
- Modify: `frontend/src/api/experiments.ts` (line 141, before `delete:`)

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/__tests__/experiments.deleteNote.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { experimentsApi } from '../experiments'

// Mock the entire apiClient module
vi.mock('../client', () => ({
  apiClient: {
    delete: vi.fn(),
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}))

import { apiClient } from '../client'

describe('experimentsApi.deleteNote', () => {
  beforeEach(() => vi.clearAllMocks())

  it('calls DELETE /experiments/{id}/notes/{noteId}', async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: undefined, status: 204 } as never)

    await experimentsApi.deleteNote('HPHT_001', 42)

    expect(apiClient.delete).toHaveBeenCalledWith('/experiments/HPHT_001/notes/42')
  })

  it('is defined on the experimentsApi object', () => {
    expect(typeof experimentsApi.deleteNote).toBe('function')
  })
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npx vitest run src/api/__tests__/experiments.deleteNote.test.ts
```

Expected: FAIL — `experimentsApi.deleteNote is not a function`.

- [ ] **Step 3: Add deleteNote to experiments.ts**

In `frontend/src/api/experiments.ts`, insert after `patchNote` (line 140) and before `delete:`:

```typescript
  deleteNote: (experimentId: string, noteId: number) =>
    apiClient.delete(`/experiments/${experimentId}/notes/${noteId}`),
```

The full block from lines 136–143 should now read:

```typescript
  addNote: (experimentId: string, text: string) =>
    apiClient.post(`/experiments/${experimentId}/notes`, { note_text: text }).then((r) => r.data),

  patchNote: (experimentId: string, noteId: number, text: string) =>
    apiClient.patch<{ id: number; note_text: string; created_at: string; updated_at: string | null }>(`/experiments/${experimentId}/notes/${noteId}`, { note_text: text }),

  deleteNote: (experimentId: string, noteId: number) =>
    apiClient.delete(`/experiments/${experimentId}/notes/${noteId}`),

  delete: (experimentId: string) =>
    apiClient.delete(`/experiments/${experimentId}`).then((r) => r.data),
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd frontend && npx vitest run src/api/__tests__/experiments.deleteNote.test.ts
```

Expected: 2 passing.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/experiments.ts frontend/src/api/__tests__/experiments.deleteNote.test.ts
git commit -m "[#24] add deleteNote service function to experimentsApi

- Tests added: yes
- Docs updated: no"
```

---

## Task 3: Fix additives edit/delete buttons in ConditionsTab

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx`

**What's broken:**
- `opacity-0 group-hover:opacity-100` hides buttons completely until hover — fails discoverability
- `text-ink-muted` (`#4d6e8a` on `#0a2440`) is ~2.1:1 contrast — fails WCAG AA
- Delete button uses `×` text (no icon, no `aria-label`)
- Edit button has `title` but no `aria-label`
- Delete fires immediately with no confirmation

**Fix:** Use `opacity-0 group-hover:opacity-100 max-sm:opacity-100` (always visible on mobile), `text-ink-secondary` for resting state, trash icon SVG for delete, `aria-label` on both, and wire `ConfirmModal` for delete.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/ExperimentDetail/__tests__/ConditionsTab.buttons.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConditionsTab } from '../ConditionsTab'

// Minimal stubs
vi.mock('@/api/chemicals', () => ({
  chemicalsApi: {
    listExperimentAdditives: vi.fn(() => Promise.resolve([
      { id: 1, compound_id: 10, compound: { name: 'Magnetite' }, amount: 5, unit: 'g', mass_in_grams: 5 },
    ])),
    listCompounds: vi.fn(() => Promise.resolve([])),
  },
}))
vi.mock('@/api/conditions', () => ({
  conditionsApi: {
    getByExperiment: vi.fn(() => Promise.resolve(null)),
  },
}))
vi.mock('@/components/ui', async () => {
  const actual = await vi.importActual<typeof import('@/components/ui')>('@/components/ui')
  return actual
})

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('ConditionsTab additives action buttons', () => {
  it('renders edit and delete buttons with aria-labels', async () => {
    wrap(<ConditionsTab conditions={null} experimentId="HPHT_001" experimentFk={1} />)

    const editBtn = await screen.findByRole('button', { name: /edit additive/i })
    const deleteBtn = await screen.findByRole('button', { name: /delete additive/i })

    expect(editBtn).toBeInTheDocument()
    expect(deleteBtn).toBeInTheDocument()
  })

  it('edit and delete buttons are not aria-hidden', async () => {
    wrap(<ConditionsTab conditions={null} experimentId="HPHT_001" experimentFk={1} />)

    const editBtn = await screen.findByRole('button', { name: /edit additive/i })
    expect(editBtn).not.toHaveAttribute('aria-hidden', 'true')
  })
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npx vitest run src/pages/ExperimentDetail/__tests__/ConditionsTab.buttons.test.tsx
```

Expected: FAIL — buttons not found (wrong/missing `aria-label`).

- [ ] **Step 3: Update ConditionsTab.tsx imports**

In `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx` line 5, add `ConfirmModal` to the UI imports:

```typescript
import { Button, Input, Select, Modal, ConfirmModal, useToast } from '@/components/ui'
```

- [ ] **Step 4: Add delete confirm state to ConditionsTab**

In `ConditionsTab.tsx`, after line 115 (after `editCompoundDropdownOpen` state), add:

```typescript
  // Delete additive confirmation state
  const [deleteAdditiveId, setDeleteAdditiveId] = useState<number | null>(null)
```

- [ ] **Step 5: Replace the additives action buttons markup**

In `ConditionsTab.tsx`, replace lines 272–292 (both the edit button and delete button) with:

```tsx
                {/* Action group — right-aligned, hover reveal on desktop, always visible on mobile */}
                <div className="ml-auto flex items-center gap-0.5 opacity-0 group-hover:opacity-100 max-sm:opacity-100 transition-opacity">
                  {/* Edit */}
                  <button
                    type="button"
                    aria-label="Edit additive"
                    onClick={() => openEditModal(a)}
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
                    aria-label="Delete additive"
                    onClick={() => setDeleteAdditiveId(a.id)}
                    className="p-1 rounded text-ink-secondary hover:text-red-400 hover:bg-surface-overlay transition-colors"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round"
                        d="M3 4h10M6 4V2h4v2M5 4v9a1 1 0 001 1h4a1 1 0 001-1V4" />
                    </svg>
                  </button>
                </div>
```

- [ ] **Step 6: Add ConfirmModal for delete at the bottom of ConditionsTab's JSX return**

In `ConditionsTab.tsx`, find the closing `</>` of the component's return block (just before the final `}` of the component function), and add the `ConfirmModal` directly before that closing tag.

The existing JSX return ends with the edit additive modal and then `</>`. Add:

```tsx
      {/* Delete additive confirmation */}
      <ConfirmModal
        open={deleteAdditiveId !== null}
        onClose={() => setDeleteAdditiveId(null)}
        onConfirm={() => {
          if (deleteAdditiveId !== null) {
            deleteAdditiveMutation.mutate(deleteAdditiveId, {
              onSuccess: () => setDeleteAdditiveId(null),
            })
          }
        }}
        loading={deleteAdditiveMutation.isPending}
        title="Remove additive?"
        description="This will permanently remove the additive from this experiment."
        confirmLabel="Remove"
        danger
      />
```

- [ ] **Step 7: Run tests to confirm they pass**

```bash
cd frontend && npx vitest run src/pages/ExperimentDetail/__tests__/ConditionsTab.buttons.test.tsx
```

Expected: 2 passing.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/ConditionsTab.tsx \
        frontend/src/pages/ExperimentDetail/__tests__/ConditionsTab.buttons.test.tsx
git commit -m "[#24] fix additives edit/delete buttons in ConditionsTab

- Visible on hover (desktop) and always on mobile
- WCAG AA contrast: text-ink-secondary replaces text-ink-muted
- aria-label on both buttons; trash icon replaces × text
- ConfirmModal gates delete action
- Tests added: yes
- Docs updated: no"
```

---

## Task 4: Fix notes edit button and add delete in NotesTab

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/NotesTab.tsx`

**What's broken:**
- Edit button is `opacity-0 group-hover:opacity-100` with `text-ink-muted` — same contrast/visibility issues as Task 3
- No `aria-label` (only `title`)
- No delete button at all — must be added

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/ExperimentDetail/__tests__/NotesTab.buttons.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { NotesTab } from '../NotesTab'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    addNote: vi.fn(),
    patchNote: vi.fn(),
    deleteNote: vi.fn(),
  },
}))
vi.mock('@/components/ui', async () => {
  const actual = await vi.importActual<typeof import('@/components/ui')>('@/components/ui')
  return actual
})

const sampleNotes = [
  { id: 1, note_text: 'First note', created_at: '2026-01-01T00:00:00Z', updated_at: null },
  { id: 2, note_text: 'Second note', created_at: '2026-01-02T00:00:00Z', updated_at: null },
]

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('NotesTab action buttons', () => {
  it('renders edit buttons with aria-label for each note', () => {
    wrap(<NotesTab experimentId="HPHT_001" notes={sampleNotes} />)
    const editBtns = screen.getAllByRole('button', { name: /edit note/i })
    expect(editBtns).toHaveLength(2)
  })

  it('renders delete buttons with aria-label for each note', () => {
    wrap(<NotesTab experimentId="HPHT_001" notes={sampleNotes} />)
    const deleteBtns = screen.getAllByRole('button', { name: /delete note/i })
    expect(deleteBtns).toHaveLength(2)
  })
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npx vitest run src/pages/ExperimentDetail/__tests__/NotesTab.buttons.test.tsx
```

Expected: FAIL — delete buttons not found.

- [ ] **Step 3: Update NotesTab.tsx**

Replace the entire content of `frontend/src/pages/ExperimentDetail/NotesTab.tsx` with:

```tsx
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { Button, ConfirmModal, useToast } from '@/components/ui'

interface Note {
  id: number
  note_text: string
  created_at: string
  updated_at: string | null
}
interface Props { experimentId: string; notes: Note[] }

/** Notes tab: chronological lab notes with inline add, inline edit, and delete. */
export function NotesTab({ experimentId, notes }: Props) {
  const [text, setText] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editText, setEditText] = useState('')
  const [deleteNoteId, setDeleteNoteId] = useState<number | null>(null)
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()

  const addNote = useMutation({
    mutationFn: () => experimentsApi.addNote(experimentId, text),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] })
      success('Note added')
      setText('')
    },
    onError: (err: Error) => toastError('Failed to add note', err.message),
  })

  const editNote = useMutation({
    mutationFn: ({ noteId, newText }: { noteId: number; newText: string }) =>
      experimentsApi.patchNote(experimentId, noteId, newText),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] })
      success('Note updated')
      setEditingId(null)
      setEditText('')
    },
    onError: (err: Error) => toastError('Failed to update note', err.message),
  })

  const deleteNote = useMutation({
    mutationFn: (noteId: number) => experimentsApi.deleteNote(experimentId, noteId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] })
      success('Note deleted')
      setDeleteNoteId(null)
    },
    onError: (err: Error) => toastError('Failed to delete note', err.message),
  })

  const startEdit = (note: Note) => {
    setEditingId(note.id)
    setEditText(note.note_text ?? '')
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditText('')
  }

  const isEdited = (note: Note) =>
    note.updated_at != null && note.updated_at !== note.created_at

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
        <Button variant="primary" size="sm" disabled={!text.trim()} loading={addNote.isPending}
          onClick={() => addNote.mutate()}>
          Add Note
        </Button>
      </div>

      {/* Feed */}
      <div className="space-y-3">
        {notes.length === 0 && <p className="text-sm text-ink-muted">No notes yet</p>}
        {[...notes].reverse().map((n, i) => (
          <div
            key={n.id}
            className={`text-xs border-b border-surface-border pb-3 group ${i === notes.length - 1 ? 'border-b-0' : ''}`}
          >
            <div className="flex items-start justify-between gap-2 mb-0.5">
              <div className="flex items-center gap-1.5 flex-wrap">
                {i === notes.length - 1 && (
                  <span className="inline-block text-[10px] font-semibold uppercase tracking-wider text-brand-red bg-brand-red/10 px-1.5 py-0.5 rounded">
                    Condition Note
                  </span>
                )}
                {isEdited(n) && (
                  <span className="text-[10px] text-ink-muted italic">(edited)</span>
                )}
              </div>
              {editingId !== n.id && (
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 max-sm:opacity-100 transition-opacity shrink-0">
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
                <p className="text-ink-secondary leading-relaxed">{n.note_text}</p>
                <p className="text-ink-muted mt-0.5 font-mono-data">
                  {new Date(n.created_at).toLocaleString()}
                </p>
              </>
            )}
          </div>
        ))}
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

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd frontend && npx vitest run src/pages/ExperimentDetail/__tests__/NotesTab.buttons.test.tsx
```

Expected: 2 passing.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/NotesTab.tsx \
        frontend/src/pages/ExperimentDetail/__tests__/NotesTab.buttons.test.tsx
git commit -m "[#24] fix notes edit button and add delete in NotesTab

- aria-label on edit and delete buttons
- text-ink-secondary for WCAG AA contrast
- trash icon matches additives pattern
- ConfirmModal gates delete; deleteNote mutation wired
- Tests added: yes
- Docs updated: no"
```

---

## Task 5: E2E tests for additives edit and delete

**Files:**
- Create: `frontend/e2e/journeys/02-additives-crud.spec.ts`

These tests require a real experiment with at least one additive. The test creates the experiment, navigates to the Conditions tab, adds an additive, edits it, then deletes it.

- [ ] **Step 1: Create the test file**

```typescript
/**
 * Journey 2 — Additives edit/delete
 *
 * Creates an experiment, adds a chemical additive, verifies the edit button
 * is accessible (via aria-label), edits the additive, then deletes it via
 * the confirmation modal.
 */
import { test, expect } from '../fixtures/auth'

test.describe('Additives edit/delete', () => {
  let expId: string

  test.beforeAll(async ({ page }) => {
    // Create a minimal experiment
    await page.goto('/experiments/new')
    await page.getByLabel(/experiment type/i).selectOption('Serum')
    const idInput = page.getByLabel(/experiment id/i)
    await expect(idInput).not.toHaveValue(/loading/i, { timeout: 10_000 })
    expId = await idInput.inputValue()
    await page.getByRole('button', { name: /next.*condition/i }).click()
    await page.getByLabel(/rock mass/i).fill('5')
    await page.getByLabel(/water volume/i).fill('50')
    await page.getByRole('button', { name: /next.*additive/i }).click()
    await page.getByRole('button', { name: /next.*review/i }).click()
    await page.getByRole('button', { name: /create experiment/i }).click()
    await expect(page).not.toHaveURL(/\/experiments\/new/, { timeout: 15_000 })
  })

  test('edit button is visible and has correct aria-label', async ({ page }) => {
    await page.goto('/experiments')
    await page.getByText(expId).first().click()

    // Conditions tab should be active; add an additive first
    await page.getByRole('button', { name: /\+ add/i }).click()
    // Type compound name in search box
    await page.getByPlaceholder(/search compounds/i).fill('Magnetite')
    await page.getByText('Magnetite').first().click()
    await page.getByLabel(/amount/i).fill('2')
    await page.getByRole('button', { name: /^add additive$/i }).click()
    await expect(page.getByText('Magnetite')).toBeVisible({ timeout: 8_000 })

    // Hover the additive row to reveal action buttons
    const row = page.locator('div.group').filter({ hasText: 'Magnetite' }).first()
    await row.hover()

    const editBtn = row.getByRole('button', { name: /edit additive/i })
    await expect(editBtn).toBeVisible({ timeout: 5_000 })
  })

  test('edit flow opens modal and saves updated amount', async ({ page }) => {
    await page.goto(`/experiments/${expId}`)

    const row = page.locator('div.group').filter({ hasText: 'Magnetite' }).first()
    await row.hover()
    await row.getByRole('button', { name: /edit additive/i }).click()

    // Edit modal should be open — change amount
    const amountInput = page.getByLabel(/amount/i)
    await amountInput.clear()
    await amountInput.fill('10')
    await page.getByRole('button', { name: /save/i }).click()

    await expect(page.getByText('10')).toBeVisible({ timeout: 5_000 })
  })

  test('delete button triggers confirmation modal and removes additive', async ({ page }) => {
    await page.goto(`/experiments/${expId}`)

    const row = page.locator('div.group').filter({ hasText: 'Magnetite' }).first()
    await row.hover()
    await row.getByRole('button', { name: /delete additive/i }).click()

    // Confirmation modal must appear
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 3_000 })
    await expect(page.getByText(/remove additive/i)).toBeVisible()

    // Confirm deletion
    await page.getByRole('button', { name: /^remove$/i }).click()

    // Additive should be gone
    await expect(page.getByText('Magnetite')).not.toBeVisible({ timeout: 5_000 })
  })

  test('cancel on confirmation modal does not remove additive', async ({ page }) => {
    // Re-add the additive so we can cancel its deletion
    await page.goto(`/experiments/${expId}`)
    await page.getByRole('button', { name: /\+ add/i }).click()
    await page.getByPlaceholder(/search compounds/i).fill('Magnetite')
    await page.getByText('Magnetite').first().click()
    await page.getByLabel(/amount/i).fill('3')
    await page.getByRole('button', { name: /^add additive$/i }).click()
    await expect(page.getByText('Magnetite')).toBeVisible({ timeout: 8_000 })

    const row = page.locator('div.group').filter({ hasText: 'Magnetite' }).first()
    await row.hover()
    await row.getByRole('button', { name: /delete additive/i }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.getByRole('button', { name: /cancel/i }).click()

    // Additive still present
    await expect(page.getByText('Magnetite')).toBeVisible()
  })
})
```

- [ ] **Step 2: Run the E2E tests**

```bash
cd frontend && npx playwright test e2e/journeys/02-additives-crud.spec.ts --headed
```

Expected: 4 passing. If any fail due to selector mismatches, adjust the `getByPlaceholder` or `getByText` selectors to match the actual rendered text in the compound search UI.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/journeys/02-additives-crud.spec.ts
git commit -m "[#24] add E2E tests for additives edit/delete flow

- Tests added: yes
- Docs updated: no"
```

---

## Task 6: E2E tests for notes edit and delete

**Files:**
- Create: `frontend/e2e/journeys/03-notes-crud.spec.ts`

- [ ] **Step 1: Create the test file**

```typescript
/**
 * Journey 3 — Notes edit/delete
 *
 * Creates an experiment, navigates to the Notes tab, adds a note, edits it,
 * then deletes it. Verifies the confirmation modal gates deletion.
 */
import { test, expect } from '../fixtures/auth'

test.describe('Notes edit/delete', () => {
  let expId: string

  test.beforeAll(async ({ page }) => {
    await page.goto('/experiments/new')
    await page.getByLabel(/experiment type/i).selectOption('Autoclave')
    const idInput = page.getByLabel(/experiment id/i)
    await expect(idInput).not.toHaveValue(/loading/i, { timeout: 10_000 })
    expId = await idInput.inputValue()
    await page.getByRole('button', { name: /next.*condition/i }).click()
    await page.getByRole('button', { name: /next.*additive/i }).click()
    await page.getByRole('button', { name: /next.*review/i }).click()
    await page.getByRole('button', { name: /create experiment/i }).click()
    await expect(page).not.toHaveURL(/\/experiments\/new/, { timeout: 15_000 })
  })

  test('edit button is accessible via aria-label', async ({ page }) => {
    await page.goto(`/experiments/${expId}`)
    await page.getByRole('tab', { name: /notes/i }).click()

    // Add a note
    await page.getByPlaceholder(/add a note/i).fill('Initial observation')
    await page.getByRole('button', { name: /add note/i }).click()
    await expect(page.getByText('Initial observation')).toBeVisible({ timeout: 5_000 })

    // Hover the note row to reveal action buttons
    const noteRow = page.locator('div.group').filter({ hasText: 'Initial observation' }).first()
    await noteRow.hover()

    await expect(noteRow.getByRole('button', { name: /edit note/i })).toBeVisible({ timeout: 3_000 })
    await expect(noteRow.getByRole('button', { name: /delete note/i })).toBeVisible({ timeout: 3_000 })
  })

  test('edit flow opens inline editor and saves updated text', async ({ page }) => {
    await page.goto(`/experiments/${expId}`)
    await page.getByRole('tab', { name: /notes/i }).click()

    const noteRow = page.locator('div.group').filter({ hasText: 'Initial observation' }).first()
    await noteRow.hover()
    await noteRow.getByRole('button', { name: /edit note/i }).click()

    // Inline editor should appear
    const textarea = noteRow.locator('textarea')
    await expect(textarea).toBeVisible()
    await textarea.clear()
    await textarea.fill('Updated observation')
    await noteRow.getByRole('button', { name: /save/i }).click()

    await expect(page.getByText('Updated observation')).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText('Initial observation')).not.toBeVisible()
  })

  test('delete button triggers confirmation modal and removes note', async ({ page }) => {
    await page.goto(`/experiments/${expId}`)
    await page.getByRole('tab', { name: /notes/i }).click()

    const noteRow = page.locator('div.group').filter({ hasText: 'Updated observation' }).first()
    await noteRow.hover()
    await noteRow.getByRole('button', { name: /delete note/i }).click()

    // Confirmation modal
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 3_000 })
    await expect(page.getByText(/delete note/i)).toBeVisible()
    await page.getByRole('button', { name: /^delete$/i }).click()

    await expect(page.getByText('Updated observation')).not.toBeVisible({ timeout: 5_000 })
  })

  test('cancel on confirmation modal preserves the note', async ({ page }) => {
    await page.goto(`/experiments/${expId}`)
    await page.getByRole('tab', { name: /notes/i }).click()

    // Add a fresh note to cancel-test
    await page.getByPlaceholder(/add a note/i).fill('Note to keep')
    await page.getByRole('button', { name: /add note/i }).click()
    await expect(page.getByText('Note to keep')).toBeVisible({ timeout: 5_000 })

    const noteRow = page.locator('div.group').filter({ hasText: 'Note to keep' }).first()
    await noteRow.hover()
    await noteRow.getByRole('button', { name: /delete note/i }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.getByRole('button', { name: /cancel/i }).click()

    await expect(page.getByText('Note to keep')).toBeVisible()
  })
})
```

- [ ] **Step 2: Run the E2E tests**

```bash
cd frontend && npx playwright test e2e/journeys/03-notes-crud.spec.ts --headed
```

Expected: 4 passing. If the Notes tab label differs from `/notes/i`, inspect `ExperimentDetail/index.tsx` for the exact tab label string and adjust the selector.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/journeys/03-notes-crud.spec.ts
git commit -m "[#24] add E2E tests for notes edit/delete flow

- Tests added: yes
- Docs updated: no"
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Task |
|-------------|------|
| Buttons clearly visible on Conditions (additives) | Task 3 |
| Buttons clearly visible on Notes tab | Task 4 |
| WCAG AA contrast (`text-ink-secondary` replaces `text-ink-muted`) | Tasks 3 & 4 |
| Edit opens correct inline edit or modal flow | Tasks 3 & 4 |
| Delete prompts confirmation, then executes DELETE API call | Tasks 3 & 4 |
| `aria-label="Edit additive"`, `aria-label="Delete additive"` | Task 3 |
| `aria-label="Edit note"`, `aria-label="Delete note"` | Task 4 |
| Placement consistent across both sections | Tasks 3 & 4 (same pattern) |
| E2E: button visibility assertion | Tasks 5 & 6 |
| E2E: edit flow | Tasks 5 & 6 |
| E2E: delete confirmation and execution | Tasks 5 & 6 |
| E2E: correct row targeted for each action | Tasks 5 & 6 |
| Backend DELETE endpoint for notes (missing before this fix) | Task 1 |
| Frontend API `deleteNote` function | Task 2 |

**Placeholder scan:** No TBDs. All code blocks are complete.

**Type consistency check:** `deleteNoteId: number | null` used in Task 4 — matches `setDeleteNoteId(n.id)` where `n.id: number`. `deleteAdditiveId: number | null` in Task 3 — matches `a.id: number`. `ConfirmModal` props (`open`, `onClose`, `onConfirm`, `loading`, `title`, `description`, `confirmLabel`, `danger`) match `Modal.tsx` lines 79–88.
