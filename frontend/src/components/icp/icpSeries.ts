import type { IcpRow } from '@/api/icp'
import { chartColors } from '@/assets/brand'
import { ICP_ELEMENTS } from './icpElements'

// Issue #143: Cu is off by default; Mg, Mn and Al are on.
const PREFERRED = ['ca', 'si', 'fe', 'ni', 'mg', 'mn', 'al']

/** A vertical marker on the chart, e.g. where a chained segment starts. */
export type ChartMarker = { day: number; experimentId: string }

/** The fields of a sample that segmentStarts reads (a CoreFloodSample fits). */
type SegmentSample = Pick<IcpRow, 'experiment_id' | 'is_variant' | 'cumulative_time_post_reaction_days'>

export type IcpPoint = { day: number } & Record<string, number | null>

/** Elements with a value in any row, in ICP_ELEMENTS order. */
export function elementsPresent(rows: IcpRow[]): string[] {
  const seen = new Set(rows.flatMap((r) => Object.keys(r.elements)))
  return ICP_ELEMENTS.filter((e) => seen.has(e))
}

/** Ca/Si/Fe/Ni/Mg/Mn/Al when present; otherwise the first five present elements. */
export function defaultSelection(present: string[]): string[] {
  const preferred = present.filter((e) => PREFERRED.includes(e))
  return preferred.length > 0 ? preferred : present.slice(0, 5)
}

/** Main-line rows with a cumulative day, sorted by day. Log mode nulls values <= 0. */
export function chartPoints(rows: IcpRow[], selected: string[], log: boolean): IcpPoint[] {
  return rows
    .filter((r) => !r.is_variant && r.cumulative_time_post_reaction_days != null)
    .sort((a, b) => a.cumulative_time_post_reaction_days! - b.cumulative_time_post_reaction_days!)
    .map((r) => {
      const point: IcpPoint = { day: r.cumulative_time_post_reaction_days! }
      for (const el of selected) {
        const v = r.elements[el]
        point[el] = v == null || (log && v <= 0) ? null : v
      }
      return point
    })
}

/** Day of each non-variant segment's first sample (server view order), minus the first segment. */
export function segmentStarts(samples: SegmentSample[]): ChartMarker[] {
  const first = new Map<string, number>()
  for (const s of samples) {
    if (s.is_variant || first.has(s.experiment_id)) continue
    if (s.cumulative_time_post_reaction_days == null) continue
    first.set(s.experiment_id, s.cumulative_time_post_reaction_days)
  }
  return [...first]
    .map(([experimentId, day]) => ({ day, experimentId }))
    .sort((a, b) => a.day - b.day)
    .slice(1)
}

// chartColors.mean is reserved for aggregate/mean series, so ICP lines use the 4 series colours only.
const LINE_COLORS: readonly string[] = chartColors.series
const LINE_DASHES: ReadonlyArray<string | undefined> = [undefined, '6 3', '2 2', '8 3 2 3', '4 4', '10 4']

/** In log mode non-positive readings are nulls; bridging them would draw through below-detection gaps. */
export function lineProps(log: boolean): { connectNulls: boolean } {
  return { connectNulls: !log }
}

/** Colour per selected line by position (4 colours); from the 5th line on, a new dash pattern per colour cycle. 24 unique styles. */
export function lineStyles(
  selected: string[],
  colors: readonly string[] = LINE_COLORS,
): Record<string, { color: string; dash?: string }> {
  return Object.fromEntries(
    selected.map((el, i) => [
      el,
      {
        color: colors[i % colors.length],
        dash: LINE_DASHES[Math.floor(i / colors.length) % LINE_DASHES.length],
      },
    ]),
  )
}

/** Tooltip value: up to 3 decimals, trailing zeros dropped; em dash when missing. */
export function fmtPpm(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return parseFloat(v.toFixed(3)).toString()
}

export type MarkerLabel = { position: 'insideTopLeft' | 'insideTopRight'; dy: number }

/** Markers closer than this share of the x span stack their labels vertically. */
const STACK_FRACTION = 0.15
const STACK_DY = 14

/** Label placement per marker (in the given order, which is by day). A label
 *  reads away from the nearer edge: 'insideTopLeft' draws it right of the line
 *  (left half), 'insideTopRight' left of it (right half), so a marker at either
 *  end of the axis is never clipped. A marker close to the previous one drops
 *  one line, so same-day segment starts don't overprint. */
export function markerLabels(markers: ChartMarker[], dataDays: number[]): MarkerLabel[] {
  const days = [...dataDays, ...markers.map((m) => m.day)]
  if (days.length === 0) return []
  const lo = Math.min(...days)
  const hi = Math.max(...days)
  const mid = (lo + hi) / 2
  const near = (hi - lo) * STACK_FRACTION
  let level = 0
  return markers.map((m, i) => {
    level = i > 0 && m.day - markers[i - 1].day <= near ? 1 - level : 0
    return { position: m.day <= mid ? 'insideTopLeft' : 'insideTopRight', dy: level * STACK_DY }
  })
}
