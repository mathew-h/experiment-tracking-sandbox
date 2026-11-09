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

/** The run list a type belongs to: `/hpht`, `/core-floods`, or null for types
 *  with no run page (Serum and the rest). */
export function runListPathFor(experimentType: unknown): '/hpht' | '/core-floods' | null {
  if (isHphtType(experimentType)) return '/hpht'
  if (isCoreFloodType(experimentType)) return '/core-floods'
  return null
}

/** Route of the run page for a base experiment ID, or null when the type has no
 *  run page or the base ID is missing. The one place a run path is spelled
 *  (issue #155); the base ID is URL-encoded here and nowhere else. The first
 *  overload is for callers with a fixed run type and a non-empty base ID. */
export function runPathFor(experimentType: 'HPHT' | 'Core Flood', baseId: string): string
export function runPathFor(experimentType: unknown, baseId: string | null | undefined): string | null
export function runPathFor(experimentType: unknown, baseId: string | null | undefined): string | null {
  const list = runListPathFor(experimentType)
  if (!list || !baseId) return null
  return `${list}/${encodeURIComponent(baseId)}`
}
