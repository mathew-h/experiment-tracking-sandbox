import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '@/api/dashboard'
import type { GanttEntry } from '@/api/dashboard'
import { MetricCard, Card, CardHeader, CardBody, PageSpinner } from '@/components/ui'
import { ReactorGrid } from './ReactorGrid'
import { ExperimentTimeline } from './ExperimentTimeline'
import { ActivityFeed } from './ActivityFeed'
import { DashboardFilters, type DashboardFilterState } from './DashboardFilters'

function applyFilters(entries: GanttEntry[], f: DashboardFilterState): GanttEntry[] {
  return entries.filter((e) => {
    if (f.statuses.length > 0 && !f.statuses.includes(e.status)) return false
    if (f.types.length > 0 && (!e.experiment_type || !f.types.includes(e.experiment_type))) return false
    if (f.dateFrom && e.started_at && e.started_at.slice(0, 10) < f.dateFrom) return false
    if (f.dateTo && e.started_at && e.started_at.slice(0, 10) > f.dateTo) return false
    return true
  })
}

export function DashboardPage() {
  const [filters, setFilters] = useState<DashboardFilterState>({
    statuses: [],
    types: [],
    dateFrom: '',
    dateTo: '',
  })

  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: dashboardApi.full,
    refetchInterval: 60_000,
  })

  const filteredTimeline = data ? applyFilters(data.timeline, filters) : []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold text-ink-primary">Dashboard</h1>
          <p className="text-xs text-ink-muted mt-0.5">
            Reactor status and lab overview · Auto-refreshes every 60s
          </p>
        </div>
      </div>

      {/* Summary metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard
          label="Active Experiments"
          value={data?.summary.active_experiments ?? '—'}
        />
        <MetricCard
          label="Reactors In Use"
          value={data?.summary.reactors_in_use ?? '—'}
          unit="/ 18"
        />
        <MetricCard
          label="Completed This Month"
          value={data?.summary.completed_this_month ?? '—'}
        />
        <MetricCard
          label="Pending Results"
          value={data?.summary.pending_results ?? '—'}
        />
      </div>

      {/* Reactor grid */}
      <Card padding="none">
        <CardHeader label="Reactor Status" />
        <CardBody>
          {isLoading && <PageSpinner />}
          {error && (
            <p className="text-sm text-red-400 py-4 text-center">Failed to load dashboard</p>
          )}
          {data && <ReactorGrid cards={data.reactors} />}
        </CardBody>
      </Card>

      {/* Filters (apply to timeline) */}
      <DashboardFilters filters={filters} onChange={setFilters} />

      {/* Gantt timeline */}
      <Card padding="none">
        <CardHeader label="Experiment Timeline">
          <span className="text-2xs text-ink-muted">
            {filteredTimeline.length} experiment{filteredTimeline.length !== 1 ? 's' : ''}
            {(filters.statuses.length > 0 || filters.types.length > 0 || filters.dateFrom || filters.dateTo) && (
              <span className="ml-1 text-brand-red">(filtered)</span>
            )}
          </span>
        </CardHeader>
        <CardBody>
          {isLoading && <PageSpinner />}
          {data && <ExperimentTimeline entries={filteredTimeline} />}
        </CardBody>
      </Card>

      {/* Recent activity */}
      <Card padding="none">
        <CardHeader label="Recent Activity">
          <span className="text-2xs text-ink-muted">Last 20 changes</span>
        </CardHeader>
        <CardBody>
          {isLoading && <PageSpinner />}
          {data && <ActivityFeed entries={data.recent_activity} />}
        </CardBody>
      </Card>
    </div>
  )
}
