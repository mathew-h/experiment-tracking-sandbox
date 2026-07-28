import { describe, expect, it } from 'vitest'
import { colors } from '../assets/brand'

const AA_MIN_CONTRAST = 4.5

function srgbToLinear(channel: number): number {
  const c = channel / 255
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

function relativeLuminance(hex: string): number {
  const value = hex.replace('#', '')
  const r = parseInt(value.slice(0, 2), 16)
  const g = parseInt(value.slice(2, 4), 16)
  const b = parseInt(value.slice(4, 6), 16)
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b)
}

function contrastRatio(hexA: string, hexB: string): number {
  const [lighter, darker] = [relativeLuminance(hexA), relativeLuminance(hexB)].sort((a, b) => b - a)
  return (lighter + 0.05) / (darker + 0.05)
}

const inkTokens = {
  inkPrimary: colors.inkPrimary,
  inkSecondary: colors.inkSecondary,
  inkMuted: colors.inkMuted,
} as const

const surfaces = {
  navyBase: colors.navyBase,
  navyRaised: colors.navyRaised,
  navyOverlay: colors.navyOverlay,
} as const

describe('ink ramp contrast (issue #88)', () => {
  for (const [tokenName, tokenHex] of Object.entries(inkTokens)) {
    for (const [surfaceName, surfaceHex] of Object.entries(surfaces)) {
      it(`${tokenName} clears AA (4.5:1) on ${surfaceName}`, () => {
        expect(contrastRatio(tokenHex, surfaceHex)).toBeGreaterThanOrEqual(AA_MIN_CONTRAST)
      })
    }
  }

  it('keeps the three tiers strictly ordered by luminance (primary > secondary > muted)', () => {
    const primaryLum = relativeLuminance(inkTokens.inkPrimary)
    const secondaryLum = relativeLuminance(inkTokens.inkSecondary)
    const mutedLum = relativeLuminance(inkTokens.inkMuted)

    expect(primaryLum).toBeGreaterThan(secondaryLum)
    expect(secondaryLum).toBeGreaterThan(mutedLum)
  })
})
