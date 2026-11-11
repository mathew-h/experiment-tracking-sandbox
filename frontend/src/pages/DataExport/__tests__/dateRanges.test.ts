import { describe, it, expect } from 'vitest'
import { addDays, presetRange, SAMPLE_DATE_PRESETS } from '../dateRanges'

describe('addDays', () => {
  it('crosses month and year boundaries', () => {
    expect(addDays('2026-11-11', -6)).toBe('2026-11-05')
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28')
    expect(addDays('2028-03-01', -1)).toBe('2028-02-29')
    expect(addDays('2027-01-01', -1)).toBe('2026-12-31')
  })

  it('is not shifted by a DST change', () => {
    // US DST ends 2026-11-01.
    expect(addDays('2026-11-03', -3)).toBe('2026-10-31')
  })
})

describe('presetRange', () => {
  const today = '2026-11-11'

  it('Last 7 / 30 days include today', () => {
    expect(presetRange('last7', today)).toEqual({ begin: '2026-11-05', end: '2026-11-11' })
    expect(presetRange('last30', today)).toEqual({ begin: '2026-10-13', end: '2026-11-11' })
  })

  it('This month runs from the 1st to today', () => {
    expect(presetRange('thisMonth', today)).toEqual({ begin: '2026-11-01', end: '2026-11-11' })
  })

  it('Last month is the whole previous calendar month', () => {
    expect(presetRange('lastMonth', today)).toEqual({ begin: '2026-10-01', end: '2026-10-31' })
    expect(presetRange('lastMonth', '2027-01-15')).toEqual({ begin: '2026-12-01', end: '2026-12-31' })
    expect(presetRange('lastMonth', '2028-03-31')).toEqual({ begin: '2028-02-01', end: '2028-02-29' })
  })

  it('every listed preset resolves', () => {
    for (const p of SAMPLE_DATE_PRESETS) {
      const r = presetRange(p.id, today)
      expect(r.begin <= r.end).toBe(true)
    }
  })
})
