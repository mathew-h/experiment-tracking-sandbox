import { useQuery } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'

interface Props { experimentId: string }

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function ChangeRequestsTab({ experimentId }: Props) {
  const { data: entries } = useQuery({
    queryKey: ['changeRequests', experimentId],
    queryFn: () => experimentsApi.getChangeRequests(experimentId),
  })

  if (!entries || entries.length === 0) {
    return <p className="text-sm text-ink-muted p-4">No change requests tracked for this experiment.</p>
  }

  return (
    <div className="p-4 space-y-3">
      {entries.map((entry) => (
        <div key={entry.id} className="border-b border-surface-border pb-3 last:border-b-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs text-ink-muted">{formatDate(entry.sync_date)}</span>
            <span className="text-xs font-mono-data text-ink-secondary">{entry.reactor_label}</span>
          </div>
          <p className="text-sm text-ink-primary">{entry.requested_change}</p>
        </div>
      ))}
    </div>
  )
}
