import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { HphtRun, HphtSample } from '@/api/hpht'
import type { RunSegment } from '@/api/runs'
import { experimentsApi } from '@/api/experiments'
import { Modal, PageSpinner, Select } from '@/components/ui'
import { ResultEntryModal } from '@/pages/ExperimentDetail/ResultEntryModal'

interface Props {
  open: boolean
  onClose: () => void
  run: HphtRun
  /** A timeline row to edit; omitted to add a sample. */
  editing?: HphtSample
}

const isOngoing = (s: RunSegment) => s.status?.toUpperCase() === 'ONGOING'

/** Segment a new sample goes to by default: the ongoing one, else the newest main-line segment. */
function defaultSegment(segments: RunSegment[]): RunSegment | undefined {
  const ongoing = segments.filter(isOngoing)
  if (ongoing.length > 0) return ongoing[0]
  const dated = (s: RunSegment) => (s.date ? Date.parse(s.date) : -Infinity)
  return [...segments].filter((s) => !s.is_variant).sort((a, b) => dated(b) - dated(a) || b.id - a.id)[0]
    ?? segments[0]
}

/** The redesigned result modal (#148) pointed at one segment of an HPHT run.
 *  With exactly one ONGOING segment a new sample goes there; otherwise a
 *  segment select is shown in the modal header. Editing targets the row's segment. */
export function HphtSampleModal({ open, onClose, run, editing }: Props) {
  if (!open) return null
  return <Body key={editing?.result_id ?? 'new'} onClose={onClose} run={run} editing={editing} />
}

function Body({ onClose, run, editing }: Omit<Props, 'open'>) {
  const ongoing = run.segments.filter(isOngoing)
  const choose = !editing && ongoing.length !== 1
  const [segmentId, setSegmentId] = useState<string | undefined>(
    () => editing?.experiment_id ?? defaultSegment(run.segments)?.experiment_id,
  )
  const segment = run.segments.find((s) => s.experiment_id === segmentId)

  // The segment's results: the same-day replace warning needs them, and edit
  // mode needs the row in the shape the modal reads.
  const { data: results, isLoading, error } = useQuery({
    queryKey: ['experiment-results', segmentId],
    queryFn: () => experimentsApi.getResults(segmentId as string),
    enabled: !!segmentId,
  })

  // Named for the run page's "+ Add sample" button (issue #161, NAV-15).
  const title = editing ? 'Edit sample' : 'Add sample'
  if (!segment) {
    return (
      <Modal open onClose={onClose} title={title} size="xl">
        <p className="text-sm text-ink-muted">This run has no segment to add a sample to.</p>
      </Modal>
    )
  }
  if (isLoading || error) {
    return (
      <Modal open onClose={onClose} title={title} size="xl">
        {error ? (
          <p role="alert" className="text-sm text-status-error">
            Could not load {segment.experiment_id}: {(error as Error).message}
          </p>
        ) : (
          <PageSpinner />
        )}
      </Modal>
    )
  }

  const editRow = editing ? results?.find((r) => r.id === editing.result_id) : undefined
  if (editing && !editRow) {
    return (
      <Modal open onClose={onClose} title={title} size="xl">
        <p role="alert" className="text-sm text-status-error">
          Result {editing.result_id} is no longer on {segment.experiment_id}.
        </p>
      </Modal>
    )
  }

  const header = choose ? (
    <Select
      label="Segment"
      value={segment.experiment_id}
      options={run.segments.map((s) => ({
        value: s.experiment_id,
        label: `${s.experiment_id}${isOngoing(s) ? ' (ongoing)' : ''}${s.is_variant ? ' (side sample)' : ''}`,
      }))}
      onChange={(e) => setSegmentId(e.target.value)}
      hint={ongoing.length === 0 ? 'No segment is ONGOING; pick where this sample belongs.' : undefined}
    />
  ) : (
    <p className="text-xs text-ink-muted" data-testid="target-segment">
      Segment <span className="font-mono-data text-ink-primary">{segment.experiment_id}</span>
    </p>
  )

  return (
    <ResultEntryModal
      // A new segment means a new start date, so the form (and its Day) starts over.
      key={segment.experiment_id}
      open
      onClose={onClose}
      experimentId={segment.experiment_id}
      experimentType="HPHT"
      experimentStart={segment.date}
      baseId={run.base_id}
      results={results ?? []}
      editing={editRow}
      headerSlot={header}
      noun="sample"
    />
  )
}
