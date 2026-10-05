import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { experimentsApi, type ExperimentNote } from '@/api/experiments'
import { NOTE_TYPE_LABELS, type NoteType } from '@/api/noteTypes'
import { Badge, Button, ConfirmModal, useToast } from '@/components/ui'
import { NoteBadge } from '@/components/experiments/NoteBadge'
import { NoteComposer } from './NoteComposer'
import { sortTimeline, timepointLabel } from './notesTimeline'

interface Props { experimentId: string; notes: ExperimentNote[] }

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
  const [reviewOnly, setReviewOnly] = useState(false)
  const [typeFilter, setTypeFilter] = useState<NoteType | 'all'>('all')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editText, setEditText] = useState('')
  const [deleteNoteId, setDeleteNoteId] = useState<number | null>(null)
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()

  const hasDescription = notes.some((n) => n.note_type === 'description')
  const reviewCount = notes.filter((n) => n.needs_review).length

  /** Every page that renders a note: this tab, the Results tab's MOD/NOTE
   *  flags, the experiments list's Description column, the reactor card. */
  const invalidateNoteQueries = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] }),
      queryClient.invalidateQueries({ queryKey: ['experiment-results', experimentId] }),
      queryClient.invalidateQueries({ queryKey: ['experiments'] }),
      queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
    ])

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

  const editNote = useMutation({
    mutationFn: ({ noteId, newText }: { noteId: number; newText: string }) =>
      experimentsApi.patchNote(experimentId, noteId, { note_text: newText }),
    onSuccess: () => {
      success('Note updated')
      setEditingId(null)
      setEditText('')
      return invalidateNoteQueries()
    },
    onError: (err: Error) => toastError('Failed to update note', err.message),
  })

  const resolveNote = useMutation({
    mutationFn: (noteId: number) => experimentsApi.patchNote(experimentId, noteId, { needs_review: false }),
    onSuccess: () => {
      success('Marked as reviewed')
      return invalidateNoteQueries()
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
      return invalidateNoteQueries()
    },
    onError: (err: Error) => toastError('Failed to change note type', err.message),
  })

  const deleteNote = useMutation({
    mutationFn: (noteId: number) => experimentsApi.deleteNote(experimentId, noteId),
    onSuccess: () => {
      success('Note deleted')
      setDeleteNoteId(null)
      return invalidateNoteQueries()
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
      <NoteComposer experimentId={experimentId} hasDescription={hasDescription} results={results} />

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
