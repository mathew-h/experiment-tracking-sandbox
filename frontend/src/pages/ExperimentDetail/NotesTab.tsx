import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { Button, useToast } from '@/components/ui'

interface Note { id: number; note_text: string; created_at: string }
interface Props { experimentId: string; notes: Note[] }

/** Notes tab: chronological lab notes with inline add-note form. */
export function NotesTab({ experimentId, notes }: Props) {
  const [text, setText] = useState('')
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

  return (
    <div className="p-4 space-y-4">
      {/* Add note */}
      <div className="space-y-2">
        <textarea
          className="w-full bg-surface-raised border border-surface-border rounded px-3 py-2 text-sm text-navy-900 placeholder-ink-muted focus:outline-none focus:ring-1 focus:ring-brand-red/50 resize-none"
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
          <div key={n.id} className={`text-xs border-b border-surface-border pb-3 ${i === notes.length - 1 ? 'border-b-0' : ''}`}>
            {i === notes.length - 1 && (
              <span className="inline-block text-[10px] font-semibold uppercase tracking-wider text-brand-red bg-brand-red/10 px-1.5 py-0.5 rounded mb-1">
                Condition Note
              </span>
            )}
            <p className="text-ink-secondary leading-relaxed">{n.note_text}</p>
            <p className="text-ink-muted mt-0.5 font-mono-data">
              {new Date(n.created_at).toLocaleString()}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
