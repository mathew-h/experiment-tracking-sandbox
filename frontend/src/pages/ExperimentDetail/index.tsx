import { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { conditionsApi } from '@/api/conditions'
import { StatusBadge, Button, PageSpinner } from '@/components/ui'
import { ConditionsTab } from './ConditionsTab'
import { ResultsTab } from './ResultsTab'
import { NotesTab } from './NotesTab'
import { ModificationsTab } from './ModificationsTab'
import { AnalysisTab } from './AnalysisTab'

const TABS = ['Conditions', 'Results', 'Notes', 'Analysis', 'Entry Logs'] as const
type Tab = typeof TABS[number]

/** Full experiment detail page with tabbed navigation (Results, Conditions, Analysis, Notes, Modifications). */
export function ExperimentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<Tab>('Conditions')

  const { data: experiment, isLoading, error } = useQuery({
    queryKey: ['experiment', id],
    queryFn: () => experimentsApi.get(id!),
    enabled: Boolean(id),
  })

  const { data: conditions } = useQuery({
    queryKey: ['conditions', id],
    queryFn: () => conditionsApi.getByExperiment(id!),
    enabled: Boolean(id),
    retry: false,
  })

  if (isLoading) return <PageSpinner />
  if (error || !experiment) return <p className="text-red-400 text-sm p-6">Experiment not found</p>

  return (
    <div className="space-y-4">
      {/* Breadcrumb */}
      <div>
        <p className="text-xs text-ink-muted mb-1">
          <Link to="/experiments" className="hover:text-ink-secondary">Experiments</Link>
          <span className="mx-1.5">›</span>
          <span className="font-mono-data">{experiment.experiment_id}</span>
        </p>
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-ink-primary font-mono-data">{experiment.experiment_id}</h1>
          <StatusBadge status={experiment.status} />
          {conditions?.experiment_type && (
            <span className="text-xs text-ink-muted">{conditions.experiment_type}</span>
          )}
        </div>
        <p className="text-xs text-ink-muted mt-0.5">
          #{experiment.experiment_number}
          {experiment.researcher && ` · ${experiment.researcher}`}
          {experiment.date && ` · ${experiment.date.slice(0, 10)}`}
          {experiment.sample_id && ` · Sample: ${experiment.sample_id}`}
          {conditions?.reactor_number != null && ` · Reactor ${conditions.reactor_number}`}
        </p>
      </div>

      {/* Quick actions */}
      <div className="flex gap-2">
        <Button variant="ghost" size="sm" onClick={() => navigate('/experiments/new')}>
          + New Experiment
        </Button>
      </div>

      {/* Tab bar */}
      <div className="border-b border-surface-border flex gap-0">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm border-b-2 transition-colors ${
              activeTab === tab
                ? 'border-brand-red text-ink-primary'
                : 'border-transparent text-ink-muted hover:text-ink-secondary'
            }`}
          >
            {tab}
            {tab === 'Notes' && experiment.notes.length > 0 && (
              <span className="ml-1.5 text-[10px] bg-surface-raised rounded px-1">{experiment.notes.length}</span>
            )}
            {tab === 'Entry Logs' && experiment.modifications.length > 0 && (
              <span className="ml-1.5 text-[10px] bg-surface-raised rounded px-1">{experiment.modifications.length}</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="bg-surface-card border border-surface-border rounded-lg overflow-hidden">
        {activeTab === 'Conditions' && (
          <ConditionsTab conditions={conditions ?? null} experimentId={id!} experimentFk={experiment.id} />
        )}
        {activeTab === 'Results' && <ResultsTab experimentId={id!} experimentFk={experiment.id} />}
        {activeTab === 'Notes' && (
          <NotesTab experimentId={id!} notes={experiment.notes} />
        )}
        {activeTab === 'Entry Logs' && (
          <ModificationsTab modifications={experiment.modifications} />
        )}
        {activeTab === 'Analysis' && <AnalysisTab experimentId={id!} />}
      </div>
    </div>
  )
}
