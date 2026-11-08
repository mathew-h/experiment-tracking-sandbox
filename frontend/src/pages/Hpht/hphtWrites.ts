import type { QueryClient } from '@tanstack/react-query'
import type { RunWrites } from '@/components/runs/runWrites'

/** Refreshes everything an HPHT run write can change: the run list, the run
 *  and its ICP, each touched segment's experiment and results, and the
 *  dashboard (reactor cards). */
export async function invalidateHphtWrites(
  qc: QueryClient,
  baseId: string,
  segmentIds: string[],
): Promise<void> {
  await Promise.all([
    qc.invalidateQueries({ queryKey: ['hpht-runs'] }),
    qc.invalidateQueries({ queryKey: ['hpht-run', baseId] }),
    qc.invalidateQueries({ queryKey: ['hpht-icp', baseId] }),
    ...segmentIds.flatMap((id) => [
      qc.invalidateQueries({ queryKey: ['experiment', id] }),
      qc.invalidateQueries({ queryKey: ['experiment-results', id] }),
    ]),
    qc.invalidateQueries({ queryKey: ['experiments'] }),
    qc.invalidateQueries({ queryKey: ['dashboard'] }),
  ])
}

export const hphtRunPath = (baseId: string) => `/hpht/${encodeURIComponent(baseId)}`

/** The HPHT run page, for the shared run components. */
export const HPHT_WRITES: RunWrites = {
  invalidate: invalidateHphtWrites,
  runPath: hphtRunPath,
  runQueryKey: (baseId) => ['hpht-run', baseId],
}
