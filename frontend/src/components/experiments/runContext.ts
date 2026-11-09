import type { QueryClient } from '@tanstack/react-query'
import { hphtApi } from '@/api/hpht'
import { coreFloodsApi } from '@/api/coreFloods'
import type { RunSegment } from '@/api/runs'
import type { RunWrites } from '@/components/runs/runWrites'
import { HPHT_WRITES } from '@/pages/Hpht/hphtWrites'
import { CORE_FLOOD_WRITES } from '@/pages/CoreFloods/useCoreFloodWrites'
import { runListPathFor } from '@/utils/experimentId'

/** How the detail page reads and refreshes the run an experiment belongs to. */
export interface RunKind {
  writes: RunWrites
  fetch: (baseId: string) => Promise<{ segments: RunSegment[] }>
}

/** The run kind for an experiment type (HPHT or Core Flood), or null for types
 *  without a run page. Uses the run page's own fetch and query key, so the
 *  detail page and the run page share one cache entry (issue #156). */
export function runKindFor(experimentType: unknown): RunKind | null {
  switch (runListPathFor(experimentType)) {
    case '/hpht':
      return { writes: HPHT_WRITES, fetch: hphtApi.get }
    case '/core-floods':
      return { writes: CORE_FLOOD_WRITES, fetch: coreFloodsApi.get }
    default:
      return null
  }
}

/** Segments in strip order: the API's run order, each segment followed by its
 *  `_Text` variants; anything left over (a variant whose parent is not in the
 *  run) goes last, so no segment is dropped. */
export function stripOrder(segments: RunSegment[]): RunSegment[] {
  const variantsOf = new Map<string, RunSegment[]>()
  for (const s of segments) {
    if (s.is_variant && s.parent_experiment_id) {
      variantsOf.set(s.parent_experiment_id, [...(variantsOf.get(s.parent_experiment_id) ?? []), s])
    }
  }
  const ordered: RunSegment[] = []
  const placed = new Set<string>()
  const visit = (s: RunSegment) => {
    if (placed.has(s.experiment_id)) return
    placed.add(s.experiment_id)
    ordered.push(s)
    for (const v of variantsOf.get(s.experiment_id) ?? []) visit(v)
  }
  for (const s of segments) if (!s.is_variant) visit(s)
  for (const s of segments) visit(s)
  return ordered
}

/** Refreshes what a status change on the detail page can affect: the experiment,
 *  the list, the dashboard's reactor cards, and, for a run segment, the run page
 *  through its own `RunWrites.invalidate`. */
export function invalidateStatusChange(
  qc: QueryClient,
  experimentId: string,
  baseId: string | null,
  experimentType: unknown,
): Promise<unknown> {
  const kind = runKindFor(experimentType)
  return Promise.all([
    qc.invalidateQueries({ queryKey: ['experiment', experimentId] }),
    qc.invalidateQueries({ queryKey: ['experiments'] }),
    qc.invalidateQueries({ queryKey: ['dashboard'] }),
    kind && baseId ? kind.writes.invalidate(qc, baseId, [experimentId]) : undefined,
  ])
}

/** True when an experiment belongs to a replicate set: it has a letter, the
 *  letter-only group lists members, or (issue #101) its stem holds more than
 *  one vial. ">1" so a lone '-t' vial does not link to a group of one. */
export function isInReplicateSet(
  replicateLabel: string | null,
  replicateMemberCount: number | undefined,
  groupMemberCount: number | undefined,
): boolean {
  return replicateLabel !== null || (replicateMemberCount ?? 0) > 0 || (groupMemberCount ?? 0) > 1
}
