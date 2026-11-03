import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { CoreFloodSegment } from '@/api/coreFloods'
import { experimentsApi, type ExperimentStatus } from '@/api/experiments'
import { Select, useToast } from '@/components/ui'
import { invalidateCoreFloodWrites } from './useCoreFloodWrites'

const STATUS_OPTIONS: { value: ExperimentStatus; label: string }[] = [
  { value: 'ONGOING', label: 'Ongoing' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'CANCELLED', label: 'Cancelled' },
  { value: 'QUEUED', label: 'Queued' },
]

interface Props {
  baseId: string
  segment: CoreFloodSegment
}

/** Status control for one segment. It is controlled by the run query, so a
 *  rejected change (for example the 409 occupancy check) shows the old value. */
export function SegmentStatusSelect({ baseId, segment }: Props) {
  const qc = useQueryClient()
  const { error: toastError } = useToast()

  const mutation = useMutation({
    mutationFn: (status: ExperimentStatus) => experimentsApi.patchStatus(segment.experiment_id, status),
    onSuccess: () => invalidateCoreFloodWrites(qc, baseId, [segment.experiment_id]),
    onError: (err: Error) => toastError('Status not changed', err.message),
  })

  return (
    <Select
      aria-label={`Status of ${segment.experiment_id}`}
      className="h-7 text-xs"
      value={segment.status?.toUpperCase() ?? ''}
      placeholder={segment.status ? undefined : '—'}
      disabled={mutation.isPending}
      options={STATUS_OPTIONS}
      onChange={(e) => mutation.mutate(e.target.value as ExperimentStatus)}
    />
  )
}
