import type { CoreFloodIcpRow, CoreFloodSample } from '@/api/coreFloods'
import { chartColors } from '@/assets/brand'
import { ICP_ELEMENTS } from './icpElements'

const PREFERRED = ['ca', 'si', 'fe', 'cu', 'ni']

export type IcpPoint = { day: number } & Record<string, number | null>

/** Elements with a value in any row, in ICP_ELEMENTS order. */
export function elementsPresent(rows: CoreFloodIcpRow[]): string[] {
  const seen = new Set(rows.flatMap((r) => Object.keys(r.elements)))
  return ICP_ELEMENTS.filter((e) => seen.has(e))
}

/** Ca/Si/Fe/Cu/Ni when present; otherwise the first five present elements. */
export function defaultSelection(present: string[]): string[] {
  const preferred = present.filter((e) => PREFERRED.includes(e))
  return preferred.length > 0 ? preferred : present.slice(0, 5)
}

/** Main-line rows with a cumulative day, sorted by day. Log mode nulls values <= 0. */
export function chartPoints(rows: CoreFloodIcpRow[], selected: string[], log: boolean): IcpPoint[] {
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
export function segmentStarts(samples: CoreFloodSample[]): Array<{ day: number; experimentId: string }> {
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

const LINE_COLORS: readonly string[] = [...chartColors.series, chartColors.mean]
const LINE_DASHES: ReadonlyArray<string | undefined> = [undefined, '6 3', '2 2', '8 3 2 3']

/** In log mode non-positive readings are nulls; bridging them would draw through below-detection gaps. */
export function lineProps(log: boolean): { connectNulls: boolean } {
  return { connectNulls: !log }
}

/** Colour per selected line by position; from the 6th line on, a new dash pattern per colour cycle. */
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
