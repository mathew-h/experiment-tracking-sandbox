import { describe, expect, it } from 'vitest'
import { splitTimepointToken } from '../experimentId'

describe('splitTimepointToken', () => {
  it('peels integer and decimal day tokens', () => {
    expect(splitTimepointToken('SERUM_001a-t7')).toEqual({ stem: 'SERUM_001a', timepointDays: 7 })
    expect(splitTimepointToken('SERUM_001a-t0')).toEqual({ stem: 'SERUM_001a', timepointDays: 0 })
    expect(splitTimepointToken('SERUM_001a-t0.5')).toEqual({ stem: 'SERUM_001a', timepointDays: 0.5 })
  })

  it('passes through IDs without a token', () => {
    for (const id of ['SERUM_001a', 'CF-015', 'HPHT_MH_001-2', 'HPHT_MH_001_Desorption']) {
      expect(splitTimepointToken(id)).toEqual({ stem: id, timepointDays: null })
    }
  })

  it('is case-sensitive and end-anchored', () => {
    expect(splitTimepointToken('SERUM_001a-T7').timepointDays).toBeNull()
    expect(splitTimepointToken('SERUM_001a-t7_Desorption').timepointDays).toBeNull()
    expect(splitTimepointToken('SERUM_001a-t').timepointDays).toBeNull()
  })
})
