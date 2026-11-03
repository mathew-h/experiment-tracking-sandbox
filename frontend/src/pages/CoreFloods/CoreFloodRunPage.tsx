import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { coreFloodsApi, type CoreFloodSample } from '@/api/coreFloods'
import { Button, Card, CardHeader, MetricCard, PageSpinner } from '@/components/ui'
import { CleanupPanel } from './CleanupPanel'
import { CoreFloodSampleModal } from './CoreFloodSampleModal'
import { SamplesTable } from './SamplesTable'
import { SegmentsTable } from './SegmentsTable'
import { fmt } from './fields'

interface ApiError extends Error {
  response?: { status?: number }
}

const HEADING = 'text-xs font-semibold text-ink-secondary uppercase tracking-wider'

/** One core flood run: header metrics, segments, samples and side samples. */
export function CoreFloodRunPage() {
  const { baseId = '' } = useParams<{ baseId: string }>()
  const [modal, setModal] = useState<{ editing?: CoreFloodSample } | null>(null)
  const [renaming, setRenaming] = useState<string | null>(null)
  const [describing, setDescribing] = useState<string | null>(null)

  const { data: run, isLoading, error } = useQuery({
    queryKey: ['core-flood', baseId],
    queryFn: () => coreFloodsApi.get(baseId),
  })

  if (isLoading) return <PageSpinner />
  if (error) {
    if ((error as ApiError).response?.status === 404) {
      return (
        <div className="space-y-2 py-4">
          <p className="text-sm text-ink-primary">No core flood run {baseId}</p>
          <Link to="/core-floods" className="text-sm text-red-400 hover:text-red-300">
            Back to Core Floods
          </Link>
        </div>
      )
    }
    return (
      <p className="text-sm text-red-400 py-4">
        Failed to load core flood: {(error as Error).message}
      </p>
    )
  }
  if (!run) return null

  const main = run.samples.filter((s) => !s.is_variant)
  const side = run.samples.filter((s) => s.is_variant)
  const last = main.at(-1)
  const rig = run.segments.filter((s) => s.reactor_slot).at(-1)?.reactor_slot
  const ongoing = run.segments
    .filter((s) => s.status?.toUpperCase() === 'ONGOING')
    .map((s) => s.experiment_id)

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-ink-primary font-mono-data">{run.base_id}</h1>
        <p className="text-xs text-ink-muted mt-0.5">
          <Link to="/core-floods" className="hover:text-ink-secondary">Core Floods</Link>
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard label="Rig" value={rig ?? '—'} />
        <MetricCard label="Ongoing" value={ongoing.length ? ongoing.join(', ') : 'None'} />
        <MetricCard
          label="Cumulative H₂ to date"
          value={fmt(last?.cumulative_h2_grams_per_ton)}
          unit="g/t"
        />
        <MetricCard label="Pore volumes to date" value={fmt(last?.cumulative_pore_volumes)} />
      </div>

      <CleanupPanel
        baseId={run.base_id}
        run={run}
        onEditSample={(s) => setModal({ editing: s })}
        onRename={setRenaming}
        onEditDescription={setDescribing}
      />

      <section aria-labelledby="segments-heading">
        <Card padding="none">
          <CardHeader>
            <h2 id="segments-heading" className={HEADING}>Segments</h2>
          </CardHeader>
          <div className="p-4">
            <SegmentsTable
              baseId={run.base_id}
              segments={run.segments}
              renaming={renaming}
              setRenaming={setRenaming}
              describing={describing}
              setDescribing={setDescribing}
            />
          </div>
        </Card>
      </section>

      <section aria-labelledby="samples-heading">
        <Card padding="none">
          <CardHeader>
            <h2 id="samples-heading" className={HEADING}>Samples</h2>
            <Button variant="primary" size="sm" onClick={() => setModal({})}>
              + Add sample
            </Button>
          </CardHeader>
          <div className="p-4">
            <SamplesTable
              samples={main}
              variant={false}
              onEdit={(s) => setModal({ editing: s })}
            />
          </div>
        </Card>
      </section>

      {side.length > 0 && (
        <section aria-labelledby="side-samples-heading">
          <Card padding="none">
            <CardHeader>
              <h2 id="side-samples-heading" className={HEADING}>
                Side samples (blanks, bypass)
              </h2>
            </CardHeader>
            <div className="p-4">
              <SamplesTable
                samples={side}
                variant
                onEdit={(s) => setModal({ editing: s })}
              />
            </div>
          </Card>
        </section>
      )}

      <CoreFloodSampleModal
        open={modal !== null}
        onClose={() => setModal(null)}
        baseId={run.base_id}
        segments={run.segments}
        samples={run.samples}
        editing={modal?.editing}
      />
    </div>
  )
}
