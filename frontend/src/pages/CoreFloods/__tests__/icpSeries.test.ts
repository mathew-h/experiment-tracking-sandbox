import { describe, it, expect } from 'vitest'
import { chartColors } from '@/assets/brand'
import type { CoreFloodIcpRow, CoreFloodSample } from '@/api/coreFloods'
import { chartPoints, defaultSelection, elementsPresent, lineProps, lineStyles, segmentStarts } from '../icpSeries'

const row = (over: Partial<CoreFloodIcpRow>): CoreFloodIcpRow => ({
  result_id: 1,
  experiment_id: 'CF_020',
  is_variant: false,
  cumulative_time_post_reaction_days: 1,
  sample_date: null,
  elements: {},
  ...over,
})

const smp = (over: Partial<CoreFloodSample>) =>
  ({
    result_id: 1,
    experiment_id: 'CF_020',
    is_variant: false,
    cumulative_time_post_reaction_days: 1,
    ...over,
  }) as CoreFloodSample

describe('icpSeries', () => {
  it('elementsPresent keeps ICP_ELEMENTS order', () => {
    const rows = [row({ elements: { cu: 1, fe: 2 } }), row({ elements: { ca: 3, zz: 9 } })]
    expect(elementsPresent(rows)).toEqual(['fe', 'ca', 'cu'])
  })

  it('defaultSelection prefers ca si fe cu ni', () => {
    expect(defaultSelection(['fe', 'si', 'mg', 'ca', 'ni', 'cu', 'mo', 'zn'])).toEqual([
      'fe', 'si', 'ca', 'ni', 'cu',
    ])
    expect(defaultSelection(['mg', 'ca', 'zn'])).toEqual(['ca'])
  })

  it('defaultSelection falls back to first five present', () => {
    expect(defaultSelection(['mg', 'mo', 'zn', 'mn', 'cr', 'co'])).toEqual([
      'mg', 'mo', 'zn', 'mn', 'cr',
    ])
  })

  it('excludes variant rows and rows without a day, sorted by day', () => {
    const rows = [
      row({ result_id: 1, cumulative_time_post_reaction_days: 5, elements: { fe: 2 } }),
      row({ result_id: 2, is_variant: true, cumulative_time_post_reaction_days: 3, elements: { fe: 9 } }),
      row({ result_id: 3, cumulative_time_post_reaction_days: null, elements: { fe: 9 } }),
      row({ result_id: 4, cumulative_time_post_reaction_days: 2, elements: { fe: 1 } }),
    ]
    expect(chartPoints(rows, ['fe', 'ca'], false)).toEqual([
      { day: 2, fe: 1, ca: null },
      { day: 5, fe: 2, ca: null },
    ])
  })

  it('drops non-positive values in log mode', () => {
    const rows = [row({ elements: { fe: 0, ca: 4 } })]
    expect(chartPoints(rows, ['fe', 'ca'], true)).toEqual([{ day: 1, fe: null, ca: 4 }])
    expect(chartPoints(rows, ['fe', 'ca'], false)).toEqual([{ day: 1, fe: 0, ca: 4 }])
  })

  it('lineProps connects nulls only on the linear scale', () => {
    expect(lineProps(false)).toEqual({ connectNulls: true })
    expect(lineProps(true)).toEqual({ connectNulls: false })
  })

  it('segmentStarts skips the first segment', () => {
    const samples = [
      smp({ result_id: 1, experiment_id: 'A', cumulative_time_post_reaction_days: 1 }),
      smp({ result_id: 2, experiment_id: 'A', cumulative_time_post_reaction_days: 3 }),
      smp({ result_id: 3, experiment_id: 'B-side', is_variant: true, cumulative_time_post_reaction_days: 4 }),
      smp({ result_id: 4, experiment_id: 'B', cumulative_time_post_reaction_days: 6 }),
      smp({ result_id: 5, experiment_id: 'B', cumulative_time_post_reaction_days: 8 }),
      smp({ result_id: 6, experiment_id: 'C', cumulative_time_post_reaction_days: 10 }),
    ]
    expect(segmentStarts(samples)).toEqual([
      { day: 6, experimentId: 'B' },
      { day: 10, experimentId: 'C' },
    ])
  })

  it('lineStyles gives distinct colours to the first four', () => {
    const st = lineStyles(['ca', 'si', 'fe', 'cu'])
    expect(new Set(Object.values(st).map((x) => x.color)).size).toBe(4)
  })

  it('lineStyles never uses the mean colour', () => {
    const els = Array.from({ length: 24 }, (_, i) => `e${i}`)
    const colors = Object.values(lineStyles(els)).map((x) => x.color)
    expect(colors).not.toContain(chartColors.mean)
  })

  it('lineStyles is solid for the first four and dashed from the fifth', () => {
    const st = Object.values(lineStyles(Array.from({ length: 6 }, (_, i) => `e${i}`)))
    expect(st.slice(0, 4).every((x) => x.dash === undefined)).toBe(true)
    expect(st[4].dash).toBeDefined()
  })

  it('lineStyles never repeats a colour+dash pair for up to 24 lines', () => {
    const els = Array.from({ length: 24 }, (_, i) => `e${i}`)
    const pairs = Object.values(lineStyles(els)).map((x) => `${x.color}|${x.dash ?? ''}`)
    expect(new Set(pairs).size).toBe(24)
  })
})
