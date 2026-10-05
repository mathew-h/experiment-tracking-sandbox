import { describe, it, expect } from 'vitest'
import { labTodayISO, LAB_TZ } from '../labDate'

describe('labTodayISO', () => {
  it('is the lab calendar day, which can differ from the UTC date', () => {
    // 02:30Z on 6 Oct is still the evening of 5 Oct in New York (EDT, UTC-4).
    expect(labTodayISO(new Date('2026-10-06T02:30:00Z'))).toBe('2026-10-05')
  })

  it('formats YYYY-MM-DD with zero padding', () => {
    expect(labTodayISO(new Date('2026-01-05T12:00:00Z'))).toBe('2026-01-05')
  })

  it('names the lab zone the server uses', () => {
    expect(LAB_TZ).toBe('America/New_York')
  })
})
