import { describe, it, expect } from 'vitest'
import type { ExperimentNote } from '@/api/experiments'
import { sortTimeline, timelineDay, recordedAt, timepointLabel } from '../notesTimeline'

/** Built WITHOUT an event_date key on purpose: the TS field is optional and
 *  a missing key must behave exactly like null (Review Focus 5). */
function note(partial: Partial<ExperimentNote> & { id: number }): ExperimentNote {
  return {
    note_text: 'x', note_type: 'observation', result_id: null, created_by: null,
    needs_review: false, created_at: '2026-04-01T12:00:00Z', updated_at: null, ...partial,
  }
}

/** A local-time ISO string, so the tests mean the same thing in any zone. */
const local = (y: number, m: number, d: number, h: number) => new Date(y, m - 1, d, h).toISOString()

describe('sortTimeline', () => {
  it('orders by day — event_date when set, else the day written — newest first', () => {
    const out = sortTimeline([
      note({ id: 1, created_at: local(2026, 9, 1, 10) }),
      note({ id: 2, note_type: 'modification', event_date: '2026-09-20', created_at: local(2026, 8, 1, 10) }),
      note({ id: 3, created_at: local(2026, 9, 10, 10) }),
    ])
    expect(out.map((n) => n.id)).toEqual([2, 3, 1])
  })

  it('a modification dated today sits above observations written earlier today (Mat, 2026-10-05)', () => {
    const out = sortTimeline([
      note({ id: 1, created_at: local(2026, 10, 5, 9) }),
      note({ id: 2, note_type: 'modification', event_date: '2026-10-05', created_at: local(2026, 10, 5, 15) }),
      note({ id: 3, created_at: local(2026, 10, 5, 11) }),
    ])
    expect(out.map((n) => n.id)).toEqual([2, 3, 1])
  })

  it('a backdated modification lands on its event day, not the day it was typed', () => {
    const out = sortTimeline([
      note({ id: 1, created_at: local(2026, 9, 16, 9) }),
      note({ id: 2, note_type: 'modification', event_date: '2026-09-14', created_at: local(2026, 10, 5, 15) }),
      note({ id: 3, created_at: local(2026, 9, 14, 11) }),
    ])
    // 9/16 first; then the two 9/14 notes, the backdated one on top because it was recorded later.
    expect(out.map((n) => n.id)).toEqual([1, 2, 3])
  })

  it('breaks full ties on id, newest first, and does not mutate its input', () => {
    const input = [note({ id: 4 }), note({ id: 9 }), note({ id: 6 })]
    const out = sortTimeline(input)
    expect(out.map((n) => n.id)).toEqual([9, 6, 4])
    expect(input.map((n) => n.id)).toEqual([4, 9, 6])
  })

  it('treats event_date: null like a missing key', () => {
    const out = sortTimeline([
      note({ id: 1, event_date: null, created_at: local(2026, 9, 1, 10) }),
      note({ id: 2, created_at: local(2026, 9, 2, 10) }),
    ])
    expect(out.map((n) => n.id)).toEqual([2, 1])
  })
})

describe('timelineDay / recordedAt', () => {
  it('a dated note belongs to its event day regardless of when it was written', () => {
    expect(timelineDay(note({ id: 1, event_date: '2026-09-20', created_at: local(2026, 10, 5, 15) }))).toBe(20260920)
  })
  it('an undated note belongs to the local day it was written', () => {
    expect(timelineDay(note({ id: 1, created_at: local(2026, 4, 1, 23) }))).toBe(20260401)
  })
  it('recordedAt is the created_at instant', () => {
    expect(recordedAt(note({ id: 1, created_at: '2026-04-01T12:00:00Z' }))).toBe(Date.parse('2026-04-01T12:00:00Z'))
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
