import type { RunSegment } from '@/api/runs'

/** Mirrors backend/services/run_service.py so a run page agrees with its run list. */

/** Non-variant, parentless segments, earliest first (the first is the run's root). */
export function rootSegments(segments: RunSegment[]): RunSegment[] {
  const date = (s: RunSegment) => (s.date ? Date.parse(s.date) : Infinity)
  return segments
    .filter((s) => !s.is_variant && s.parent_experiment_id == null)
    .sort((a, b) => date(a) - date(b))
}

/** The root segment's description: non-variant, no parent, earliest date; else the first described segment. */
export function runDescription(segments: RunSegment[]): string | null {
  return rootSegments(segments)[0]?.description || segments.find((s) => s.description)?.description || null
}

/** The latest-dated segment (undated lose, id breaks ties), as the run list's reactor/rig column uses. */
export function latestSegment(segments: RunSegment[]): RunSegment | undefined {
  return segments.reduce<RunSegment | undefined>((best, s) => {
    if (!best) return s
    const [a, b] = [best, s].map((x) => (x.date ? Date.parse(x.date) : -Infinity))
    return b > a || (b === a && s.id > best.id) ? s : best
  }, undefined)
}

/** IDs of the ONGOING segments, in run order. */
export function ongoingIds(segments: RunSegment[]): string[] {
  return segments.filter((s) => s.status?.toUpperCase() === 'ONGOING').map((s) => s.experiment_id)
}
