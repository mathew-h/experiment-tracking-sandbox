import { describe, it, expect } from 'vitest'
import type { ExperimentNote } from '@/api/experiments'
import { sortTimeline, timelineKey, timepointLabel } from '../notesTimeline'

/** Built WITHOUT an event_date key on purpose: the TS field is optional and
 *  a missing key must behave exactly like null (Review Focus 5). */
function note(partial: Partial<ExperimentNote> & { id: number }): ExperimentNote {
  return {
    note_text: 'x', note_type: 'observation', result_id: null, created_by: null,
    needs_review: false, created_at: '2026-04-01T12:00:00Z', updated_at: null, ...partial,
  }
}

describe('sortTimeline', () => {
  it('orders by event_date when set, else created_at, newest first', () => {
    const out = sortTimeline([
      note({ id: 1, created_at: '2026-09-01T10:00:00Z' }),
      note({ id: 2, note_type: 'modification', event_date: '2026-09-20', created_at: '2026-08-01T10:00:00Z' }),
      note({ id: 3, created_at: '2026-09-10T10:00:00Z' }),
    ])
    expect(out.map((n) => n.id)).toEqual([2, 3, 1])
  })

  it('breaks ties on id, newest first, and does not mutate its input', () => {
    const input = [note({ id: 4 }), note({ id: 9 }), note({ id: 6 })]
    const out = sortTimeline(input)
    expect(out.map((n) => n.id)).toEqual([9, 6, 4])
    expect(input.map((n) => n.id)).toEqual([4, 9, 6])
  })

  it('treats event_date: null like a missing key', () => {
    const out = sortTimeline([
      note({ id: 1, event_date: null, created_at: '2026-09-01T10:00:00Z' }),
      note({ id: 2, created_at: '2026-09-02T10:00:00Z' }),
    ])
    expect(out.map((n) => n.id)).toEqual([2, 1])
  })
})

describe('timelineKey', () => {
  it('a dated note keys at local midnight of its lab calendar day', () => {
    expect(timelineKey(note({ id: 1, event_date: '2026-09-20' }))).toBe(new Date(2026, 8, 20).getTime())
  })
  it('an undated note keys at the instant it was created', () => {
    expect(timelineKey(note({ id: 1, created_at: '2026-04-01T12:00:00Z' }))).toBe(Date.parse('2026-04-01T12:00:00Z'))
  })
})

describe('timepointLabel', () => {
  it('formats known days and falls back to T+? for unknown', () => {
    expect(timepointLabel(7)).toBe('T+7')
    expect(timepointLabel(0.5)).toBe('T+0.5')
    expect(timepointLabel(null)).toBe('T+?')
    expect(timepointLabel(undefined)).toBe('T+?')
  })
})
