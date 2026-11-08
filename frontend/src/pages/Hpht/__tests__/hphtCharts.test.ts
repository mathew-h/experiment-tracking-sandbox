import { describe, it, expect } from 'vitest'
import { chartMarkers, chartPoints, hasH2 } from '../hphtSeries'
import { RUN, sample } from './fixtures'

describe('HPHT chart series (issue #150)', () => {
  it('excludes variants from the cumulative series', () => {
    const points = chartPoints(RUN.samples)
    expect(points.map((p) => p.day)).toEqual([1, 4, 8])
    expect(points.map((p) => p.cumH2)).toEqual([0.1, 0.3, 0.7])
    // The variant's day-6 row and its 9.9 g/t never reach the chart.
    expect(points.some((p) => p.day === 6)).toBe(false)
  })

  it('keeps a NULL rate as a gap, not a zero', () => {
    const points = chartPoints(RUN.samples)
    expect(points[1].rate).toBeNull()
    expect(points[1].rate).not.toBe(0)
  })

  it('drops rows without a cumulative day and sorts by day', () => {
    const points = chartPoints([
      sample({ result_id: 2, cumulative_time_post_reaction_days: 5 }),
      sample({ result_id: 3, cumulative_time_post_reaction_days: null }),
      sample({ result_id: 1, cumulative_time_post_reaction_days: 2 }),
    ])
    expect(points.map((p) => p.day)).toEqual([2, 5])
  })

  it('marks where each later non-variant segment starts', () => {
    expect(chartMarkers(RUN.samples)).toEqual([{ day: 8, experimentId: 'HPHT_297-2' }])
  })

  it('reports no H₂ when only variants have it', () => {
    expect(hasH2(RUN.samples)).toBe(true)
    expect(hasH2([
      sample({ h2_grams_per_ton_yield: null }),
      sample({ result_id: 2, is_variant: true, h2_grams_per_ton_yield: 5 }),
    ])).toBe(false)
  })
})
