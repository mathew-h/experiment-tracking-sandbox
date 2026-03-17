import { useQuery } from '@tanstack/react-query'
import { dashboardApi, ReactorStatus } from '@/api/dashboard'
import { MetricCard, Card, CardHeader, CardBody, PageSpinner } from '@/components/ui'

function ReactorCard({ reactor }: { reactor: ReactorStatus }) {
  const occupied = Boolean(reactor.experiment_id)
  return (
    <Card className="hover:border-ink-muted transition-colors duration-150">
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="text-2xs text-ink-muted uppercase tracking-wider font-medium mb-0.5">Reactor</p>
          <p className="text-xl font-bold text-ink-primary font-mono-data leading-none">
            {String(reactor.reactor_number).padStart(2, '0')}
          </p>
        </div>
        <span className={[
          'inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-2xs font-semibold uppercase tracking-wider border',
          occupied
            ? 'text-status-ongoing bg-status-ongoing/10 border-status-ongoing/20'
            : 'text-ink-muted bg-surface-overlay border-surface-border',
        ].join(' ')}>
          <span className={['w-1.5 h-1.5 rounded-full', occupied ? 'bg-status-ongoing animate-pulse-slow' : 'bg-surface-border'].join(' ')} />
          {occupied ? 'Active' : 'Empty'}
        </span>
      </div>

      {occupied ? (
        <div className="space-y-1.5">
          <p className="text-sm font-medium text-ink-primary font-mono-data">{reactor.experiment_id}</p>
          {reactor.researcher && <p className="text-xs text-ink-secondary">{reactor.researcher}</p>}
          {reactor.experiment_type && (
            <p className="text-xs text-ink-muted">{reactor.experiment_type}</p>
          )}
          <div className="flex items-center gap-3 pt-1">
            {reactor.temperature_c != null && (
              <span className="text-xs text-ink-muted">
                <span className="font-mono-data text-ink-secondary">{reactor.temperature_c}</span> °C
              </span>
            )}
            {reactor.days_running != null && (
              <span className="text-xs text-ink-muted">
                Day <span className="font-mono-data text-ink-secondary">{reactor.days_running}</span>
              </span>
            )}
          </div>
        </div>
      ) : (
        <p className="text-xs text-ink-muted">No active experiment</p>
      )}
    </Card>
  )
}

export function DashboardPage() {
  const { data: reactors, isLoading, error } = useQuery({
    queryKey: ['reactor-status'],
    queryFn: dashboardApi.reactorStatus,
    refetchInterval: 60_000,
  })

  const activeCount = reactors?.filter((r) => r.experiment_id).length ?? 0
  const totalCount  = reactors?.length ?? 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-ink-primary">Dashboard</h1>
        <p className="text-xs text-ink-muted mt-0.5">Reactor status and lab overview</p>
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard label="Active Reactors" value={activeCount} unit={`/ ${totalCount}`} />
        <MetricCard label="Capacity" value={totalCount > 0 ? Math.round((activeCount / totalCount) * 100) : 0} unit="%" />
        <MetricCard label="Total Reactors" value={totalCount} />
        <MetricCard label="Available" value={totalCount - activeCount} />
      </div>

      {/* Reactor grid */}
      <Card padding="none">
        <CardHeader label="Reactor Status">
          <span className="text-2xs text-ink-muted">Auto-refreshes every 60s</span>
        </CardHeader>
        <CardBody>
          {isLoading && <PageSpinner />}
          {error && (
            <div className="text-sm text-red-400 py-4 text-center">
              Failed to load reactor status
            </div>
          )}
          {reactors && (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3">
              {reactors.map((r) => (
                <ReactorCard key={r.reactor_number} reactor={r} />
              ))}
            </div>
          )}
          {reactors?.length === 0 && (
            <p className="text-sm text-ink-muted text-center py-8">No reactors found</p>
          )}
        </CardBody>
      </Card>

      {/* Recent experiments placeholder */}
      <Card padding="none">
        <CardHeader label="Recent Experiments" />
        <CardBody>
          <p className="text-sm text-ink-muted text-center py-8">
            Full experiment list available in <a href="/experiments" className="text-red-400 hover:text-red-300">Experiments</a>
          </p>
        </CardBody>
      </Card>
    </div>
  )
}

