import { useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Input, Modal, PageSpinner, useToast } from '@/components/ui'
import { NoteBadge } from '@/components/experiments/NoteBadge'
import {
  experimentsApi,
  type ResultEntryCreate,
  type ResultEntryUpdate,
  type ResultWithFlags,
} from '@/api/experiments'
import { resultsApi, type ScalarResult } from '@/api/results'
import {
  changedFields,
  createBodyFrom,
  dateField,
  emptyFormFor,
  numberField,
  psiAsMpaField,
  validateFields,
  withSampleDate,
  type FieldDef,
  type FormOf,
} from '@/components/results/sampleFields'
import { labDateOf, labTodayISO } from '@/utils/labDate'
import { isHphtType } from '@/utils/experimentId'
import { formatPrecise } from '@/utils/numberFormat'

interface Props {
  open: boolean
  onClose: () => void
  experimentId: string
  /** `conditions.experiment_type`; HPHT hides the NH₄ input. */
  experimentType?: string | null
  /** The experiment's start date. A new result's Day counts from it. */
  experimentStart?: string | null
  /** Day parsed from a -t<days> token on the experiment ID (issue #81). When set,
   *  Day is defaulted and locked to this value. */
  idTimepointDays?: number | null
  /** Base experiment ID. When given, the HPHT run queries and the dashboard are refreshed too. */
  baseId?: string | null
  /** Shown at the top of the form, e.g. the HPHT run page's segment select (issue #150). */
  headerSlot?: ReactNode
  /** What the caller's button calls a row, e.g. "sample" on the HPHT run page, so the
   *  dialog reads "Add sample" / "Save sample". Omitted: "Add Results" / "Save Results"
   *  (issue #161). */
  noun?: string
  /** The experiment's results, used to warn before a same-day add replaces one. */
  results?: ResultWithFlags[]
  /** Set to edit this (primary) result instead of adding one. */
  editing?: ResultWithFlags
  /** Unused. Kept so callers of the old AddResultsModal still type-check. */
  experimentFk?: number
}

type EntryKey =
  | 'measurement_date'
  | 'time_post_reaction_days'
  | 'sample_tube_number'
  | 'final_ph'
  | 'final_conductivity_mS_cm'
  | 'sampling_volume_mL'
  | 'gross_ammonium_concentration_mM'
  | 'h2_concentration'
  | 'gas_sampling_pressure_MPa'
  | 'gas_sampling_volume_ml'
  | 'gc_run_date'

type EntryForm = FormOf<EntryKey>
type Errors = Partial<Record<EntryKey, string>>

const ENTRY_FIELDS: readonly FieldDef<EntryKey>[] = [
  dateField('measurement_date', 'Sample date', { required: true }),
  numberField('time_post_reaction_days', 'Day', { unit: 'days', min: 0, required: true }),
  numberField('sample_tube_number', 'Tube #', { kind: 'integer', min: 0, minExclusive: true }),
  numberField('final_ph', 'pH'),
  numberField('final_conductivity_mS_cm', 'Conductivity', { unit: 'mS/cm' }),
  numberField('sampling_volume_mL', 'Liquid sample volume', { unit: 'mL', min: 0 }),
  numberField('gross_ammonium_concentration_mM', 'NH₄', { unit: 'mM', min: 0 }),
  numberField('h2_concentration', 'H₂', { unit: 'ppm', min: 0 }),
  psiAsMpaField('gas_sampling_pressure_MPa', 'Gas pressure'),
  numberField('gas_sampling_volume_ml', 'Gas volume', { unit: 'mL', min: 0 }),
  dateField('gc_run_date', 'GC run date'),
]
const FIELD = Object.fromEntries(ENTRY_FIELDS.map((f) => [f.key, f])) as Record<
  EntryKey,
  FieldDef<EntryKey>
>
const HEADER_KEYS: readonly EntryKey[] = ['measurement_date', 'time_post_reaction_days', 'sample_tube_number']
const SOLUTION_KEYS: readonly EntryKey[] = [
  'final_ph',
  'final_conductivity_mS_cm',
  'sampling_volume_mL',
  'gross_ammonium_concentration_mM',
]
const GC_KEYS: readonly EntryKey[] = [
  'h2_concentration',
  'gas_sampling_pressure_MPa',
  'gas_sampling_volume_ml',
  'gc_run_date',
]
/** GC readings; a create sends the auto-filled GC date only alongside one. */
const GC_VALUE_KEYS = GC_KEYS.filter((k) => k !== 'gc_run_date')

const SECTION_CLASS = 'flex flex-col gap-3 rounded border border-surface-border p-3'
const HEADING_CLASS = 'text-xs font-semibold uppercase tracking-wider text-ink-muted'
const LABEL_CLASS = 'text-xs font-medium text-ink-secondary uppercase tracking-wider'
const TEXTAREA_CLASS =
  'w-full bg-surface-raised border border-surface-border hover:border-ink-muted rounded px-3 py-2 text-sm text-ink-primary placeholder-ink-muted transition-colors duration-100 focus:outline-none focus:border-red-500 focus:ring-1 focus:ring-red-500/30'

/** Edit-form values for a stored result. The list row carries the headline
 *  values; the scalar row adds the volumes and gas pressure it lacks. */
function formFromResult(r: ResultWithFlags, s: ScalarResult | undefined): EntryForm {
  const raw: Record<EntryKey, string | number | null | undefined> = {
    measurement_date: s?.measurement_date ?? r.scalar_measurement_date,
    time_post_reaction_days: r.time_post_reaction_days,
    sample_tube_number: r.sample_tube_number,
    final_ph: s?.final_ph ?? r.final_ph,
    final_conductivity_mS_cm: s?.final_conductivity_mS_cm ?? r.final_conductivity_mS_cm,
    sampling_volume_mL: s?.sampling_volume_mL,
    gross_ammonium_concentration_mM: s?.gross_ammonium_concentration_mM ?? r.gross_ammonium_concentration_mM,
    h2_concentration: s?.h2_concentration ?? r.h2_concentration,
    gas_sampling_pressure_MPa: s?.gas_sampling_pressure_MPa,
    gas_sampling_volume_ml: s?.gas_sampling_volume_ml,
    gc_run_date: s?.gc_run_date ?? r.gc_run_date,
  }
  const form = emptyFormFor(ENTRY_FIELDS)
  for (const f of ENTRY_FIELDS) form[f.key] = f.fromWire(raw[f.key])
  return form
}

function firstResultNote(r: ResultWithFlags | undefined) {
  return r?.notes.find((n) => n.note_type === 'result_note')
}

/** Add or edit one hand-entered result of a non-core-flood experiment
 *  (issue #148). One POST to add, one PATCH of the changed fields to edit;
 *  the server writes the result, its scalar row, its notes and the audit
 *  rows together (issue #146). The body only mounts while open, so every
 *  open starts from a fresh form. */
export function ResultEntryModal(props: Props) {
  if (!props.open) return null
  if (props.editing) return <EditLoader key={props.editing.id} {...props} editing={props.editing} />
  return <ModalBody {...props} />
}

/** Loads the result's scalar row (its volumes and gas pressure are not on the
 *  list payload) before building the edit form from it. */
function EditLoader(props: Props & { editing: ResultWithFlags }) {
  const { editing } = props
  const { data: scalar, isLoading } = useQuery({
    queryKey: ['scalar', editing.id],
    queryFn: () => resultsApi.getScalar(editing.id),
    enabled: editing.has_scalar,
  })
  if (editing.has_scalar && isLoading) {
    return (
      <Modal open onClose={props.onClose} title={`Edit ${props.noun ?? 'result'}`} size="xl">
        <PageSpinner />
      </Modal>
    )
  }
  return <ModalBody {...props} initialEdit={formFromResult(editing, scalar)} />
}

function ModalBody({
  onClose,
  experimentId,
  experimentType,
  experimentStart,
  idTimepointDays,
  baseId,
  headerSlot,
  noun,
  results = [],
  editing,
  initialEdit,
}: Props & { initialEdit?: EntryForm }) {
  const qc = useQueryClient()
  const { success } = useToast()
  const locked = idTimepointDays != null

  const [initial] = useState<EntryForm>(() => initialEdit ?? emptyFormFor(ENTRY_FIELDS))
  const [form, setForm] = useState<EntryForm>(() => {
    if (initialEdit) return initialEdit
    const next = withSampleDate(emptyFormFor(ENTRY_FIELDS), labTodayISO(), {
      startDate: experimentStart ?? null,
      gcEdited: false,
      dayEdited: locked,
    })
    if (locked) next.time_post_reaction_days = String(idTimepointDays)
    return next
  })
  const [gcEdited, setGcEdited] = useState(false)
  const [dayEdited, setDayEdited] = useState(locked)
  const initialNote = firstResultNote(editing)?.note_text ?? ''
  const [noteText, setNoteText] = useState(initialNote)
  const noteChanged = noteText.trim() !== initialNote.trim()
  const [modOpen, setModOpen] = useState(false)
  const [modText, setModText] = useState('')
  const [errors, setErrors] = useState<Errors>({})
  const [serverError, setServerError] = useState<string | null>(null)
  /** The day whose replace warning the researcher has already seen. */
  const [armedDay, setArmedDay] = useState<number | null>(null)

  // HPHT runs record H₂, not NH₄ (0 NH₄ on every active HPHT run), so the input
  // is hidden there, unless an edited row already holds a value to correct.
  const showNh4 = !isHphtType(experimentType) || initial.gross_ammonium_concentration_mM !== ''
  const fields = ENTRY_FIELDS.filter((f) => showNh4 || f.key !== 'gross_ammonium_concentration_mM')
  const firstNoteId = firstResultNote(editing)?.id
  const otherNotes = editing ? editing.notes.filter((n) => n.id !== firstNoteId) : []

  // A POST into a day bucket that holds a primary result demotes it ("newest
  // wins"), so a same-day add is a replace. Compare numerically: "7" and "7.0"
  // are the same bucket.
  const dayText = form.time_post_reaction_days.trim()
  const dayNum = /^-?\d+(\.\d+)?$/.test(dayText) ? Number(dayText) : null
  const clash =
    !editing && dayNum !== null
      ? results.find(
          (r) =>
            r.is_primary_timepoint_result &&
            Math.abs((r.time_post_reaction_bucket_days ?? r.time_post_reaction_days ?? NaN) - dayNum) < 1e-6,
        )
      : undefined
  const armed = clash !== undefined && armedDay === dayNum

  function onFieldChange(key: EntryKey, value: string) {
    if (key === 'measurement_date' && !editing) {
      const next = withSampleDate(form, value, { startDate: experimentStart ?? null, gcEdited, dayEdited })
      const changed = ENTRY_FIELDS.map((f) => f.key).filter((k) => next[k] !== form[k])
      setForm(next)
      setErrors((e) => {
        const cleared = { ...e }
        for (const k of changed) cleared[k] = undefined
        return cleared
      })
      return
    }
    if (key === 'gc_run_date') setGcEdited(true)
    if (key === 'time_post_reaction_days') setDayEdited(true)
    setErrors((e) => ({ ...e, [key]: undefined }))
    setForm((f) => ({ ...f, [key]: value }))
  }

  function buildCreate(): ResultEntryCreate {
    const body = createBodyFrom(fields, form) as unknown as ResultEntryCreate
    // The GC date only follows the sample date as a convenience; without a gas
    // reading it would make a solution-only sample count as a GC measurement.
    if (!gcEdited && !GC_VALUE_KEYS.some((k) => form[k].trim() !== '')) delete body.gc_run_date
    if (noteText.trim() !== '') body.result_note = noteText.trim()
    if (modText.trim() !== '') body.modification_note = modText.trim()
    return body
  }

  function buildPatch(): ResultEntryUpdate {
    const body = changedFields(fields, initial, form) as ResultEntryUpdate
    // Blank deletes the sample's first result note on the server.
    if (noteChanged) body.result_note = noteText.trim()
    if (modText.trim() !== '') body.modification_note = modText.trim()
    return body
  }

  const mutation = useMutation({
    mutationFn: () =>
      editing
        ? experimentsApi.updateResult(experimentId, editing.id, buildPatch())
        : experimentsApi.createResult(experimentId, buildCreate()),
    onSuccess: async () => {
      const keys: unknown[][] = [['experiment-results', experimentId], ['experiment', experimentId]]
      if (editing) keys.push(['scalar', editing.id])
      if (baseId) keys.push(['hpht-runs'], ['hpht-run', baseId], ['hpht-icp', baseId], ['dashboard'])
      await Promise.all(keys.map((queryKey) => qc.invalidateQueries({ queryKey })))
      success(editing ? 'Result updated' : 'Result added')
      onClose()
    },
    onError: (err: Error) => setServerError(err.message || 'Failed to save results. Please try again.'),
  })

  function handleSubmit() {
    setServerError(null)
    const found: Errors = validateFields(fields, form, editing ? initial : undefined)
    if (
      !editing &&
      locked &&
      dayNum !== null &&
      Math.abs(dayNum - (idTimepointDays as number)) > 0.0001
    ) {
      found.time_post_reaction_days = `Locked to day ${idTimepointDays} by the experiment ID; remove the -t token to log a different day.`
    }
    setErrors(found)
    if (Object.values(found).some(Boolean)) return
    if (clash && !armed) {
      setArmedDay(dayNum)
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
    ? "Day can't be edited here"
    : locked
      ? `Locked to day ${idTimepointDays} from the experiment ID (-t${idTimepointDays}).`
      : experimentStart
        ? `Days since the experiment started (${labDateOf(experimentStart)})`
        : 'This experiment has no start date. Enter the day.'

  function renderField(key: EntryKey) {
    const f = FIELD[key]
    const isDay = key === 'time_post_reaction_days'
    const label = `${f.label}${f.unit ? ` (${f.unit})` : ''}${f.required ? ' *' : ''}`
    return (
      <Input
        key={key}
        label={label}
        type={f.kind === 'date' ? 'date' : 'text'}
        inputMode={f.kind === 'date' ? undefined : 'decimal'}
        value={form[key]}
        onChange={(e) => onFieldChange(key, e.target.value)}
        disabled={isDay && (!!editing || locked)}
        error={errors[key]}
        hint={isDay ? dayHint : f.help}
      />
    )
  }

  const title = editing
    ? `Edit ${noun ?? 'result'} — T+${formatPrecise(editing.time_post_reaction_days)}`
    : noun ? `Add ${noun}` : 'Add Results'
  const saveLabel = noun ? `Save ${noun}` : editing ? 'Save' : 'Save Results'

  return (
    <Modal
      open
      onClose={handleClose}
      size="xl"
      title={title}
      description={editing ? undefined : 'Create a new timepoint result for this experiment.'}
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={handleClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" onClick={handleSubmit} loading={mutation.isPending}>
            {!editing && armed ? 'Replace existing result' : saveLabel}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {serverError && (
          <div
            role="alert"
            className="rounded border border-status-error/30 bg-status-error/5 px-3 py-2 text-xs text-status-error"
          >
            {serverError}
          </div>
        )}
        {clash && (
          <div
            role="alert"
            className="rounded border border-status-warning/30 bg-status-warning/5 px-3 py-2 text-xs text-status-warning"
          >
            {`Day ${formatPrecise(dayNum)} already has a result (${
              clash.scalar_measurement_date ? labDateOf(clash.scalar_measurement_date) : 'no date'
            }). Saving replaces it as the primary result for that day.`}
          </div>
        )}

        {headerSlot}

        {/* Header */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">{HEADER_KEYS.map(renderField)}</div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="result-description" className={LABEL_CLASS}>
            Result Note/Sample Description
          </label>
          <textarea
            id="result-description"
            rows={2}
            maxLength={2000}
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            className={`${TEXTAREA_CLASS} resize-none`}
          />
          <p className="text-xs text-ink-muted">Sample note</p>
        </div>
        <div className="flex flex-col gap-1.5">
          <button
            type="button"
            aria-expanded={modOpen}
            aria-controls="result-modification"
            onClick={() => setModOpen((o) => !o)}
            className="self-start text-xs font-medium text-ink-secondary hover:text-ink-primary"
          >
            {modOpen ? '▾' : '▸'} Modification
          </button>
          {modOpen && (
            <>
              <textarea
                id="result-modification"
                aria-label="Modification note"
                rows={2}
                maxLength={2000}
                placeholder="What was done to the experiment — e.g. brine replaced with DI water"
                value={modText}
                onChange={(e) => setModText(e.target.value)}
                className={`${TEXTAREA_CLASS} resize-none`}
              />
              {editing && (
                <p className="text-xs text-ink-muted">Adds a new modification note; earlier ones are kept.</p>
              )}
            </>
          )}
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <section aria-label="Solution" className={SECTION_CLASS}>
            <h3 className={HEADING_CLASS}>Solution</h3>
            {SOLUTION_KEYS.filter((k) => fields.some((f) => f.key === k)).map(renderField)}
          </section>
          <section aria-label="GC" className={SECTION_CLASS}>
            <h3 className={HEADING_CLASS}>GC</h3>
            {GC_KEYS.map(renderField)}
          </section>
        </div>

        {otherNotes.length > 0 && (
          <div>
            <p className={`${LABEL_CLASS} mb-1`}>Existing notes</p>
            <ul data-testid="existing-notes" className="flex flex-col gap-1">
              {otherNotes.map((n) => (
                <li key={n.id} className="flex items-start gap-2 text-xs">
                  <NoteBadge type={n.note_type} />
                  <span className="text-ink-primary">{n.note_text}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Modal>
  )
}
