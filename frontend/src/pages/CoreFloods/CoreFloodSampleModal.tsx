import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Input, Modal, Select, useToast } from '@/components/ui'
import {
  coreFloodsApi,
  type CoreFloodSample,
  type CoreFloodSegment,
} from '@/api/coreFloods'
import { labDateOf, labTodayISO } from '@/utils/labDate'
import {
  SAMPLE_FIELDS,
  buildCreateBody,
  buildPatchBody,
  emptyForm,
  formFromSample,
  fmt,
  prefillFromPrevious,
  validateForm,
  withSampleDate,
  type SampleFieldKey,
  type SampleForm,
} from './fields'
import { invalidateCoreFloodWrites } from './useCoreFloodWrites'

interface Props {
  open: boolean
  onClose: () => void
  baseId: string
  segments: CoreFloodSegment[]
  samples: CoreFloodSample[]
  /** Set to edit this sample instead of adding one. */
  editing?: CoreFloodSample
}

type Errors = Partial<Record<SampleFieldKey | 'segment', string>>

interface ApiError extends Error {
  response?: { status?: number }
}

function initialSegmentId(segments: CoreFloodSegment[]): string {
  const ongoing = segments.filter((s) => s.status?.toUpperCase() === 'ONGOING')
  return ongoing.length === 1 ? ongoing[0].experiment_id : ''
}

function lastNonVariant(samples: CoreFloodSample[]): CoreFloodSample | undefined {
  return samples.filter((s) => !s.is_variant).at(-1)
}

/** Add or edit one core flood sample. State lives in the body, which only
 *  mounts while the modal is open, so every open starts from a fresh form. */
export function CoreFloodSampleModal(props: Props) {
  if (!props.open) return null
  return <ModalBody key={props.editing?.result_id ?? 'new'} {...props} />
}

function ModalBody({ onClose, baseId, segments, samples, editing }: Props) {
  const qc = useQueryClient()
  const { success, error: toastError } = useToast()

  const [segmentId, setSegmentId] = useState(() => (editing ? editing.experiment_id : initialSegmentId(segments)))
  const [initial] = useState<SampleForm>(() => (editing ? formFromSample(editing) : emptyForm()))
  const [form, setForm] = useState<SampleForm>(() => {
    if (editing) return initial
    const start = segments.find((s) => s.experiment_id === initialSegmentId(segments))?.date ?? null
    return withSampleDate(prefillFromPrevious(emptyForm(), lastNonVariant(samples)), labTodayISO(), {
      segmentStart: start,
      gcEdited: false,
      dayEdited: false,
    })
  })
  const [gcEdited, setGcEdited] = useState(false)
  const [dayEdited, setDayEdited] = useState(false)
  const [errors, setErrors] = useState<Errors>({})
  const [serverError, setServerError] = useState<string | null>(null)
  /** The segment|day pair whose replace warning the researcher has already seen. */
  const [armedKey, setArmedKey] = useState<string | null>(null)

  const segment = segments.find((s) => s.experiment_id === segmentId)
  const segmentOptions = segments.map((s) => ({
    value: s.experiment_id,
    label: s.is_variant ? `${s.experiment_id} (side)` : s.experiment_id,
  }))

  /** Applies an auto-recompute and drops the errors of every key it changed. */
  // A POST into a bucket that holds a sample demotes it ("newest wins"), so a same-day
  // add is a replace. Compare numerically: "11" and "11.0" are the same bucket.
  const dayText = form.time_post_reaction_days.trim()
  const clash =
    !editing && segmentId && /^-?\d+(\.\d+)?$/.test(dayText)
      ? samples.find(
          (s) => s.experiment_id === segmentId && s.time_post_reaction_days === Number(dayText),
        )
      : undefined
  const clashKey = clash ? `${segmentId}|${Number(dayText)}` : null
  const armed = clashKey !== null && armedKey === clashKey

  function applyRecompute(start: string | null, date: string) {
    const next = withSampleDate(form, date, { segmentStart: start, gcEdited, dayEdited })
    const changed = SAMPLE_FIELDS.map((f) => f.key).filter((k) => next[k] !== form[k])
    setForm(next)
    setErrors((e) => {
      const cleared = { ...e }
      for (const k of changed) cleared[k] = undefined
      return cleared
    })
  }

  function onSegmentChange(id: string) {
    setSegmentId(id)
    setErrors((e) => ({ ...e, segment: undefined }))
    applyRecompute(segments.find((s) => s.experiment_id === id)?.date ?? null, form.measurement_date)
  }

  function onFieldChange(key: SampleFieldKey, value: string) {
    setErrors((e) => ({ ...e, [key]: undefined }))
    if (key === 'gc_run_date') setGcEdited(true)
    if (key === 'time_post_reaction_days') setDayEdited(true)
    if (key === 'measurement_date' && !editing) {
      applyRecompute(segment?.date ?? null, value)
      return
    }
    setForm((f) => ({ ...f, [key]: value }))
  }

  const mutation = useMutation({
    mutationFn: () =>
      editing
        ? coreFloodsApi.updateSample(editing.result_id, buildPatchBody(initial, form))
        : coreFloodsApi.createSample(segmentId, buildCreateBody(form)),
    onSuccess: async () => {
      await invalidateCoreFloodWrites(qc, baseId, segments.map((s) => s.experiment_id))
      success(editing ? 'Sample updated' : 'Sample added')
      onClose()
    },
    onError: (err: ApiError) => {
      const status = err.response?.status
      if (status === 404 || status === 422) setServerError(err.message)
      else toastError('Could not save sample', err.message)
    },
  })

  function handleSubmit() {
    setServerError(null)
    const found: Errors = validateForm(form, editing ? initial : undefined)
    if (!editing && !segment) found.segment = 'Choose a segment'
    if (!editing && segment && !segment.date && dayText === '') {
      found.time_post_reaction_days = `Required — ${segment.experiment_id} has no start date`
    }
    setErrors(found)
    if (Object.values(found).some(Boolean)) return
    if (clashKey && !armed) {
      setArmedKey(clashKey)
      return
    }
    if (editing && Object.keys(buildPatchBody(initial, form)).length === 0) {
      onClose()
      return
    }
    mutation.mutate()
  }

  function handleClose() {
    if (!mutation.isPending) onClose()
  }

  const dayHint = editing
    ? form.measurement_date !== initial.measurement_date
      ? `Day stays ${fmt(editing.time_post_reaction_days)} — the day can't be changed after a sample is created.`
      : "Day can't be edited here"
    : segment?.date
      ? `Days since ${segment.experiment_id} started (${labDateOf(segment.date)})`
      : undefined

  return (
    <Modal
      open
      onClose={handleClose}
      size="lg"
      title={editing ? `Edit sample — ${editing.experiment_id}` : 'Add sample'}
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={handleClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" onClick={handleSubmit} loading={mutation.isPending}>
            {editing ? 'Save' : armed ? 'Replace existing sample' : 'Add sample'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {serverError && (
          <div role="alert" className="rounded border border-red-500 bg-red-500/5 px-3 py-2 text-xs text-red-400">
            {serverError}
          </div>
        )}
        {editing ? (
          <p className="text-xs text-ink-secondary">Segment: {editing.experiment_id}</p>
        ) : (
          <Select
            label="Segment"
            value={segmentId}
            onChange={(e) => onSegmentChange(e.target.value)}
            options={segmentOptions}
            placeholder="Select a segment"
            error={errors.segment}
          />
        )}
        {clash && (
          <div role="alert" className="rounded border border-status-warning/30 bg-status-warning/5 px-3 py-2 text-xs text-status-warning">
            {`${clash.experiment_id} already has a sample on day ${fmt(clash.time_post_reaction_days)} (${
              clash.sample_date ? labDateOf(clash.sample_date) : 'no date'
            }). Saving replaces it in the run. Enter a fractional day (e.g. ${fmt(clash.time_post_reaction_days)}${Number.isInteger(clash.time_post_reaction_days) ? '.5' : '5'}) to keep both.`}
          </div>
        )}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {SAMPLE_FIELDS.map((f) => {
            const isDay = f.key === 'time_post_reaction_days'
            return (
              <Input
                key={f.key}
                label={f.unit ? `${f.label} (${f.unit})` : f.label}
                type={f.kind === 'date' ? 'date' : 'text'}
                inputMode={f.kind === 'date' ? undefined : 'decimal'}
                value={form[f.key]}
                onChange={(e) => onFieldChange(f.key, e.target.value)}
                disabled={isDay && !!editing}
                error={errors[f.key]}
                hint={isDay ? dayHint : f.help}
              />
            )
          })}
        </div>
      </div>
    </Modal>
  )
}
