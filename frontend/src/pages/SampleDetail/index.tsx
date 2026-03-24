// frontend/src/pages/SampleDetail/index.tsx
import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { samplesApi } from '@/api/samples'
import { PageSpinner } from '@/components/ui'
import { OverviewTab } from './OverviewTab'
import { PhotosTab } from './PhotosTab'
import { AnalysesTab } from './AnalysesTab'
import { ActivityTab } from './ActivityTab'

type Tab = 'overview' | 'photos' | 'analyses' | 'activity'

export function SampleDetailPage() {
  const { sampleId } = useParams<{ sampleId: string }>()
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('overview')

  const { data: sample, isLoading, error } = useQuery({
    queryKey: ['sample', sampleId],
    queryFn: () => samplesApi.get(sampleId!),
    enabled: Boolean(sampleId),
  })

  if (isLoading) return <PageSpinner />
  if (error || !sample) return (
    <div className="text-sm text-ink-muted p-8 text-center">
      Sample not found. <button onClick={() => navigate('/samples')} className="text-brand-red underline">Back to inventory</button>
    </div>
  )

  const TABS: { id: Tab; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'photos', label: `Photos (${sample.photos.length})` },
    { id: 'analyses', label: `Analyses (${sample.analyses.length})` },
    { id: 'activity', label: 'Activity' },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/samples')} className="text-ink-muted hover:text-ink-primary text-sm">
          ← Samples
        </button>
        <h1 className="text-lg font-semibold font-mono-data text-ink-primary">{sample.sample_id}</h1>
        {sample.rock_classification && (
          <span className="text-sm text-ink-muted">{sample.rock_classification}</span>
        )}
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-surface-border">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
              tab === t.id
                ? 'border-brand-red text-ink-primary'
                : 'border-transparent text-ink-muted hover:text-ink-primary'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && <OverviewTab sample={sample} />}
      {tab === 'photos' && <PhotosTab sample={sample} />}
      {tab === 'analyses' && <AnalysesTab sample={sample} />}
      {tab === 'activity' && <ActivityTab sampleId={sample.sample_id} />}
    </div>
  )
}
