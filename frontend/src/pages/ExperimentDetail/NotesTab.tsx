import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { experimentsApi, type ExperimentNote } from '@/api/experiments'
import { NOTE_TYPE_LABELS, type NoteType } from '@/api/noteTypes'
import { Badge, Button, ConfirmModal, useToast } from '@/components/ui'

interface Props { experimentId: string; notes: ExperimentNote[] }

/** Types a researcher can pick when writing an experiment-level note here.
 *  'modification' and 'result_note' are scoped to a timepoint and are written
 *  from the Results tab (Add Results), not from this feed. */
const ADDABLE_TYPES: NoteType[] = ['observation', 'description']

/** Types a note may be retyped to, given its anchor — the UI mirror of the
 *  ck_note_scope CHECK (issue #122, design decision 8). The DB stays the
 *  authority: an invalid combination is still a 422 from PATCH. */
function retypeOptions(n: ExperimentNote): NoteType[] {
  return n.result_id == null
    ? ['observation', 'description']
    : ['observation', 'modification', 'result_note']
}

/** Notes tab (issue #118): typed lab notes with inline add, edit, delete, and
 *  the review queue for rows the backfill could not place with certainty. */
export function NotesTab({ experimentId, notes }: Props) {
  const [text, setText] = useState('')
  const [newType, setNewType] = useState<NoteType>('observation')
  const [reviewOnly, setReviewOnly] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editText, setEditText] = useState('')
  const [deleteNoteId, setDeleteNoteId] = useState<number | null>(null)
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()

  const hasDescription = notes.some((n) => n.note_type === 'description')
  const reviewCount = notes.filter((n) => n.needs_review).length
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] })

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

  const visible = [...notes].reverse().filter((n) => !reviewOnly || n.needs_review)

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

      {/* Review-queue filter */}
      {reviewCount > 0 && (
        <label className="flex items-center gap-2 text-xs text-ink-secondary">
          <input
            type="checkbox"
            checked={reviewOnly}
            onChange={(e) => setReviewOnly(e.target.checked)}
          />
          Review queue only ({reviewCount})
        </label>
      )}

      {/* Feed */}
      <div className="space-y-3">
        {notes.length === 0 && <p className="text-sm text-ink-muted">No notes yet</p>}
        {notes.length > 0 && visible.length === 0 && (
          <p className="text-sm text-ink-muted">Nothing left to review</p>
        )}
        {visible.map((n, i) => {
          const isRetyping = retypeNote.isPending && retypeNote.variables?.noteId === n.id
          return (
          <div
            key={n.id}
            className={`text-xs border-b border-surface-border pb-3 group ${i === visible.length - 1 ? 'border-b-0' : ''}`}
          >
            <div className="flex items-start justify-between gap-2 mb-0.5">
              <div className="flex items-center gap-1.5 flex-wrap">
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
                {n.result_id != null && (
                  <span className="text-[10px] text-ink-muted">on a timepoint</span>
                )}
                {n.needs_review && (
                  <Badge variant="error" dot>Needs review</Badge>
                )}
                {isEdited(n) && (
                  <span className="text-[10px] text-ink-muted italic">(edited)</span>
                )}
              </div>
              {editingId !== n.id && (
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 max-sm:opacity-100 transition-opacity shrink-0">
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
