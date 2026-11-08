import { useMutation } from '@tanstack/react-query'
import type { RunSegment } from '@/api/runs'
import { experimentsApi, type ExperimentStatus } from '@/api/experiments'
import { Select, useToast } from '@/components/ui'

const STATUS_OPTIONS: { value: ExperimentStatus; label: string }[] = [
  { value: 'ONGOING', label: 'Ongoing' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'CANCELLED', label: 'Cancelled' },
  { value: 'QUEUED', label: 'Queued' },
]

interface Props {
  segment: RunSegment
  /** Refreshes the page's run queries after a successful change. */
  onChanged: () => Promise<unknown> | void
}

/** Status control for one run segment (Core Flood and HPHT run pages). It is
 *  controlled by the run query, so a rejected change (for example the 409
 *  occupancy check) shows the old value. */
export function SegmentStatusSelect({ segment, onChanged }: Props) {
  const { error: toastError } = useToast()

  const mutation = useMutation({
    mutationFn: (status: ExperimentStatus) => experimentsApi.patchStatus(segment.experiment_id, status),
    onSuccess: () => onChanged(),
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
