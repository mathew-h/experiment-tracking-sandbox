// Mirror of database/experiment_id_parser.py::split_timepoint_token (issue #81).
// '-t<days>' at the end of an experiment ID encodes the vial's time
// post-reaction in days (decimals allowed). Lowercase 't' only.
const TIMEPOINT_TOKEN_RE = /-t(\d+(?:\.\d+)?)$/

export function splitTimepointToken(experimentId: string): {
  stem: string
  timepointDays: number | null
} {
  const match = TIMEPOINT_TOKEN_RE.exec(experimentId)
  if (!match) return { stem: experimentId, timepointDays: null }
  return {
    stem: experimentId.slice(0, match.index),
    timepointDays: parseFloat(match[1]),
  }
}

/** True for the serum experiment types in real data (`SERUM`, `Serum`, `Serum Vial`).
 *  Case-, whitespace- and padding-insensitive; mirrors
 *  database/reactor_slot.py::normalize_experiment_type (issue #144). */
export function isSerumType(t: unknown): boolean {
  if (typeof t !== 'string') return false
  const norm = t.trim().replace(/\s+/g, ' ').toLowerCase()
  return norm === 'serum' || norm === 'serum vial'
}

function normalizeType(t: unknown): string {
  return typeof t === 'string' ? t.trim().replace(/\s+/g, ' ').toLowerCase() : ''
}

/** True for HPHT in any casing; mirrors database/reactor_slot.py. */
export function isHphtType(t: unknown): boolean {
  return normalizeType(t) === 'hpht'
}

/** True for the core flood spellings the backend's series_prefix maps to 'CF'. */
export function isCoreFloodType(t: unknown): boolean {
  const n = normalizeType(t)
  return n === 'core flood' || n === 'coreflood' || n === 'cf'
}
