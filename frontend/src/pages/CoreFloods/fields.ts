import type {
  CoreFloodSample,
  CoreFloodSampleCreate,
  CoreFloodSampleUpdate,
} from '@/api/coreFloods'
import { labCalendarDays, labDateOf } from '@/utils/labDate'
import { PSI_TO_MPA } from '@/utils/units'

export type SampleFieldKey =
  | 'measurement_date'
  | 'time_post_reaction_days'
  | 'gc_run_date'
  | 'sample_tube_number'
  | 'flow_rate_mL_min'
  | 'nitrogen_flow_rate_mL_min'
  | 'inlet_pressure_psi'
  | 'outlet_pressure_psi'
  | 'sampling_volume_mL'
  | 'h2_concentration'
  | 'gas_sampling_volume_ml'
  | 'gas_sampling_pressure_MPa'
  | 'final_ph'
  | 'final_conductivity_mS_cm'

export interface SampleFieldDef {
  key: SampleFieldKey
  label: string
  unit?: string
  kind: 'date' | 'number' | 'integer'
  required?: boolean
  min?: number
  minExclusive?: boolean
  help?: string
  /** Form string to the API value. Only called on a non-blank, validated string. */
  toWire(s: string): string | number
  /** API value to the form string. */
  fromWire(v: string | number | null | undefined): string
}

const num = (s: string) => Number(s.trim())
const plain = (v: string | number | null | undefined) => (v == null ? '' : String(v))
const dateFromWire = (v: string | number | null | undefined) =>
  v == null || v === '' ? '' : labDateOf(String(v))

function numberField(
  key: SampleFieldKey,
  label: string,
  extra: Partial<SampleFieldDef> = {},
): SampleFieldDef {
  return { key, label, kind: 'number', toWire: num, fromWire: plain, ...extra }
}

function dateField(
  key: SampleFieldKey,
  label: string,
  extra: Partial<SampleFieldDef> = {},
): SampleFieldDef {
  return { key, label, kind: 'date', toWire: (s) => s.trim(), fromWire: dateFromWire, ...extra }
}

export const SAMPLE_FIELDS: readonly SampleFieldDef[] = [
  dateField('measurement_date', 'Sample date', { required: true }),
  numberField('time_post_reaction_days', 'Day', { unit: 'days', min: 0 }),
  dateField('gc_run_date', 'GC run date'),
  numberField('sample_tube_number', 'Tube #', { kind: 'integer', min: 0, minExclusive: true }),
  numberField('flow_rate_mL_min', 'Flow rate', {
    unit: 'mL/min',
    required: true,
    min: 0,
    help: 'Rate since the previous sample. Enter 0 for a hold.',
  }),
  numberField('nitrogen_flow_rate_mL_min', 'N₂ flow', { unit: 'mL/min' }),
  numberField('inlet_pressure_psi', 'Inlet pressure', { unit: 'psi' }),
  numberField('outlet_pressure_psi', 'Outlet pressure', { unit: 'psi' }),
  numberField('sampling_volume_mL', 'Liquid sample volume', { unit: 'mL', min: 0 }),
  numberField('h2_concentration', 'H₂', { unit: 'ppm', min: 0 }),
  numberField('gas_sampling_volume_ml', 'Gas volume', { unit: 'mL', min: 0 }),
  numberField('gas_sampling_pressure_MPa', 'Gas pressure', {
    unit: 'psi',
    min: 0,
    toWire: (s) => num(s) * PSI_TO_MPA,
    fromWire: (v) => (v == null ? '' : parseFloat((Number(v) / PSI_TO_MPA).toFixed(2)).toString()),
  }),
  numberField('final_ph', 'pH'),
  numberField('final_conductivity_mS_cm', 'Conductivity', { unit: 'mS/cm' }),
]

export const FIELD_BY_KEY = Object.fromEntries(
  SAMPLE_FIELDS.map((f) => [f.key, f]),
) as Record<SampleFieldKey, SampleFieldDef>

export type SampleForm = Record<SampleFieldKey, string>

export function emptyForm(): SampleForm {
  return Object.fromEntries(SAMPLE_FIELDS.map((f) => [f.key, ''])) as SampleForm
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

/** A new sample usually keeps the previous one's flow and pressures. */
export function prefillFromPrevious(
  form: SampleForm,
  prev: CoreFloodSample | undefined,
): SampleForm {
  if (!prev) return form
  const next = { ...form }
  for (const key of [
    'flow_rate_mL_min',
    'nitrogen_flow_rate_mL_min',
    'inlet_pressure_psi',
    'outlet_pressure_psi',
  ] as const) {
    next[key] = FIELD_BY_KEY[key].fromWire(prev[key])
  }
  return next
}

const YMD_RE = /^\d{4}-\d{2}-\d{2}$/
const NUMBER_RE = /^-?\d+(\.\d+)?$/

/** Sets the sample date, and the GC date and day unless the user edited them. */
export function withSampleDate(
  form: SampleForm,
  date: string,
  opts: { segmentStart: string | null; gcEdited: boolean; dayEdited: boolean },
): SampleForm {
  const next = { ...form, measurement_date: date }
  if (!opts.gcEdited) next.gc_run_date = date
  if (!opts.dayEdited) {
    next.time_post_reaction_days =
      opts.segmentStart && YMD_RE.test(date)
        ? String(labCalendarDays(opts.segmentStart, date))
        : ''
  }
  return next
}

export function validateForm(form: SampleForm): Partial<Record<SampleFieldKey, string>> {
  const errors: Partial<Record<SampleFieldKey, string>> = {}
  for (const f of SAMPLE_FIELDS) {
    const v = form[f.key].trim()
    if (v === '') {
      if (f.required) errors[f.key] = 'Required'
      continue
    }
    if (f.kind === 'date') {
      if (!YMD_RE.test(v)) errors[f.key] = 'Must be a date (YYYY-MM-DD)'
      continue
    }
    if (!NUMBER_RE.test(v)) {
      errors[f.key] = 'Must be a number'
    } else if (f.kind === 'integer' && !Number.isInteger(Number(v))) {
      errors[f.key] = 'Must be a whole number'
    } else if (f.min !== undefined) {
      const n = Number(v)
      if (f.minExclusive ? n <= f.min : n < f.min) {
        errors[f.key] = f.minExclusive ? `Must be > ${f.min}` : `Must be ≥ ${f.min}`
      }
    }
  }
  return errors
}

/** Create body from a validated form. Blank optional fields are omitted. */
export function buildCreateBody(form: SampleForm): CoreFloodSampleCreate {
  const body: Record<string, string | number> = {}
  for (const f of SAMPLE_FIELDS) {
    const v = form[f.key].trim()
    if (v !== '') body[f.key] = f.toWire(v)
  }
  return body as unknown as CoreFloodSampleCreate
}

/** Only the fields whose trimmed text changed; blank becomes null. Never the day. */
export function buildPatchBody(initial: SampleForm, form: SampleForm): CoreFloodSampleUpdate {
  const body: Record<string, string | number | null> = {}
  for (const f of SAMPLE_FIELDS) {
    if (f.key === 'time_post_reaction_days') continue
    const before = initial[f.key].trim()
    const after = form[f.key].trim()
    if (before === after) continue
    body[f.key] = after === '' ? null : f.toWire(after)
  }
  return body as CoreFloodSampleUpdate
}

/** Number for display; a dash for missing values, never 0 or NaN. */
export function fmt(v: number | null | undefined, digits = 3): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return parseFloat(v.toFixed(digits)).toString()
}
