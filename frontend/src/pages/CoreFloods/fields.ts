import type {
  CoreFloodSample,
  CoreFloodSampleNote,
  CoreFloodSampleCreate,
  CoreFloodSampleUpdate,
} from '@/api/coreFloods'
import {
  changedFields,
  createBodyFrom,
  dateField,
  emptyFormFor,
  numberField,
  psiAsMpaField,
  validateFields,
  withSampleDate as withSharedSampleDate,
  type FieldDef,
} from '@/components/results/sampleFields'

// Issue #148: the builders, validation, create/patch logic and `fmt` live in
// components/results/sampleFields.ts, shared with ResultEntryModal. This file
// keeps the core flood field list, groups and core-flood-only rules.
export { fmt } from '@/components/results/sampleFields'

export type SampleFieldKey =
  | 'measurement_date'
  | 'time_post_reaction_days'
  | 'gc_run_date'
  | 'sample_tube_number'
  | 'flow_rate_mL_min'
  | 'nitrogen_flow_rate_mL_min'
  | 'permeability_flow_rate_mL_min'
  | 'inlet_pressure_psi'
  | 'outlet_pressure_psi'
  | 'sampling_volume_mL'
  | 'h2_concentration'
  | 'gas_sampling_volume_ml'
  | 'gas_sampling_pressure_MPa'
  | 'final_ph'
  | 'final_conductivity_mS_cm'

export type SampleFieldDef = FieldDef<SampleFieldKey>

export const SAMPLE_FIELDS: readonly SampleFieldDef[] = [
  dateField('measurement_date', 'Sample date', { required: true }),
  numberField('time_post_reaction_days', 'Day', { unit: 'days', min: 0 }),
  dateField('gc_run_date', 'GC run date'),
  numberField('sample_tube_number', 'Tube #', { kind: 'integer', min: 0, minExclusive: true }),
  numberField('flow_rate_mL_min', 'Flow rate', {
    unit: 'mL/min',
    required: true,
    min: 0,
    help: 'Rate since the previous sample.',
  }),
  numberField('nitrogen_flow_rate_mL_min', 'N₂ flow', { unit: 'mL/min' }),
  numberField('permeability_flow_rate_mL_min', 'Permeability test flow rate', {
    unit: 'mL/min',
    min: 0,
    minExclusive: true,
    help: 'Rate while pressures were read. Marks this sample as a permeability test.',
  }),
  numberField('inlet_pressure_psi', 'Inlet pressure', { unit: 'psi' }),
  numberField('outlet_pressure_psi', 'Outlet pressure', { unit: 'psi' }),
  numberField('sampling_volume_mL', 'Liquid sample volume', { unit: 'mL', min: 0 }),
  numberField('h2_concentration', 'H₂', { unit: 'ppm', min: 0 }),
  numberField('gas_sampling_volume_ml', 'Gas volume', { unit: 'mL', min: 0 }),
  psiAsMpaField('gas_sampling_pressure_MPa', 'Gas pressure'),
  numberField('final_ph', 'pH'),
  numberField('final_conductivity_mS_cm', 'Conductivity', { unit: 'mS/cm' }),
]

export const SAMPLE_GROUPS: Record<'gc' | 'solution' | 'coreflood', readonly SampleFieldKey[]> = {
  gc: ['h2_concentration', 'gas_sampling_pressure_MPa', 'gas_sampling_volume_ml', 'gc_run_date'],
  solution: ['final_ph', 'final_conductivity_mS_cm', 'sampling_volume_mL'],
  coreflood: [
    'flow_rate_mL_min',
    'permeability_flow_rate_mL_min',
    'inlet_pressure_psi',
    'outlet_pressure_psi',
    'nitrogen_flow_rate_mL_min',
  ],
}

export const FIELD_BY_KEY = Object.fromEntries(
  SAMPLE_FIELDS.map((f) => [f.key, f]),
) as Record<SampleFieldKey, SampleFieldDef>

export type SampleForm = Record<SampleFieldKey, string>

export function emptyForm(): SampleForm {
  return emptyFormFor(SAMPLE_FIELDS)
}

/** Edit-form values for a stored sample, each through its field's fromWire. */
export function formFromSample(s: CoreFloodSample): SampleForm {
  const form = emptyForm()
  for (const f of SAMPLE_FIELDS) {
    const raw = f.key === 'measurement_date' ? s.sample_date : s[f.key]
    form[f.key] = f.fromWire(raw)
  }
  return form
}

/** A new sample keeps the previous flow and N₂ flow. Pressures are only recorded
 *  when permeability is tested, so they never carry forward. */
export function prefillFromPrevious(
  form: SampleForm,
  prev: CoreFloodSample | undefined,
): SampleForm {
  if (!prev) return form
  const next = { ...form }
  for (const key of ['flow_rate_mL_min', 'nitrogen_flow_rate_mL_min'] as const) {
    next[key] = FIELD_BY_KEY[key].fromWire(prev[key])
  }
  return next
}

/** Sets a pressure. A non-blank pressure fills a blank, untouched test rate with
 *  the current non-zero flow rate. */
export function withPressure(
  form: SampleForm,
  key: 'inlet_pressure_psi' | 'outlet_pressure_psi',
  value: string,
  opts: { permEdited: boolean },
): SampleForm {
  const next = { ...form, [key]: value }
  const flow = form.flow_rate_mL_min.trim()
  if (
    value.trim() !== '' &&
    !opts.permEdited &&
    next.permeability_flow_rate_mL_min.trim() === '' &&
    flow !== '' &&
    Number(flow) !== 0 &&
    !Number.isNaN(Number(flow))
  ) {
    next.permeability_flow_rate_mL_min = form.flow_rate_mL_min.trim()
  }
  return next
}

/** Pressures and the test rate go together: either both or neither. */
export function validatePermeability(form: SampleForm): Partial<Record<SampleFieldKey, string>> {
  const errors: Partial<Record<SampleFieldKey, string>> = {}
  const hasPressure =
    form.inlet_pressure_psi.trim() !== '' || form.outlet_pressure_psi.trim() !== ''
  const hasRate = form.permeability_flow_rate_mL_min.trim() !== ''
  if (hasPressure && !hasRate) {
    errors.permeability_flow_rate_mL_min = 'Enter the test flow rate used for these pressures'
  } else if (hasRate && !hasPressure) {
    errors.inlet_pressure_psi = 'Enter inlet or outlet pressure for this permeability test'
  }
  return errors
}

export function resultNoteOf(s: CoreFloodSample): CoreFloodSampleNote | undefined {
  return s.notes.find((n) => n.note_type === 'result_note')
}

/** Result and observation texts in order, joined for a table cell. */
export function noteSummary(s: CoreFloodSample): { text: string; hasModification: boolean } {
  return {
    text: s.notes
      .filter((n) => n.note_type === 'result_note' || n.note_type === 'observation')
      .map((n) => n.note_text)
      .join(' · '),
    hasModification: s.notes.some((n) => n.note_type === 'modification'),
  }
}

/** Sets the sample date, and the GC date and day unless the user edited them. */
export function withSampleDate(
  form: SampleForm,
  date: string,
  opts: { segmentStart: string | null; gcEdited: boolean; dayEdited: boolean },
): SampleForm {
  const { segmentStart, ...rest } = opts
  return withSharedSampleDate(form, date, { startDate: segmentStart, ...rest })
}

/** With `initial` (edit mode), a required field is only an error when the user
 *  cleared a value it started with; a historical row that never had it can still
 *  be edited, since the patch omits unchanged fields. */
export function validateForm(
  form: SampleForm,
  initial?: SampleForm,
): Partial<Record<SampleFieldKey, string>> {
  return validateFields(SAMPLE_FIELDS, form, initial)
}

/** Create body from a validated form. Blank optional fields are omitted. */
export function buildCreateBody(form: SampleForm): CoreFloodSampleCreate {
  return createBodyFrom(SAMPLE_FIELDS, form) as unknown as CoreFloodSampleCreate
}

/** Only the fields whose trimmed text changed; blank becomes null. Never the day. */
export function buildPatchBody(initial: SampleForm, form: SampleForm): CoreFloodSampleUpdate {
  return changedFields(SAMPLE_FIELDS, initial, form) as CoreFloodSampleUpdate
}
