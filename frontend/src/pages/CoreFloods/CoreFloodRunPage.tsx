import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { coreFloodsApi, type CoreFloodSample } from '@/api/coreFloods'
import { Badge, Breadcrumb, Button, Card, CardHeader, MetricCard, PageSpinner } from '@/components/ui'
import { ExportAllButton } from '@/components/experiments/ExportAllButton'
import { CleanupPanel } from './CleanupPanel'
import { Collapsible } from '@/components/runs/Collapsible'
import { RunNotFound, SegmentIdList, useCanonicalRunUrl } from '@/components/runs/runPageNav'
import { CORE_FLOOD_WRITES } from './useCoreFloodWrites'
import { latestSegment, ongoingIds, rootSegments, runDescription } from '@/components/runs/runSegments'
import { CoreFloodSampleModal } from './CoreFloodSampleModal'
import { RunSamplesTable } from '@/components/results/RunSamplesTable'
import { fromCoreFlood } from '@/components/results/sampleRows'
import { SegmentsTable } from './SegmentsTable'
import { fmt } from './fields'
import { IcpChart } from '@/components/icp/IcpChart'
import { segmentStarts } from '@/components/icp/icpSeries'

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
  // null until the user toggles it: then a run with several segments opens with
  // the table showing (issue #158).
  const [segmentsOpen, setSegmentsOpen] = useState<boolean | null>(null)

  const { data: run, isLoading, error } = useQuery({
    queryKey: CORE_FLOOD_WRITES.runQueryKey(baseId),
    queryFn: () => coreFloodsApi.get(baseId),
  })
  useCanonicalRunUrl(baseId, run, CORE_FLOOD_WRITES)

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
      return <RunNotFound kind="core flood" requestedId={baseId} writes={CORE_FLOOD_WRITES} listLabel="Core Floods" />
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
  const rig = latestSegment(run.segments)?.reactor_slot
  const ongoing = ongoingIds(run.segments)

  const description = runDescription(run.segments)
  // The export covers the whole lineage from any segment; send the root's ID.
  const exportId = (rootSegments(run.segments)[0] ?? run.segments[0])?.experiment_id
  const onEdit = (s: CoreFloodSample) => setModal({ editing: s })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <Breadcrumb items={[{ label: 'Core Floods', to: '/core-floods' }, { label: run.base_id, mono: true }]} />
          <h1 className="text-lg font-semibold text-ink-primary font-mono-data">{run.base_id}</h1>
          {description && <p className="text-sm text-ink-secondary max-w-prose">{description}</p>}
          <div className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            <span>Rig {rig ?? '—'}</span>
            {ongoing.length > 0 && (
              <Badge variant="ongoing">
                Ongoing: <SegmentIdList ids={ongoing} inherit />
              </Badge>
            )}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {exportId && <ExportAllButton experimentId={exportId} />}
          <Button variant="primary" size="sm" onClick={() => setModal({})}>
            + Add sample
          </Button>
        </div>
      </div>

      <section aria-labelledby="samples-heading">
        <Card padding="none">
          <CardHeader>
            <h2 id="samples-heading" className={HEADING}>Samples</h2>
          </CardHeader>
          <div className="p-4">
            {/* Issue #163: newest first (the server sends oldest first). */}
            <RunSamplesTable
              rows={[...main].reverse().map(fromCoreFlood)}
              scope="run"
              kind="core-flood"
              onEdit={onEdit}
              icpByResult={icpByResult}
            />
          </div>
        </Card>
      </section>

      {side.length > 0 && (
        <Collapsible
          title="Side samples"
          summary={`${side.length} (blanks, bypass)`}
        >
          <RunSamplesTable
            rows={[...side].reverse().map(fromCoreFlood)}
            scope="run"
            kind="core-flood"
            variant
            onEdit={onEdit}
            icpByResult={icpByResult}
          />
        </Collapsible>
      )}

      {icpRows && icpRows.length > 0 && (
        <Collapsible
          title="ICP over time"
          summary={`${icpRows.length} ${icpRows.length === 1 ? 'sample' : 'samples'}`}
        >
          <IcpChart rows={icpRows} markers={segmentStarts(run.samples)} />
        </Collapsible>
      )}

      <Collapsible
        title="Segments"
        summary={run.segments.length}
        links={<>(<SegmentIdList ids={run.segments.map((s) => s.experiment_id)} />)</>}
        open={segmentsOpen ?? run.segments.length > 1}
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
