import { useQuery } from '@tanstack/react-query'
import { analysisApi } from '@/api/analysis'

interface Props { experimentId: string }

/** Analysis tab: external analyses, XRD phases, and pXRF readings for an experiment. */
export function AnalysisTab({ experimentId }: Props) {
  const { data: xrd } = useQuery({
    queryKey: ['xrd', experimentId],
    queryFn: () => analysisApi.getXRD(experimentId),
  })
  const { data: external } = useQuery({
    queryKey: ['external-analysis', experimentId],
    queryFn: () => analysisApi.getExternal(experimentId),
  })

  const hasData = (xrd?.length ?? 0) + (external?.length ?? 0) > 0
  if (!hasData) return <p className="text-sm text-ink-muted p-4">No external analyses linked</p>

  return (
    <div className="p-4 space-y-3">
      {(xrd ?? []).map((x) => (
        <div key={x.id} className="text-xs border-b border-surface-border pb-2">
          <span className="font-semibold text-ink-secondary">XRD</span>
          <span className="text-ink-muted ml-2">{x.analysis_date ?? '—'} · {x.laboratory ?? '—'}</span>
        </div>
      ))}
      {(external ?? []).map((e) => (
        <div key={e.id} className="text-xs border-b border-surface-border pb-2">
          <span className="font-semibold text-ink-secondary">{e.analysis_type ?? 'Analysis'}</span>
          <span className="text-ink-muted ml-2">{e.analysis_date ?? '—'} · {e.laboratory ?? '—'}</span>
        </div>
      ))}
    </div>
  )
}
