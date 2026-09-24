import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  experimentsApi,
  type ReviewNoteItem,
  type ReviewOrder,
  type ReviewQueueParams,
  type NotesBulkPatch,
} from '@/api/experiments'
import { NOTE_TYPE_LABELS, type NoteType } from '@/api/noteTypes'
import {
  Badge, Button, ConfirmModal, Input, Select, Spinner,
  Table, TableBody, TableHead, TableRow, Td, Th, useToast,
} from '@/components/ui'

/** One page = one bulk call: the server caps bulk bodies at 500 ids, so the
 *  page never loads more than it can act on in one go. */
const PAGE_LIMIT = 500

const NOTE_TYPES: NoteType[] = ['description', 'modification', 'observation', 'result_note']

type PendingAction = { kind: 'review' } | { kind: 'retype'; to: NoteType } | { kind: 'delete' } | null

function typeBadgeVariant(t: NoteType): 'default' | 'warning' | 'info' {
  if (t === 'modification') return 'warning'
  if (t === 'description') return 'info'
  return 'default'
}

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

/** Issue #122 PR-A: the global review queue. Every row is a note the #118
 *  backfill flagged `needs_review`. Researchers filter, select (rows, all
 *  loaded, or "every row reading X"), then Mark reviewed / Retype / Delete in
 *  one atomic, per-note-audited call. */
export function NotesReviewPage() {
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()

  // Filters
  const [researcher, setResearcher] = useState('')
  const [experimentId, setExperimentId] = useState('')
  const [noteType, setNoteType] = useState<NoteType | ''>('')
  const [search, setSearch] = useState('')
  const [order, setOrder] = useState<ReviewOrder>('experiment')
  const [desc, setDesc] = useState(false)
  const q = useDebounced(search.trim(), 300)
  const researcherQ = useDebounced(researcher.trim(), 300)
  const experimentQ = useDebounced(experimentId.trim(), 300)

  const params = useMemo<ReviewQueueParams>(() => ({
    limit: PAGE_LIMIT,
    skip: 0,
    order,
    desc,
    ...(researcherQ ? { researcher: researcherQ } : {}),
    ...(experimentQ ? { experiment_id: experimentQ } : {}),
    ...(noteType ? { note_type: noteType } : {}),
    ...(q ? { q } : {}),
  }), [order, desc, researcherQ, experimentQ, noteType, q])

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['notes-review', 'list', params],
    queryFn: () => experimentsApi.getReviewQueue(params),
  })
  const items: ReviewNoteItem[] = useMemo(() => data?.items ?? [], [data])
  const total = data?.total ?? 0

  // Selection (ids of loaded rows only)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  useEffect(() => {
    // Drop ids that left the loaded set (filter change or a completed action).
    setSelected((prev) => {
      const live = new Set(items.map((i) => i.id))
      const next = new Set([...prev].filter((id) => live.has(id)))
      return next.size === prev.size ? prev : next
    })
  }, [items])

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  const allSelected = items.length > 0 && items.every((i) => selected.has(i.id))
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(items.map((i) => i.id)))
  const selectText = (text: string) =>
    setSelected((prev) => new Set([...prev, ...items.filter((i) => i.note_text === text).map((i) => i.id)]))
  const selectedIds = () => items.filter((i) => selected.has(i.id)).map((i) => i.id)

  // Actions
  const [retypeTo, setRetypeTo] = useState<NoteType>('observation')
  const [pending, setPending] = useState<PendingAction>(null)
  const afterAction = (msg: string) => {
    success(msg)
    setSelected(new Set())
    setPending(null)
    queryClient.invalidateQueries({ queryKey: ['notes-review'] })
  }
  const patch = useMutation({
    mutationFn: (body: NotesBulkPatch) => experimentsApi.bulkPatchNotes(body),
    onSuccess: (r) => afterAction(`${plural(r.count, 'note')} updated`),
    onError: (err: Error) => toastError('Bulk update failed', err.message),
  })
  const remove = useMutation({
    mutationFn: (ids: number[]) => experimentsApi.bulkDeleteNotes(ids),
    onSuccess: (r) => afterAction(`${plural(r.count, 'note')} deleted`),
    onError: (err: Error) => toastError('Bulk delete failed', err.message),
  })

  const confirmPending = () => {
    const ids = selectedIds()
    if (!pending || ids.length === 0) return
    if (pending.kind === 'review') patch.mutate({ ids, needs_review: false })
    else if (pending.kind === 'retype') patch.mutate({ ids, note_type: pending.to, needs_review: false })
    else remove.mutate(ids)
  }

  const busy = patch.isPending || remove.isPending
  const count = selected.size
  const pendingCopy = (() => {
    if (!pending) return { title: '', description: '', label: 'Confirm', danger: false }
    if (pending.kind === 'review')
      return { title: 'Mark as reviewed?', description: `${plural(count, 'note')} will leave the review queue. They are not changed otherwise.`, label: 'Mark reviewed', danger: false }
    if (pending.kind === 'retype')
      return { title: `Retype as ${NOTE_TYPE_LABELS[pending.to]}?`, description: `${plural(count, 'note')} will become "${NOTE_TYPE_LABELS[pending.to]}" and leave the review queue. Scope rules apply: the whole batch is rejected if any note cannot take this type.`, label: 'Retype', danger: false }
    return { title: 'Delete notes?', description: `${plural(count, 'note')} will be permanently deleted. Each deletion is recorded in the entry log.`, label: 'Delete', danger: true }
  })()

  return (
    <div className="space-y-4 pb-20">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-lg font-semibold text-ink-primary">Notes review</h1>
          <p className="text-xs text-ink-muted mt-0.5">
            {isLoading ? 'Loading…' : data ? `${total} open` : '—'}
            {!isLoading && total > items.length && (
              <> · showing first {items.length} of {total} — narrow the filter to reach the rest</>
            )}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3 items-end">
        <Input label="Researcher" value={researcher} onChange={(e) => setResearcher(e.target.value)} placeholder="MH" />
        <Input label="Experiment" value={experimentId} onChange={(e) => setExperimentId(e.target.value)} placeholder="SERUM_001" />
        <Select
          label="Type"
          value={noteType}
          onChange={(e) => setNoteType(e.target.value as NoteType | '')}
          options={[{ value: '', label: 'Any type' }, ...NOTE_TYPES.map((t) => ({ value: t, label: NOTE_TYPE_LABELS[t] }))]}
        />
        <Input label="Search text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="t=0" />
        <Select
          label="Order"
          value={order}
          onChange={(e) => setOrder(e.target.value as ReviewOrder)}
          options={[
            { value: 'experiment', label: 'Experiment' },
            { value: 'created_at', label: 'Created' },
            { value: 'text', label: 'Text' },
          ]}
        />
        <Button variant="secondary" size="md" onClick={() => setDesc((d) => !d)} aria-label="Toggle sort direction">
          {desc ? 'Descending' : 'Ascending'}
        </Button>
      </div>

      {/* Distinct-text chips */}
      {data && data.distinct_texts.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {data.distinct_texts.map((d) => {
            // distinct_texts.count is server-side over the whole filter, but a
            // chip click only selects rows already LOADED on the page — name
            // the chip honestly when the loaded set is a truncated subset.
            const loadedCount = items.filter((i) => i.note_text === d.text).length
            const truncated = loadedCount !== d.count
            const shown = d.text || '(blank)'
            const label = truncated
              ? `Select ${loadedCount} loaded of ${d.count} reading ${d.text}`
              : `Select all ${d.count} reading ${d.text}`
            const title = truncated
              ? `Select ${loadedCount} loaded of ${d.count} reading "${shown}"`
              : `Select all ${d.count} reading "${shown}"`
            return (
              <button
                key={d.text}
                type="button"
                aria-label={label}
                title={title}
                onClick={() => selectText(d.text)}
                className="inline-flex items-center gap-1.5 max-w-xs px-2 py-0.5 rounded border border-surface-border bg-surface-raised text-2xs text-ink-secondary hover:text-ink-primary hover:border-ink-muted transition-colors"
              >
                <span className="truncate font-mono-data">{d.text || '(blank)'}</span>
                <span className="text-ink-muted">×{d.count}</span>
              </button>
            )
          })}
        </div>
      )}

      {/* Table */}
      {isLoading && <div className="py-12 flex justify-center"><Spinner /></div>}
      {isError && <p className="text-sm text-status-error">Failed to load: {(error as Error).message}</p>}
      {data && items.length === 0 && <p className="text-sm text-ink-muted py-8">Nothing left to review in this filter.</p>}
      {items.length > 0 && (
        <Table>
          <TableHead>
            <tr>
              <Th className="w-8">
                <input type="checkbox" aria-label="Select all" checked={allSelected} onChange={toggleAll} />
              </Th>
              <Th>Experiment</Th>
              <Th>Researcher</Th>
              <Th>Timepoint</Th>
              <Th>Type</Th>
              <Th>Text</Th>
              <Th>Author</Th>
              <Th>Date</Th>
            </tr>
          </TableHead>
          <TableBody>
            {items.map((n) => (
              <TableRow key={n.id} className={selected.has(n.id) ? 'bg-red-500/5' : ''}>
                <Td>
                  <input
                    type="checkbox"
                    aria-label={`Select note ${n.id}`}
                    checked={selected.has(n.id)}
                    onChange={() => toggle(n.id)}
                  />
                </Td>
                <Td>
                  <Link to={`/experiments/${encodeURIComponent(n.experiment_id)}`} className="text-ink-primary hover:text-red-400 font-mono-data">
                    {n.experiment_id}
                  </Link>
                </Td>
                <Td className="text-ink-secondary">{n.researcher ?? '—'}</Td>
                <Td className="font-mono-data text-ink-secondary">
                  {n.time_post_reaction_days != null ? `T+${n.time_post_reaction_days}` : '—'}
                </Td>
                <Td><Badge variant={typeBadgeVariant(n.note_type)}>{NOTE_TYPE_LABELS[n.note_type]}</Badge></Td>
                <Td className="max-w-md whitespace-pre-wrap text-ink-primary">{n.note_text}</Td>
                <Td className="text-ink-muted text-xs">{n.created_by ?? '—'}</Td>
                <Td className="text-ink-muted text-xs font-mono-data whitespace-nowrap">
                  {new Date(n.created_at).toLocaleDateString()}
                </Td>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {/* Sticky action bar */}
      {count > 0 && (
        <div className="fixed bottom-0 left-[240px] right-0 border-t border-surface-border bg-surface-raised/95 backdrop-blur-sm px-6 py-3 flex items-center gap-3 flex-wrap z-20">
          <span className="text-sm text-ink-primary font-medium">{count} selected</span>
          <Button variant="primary" size="sm" disabled={busy} onClick={() => setPending({ kind: 'review' })}>
            Mark reviewed
          </Button>
          <div className="flex items-center gap-1.5">
            <label htmlFor="retype-to" className="text-xs text-ink-secondary">Retype to</label>
            <select
              id="retype-to"
              value={retypeTo}
              onChange={(e) => setRetypeTo(e.target.value as NoteType)}
              className="text-xs px-2 py-1 border border-surface-border rounded bg-surface-raised text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50"
            >
              {NOTE_TYPES.map((t) => <option key={t} value={t}>{NOTE_TYPE_LABELS[t]}</option>)}
            </select>
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => setPending({ kind: 'retype', to: retypeTo })}>
              Retype
            </Button>
          </div>
          <Button variant="danger" size="sm" disabled={busy} onClick={() => setPending({ kind: 'delete' })}>
            Delete
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>Clear</Button>
        </div>
      )}

      <ConfirmModal
        open={pending !== null}
        onClose={() => setPending(null)}
        onConfirm={confirmPending}
        loading={busy}
        title={pendingCopy.title}
        description={pendingCopy.description}
        confirmLabel={pendingCopy.label}
        danger={pendingCopy.danger}
      />
    </div>
  )
}
