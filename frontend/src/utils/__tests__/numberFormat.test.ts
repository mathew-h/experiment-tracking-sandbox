import { describe, it, expect } from 'vitest'
import { formatNumber, formatPrecise, fullValueTitle, MISSING } from '../numberFormat'

describe('formatNumber', () => {
  it('renders missing and non-finite values as the dash', () => {
    expect(MISSING).toBe('—')
    expect(formatNumber(null)).toBe('—')
    expect(formatNumber(undefined)).toBe('—')
    expect(formatNumber(NaN)).toBe('—')
    expect(formatNumber(Infinity)).toBe('—')
  })

  it('renders zero as "0"', () => {
    expect(formatNumber(0)).toBe('0')
    expect(formatNumber(-0)).toBe('0')
  })

  it('never shows a small nonzero value as zero', () => {
    expect(formatNumber(0.04)).toBe('<0.1')
    expect(formatNumber(0.0001)).toBe('<0.1')
    expect(formatNumber(-0.04)).toBe('>-0.1')
  })

  it('rounds to 1 dp and trims the trailing zero', () => {
    expect(formatNumber(0.05)).toBe('0.1')
    expect(formatNumber(5)).toBe('5')
    expect(formatNumber(3.14159)).toBe('3.1')
    expect(formatNumber(2.96)).toBe('3')
    expect(formatNumber(-12.34)).toBe('-12.3')
    expect(formatNumber(52.776)).toBe('52.8')
  })
})

describe('formatPrecise', () => {
  it('keeps up to 3 dp with trailing zeros trimmed', () => {
    expect(formatPrecise(7.55)).toBe('7.55')
    expect(formatPrecise(0.05)).toBe('0.05')
    expect(formatPrecise(0.125)).toBe('0.125')
    expect(formatPrecise(10)).toBe('10')
    expect(formatPrecise(1.23456)).toBe('1.235')
  })

  it('renders missing values as the dash', () => {
    expect(formatPrecise(null)).toBe('—')
    expect(formatPrecise(NaN)).toBe('—')
  })
})

describe('fullValueTitle', () => {
  it('is the full stored number, or undefined when missing', () => {
    expect(fullValueTitle(0.4088873141807249)).toBe('0.4088873141807249')
    expect(fullValueTitle(null)).toBeUndefined()
    expect(fullValueTitle(NaN)).toBeUndefined()
  })
})
