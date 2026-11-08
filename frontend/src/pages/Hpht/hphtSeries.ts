import type { HphtSample } from '@/api/hpht'
import { segmentStarts, type ChartMarker } from '@/components/icp/icpSeries'

/** One point of the run charts. NULL stays NULL so Recharts draws a gap,
 *  never a dip to zero. */
export interface HphtPoint {
  day: number
  /** Cumulative H₂ to date (g/t). */
  cumH2: number | null
  /** H₂ per day over the interval since the previous sample (g/t/day). */
  rate: number | null
  /** Cumulative Fe²⁺ → H₂ yield to date (%). */
  cumFe: number | null
}

/** Main-line samples (variants excluded) that have a cumulative day, in day order. */
export function chartPoints(samples: HphtSample[]): HphtPoint[] {
  return samples
    .filter((s) => !s.is_variant && s.cumulative_time_post_reaction_days != null)
    .sort(
      (a, b) =>
        a.cumulative_time_post_reaction_days! - b.cumulative_time_post_reaction_days! ||
        a.result_id - b.result_id,
    )
    .map((s) => ({
      day: s.cumulative_time_post_reaction_days!,
      cumH2: s.cumulative_h2_grams_per_ton,
      rate: s.h2_grams_per_ton_per_day,
      cumFe: s.cumulative_ferrous_iron_yield_h2_pct,
    }))
}

/** True when any main-line sample has an H₂ yield; otherwise the charts show an empty state. */
export function hasH2(samples: HphtSample[]): boolean {
  return samples.some((s) => !s.is_variant && s.h2_grams_per_ton_yield != null)
}

/** Dashed segment-start lines: the first sample of each non-variant segment
 *  after the first (the same rule as the run ICP chart). */
export function chartMarkers(samples: HphtSample[]): ChartMarker[] {
  return segmentStarts(samples)
}
