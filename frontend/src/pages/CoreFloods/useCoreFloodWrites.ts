import type { QueryClient } from '@tanstack/react-query'

/** Refreshes everything a core flood sample write can change: the run list and
 *  run page, each touched segment's experiment and results, and the lists that
 *  show reactor state. */
export async function invalidateCoreFloodWrites(
  qc: QueryClient,
  baseId: string,
  segmentIds: string[],
): Promise<void> {
  await Promise.all([
    qc.invalidateQueries({ queryKey: ['core-floods'] }),
    qc.invalidateQueries({ queryKey: ['core-flood', baseId] }),
    qc.invalidateQueries({ queryKey: ['core-flood-icp', baseId] }),
    ...segmentIds.flatMap((id) => [
      qc.invalidateQueries({ queryKey: ['experiment', id] }),
      qc.invalidateQueries({ queryKey: ['experiment-results', id] }),
    ]),
    qc.invalidateQueries({ queryKey: ['experiments'] }),
    qc.invalidateQueries({ queryKey: ['dashboard'] }),
  ])
}
