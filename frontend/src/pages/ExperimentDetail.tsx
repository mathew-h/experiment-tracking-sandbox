import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { resultsApi } from '@/api/results'
import { Card, CardHeader, CardBody, StatusBadge, Button, PageSpinner, Badge } from '@/components/ui'

export function ExperimentDetailPage() {
  const { id } = useParams<{ id: string }>()

  const { data: experiment, isLoading, error } = useQuery({
    queryKey: ['experiment', id],
    queryFn: () => experimentsApi.get(id!),
    enabled: Boolean(id),
  })

  const { data: results } = useQuery({
    queryKey: ['results', id],
    queryFn: () => resultsApi.list(id!),
    enabled: Boolean(id),
  })

  if (isLoading) return <PageSpinner />
  if (error || !experiment) return <p className="text-red-400 text-sm p-6">Experiment not found</p>

  const conditions = experiment.conditions as Record<string, unknown> | null

  return (
    <div className="space-y-5">
      {/* Breadcrumb + header */}
      <div>
        <p className="text-xs text-ink-muted mb-1">
          <Link to="/experiments" className="hover:text-ink-secondary">Experiments</Link>
          <span className="mx-1.5">›</span>
          <span className="font-mono-data">{experiment.experiment_id}</span>
        </p>
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-ink-primary font-mono-data">{experiment.experiment_id}</h1>
          <StatusBadge status={experiment.status} />
        </div>
        <p className="text-xs text-ink-muted mt-0.5">
          #{experiment.experiment_number}
          {experiment.researcher && ` · ${experiment.researcher}`}
          {experiment.date && ` · ${experiment.date}`}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Conditions summary */}
        <Card className="lg:col-span-2" padding="none">
          <CardHeader label="Conditions">
            <Button variant="ghost" size="xs">Edit</Button>
          </CardHeader>
          <CardBody>
            {conditions ? (
              <div className="grid grid-cols-2 gap-x-6 gap-y-2">
                {[
                  ['Temperature', conditions.temperature_c, '°C'],
                  ['Initial pH', conditions.initial_ph, ''],
                  ['Rock Mass', conditions.rock_mass_g, 'g'],
                  ['Water Volume', conditions.water_volume_mL, 'mL'],
                  ['Reactor', conditions.reactor_number, ''],
                  ['Stir Speed', conditions.stir_speed_rpm, 'RPM'],
                  ['Type', conditions.experiment_type, ''],
                  ['Feedstock', conditions.feedstock, ''],
                ].map(([label, val, unit]) =>
                  val != null ? (
                    <div key={String(label)} className="flex items-baseline justify-between py-1 border-b border-surface-border/50">
                      <span className="text-xs text-ink-muted">{String(label)}</span>
                      <span className="text-xs font-mono-data text-ink-primary">
                        {String(val)}{unit ? ` ${String(unit)}` : ''}
                      </span>
                    </div>
                  ) : null
                )}
              </div>
            ) : (
              <p className="text-sm text-ink-muted">No conditions recorded</p>
            )}
          </CardBody>
        </Card>

        {/* Notes */}
        <Card padding="none">
          <CardHeader label="Notes" />
          <CardBody>
            {(experiment.notes as unknown[]).length === 0 ? (
              <p className="text-xs text-ink-muted">No notes</p>
            ) : (
              <div className="space-y-2">
                {(experiment.notes as Array<{ id: number; note_text: string; created_at: string }>).map((n) => (
                  <div key={n.id} className="text-xs text-ink-secondary border-b border-surface-border pb-2">
                    <p>{n.note_text}</p>
                    <p className="text-ink-muted mt-0.5 font-mono-data">
                      {new Date(n.created_at).toLocaleDateString()}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      {/* Results table */}
      <Card padding="none">
        <CardHeader label="Results">
          <Badge variant="default">{results?.length ?? 0} timepoints</Badge>
        </CardHeader>
        <CardBody>
          {results?.length === 0 && <p className="text-sm text-ink-muted text-center py-6">No results recorded</p>}
          {(results ?? []).map((r) => (
            <div key={r.id} className="flex items-center gap-4 py-2 border-b border-surface-border last:border-0">
              <span className="font-mono-data text-ink-primary text-sm w-16">
                T+{r.time_post_reaction_days ?? '?'}d
              </span>
              <span className="text-xs text-ink-secondary flex-1">{r.description}</span>
              {r.is_primary_timepoint_result && <Badge variant="info" dot>Primary</Badge>}
            </div>
          ))}
        </CardBody>
      </Card>
    </div>
  )
}
