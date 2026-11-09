import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { RunSegment } from '@/api/runs'
import { experimentsApi } from '@/api/experiments'
import { Button, Input, Table, TableBody, TableHead, TableRow, Td, Th, useToast } from '@/components/ui'
import { useExperimentIdValidation } from '@/hooks/useExperimentIdValidation'
import { DescriptionEditor } from '@/pages/ExperimentDetail/DescriptionEditor'
import { SegmentStatusSelect } from '@/components/runs/SegmentStatusSelect'
import { SegmentLink } from '@/components/runs/SegmentLink'
import type { RunWrites } from '@/components/runs/runWrites'
import { CORE_FLOOD_WRITES } from './useCoreFloodWrites'

interface Props {
  baseId: string
  segments: RunSegment[]
  /** Experiment ID whose rename input is open, or null. */
  renaming: string | null
  setRenaming: (experimentId: string | null) => void
  /** Experiment ID whose description editor is open, or null. */
  describing: string | null
  setDescribing: (experimentId: string | null) => void
  /** Refresh and routing for the page the table sits on; Core Flood by default. */
  writes?: RunWrites
}

interface SegmentProps {
  baseId: string
  segment: RunSegment
  writes: RunWrites
}

/** Inline rename. Renaming re-derives lineage on the server, so the segment can
 *  leave this run; the page follows it when it was the run's only segment. */
function RenameCell({
  baseId,
  segment,
  writes,
  segmentCount,
  onDone,
}: SegmentProps & { segmentCount: number; onDone: () => void }) {
  const [draft, setDraft] = useState(segment.experiment_id)
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { success, error: toastError } = useToast()
  const validation = useExperimentIdValidation(draft, segment.experiment_id)
  const trimmed = draft.trim()

  const mutation = useMutation({
    mutationFn: (newId: string) => experimentsApi.patch(segment.experiment_id, { experiment_id: newId }),
    onSuccess: (updated) => {
      const newBase = updated.base_experiment_id ?? updated.experiment_id
      onDone()
      if (newBase !== baseId) {
        if (segmentCount === 1) {
          navigate(writes.runPath(newBase), { replace: true })
        } else {
          success('Segment renamed', `${updated.experiment_id} moved to run ${newBase}`)
        }
        void writes.invalidate(qc, newBase, [])
        // The run's only segment left it, so the old run is gone: refetching 404s.
        if (segmentCount === 1) qc.removeQueries({ queryKey: writes.runQueryKey(baseId) })
      }
      return writes.invalidate(qc, baseId, [segment.experiment_id, updated.experiment_id])
    },
    onError: (err: Error) => toastError('Rename failed', err.message),
  })

  const canSave =
    validation.status === 'available' && trimmed !== segment.experiment_id && !mutation.isPending

  return (
    <div className="space-y-1.5">
      <Input
        aria-label="New experiment ID"
        className="font-mono-data text-xs"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onDone()
          if (e.key === 'Enter' && canSave) mutation.mutate(trimmed)
        }}
        error={validation.status === 'taken' || validation.status === 'error' ? validation.message : undefined}
        hint={validation.status === 'available' ? validation.message : undefined}
        autoFocus
      />
      <div className="flex gap-2">
        <Button
          variant="primary"
          size="xs"
          disabled={!canSave}
          loading={mutation.isPending}
          onClick={() => mutation.mutate(trimmed)}
        >
          Save
        </Button>
        <Button variant="ghost" size="xs" onClick={onDone}>Cancel</Button>
      </div>
    </div>
  )
}

/** The description, loaded on demand: the note ID only exists on the experiment detail. */
function DescribeCell({ baseId, segment, writes, onDone }: SegmentProps & { onDone: () => void }) {
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ['experiment', segment.experiment_id],
    queryFn: () => experimentsApi.get(segment.experiment_id),
  })
  if (error) {
    return (
      <span className="text-red-400">
        Could not load description: {(error as Error).message}{' '}
        <Button variant="ghost" size="xs" onClick={onDone}>Close</Button>
      </span>
    )
  }
  if (isLoading || !data) return <span className="text-ink-muted">Loading…</span>
  return (
    <DescriptionEditor
      experimentId={segment.experiment_id}
      note={data.notes.find((n) => n.note_type === 'description')}
      initialEditing
      onCancel={onDone}
      onSaved={() => {
        onDone()
        void writes.invalidate(qc, baseId, [segment.experiment_id])
      }}
    />
  )
}

/** The run's segments, with inline status, description and rename edits. */
export function SegmentsTable({
  baseId, segments, renaming, setRenaming, describing, setDescribing, writes = CORE_FLOOD_WRITES,
}: Props) {
  const qc = useQueryClient()
  return (
    <Table>
      <TableHead>
        <tr>
          <Th>Segment</Th>
          <Th>Status</Th>
          <Th>Description</Th>
        </tr>
      </TableHead>
      <TableBody>
        {segments.map((seg) => (
          <TableRow key={seg.id}>
            <Td>
              {renaming === seg.experiment_id ? (
                <RenameCell
                  baseId={baseId}
                  segment={seg}
                  writes={writes}
                  segmentCount={segments.length}
                  onDone={() => setRenaming(null)}
                />
              ) : (
                <div className="flex items-center gap-2">
                  <SegmentLink id={seg.experiment_id} />
                  <Button
                    variant="ghost"
                    size="xs"
                    aria-label={`Rename ${seg.experiment_id}`}
                    onClick={() => setRenaming(seg.experiment_id)}
                  >
                    Rename
                  </Button>
                </div>
              )}
            </Td>
            <Td>
              <SegmentStatusSelect
                segment={seg}
                onChanged={() => writes.invalidate(qc, baseId, [seg.experiment_id])}
              />
            </Td>
            <Td className="text-xs">
              {describing === seg.experiment_id ? (
                <DescribeCell baseId={baseId} segment={seg} writes={writes} onDone={() => setDescribing(null)} />
              ) : (
                <button
                  type="button"
                  aria-label={`Edit description of ${seg.experiment_id}`}
                  onClick={() => setDescribing(seg.experiment_id)}
                  className="text-left hover:text-ink-primary"
                >
                  {seg.description ?? <span className="text-ink-muted">Add description</span>}
                </button>
              )}
            </Td>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
