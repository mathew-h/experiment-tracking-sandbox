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
