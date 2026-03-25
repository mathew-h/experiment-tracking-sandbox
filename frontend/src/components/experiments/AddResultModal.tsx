/**
 * AddResultModal — record a new result timepoint for an experiment.
 *
 * IMPORTANT: this component receives `experimentPk`, the INTEGER primary key
 * from experiments.id — never the string experiment_id from the URL.
 *
 * Correct usage (in ExperimentDetail):
 *   const { data: experiment } = useQuery(...)
 *   <AddResultModal experimentPk={experiment.id} ... />   // ← integer PK
 *
 * Wrong:
 *   <AddResultModal experimentPk={id} ... />              // id is URL string
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Modal, Button, Input } from '@/components/ui'
import { resultsApi } from '@/api/results'

interface Props {
  /** experiments.id integer PK — NOT the string experiment_id URL param */
  experimentPk: number
  /** string experiment_id (e.g. "HPHT_001") used only to invalidate the query cache */
  experimentStringId: string
  open: boolean
  onClose: () => void
}

interface FormState {
  description: string
  time_post_reaction_days: string
  is_primary_timepoint_result: boolean
}

const INITIAL: FormState = {
  description: '',
  time_post_reaction_days: '',
  is_primary_timepoint_result: true,
}

export function AddResultModal({ experimentPk, experimentStringId, open, onClose }: Props) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<FormState>(INITIAL)
  const [errors, setErrors] = useState<Partial<FormState>>({})

  const mutation = useMutation({
    mutationFn: () =>
      resultsApi.createResult({
        // experiment_fk receives the integer PK (experiments.id), never the URL string
        experiment_fk: experimentPk,
        description: form.description.trim(),
        time_post_reaction_days: form.time_post_reaction_days
          ? parseFloat(form.time_post_reaction_days)
          : null,
        is_primary_timepoint_result: form.is_primary_timepoint_result,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['results', experimentStringId] })
      setForm(INITIAL)
      onClose()
    },
  })

  function validate(): boolean {
    const next: Partial<FormState> = {}
    if (!form.description.trim()) next.description = 'Description is required'
    if (form.time_post_reaction_days && isNaN(parseFloat(form.time_post_reaction_days))) {
      next.time_post_reaction_days = 'Must be a number'
    }
    setErrors(next)
    return Object.keys(next).length === 0
  }

  function handleSubmit() {
    if (!validate()) return
    mutation.mutate()
  }

  function handleClose() {
    setForm(INITIAL)
    setErrors({})
    mutation.reset()
    onClose()
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Add Result Timepoint"
      description="Record a new measurement timepoint for this experiment"
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSubmit} loading={mutation.isPending}>
            Save Timepoint
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {mutation.isError && (
          <p className="text-xs text-red-400 bg-red-500/10 rounded px-3 py-2">
            {(mutation.error as Error).message}
          </p>
        )}

        <Input
          label="Description *"
          placeholder="e.g. Day 7 sampling — reactor A"
          value={form.description}
          onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
          error={errors.description}
        />

        <Input
          label="Days Post-Reaction"
          placeholder="e.g. 7"
          type="number"
          min={0}
          step="0.5"
          value={form.time_post_reaction_days}
          onChange={(e) =>
            setForm((f) => ({ ...f, time_post_reaction_days: e.target.value }))
          }
          error={errors.time_post_reaction_days}
          hint="Leave blank if unknown"
        />

        <label className="flex items-center gap-2.5 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={form.is_primary_timepoint_result}
            onChange={(e) =>
              setForm((f) => ({ ...f, is_primary_timepoint_result: e.target.checked }))
            }
            className="w-4 h-4 rounded border-surface-border accent-red-500 cursor-pointer"
          />
          <span className="text-sm text-ink-secondary">
            Primary timepoint result
            <span className="block text-xs text-ink-muted font-normal">
              Used in Power BI dashboard aggregations
            </span>
          </span>
        </label>
      </div>
    </Modal>
  )
}
