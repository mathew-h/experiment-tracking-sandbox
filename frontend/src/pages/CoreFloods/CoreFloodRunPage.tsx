import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { coreFloodsApi, type CoreFloodSample, type CoreFloodSegment } from '@/api/coreFloods'
import { Badge, Button, Card, CardHeader, MetricCard, PageSpinner } from '@/components/ui'
import { CleanupPanel } from './CleanupPanel'
import { Collapsible } from './Collapsible'
import { CoreFloodSampleModal } from './CoreFloodSampleModal'
import { SamplesTable } from './SamplesTable'
import { SegmentsTable } from './SegmentsTable'
import { fmt } from './fields'

interface ApiError extends Error {
  response?: { status?: number }
}

const HEADING = 'text-xs font-semibold text-ink-secondary uppercase tracking-wider'

/** The root segment's description: non-variant, no parent, earliest date; else the first described segment. */
function runDescription(segments: CoreFloodSegment[]): string | null {
  const date = (s: CoreFloodSegment) => (s.date ? Date.parse(s.date) : Infinity)
  const roots = segments
    .filter((s) => !s.is_variant && s.parent_experiment_id == null)
    .sort((a, b) => date(a) - date(b))
  return roots[0]?.description ?? segments.find((s) => s.description)?.description ?? null
}

/** One core flood run: header metrics, segments, samples and side samples. */
export function CoreFloodRunPage() {
  const { baseId = '' } = useParams<{ baseId: string }>()
  const [modal, setModal] = useState<{ editing?: CoreFloodSample } | null>(null)
  const [renaming, setRenaming] = useState<string | null>(null)
  const [describing, setDescribing] = useState<string | null>(null)
  const [segmentsOpen, setSegmentsOpen] = useState(false)

  const { data: run, isLoading, error } = useQuery({
    queryKey: ['core-flood', baseId],
    queryFn: () => coreFloodsApi.get(baseId),
  })

  // An ICP failure only hides the expanders; it never breaks the run page.
  const { data: icpRows } = useQuery({
    queryKey: ['core-flood-icp', baseId],
    queryFn: () => coreFloodsApi.icp(baseId),
  })
  const icpByResult = useMemo(
    () => new Map<number, Record<string, number>>((icpRows ?? []).map((r) => [r.result_id, r.elements])),
    [icpRows],
  )

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
  // Same rule as the run list: the latest-dated segment's slot (undated lose, id breaks ties).
  const rig = run.segments.reduce<CoreFloodSegment | undefined>((best, s) => {
    if (!best) return s
    const [a, b] = [best, s].map((x) => (x.date ? Date.parse(x.date) : -Infinity))
    return b > a || (b === a && s.id > best.id) ? s : best
  }, undefined)?.reactor_slot
  const ongoing = run.segments
    .filter((s) => s.status?.toUpperCase() === 'ONGOING')
    .map((s) => s.experiment_id)

  const description = runDescription(run.segments)
  const onEdit = (s: CoreFloodSample) => setModal({ editing: s })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="text-xs text-ink-muted">
            <Link to="/core-floods" className="hover:text-ink-secondary">Core Floods</Link>
          </p>
          <h1 className="text-lg font-semibold text-ink-primary font-mono-data">{run.base_id}</h1>
          {description && <p className="text-sm text-ink-secondary max-w-prose">{description}</p>}
          <div className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            <span>Rig {rig ?? '—'}</span>
            {ongoing.length > 0 && <Badge variant="ongoing">Ongoing: {ongoing.join(', ')}</Badge>}
          </div>
        </div>
        <Button variant="primary" size="sm" onClick={() => setModal({})}>
          + Add sample
        </Button>
      </div>

      <section aria-labelledby="samples-heading">
        <Card padding="none">
          <CardHeader>
            <h2 id="samples-heading" className={HEADING}>Samples</h2>
          </CardHeader>
          <div className="p-4">
            <SamplesTable samples={main} variant={false} onEdit={onEdit} icpByResult={icpByResult} />
          </div>
        </Card>
      </section>

      {side.length > 0 && (
        <Collapsible
          title="Side samples"
          summary={`${side.length} (blanks, bypass)`}
        >
          <SamplesTable samples={side} variant onEdit={onEdit} icpByResult={icpByResult} />
        </Collapsible>
      )}

      {/* Task 7: "ICP over time" collapsible goes here. */}

      <Collapsible
        title="Segments"
        summary={`${run.segments.length} (${run.segments.map((s) => s.experiment_id).join(', ')})`}
        open={segmentsOpen}
        onOpenChange={setSegmentsOpen}
      >
        <SegmentsTable
          baseId={run.base_id}
          segments={run.segments}
          renaming={renaming}
          setRenaming={setRenaming}
          describing={describing}
          setDescribing={setDescribing}
        />
      </Collapsible>

      {run.warnings.length > 0 && (
        <Collapsible title="Data checks" summary={run.warnings.length}>
          <CleanupPanel
            baseId={run.base_id}
            run={run}
            onEditSample={onEdit}
            onRename={(id) => {
              setSegmentsOpen(true)
              setRenaming(id)
            }}
            onEditDescription={(id) => {
              setSegmentsOpen(true)
              setDescribing(id)
            }}
          />
        </Collapsible>
      )}

      <Collapsible
        title="Run totals"
        summary={`Cum. H₂ ${fmt(last?.cumulative_h2_grams_per_ton)} g/t · Pore volumes ${fmt(last?.cumulative_pore_volumes)}`}
      >
        <div className="grid grid-cols-2 gap-3 max-w-xl">
          <MetricCard
            label="Cumulative H₂ to date"
            value={fmt(last?.cumulative_h2_grams_per_ton)}
            unit="g/t"
          />
          <MetricCard label="Pore volumes to date" value={fmt(last?.cumulative_pore_volumes)} />
        </div>
      </Collapsible>

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
