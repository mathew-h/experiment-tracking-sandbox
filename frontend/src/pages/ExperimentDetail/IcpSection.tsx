import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { IcpChart } from '@/components/icp/IcpChart'
import { Collapsible } from '@/components/runs/Collapsible'

interface Props { experimentId: string }

/** ICP over time for the experiment's whole series (issue #143); hidden when
 *  the series has no ICP readings. Shares IcpChart with the run pages and, like
 *  them, opens collapsed with the sample count in the header (issue #161). */
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
  const summary =
    `${data.rows.length} ${data.rows.length === 1 ? 'sample' : 'samples'} · ` +
    `${experiments} ${experiments === 1 ? 'experiment' : 'experiments'} in series`
  return (
    <div className="p-4 border-t border-surface-border">
      <Collapsible title="ICP over time" summary={summary}>
        <IcpChart rows={data.rows} markers={markers} />
      </Collapsible>
    </div>
  )
}
