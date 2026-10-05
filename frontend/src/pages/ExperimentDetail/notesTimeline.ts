import type { ExperimentNote } from '@/api/experiments'

/** Sort key for the Notes timeline (issue #122 PR-C): COALESCE(event_date,
 *  created_at). A dated note sorts at local midnight of its lab calendar day
 *  (the date is a day, not an instant); everything else at the instant it was
 *  written. A missing event_date key behaves like null. */
export function timelineKey(n: ExperimentNote): number {
  if (n.event_date) {
    const [y, m, d] = n.event_date.split('-').map(Number)
    return new Date(y, m - 1, d).getTime()
  }
  return new Date(n.created_at).getTime()
}

/** Newest first; equal keys → higher id first. Returns a new array. */
export function sortTimeline(notes: ExperimentNote[]): ExperimentNote[] {
  return [...notes].sort((a, b) => timelineKey(b) - timelineKey(a) || b.id - a.id)
}

/** `T+7` for a result-scoped note whose result is known; `T+?` when the
 *  results list has not loaded or no longer contains that result. */
export function timepointLabel(days: number | null | undefined): string {
  return days == null ? 'T+?' : `T+${days}`
}
