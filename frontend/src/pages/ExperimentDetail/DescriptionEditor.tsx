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
    // addNote resolves the unwrapped ExperimentNote; patchNote resolves the
    // raw AxiosResponse. Neither value is used below, so the mutation result
    // is typed unknown rather than forcing the two shapes to unify.
    mutationFn: (text: string): Promise<unknown> =>
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
