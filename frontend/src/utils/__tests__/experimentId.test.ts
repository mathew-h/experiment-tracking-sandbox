import { describe, expect, it } from 'vitest'
import { isSerumType, runListPathFor, runPathFor, splitTimepointToken } from '../experimentId'

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

describe('isSerumType', () => {
  it('accepts every serum spelling in real data', () => {
    expect(isSerumType('SERUM')).toBe(true)
    expect(isSerumType('Serum')).toBe(true)
    expect(isSerumType(' Serum  Vial ')).toBe(true)
    expect(isSerumType('Serum Vial')).toBe(true)
  })

  it('rejects other types and non-strings', () => {
    expect(isSerumType('HPHT')).toBe(false)
    expect(isSerumType('Serumx')).toBe(false)
    expect(isSerumType(null)).toBe(false)
    expect(isSerumType(undefined)).toBe(false)
  })
})

describe('runPathFor', () => {
  it('routes every HPHT spelling to /hpht', () => {
    expect(runPathFor('HPHT', 'HPHT_297')).toBe('/hpht/HPHT_297')
    expect(runPathFor('hpht', 'HPHT_297')).toBe('/hpht/HPHT_297')
  })

  it('routes every core flood spelling to /core-floods', () => {
    for (const t of ['Core Flood', 'coreflood', 'CF', ' core  flood ']) {
      expect(runPathFor(t, 'CF_018')).toBe('/core-floods/CF_018')
    }
  })

  it('returns null for types without a run page', () => {
    expect(runPathFor('Serum', 'SERUM_001')).toBeNull()
    expect(runPathFor(null, 'HPHT_297')).toBeNull()
    expect(runPathFor(undefined, 'HPHT_297')).toBeNull()
  })

  it('returns null without a base ID', () => {
    expect(runPathFor('HPHT', null)).toBeNull()
    expect(runPathFor('HPHT', undefined)).toBeNull()
    expect(runPathFor('Core Flood', '')).toBeNull()
  })

  it('URL-encodes the base ID exactly once', () => {
    expect(runPathFor('HPHT', 'HPHT 1/2#a')).toBe('/hpht/HPHT%201%2F2%23a')
    expect(runPathFor('HPHT', 'HPHT%20X')).toBe('/hpht/HPHT%2520X')
  })
})

describe('runListPathFor', () => {
  it('names the run list for HPHT and core flood types', () => {
    expect(runListPathFor('HPHT')).toBe('/hpht')
    expect(runListPathFor('Core Flood')).toBe('/core-floods')
    expect(runListPathFor('cf')).toBe('/core-floods')
  })

  it('returns null for other types', () => {
    expect(runListPathFor('Serum')).toBeNull()
    expect(runListPathFor(null)).toBeNull()
    expect(runListPathFor(42)).toBeNull()
  })
})
