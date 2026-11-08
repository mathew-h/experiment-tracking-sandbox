import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { CoreFloodRun, CoreFloodSample, CoreFloodWarning } from '@/api/coreFloods'
import { conditionsApi } from '@/api/conditions'
import { Button, Card, CardHeader, Input, useToast } from '@/components/ui'
import { labDateOf } from '@/utils/labDate'
import { SegmentStatusSelect } from '@/components/runs/SegmentStatusSelect'
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
      const settled = await Promise.allSettled(
        writable.map((s) => conditionsApi.patch(s.conditions_id as number, { pore_volume_mL: v })),
      )
      const touched: string[] = []
      const failed: string[] = []
      settled.forEach((r, i) => {
        if (r.status === 'fulfilled') touched.push(writable[i].experiment_id)
        else failed.push(`${writable[i].experiment_id} (${(r.reason as Error).message})`)
      })
      return {
        skipped: listed.filter((s) => s.conditions_id == null).map((s) => s.experiment_id),
        touched,
        failed,
      }
    },
    onSuccess: ({ skipped, touched, failed }) => {
      if (failed.length === 0) setDraft('')
      const notes = [
        failed.length > 0 ? `Failed: ${failed.join('; ')}` : '',
        skipped.length > 0 ? `No conditions row on: ${skipped.join(', ')}` : '',
      ].filter(Boolean)
      if (failed.length > 0) toastError('Pore volume not set on every segment', notes.join('. '))
      else if (skipped.length > 0) toastError('Some segments skipped', notes.join('. '))
      else success('Pore volume set')
      // Always refresh: patches that succeeded are committed even when others failed.
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
  const qc = useQueryClient()
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
                <Button key={id} variant="secondary" size="xs" onClick={() => onRename(id)}>
                  Rename {id}
                </Button>
              ))}
            </div>
          </>
        )
      case 'multiple_ongoing':
        return (
          <>
            <p>More than one segment is ONGOING: {joined}.</p>
            <div className="flex flex-wrap gap-x-4 gap-y-2 mt-1">
              {ids.map((id) => {
                const seg = segment(id)
                return seg ? (
                  <div key={id} className="flex items-center gap-2">
                    <span className="font-mono-data text-xs text-ink-primary">{id}</span>
                    <SegmentStatusSelect
                      segment={seg}
                      onChanged={() => invalidateCoreFloodWrites(qc, baseId, [id])}
                    />
                  </div>
                ) : null
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
                <Button key={id} variant="secondary" size="xs" onClick={() => onEditDescription(id)}>
                  Describe {id}
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
                  Edit {s.experiment_id} · {s.sample_date ? labDateOf(s.sample_date) : 'no date'}
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
