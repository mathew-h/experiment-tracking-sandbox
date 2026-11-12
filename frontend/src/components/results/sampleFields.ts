/** Field-definition helpers shared by the two hand-entry forms for a sample:
 *  the core flood sample modal and the generic result entry modal (issue #148).
 *  Each form keeps its own field list; everything here takes that list. */
import { labCalendarDays, labDateOf } from '@/utils/labDate'
import { PSI_TO_MPA } from '@/utils/units'
import { formatNumber } from '@/utils/numberFormat'

export interface FieldDef<K extends string = string> {
  key: K
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

export type WireValue = string | number | null | undefined

const num = (s: string) => Number(s.trim())
const plain = (v: WireValue) => (v == null ? '' : String(v))
const dateFromWire = (v: WireValue) => (v == null || v === '' ? '' : labDateOf(String(v)))

export function numberField<K extends string>(
  key: K,
  label: string,
  extra: Partial<FieldDef<K>> = {},
): FieldDef<K> {
  return { key, label, kind: 'number', toWire: num, fromWire: plain, ...extra }
}

export function dateField<K extends string>(
  key: K,
  label: string,
  extra: Partial<FieldDef<K>> = {},
): FieldDef<K> {
  return { key, label, kind: 'date', toWire: (s) => s.trim(), fromWire: dateFromWire, ...extra }
}

/** Gas pressure: entered in psi, stored in MPa. Read back to 2 decimals so a
 *  stored value round-trips to the text the researcher typed. */
export function psiAsMpaField<K extends string>(
  key: K,
  label: string,
  extra: Partial<FieldDef<K>> = {},
): FieldDef<K> {
  return numberField(key, label, {
    unit: 'psi',
    min: 0,
    toWire: (s) => num(s) * PSI_TO_MPA,
    fromWire: (v) => (v == null ? '' : parseFloat((Number(v) / PSI_TO_MPA).toFixed(2)).toString()),
    ...extra,
  })
}

export type FormOf<K extends string> = Record<K, string>

export function emptyFormFor<K extends string>(fields: readonly FieldDef<K>[]): FormOf<K> {
  return Object.fromEntries(fields.map((f) => [f.key, ''])) as FormOf<K>
}

export const YMD_RE = /^\d{4}-\d{2}-\d{2}$/
export const NUMBER_RE = /^-?\d+(\.\d+)?$/

/** The three keys `withSampleDate` keeps in step. */
export interface DatedForm {
  measurement_date: string
  gc_run_date: string
  time_post_reaction_days: string
}

/** Sets the sample date, and the GC date and day unless the user edited them.
 *  The day is whole lab calendar days since `startDate`, blank without one. */
export function withSampleDate<F extends DatedForm>(
  form: F,
  date: string,
  opts: { startDate: string | null; gcEdited: boolean; dayEdited: boolean },
): F {
  const next = { ...form, measurement_date: date }
  if (!opts.gcEdited) next.gc_run_date = date
  if (!opts.dayEdited) {
    next.time_post_reaction_days =
      opts.startDate && YMD_RE.test(date) ? String(labCalendarDays(opts.startDate, date)) : ''
  }
  return next
}

/** With `initial` (edit mode), a required field is only an error when the user
 *  cleared a value it started with; a historical row that never had it can still
 *  be edited, since the patch omits unchanged fields. */
export function validateFields<K extends string>(
  fields: readonly FieldDef<K>[],
  form: FormOf<K>,
  initial?: FormOf<K>,
): Partial<Record<K, string>> {
  const errors: Partial<Record<K, string>> = {}
  for (const f of fields) {
    const v = form[f.key].trim()
    if (v === '') {
      if (f.required && (!initial || initial[f.key].trim() !== '')) errors[f.key] = 'Required'
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
export function createBodyFrom<K extends string>(
  fields: readonly FieldDef<K>[],
  form: FormOf<K>,
): Record<string, string | number> {
  const body: Record<string, string | number> = {}
  for (const f of fields) {
    const v = form[f.key].trim()
    if (v !== '') body[f.key] = f.toWire(v)
  }
  return body
}

/** Only the fields whose trimmed text changed; blank becomes null. Never the day,
 *  which is fixed once a sample exists (re-bucketing would shift its lineage). */
export function changedFields<K extends string>(
  fields: readonly FieldDef<K>[],
  initial: FormOf<K>,
  form: FormOf<K>,
): Record<string, string | number | null> {
  const body: Record<string, string | number | null> = {}
  for (const f of fields) {
    if (f.key === 'time_post_reaction_days') continue
    const before = initial[f.key].trim()
    const after = form[f.key].trim()
    if (before === after) continue
    body[f.key] = after === '' ? null : f.toWire(after)
  }
  return body
}

/** Number for display: the shared 1-dp format, a dash for missing values (issue #169).
 *  Day / tube labels and flow rates use `formatPrecise` instead. */
export function fmt(v: number | null | undefined): string {
  return formatNumber(v)
}
