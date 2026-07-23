import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { Modal, Button, Input, useToast } from '@/components/ui'

const LETTERS = 'abcdefghijklmnopqrstuvwxyz'

interface CreateReplicatesModalProps {
  open: boolean
  onClose: () => void
  baseExperimentId: string
}

/** Batch-create lettered replicates of a base experiment (issue #70 P2).
 *  Conditions and chemical additives are copied server-side from the base. */
export function CreateReplicatesModal({ open, onClose, baseExperimentId }: CreateReplicatesModalProps) {
  const [count, setCount] = useState(3)
  const { success, error: toastError } = useToast()
  const queryClient = useQueryClient()

  const { data: group } = useQuery({
    queryKey: ['replicate-group', baseExperimentId],
    queryFn: () => experimentsApi.getReplicateGroup(baseExperimentId),
    enabled: open,
  })

  const resolvedBase = group?.base_experiment_id ?? baseExperimentId

  const previewIds = useMemo(() => {
    const existing = new Set((group?.members ?? []).map((m) => m.replicate_label))
    return LETTERS.split('')
      .filter((l) => !existing.has(l))
      .slice(0, count)
      .map((l) => `${resolvedBase}${l}`)
  }, [group, resolvedBase, count])

  function resetAndClose() {
    setCount(3)
    onClose()
  }

  const mutation = useMutation({
    mutationFn: () =>
      experimentsApi.createReplicates({ base_experiment_id: baseExperimentId, count }),
    onSuccess: (data) => {
      const ids = data.created.map((e) => e.experiment_id)
      success(ids.length ? `Created ${ids.join(', ')}` : 'No replicates created')
      data.skipped.forEach((msg) => toastError('Skipped', msg))
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
      queryClient.invalidateQueries({ queryKey: ['replicate-group', baseExperimentId] })
      resetAndClose()
    },
    onError: (err: Error) => toastError('Failed to create replicates', err.message),
  })

  return (
    <Modal
      open={open}
      onClose={resetAndClose}
      title="Create Replicates"
      description="Copies this experiment's conditions and additives to new lettered replicate vials. Per-vial actuals (e.g. actual rock mass) stay editable on each replicate."
      size="sm"
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={resetAndClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={mutation.isPending || count < 1}
          >
            Create Replicates
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <p className="text-xs text-ink-secondary">
          Replicates are created under{' '}
          <span className="font-mono-data text-ink-primary">{resolvedBase}</span>, copying its
          conditions and additives.
        </p>
        <div className="w-28">
          <Input
            label="How many?"
            type="number"
            min={1}
            max={25}
            value={String(count)}
            onChange={(e) => setCount(Math.max(1, Math.min(25, Number(e.target.value) || 1)))}
          />
        </div>
        <p className="text-xs text-ink-secondary">
          Will create:{' '}
          <span className="font-mono-data text-ink-primary">{previewIds.join(', ') || '—'}</span>
        </p>
      </div>
    </Modal>
  )
}
