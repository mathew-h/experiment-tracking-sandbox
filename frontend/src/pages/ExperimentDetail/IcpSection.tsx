import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { IcpChart } from '@/components/icp/IcpChart'

interface Props { experimentId: string }

/** ICP over time for the experiment's whole series (issue #143); hidden when
 *  the series has no ICP readings. Shares IcpChart with the core flood run page. */
export function IcpSection({ experimentId }: Props) {
  const { data } = useQuery({
    queryKey: ['experiment-icp', experimentId],
    queryFn: () => experimentsApi.getIcp(experimentId),
  })
  const markers = useMemo(
    () => (data?.segment_starts ?? []).map((s) => ({ day: s.day, experimentId: s.experiment_id })),
    [data],
  )
  if (!data || data.rows.length === 0) return null

  const experiments = new Set(data.rows.map((r) => r.experiment_id)).size
  return (
    <section className="p-4 border-t border-surface-border space-y-3">
      <div className="flex items-baseline gap-3">
        <h3 className="text-xs font-semibold text-ink-secondary uppercase tracking-wider">ICP over time</h3>
        <span className="text-xs text-ink-muted">
          {data.rows.length} {data.rows.length === 1 ? 'sample' : 'samples'} · {experiments}{' '}
          {experiments === 1 ? 'experiment' : 'experiments'} in series
        </span>
      </div>
      <IcpChart rows={data.rows} markers={markers} />
    </section>
  )
}
