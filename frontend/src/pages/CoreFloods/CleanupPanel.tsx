import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { CoreFloodRun, CoreFloodSample, CoreFloodWarning } from '@/api/coreFloods'
import { conditionsApi } from '@/api/conditions'
import { Button, Card, CardHeader, Input, useToast } from '@/components/ui'
import { labDateOf } from '@/utils/labDate'
import { SegmentStatusSelect } from './SegmentStatusSelect'
import { invalidateCoreFloodWrites } from './useCoreFloodWrites'

interface Props {
  baseId: string
  run: CoreFloodRun
  onEditSample: (s: CoreFloodSample) => void
  onRename: (experimentId: string) => void
  onEditDescription: (experimentId: string) => void
}

/** Sets one pore volume on every listed segment that has a conditions row. */
function PoreVolumeAll({ baseId, run, ids }: { baseId: string; run: CoreFloodRun; ids: string[] }) {
  const [draft, setDraft] = useState('')
  const qc = useQueryClient()
  const { success, error: toastError } = useToast()
  const value = Number(draft.trim())
  const valid = draft.trim() !== '' && Number.isFinite(value) && value > 0

  const mutation = useMutation({
    mutationFn: async (v: number) => {
      const listed = run.segments.filter((s) => ids.includes(s.experiment_id))
      const writable = listed.filter((s) => s.conditions_id != null)
      await Promise.all(
        writable.map((s) => conditionsApi.patch(s.conditions_id as number, { pore_volume_mL: v })),
      )
      return {
        skipped: listed.filter((s) => s.conditions_id == null).map((s) => s.experiment_id),
        touched: writable.map((s) => s.experiment_id),
      }
    },
    onSuccess: ({ skipped, touched }) => {
      setDraft('')
      if (skipped.length > 0) {
        toastError('Some segments skipped', `No conditions row on: ${skipped.join(', ')}`)
      } else {
        success('Pore volume set')
      }
      return invalidateCoreFloodWrites(qc, baseId, touched)
    },
    onError: (err: Error) => toastError('Pore volume not saved', err.message),
  })

  return (
    <div className="flex items-start gap-2 mt-1">
      <Input
        type="number"
        aria-label="Pore volume for all segments"
        className="w-28 font-mono-data text-xs"
        value={draft}
        min={0}
        step="any"
        placeholder="mL"
        error={draft.trim() !== '' && !valid ? 'Must be greater than 0' : undefined}
        onChange={(e) => setDraft(e.target.value)}
      />
      <Button
        variant="secondary"
        size="sm"
        disabled={!valid}
        loading={mutation.isPending}
        onClick={() => mutation.mutate(value)}
      >
        Set pore volume for all segments
      </Button>
    </div>
  )
}

/** One line per run warning, each with the control that fixes it. */
export function CleanupPanel({ baseId, run, onEditSample, onRename, onEditDescription }: Props) {
  if (run.warnings.length === 0) return null

  const segment = (id: string) => run.segments.find((s) => s.experiment_id === id)

  const line = (w: CoreFloodWarning) => {
    const ids = w.experiment_ids
    const joined = ids.join(', ')
    switch (w.code) {
      case 'multiple_roots':
        return (
          <>
            <p>
              Several segments have no parent: {joined}. Rename the extra roots into this run&apos;s sequence.
            </p>
            <div className="flex flex-wrap gap-2 mt-1">
              {ids.map((id) => (
                <Button key={id} variant="secondary" size="xs" aria-label={`Rename ${id}`} onClick={() => onRename(id)}>
                  Rename
                </Button>
              ))}
            </div>
          </>
        )
      case 'multiple_ongoing':
        return (
          <>
            <p>More than one segment is ONGOING: {joined}.</p>
            <div className="flex flex-wrap gap-3 mt-1">
              {ids.map((id) => {
                const seg = segment(id)
                return seg ? <SegmentStatusSelect key={id} baseId={baseId} segment={seg} /> : null
              })}
            </div>
          </>
        )
      case 'missing_pore_volume':
        return (
          <>
            <p>No pore volume on: {joined}.</p>
            <PoreVolumeAll baseId={baseId} run={run} ids={ids} />
          </>
        )
      case 'missing_description':
        return (
          <>
            <p>No description on: {joined}.</p>
            <div className="flex flex-wrap gap-2 mt-1">
              {ids.map((id) => (
                <Button
                  key={id}
                  variant="secondary"
                  size="xs"
                  aria-label={`Describe ${id}`}
                  onClick={() => onEditDescription(id)}
                >
                  Describe
                </Button>
              ))}
            </div>
          </>
        )
      case 'sample_missing_flow_rate': {
        const matching = run.samples.filter(
          (s) => !s.is_variant && s.flow_rate_mL_min == null && ids.includes(s.experiment_id),
        )
        return (
          <>
            <p>Samples with no flow rate on: {joined}.</p>
            <div className="flex flex-wrap gap-2 mt-1">
              {matching.map((s) => (
                <Button key={s.result_id} variant="secondary" size="xs" onClick={() => onEditSample(s)}>
                  Edit {s.sample_date ? labDateOf(s.sample_date) : s.experiment_id}
                </Button>
              ))}
            </div>
          </>
        )
      }
    }
  }

  return (
    <section aria-labelledby="cleanup-heading">
      <Card padding="none">
        <CardHeader>
          <h2 id="cleanup-heading" className="text-xs font-semibold text-ink-secondary uppercase tracking-wider">
            Cleanup
          </h2>
        </CardHeader>
        <ul className="p-4 space-y-3 text-sm text-ink-secondary">
          {run.warnings.map((w) => (
            <li key={w.code}>{line(w)}</li>
          ))}
        </ul>
      </Card>
    </section>
  )
}
