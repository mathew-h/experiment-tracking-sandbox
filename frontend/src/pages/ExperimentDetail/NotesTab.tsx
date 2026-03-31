import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { Button, useToast } from '@/components/ui'

interface Note {
  id: number
  note_text: string
  created_at: string
  updated_at: string | null
}
interface Props { experimentId: string; notes: Note[] }

/** Notes tab: chronological lab notes with inline add and inline edit. */
export function NotesTab({ experimentId, notes }: Props) {
  const [text, setText] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editText, setEditText] = useState('')
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
                <button
                  type="button"
                  className="opacity-0 group-hover:opacity-100 transition-opacity text-ink-muted hover:text-ink-primary p-0.5"
                  onClick={() => startEdit(n)}
                  title="Edit note"
                >
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round"
                      d="M11.5 2.5a1.414 1.414 0 012 2L5 13H3v-2L11.5 2.5z" />
                  </svg>
                </button>
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
    </div>
  )
}
