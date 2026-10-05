import type { ExperimentNote } from '@/api/experiments'

/** A local calendar day as a sortable integer (YYYYMMDD). */
function localDayNumber(d: Date): number {
  return d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate()
}

/** The calendar day a note belongs to on the timeline (issue #122 PR-C, Mat
 *  2026-10-05): its `event_date` when it has one — a dated modification is
 *  "something done on that day" — otherwise the local day it was written.
 *  A missing event_date key behaves like null. */
export function timelineDay(n: ExperimentNote): number {
  if (n.event_date) {
    const [y, m, d] = n.event_date.split('-').map(Number)
    return localDayNumber(new Date(y, m - 1, d))
  }
  return localDayNumber(new Date(n.created_at))
}

/** When the note was recorded, as a timestamp — the only time information a
 *  dated note has, used to order notes within one day. */
export function recordedAt(n: ExperimentNote): number {
  return new Date(n.created_at).getTime()
}

/** Day first, newest day first; within a day, most recently recorded first;
 *  equal → higher id first. A modification dated today therefore sits above
 *  the observations written earlier today (a midnight key put it below them),
 *  and a backdated one still lands on its event day. Returns a new array. */
export function sortTimeline(notes: ExperimentNote[]): ExperimentNote[] {
  return [...notes].sort(
    (a, b) => timelineDay(b) - timelineDay(a) || recordedAt(b) - recordedAt(a) || b.id - a.id,
  )
}

/** `T+7` for a result-scoped note whose result is known; `T+?` when the
 *  results list has not loaded or no longer contains that result. */
export function timepointLabel(days: number | null | undefined): string {
  return days == null ? 'T+?' : `T+${days}`
}
