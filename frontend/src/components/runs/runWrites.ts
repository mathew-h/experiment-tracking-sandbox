import type { QueryClient } from '@tanstack/react-query'

/** What a shared run component needs to know about the page it sits on: how to
 *  refresh after a write, and where a run lives (route and query key). Core Flood
 *  and HPHT each supply one. */
export interface RunWrites {
  /** Refreshes the run list, the run, and each touched segment's queries. */
  invalidate: (qc: QueryClient, baseId: string, segmentIds: string[]) => Promise<void>
  /** Route of a run page. */
  runPath: (baseId: string) => string
  /** Query key of a run's detail query (removed when the run disappears). */
  runQueryKey: (baseId: string) => unknown[]
}
