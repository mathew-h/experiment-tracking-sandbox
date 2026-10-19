import type { ExperimentType } from './fieldVisibility'

/** Nominal serum vial size (whole mL). Strict on purpose: the wizard creates the
 *  experiment before its conditions, so a value the API would 422 must be caught
 *  here or the experiment is left with no conditions row. */
export const VIAL_SIZE_ERROR = 'Enter a whole number of mL greater than 0'

export type ParsedVialSize = { value?: number; error?: string }

export function parseVialSize(raw: string): ParsedVialSize {
  const s = raw.trim()
  if (s === '') return {}
  if (!/^\d+$/.test(s)) return { error: VIAL_SIZE_ERROR }
  const n = Number(s)
  return n > 0 ? { value: n } : { error: VIAL_SIZE_ERROR }
}

/** The value to send on conditions create. Serum only: a value left in state
 *  after switching to another type is hidden, so it is dropped, not sent.
 *  Throws on an invalid Serum value so the caller aborts before creating anything. */
export function vialSizeForPayload(type: ExperimentType | '', raw: string): number | undefined {
  if (type !== 'Serum') return undefined
  const { value, error } = parseVialSize(raw)
  if (error) throw new Error(`Serum vial size: ${error}`)
  return value
}
