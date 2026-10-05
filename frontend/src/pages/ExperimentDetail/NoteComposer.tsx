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
        // A result-scoped note changes the Results tab's MOD/NOTE flags.
        queryClient.invalidateQueries({ queryKey: ['experiment-results', experimentId] }),
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
