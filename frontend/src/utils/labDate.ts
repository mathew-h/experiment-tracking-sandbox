/** The lab's time zone. "Today" for a dated note is the lab's calendar day,
 *  not UTC and not the browser's zone (Mat, 2026-10-05). The server uses the
 *  same zone (`LAB_TZ` in backend/api/routers/dashboard.py) for the reactor
 *  card's "modified today" line. */
export const LAB_TZ = 'America/New_York'

/** Today as YYYY-MM-DD in the lab's time zone. `now` is injectable for tests. */
export function labTodayISO(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: LAB_TZ, year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(now)
}

const OFFSET_RE = /(Z|[+-]\d{2}:?\d{2})$/i

/** Lab-local YYYY-MM-DD of an ISO string. A value with no Z or offset is already
 *  lab wall clock (production stores dates at local midnight), so its first 10
 *  characters are the answer; an aware instant is formatted in LAB_TZ. */
export function labDateOf(value: string): string {
  const time = value.split('T')[1]
  if (time === undefined || !OFFSET_RE.test(time)) return value.slice(0, 10)
  return labTodayISO(new Date(value))
}

/** Whole lab calendar days from `start` to `sampleYmd`. Both sides are reduced to
 *  a calendar date and differenced in UTC, so a DST hour never shifts the count. */
export function labCalendarDays(start: string, sampleYmd: string): number {
  const ms = (ymd: string) => {
    const [y, m, d] = ymd.split('-').map(Number)
    return Date.UTC(y, m - 1, d)
  }
  return (ms(sampleYmd) - ms(labDateOf(start))) / 86_400_000
}
