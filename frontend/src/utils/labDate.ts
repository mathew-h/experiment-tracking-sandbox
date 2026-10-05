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
