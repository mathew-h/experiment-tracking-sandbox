import { describe, it, expect } from 'vitest'
import { parseVialSize, vialSizeForPayload, VIAL_SIZE_ERROR } from '../vialSize'

describe('parseVialSize', () => {
  it('treats blank and whitespace as no value, no error', () => {
    expect(parseVialSize('')).toEqual({})
    expect(parseVialSize('   ')).toEqual({})
  })

  it('accepts positive whole numbers', () => {
    expect(parseVialSize('120')).toEqual({ value: 120 })
    expect(parseVialSize(' 20 ')).toEqual({ value: 20 })
  })

  it.each(['0', '-1', '120.5', '120.0', '1e2', 'abc'])('rejects %s', (raw) => {
    expect(parseVialSize(raw)).toEqual({ error: VIAL_SIZE_ERROR })
  })
})

describe('vialSizeForPayload', () => {
  it('returns the integer for Serum', () => {
    expect(vialSizeForPayload('Serum', '160')).toBe(160)
  })

  it('returns undefined for blank Serum', () => {
    expect(vialSizeForPayload('Serum', '')).toBeUndefined()
  })

  it('drops a stale hidden value for non-Serum types', () => {
    expect(vialSizeForPayload('HPHT', '120')).toBeUndefined()
    expect(vialSizeForPayload('HPHT', '120.5')).toBeUndefined()
    expect(vialSizeForPayload('', '120')).toBeUndefined()
  })

  it('throws for an invalid Serum value so no experiment is created', () => {
    expect(() => vialSizeForPayload('Serum', '0')).toThrow(VIAL_SIZE_ERROR)
  })
})
