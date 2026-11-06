import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Input, Modal, Select, useToast } from '@/components/ui'
import {
  coreFloodsApi,
  type CoreFloodSample,
  type CoreFloodSampleNote,
  type CoreFloodSegment,
} from '@/api/coreFloods'
import { labDateOf, labTodayISO } from '@/utils/labDate'
import {
  FIELD_BY_KEY,
  SAMPLE_FIELDS,
  SAMPLE_GROUPS,
  buildCreateBody,
  buildPatchBody,
  emptyForm,
  formFromSample,
  fmt,
  prefillFromPrevious,
  resultNoteOf,
  validateForm,
  validatePermeability,
  withPressure,
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

const NOTE_LABEL: Record<CoreFloodSampleNote['note_type'], string> = {
  observation: 'Observation',
  modification: 'Modification',
  result_note: 'Result note',
}

type Errors = Partial<Record<SampleFieldKey | 'segment', string>>

interface ApiError extends Error {
  response?: { status?: number }
}

const TOP_KEYS: readonly SampleFieldKey[] = [
  'measurement_date',
  'time_post_reaction_days',
  'sample_tube_number',
]
const SECTION_CLASS = 'flex flex-col gap-3 rounded border border-surface-border p-3'
const HEADING_CLASS = 'text-xs font-semibold uppercase tracking-wider text-ink-muted'

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
  const [permEdited, setPermEdited] = useState(false)
  const initialNote = editing ? (resultNoteOf(editing)?.note_text ?? '') : ''
  const [noteText, setNoteText] = useState(initialNote)
  const noteChanged = noteText.trim() !== initialNote.trim()
  const firstNoteId = editing ? resultNoteOf(editing)?.id : undefined
  const otherNotes = editing ? editing.notes.filter((n) => n.id !== firstNoteId) : []
  const isHoldFlow = (v: string) => v.trim() !== '' && Number(v) === 0
  const hold = isHoldFlow(form.flow_rate_mL_min)
  // Locked only by the checkbox (or an initial hold), so typing "0." on the way to "0.5" never traps the input.
  const [flowLocked, setFlowLocked] = useState(() => isHoldFlow(form.flow_rate_mL_min))
  const [storedFlow, setStoredFlow] = useState('')
  const permRef = useRef<HTMLInputElement>(null)
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

  function buildPatch() {
    const body = buildPatchBody(initial, form)
    if (noteChanged) body.result_note = noteText.trim() === '' ? null : noteText.trim()
    return body
  }

  function onHoldChange(checked: boolean) {
    setFlowLocked(checked)
    setErrors((e) => ({ ...e, flow_rate_mL_min: undefined }))
    if (checked) {
      setStoredFlow(form.flow_rate_mL_min)
      setForm((f) => ({ ...f, flow_rate_mL_min: '0' }))
      permRef.current?.focus()
    } else {
      setForm((f) => ({ ...f, flow_rate_mL_min: storedFlow }))
    }
  }

  function onFieldChange(key: SampleFieldKey, value: string) {
    setErrors((e) => ({ ...e, [key]: undefined }))
    if (key === 'permeability_flow_rate_mL_min') setPermEdited(true)
    if (key === 'inlet_pressure_psi' || key === 'outlet_pressure_psi') {
      const next = withPressure(form, key, value, { permEdited })
      if (next.permeability_flow_rate_mL_min !== form.permeability_flow_rate_mL_min) {
        setErrors((e) => ({ ...e, permeability_flow_rate_mL_min: undefined }))
      }
      setForm(next)
      return
    }
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
        ? coreFloodsApi.updateSample(editing.result_id, buildPatch())
        : coreFloodsApi.createSample(segmentId, {
            ...buildCreateBody(form),
            ...(noteText.trim() !== '' ? { result_note: noteText.trim() } : {}),
          }),
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
    const permKeys = ['inlet_pressure_psi', 'outlet_pressure_psi', 'permeability_flow_rate_mL_min'] as const
    const permTouched = !editing || permKeys.some((k) => form[k].trim() !== initial[k].trim())
    const found: Errors = {
      ...validateForm(form, editing ? initial : undefined),
      ...(permTouched ? validatePermeability(form) : {}),
    }
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
    if (editing && Object.keys(buildPatch()).length === 0) {
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

  function renderField(key: SampleFieldKey) {
    const f = FIELD_BY_KEY[key]
    const isDay = key === 'time_post_reaction_days'
    const isFlow = key === 'flow_rate_mL_min'
    return (
      <Input
        key={key}
        ref={key === 'permeability_flow_rate_mL_min' ? permRef : undefined}
        label={f.unit ? `${f.label} (${f.unit})` : f.label}
        type={f.kind === 'date' ? 'date' : 'text'}
        inputMode={f.kind === 'date' ? undefined : 'decimal'}
        value={form[key]}
        onChange={(e) => onFieldChange(key, e.target.value)}
        disabled={(isDay && !!editing) || (isFlow && flowLocked)}
        error={errors[key]}
        hint={isDay ? dayHint : f.help}
      />
    )
  }

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
        {clash && (
          <div role="alert" className="rounded border border-status-warning/30 bg-status-warning/5 px-3 py-2 text-xs text-status-warning">
            {`${clash.experiment_id} already has a sample on day ${fmt(clash.time_post_reaction_days)} (${
              clash.sample_date ? labDateOf(clash.sample_date) : 'no date'
            }). Saving replaces it in the run. Enter a fractional day (e.g. ${fmt(clash.time_post_reaction_days)}${Number.isInteger(clash.time_post_reaction_days) ? '.5' : '5'}) to keep both.`}
          </div>
        )}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
          {editing ? (
            <p className="text-xs text-ink-secondary sm:col-span-4">Segment: {editing.experiment_id}</p>
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
          {TOP_KEYS.map(renderField)}
        </div>
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="result-note"
            className="text-xs font-medium text-ink-secondary uppercase tracking-wider"
          >
            Result note
          </label>
          <textarea
            id="result-note"
            rows={3}
            maxLength={2000}
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            className="w-full bg-surface-raised border border-surface-border hover:border-ink-muted rounded px-3 py-2 text-sm text-ink-primary placeholder-ink-muted transition-colors duration-100 focus:outline-none focus:border-red-500 focus:ring-1 focus:ring-red-500/30"
          />
          {otherNotes.length > 0 && (
            <ul className="flex flex-col gap-1 text-xs text-ink-muted">
              {otherNotes.map((n) => (
                <li key={n.id}>
                  <span className="font-medium text-ink-secondary">{NOTE_LABEL[n.note_type]}</span>
                  {': '}
                  <span>{n.note_text}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <section aria-label="GC" className={SECTION_CLASS}>
            <h3 className={HEADING_CLASS}>GC</h3>
            {SAMPLE_GROUPS.gc.map(renderField)}
          </section>
          <section aria-label="Solution" className={SECTION_CLASS}>
            <h3 className={HEADING_CLASS}>Solution</h3>
            {SAMPLE_GROUPS.solution.map(renderField)}
          </section>
          <section aria-label="Core flood" className={SECTION_CLASS}>
            <h3 className={HEADING_CLASS}>Core flood</h3>
            <label className="flex items-center gap-2 text-sm text-ink-primary">
              <input
                type="checkbox"
                checked={hold}
                onChange={(e) => onHoldChange(e.target.checked)}
                className="h-4 w-4"
              />
              Hold since last sample
            </label>
            {SAMPLE_GROUPS.coreflood.map(renderField)}
          </section>
        </div>
      </div>
    </Modal>
  )
}
