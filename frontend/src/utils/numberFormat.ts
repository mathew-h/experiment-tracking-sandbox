/**
 * Shared display formatting for numbers (issue #169).
 *
 * Display only: stored values, API payloads and exports keep full precision.
 * Never use these for form prefills or edit round-trips; a rounded prefill would
 * silently truncate the value on the next save.
 */

/** Shown for null, undefined and non-finite values; never "0" or "NaN". */
export const MISSING = '—'

/** Below this magnitude a nonzero value would round to 0 at 1 dp. */
const SMALL = 0.05

/**
 * Default display format: 1 dp, trailing zero trimmed (3.14159 -> "3.1", 2.96 -> "3").
 * A nonzero value that would round to 0 shows as "<0.1" (">-0.1" when negative),
 * so a small measured value never reads as a true zero.
 */
export function formatNumber(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return MISSING
  if (v === 0) return '0'
  if (Math.abs(v) < SMALL) return v > 0 ? '<0.1' : '>-0.1'
  return parseFloat(v.toFixed(1)).toString()
}

/**
 * Up to 3 dp, trailing zeros trimmed, no "<0.1" rule (0.125 -> "0.125", 7.55 -> "7.55").
 * Only for values where 1 dp loses real information: day / T+ / tube labels, core
 * flood flow rates, catalyst ppm, additive amounts and chemical densities.
 */
export function formatPrecise(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return MISSING
  return parseFloat(v.toFixed(3)).toString()
}

/** `title` text for a rounded value: the full stored number, or undefined when missing. */
export function fullValueTitle(v: number | null | undefined): string | undefined {
  return v == null || !Number.isFinite(v) ? undefined : String(v)
}
