import { describe, it, expect } from 'vitest'
import type { CoreFloodIcpRow, CoreFloodSample } from '@/api/coreFloods'
import { chartPoints, defaultSelection, elementsPresent, segmentStarts } from '../icpSeries'

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
})
