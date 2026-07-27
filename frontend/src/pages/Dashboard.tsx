import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '@/api/dashboard'
import type { GanttEntry, SlotOccupancy } from '@/api/dashboard'
import { MetricCard, Card, CardHeader, CardBody, PageSpinner, SlotBar } from '@/components/ui'
import type { SlotSegment } from '@/components/ui'
import { ReactorGrid } from './ReactorGrid'
import { ExperimentTimeline } from './ExperimentTimeline'
import { ActivityFeed } from './ActivityFeed'
import { DashboardFilters, type DashboardFilterState } from './DashboardFilters'

const R_FALLBACK = 16
const CF_FALLBACK = 3

function occupancySegments(o?: SlotOccupancy): SlotSegment[] {
  return [
    { count: o?.ongoing ?? 0, className: 'bg-status-ongoing', label: 'ongoing' },
    { count: o?.queued ?? 0, className: 'bg-status-queued', label: 'queued' },
  ]
}

function applyFilters(entries: GanttEntry[], f: DashboardFilterState): GanttEntry[] {
  return entries.filter((e) => {
    if (f.statuses.length > 0 && !f.statuses.includes(e.status)) return false
    if (f.types.length > 0 && (!e.experiment_type || !f.types.includes(e.experiment_type))) return false
    if (f.dateFrom && e.started_at && e.started_at.slice(0, 10) < f.dateFrom) return false
    if (f.dateTo && e.started_at && e.started_at.slice(0, 10) > f.dateTo) return false
    return true
  })
}

/** Main dashboard: KPI metrics, reactor grid, activity feed, and experiment timeline. */
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
          label="Reactor Occupancy"
          value={data?.summary.reactors.ongoing ?? '—'}
          unit={`/ ${data?.summary.reactors.total ?? R_FALLBACK} ongoing`}
          sub={
            data
              ? `${data.summary.reactors.queued} queued · ${data.summary.reactors.empty} empty`
              : undefined
          }
        >
          {data && <SlotBar total={data.summary.reactors.total} segments={occupancySegments(data.summary.reactors)} />}
        </MetricCard>

        <MetricCard
          label="GC Measurements"
          value={data?.summary.gc_measurements_7wd ?? '—'}
          sub={
            data
              ? `${data.summary.workday_window_start} – ${data.summary.workday_window_end} · across ${data.summary.gc_experiments_7wd} experiment${data.summary.gc_experiments_7wd === 1 ? '' : 's'}`
              : undefined
          }
          title={data ? `${data.summary.workday_window_start} – ${data.summary.workday_window_end}` : undefined}
        />

        <MetricCard
          label="Serum Vials Started"
          value={data?.summary.serum_vials_started_7wd ?? '—'}
          sub={
            data
              ? `${data.summary.workday_window_start} – ${data.summary.workday_window_end} · ${data.summary.serum_experiments_7wd} experiment${data.summary.serum_experiments_7wd === 1 ? '' : 's'}`
              : undefined
          }
          title={data ? `${data.summary.workday_window_start} – ${data.summary.workday_window_end}` : undefined}
        />

        <MetricCard
          label="Core Floods Ongoing"
          value={data?.summary.core_floods.ongoing ?? '—'}
          unit={`/ ${data?.summary.core_floods.total ?? CF_FALLBACK}`}
          sub={
            data
              ? `${data.summary.core_floods.queued} queued · ${data.summary.core_floods.empty} idle`
              : undefined
          }
        >
          {data && <SlotBar total={data.summary.core_floods.total} segments={occupancySegments(data.summary.core_floods)} />}
        </MetricCard>
      </div>

      {/* Reactor grid */}
      <Card padding="none">
        <CardHeader label="Reactor Status" />
        <CardBody>
          {isLoading && <PageSpinner />}
          {error && (
            <p className="text-sm text-red-400 py-4 text-center">Failed to load dashboard</p>
          )}
          {data && (
            <ReactorGrid
              cards={data.reactors}
              rSlotCount={data.summary.reactors.total}
              cfSlotCount={data.summary.core_floods.total}
            />
          )}
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
