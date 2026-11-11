/** Calendar-date helpers for the Data Export date-range filters.
 *  Every value is a lab-local YYYY-MM-DD string; arithmetic runs in UTC on the
 *  bare date, so a DST change can never shift a day. */

export interface DateRange {
  begin: string
  end: string
}

export type PresetId = 'last7' | 'last30' | 'thisMonth' | 'lastMonth'

export interface Preset {
  id: PresetId
  label: string
}

/** Quick ranges for the Last sample date filter, in display order. */
export const SAMPLE_DATE_PRESETS: Preset[] = [
  { id: 'last7', label: 'Last 7 days' },
  { id: 'last30', label: 'Last 30 days' },
  { id: 'thisMonth', label: 'This month' },
  { id: 'lastMonth', label: 'Last month' },
]

const toUtc = (ymd: string) => {
  const [y, m, d] = ymd.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d))
}
const toYmd = (dt: Date) => dt.toISOString().slice(0, 10)

/** `ymd` shifted by `days` calendar days. */
export function addDays(ymd: string, days: number): string {
  const dt = toUtc(ymd)
  dt.setUTCDate(dt.getUTCDate() + days)
  return toYmd(dt)
}

/** The inclusive range a preset stands for, relative to the lab's `today`. */
export function presetRange(id: PresetId, today: string): DateRange {
  const firstOfMonth = `${today.slice(0, 8)}01`
  switch (id) {
    case 'last7':
      return { begin: addDays(today, -6), end: today }
    case 'last30':
      return { begin: addDays(today, -29), end: today }
    case 'thisMonth':
      return { begin: firstOfMonth, end: today }
    case 'lastMonth': {
      const end = addDays(firstOfMonth, -1)
      return { begin: `${end.slice(0, 8)}01`, end }
    }
  }
}
