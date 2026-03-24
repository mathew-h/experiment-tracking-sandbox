// frontend/src/pages/SampleDetail/ActivityTab.tsx
import { useQuery } from '@tanstack/react-query'
import { samplesApi } from '@/api/samples'
import { PageSpinner } from '@/components/ui'

interface Props { sampleId: string }

export function ActivityTab({ sampleId }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ['sample-activity', sampleId],
    queryFn: () => samplesApi.listActivity(sampleId),
  })

  if (isLoading) return <PageSpinner />

  return (
    <div className="space-y-2">
      {(!data || data.length === 0) ? (
        <p className="text-sm text-ink-muted text-center py-8">No activity recorded.</p>
      ) : (
        data.map((entry) => (
          <div key={entry.id} className="rounded-lg border border-surface-border bg-surface-raised p-3 flex items-start gap-3">
            <span className={`text-xs px-2 py-0.5 rounded font-medium ${
              entry.modification_type === 'create' ? 'bg-green-500/10 text-green-400' :
              entry.modification_type === 'delete' ? 'bg-red-500/10 text-red-400' :
              'bg-blue-500/10 text-blue-400'
            }`}>
              {entry.modification_type}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-ink-secondary">
                <span className="font-medium">{entry.modified_table}</span> · {entry.modified_by}
              </p>
              <p className="text-xs text-ink-muted mt-0.5">{new Date(entry.created_at).toLocaleString()}</p>
            </div>
          </div>
        ))
      )}
    </div>
  )
}
