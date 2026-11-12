import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { experimentsApi, type ResultWithFlags } from '@/api/experiments'
import { resultsApi } from '@/api/results'
import { Button, Num, PageSpinner, Spinner } from '@/components/ui'
import { RunSamplesTable, type SampleKind } from '@/components/results/RunSamplesTable'
import { fromResult, type SampleRow } from '@/components/results/sampleRows'
import { ResultEntryModal } from './ResultEntryModal'
import { isCoreFloodType, isHphtType, runPathFor } from '@/utils/experimentId'
import { GroupedResultsView } from './GroupedResultsView'
import { IcpSection } from './IcpSection'

/** DETAILS extras on the Results tab: scalar values that are not table columns.
 *  Loaded when the section opens (the list payload does not carry them). */
function ScalarExtras({ resultId }: { resultId: number }) {
  const { data: scalar, isLoading } = useQuery({
    queryKey: ['scalar', resultId],
    queryFn: () => resultsApi.getScalar(resultId),
  })
  if (isLoading) return <Spinner size="sm" />
  if (!scalar) return null
  const values = ([
    ['DO', scalar.final_dissolved_oxygen_mg_L, 'mg/L'],
    ['Fe(II)', scalar.ferrous_iron_yield, ''],
  ] as const).filter(([, v]) => v != null)
  if (values.length === 0) return null
  return (
    <div>
      <p className="text-xs font-semibold text-ink-secondary mb-1">Scalar Results</p>
      <div className="grid grid-cols-4 gap-x-4 gap-y-1">
        {values.map(([label, v, unit]) => (
          <div key={label} className="text-xs">
            <span className="text-ink-muted">{label}: </span>
            <span className="font-mono-data text-ink-primary"><Num value={v} />{unit ? ` ${unit}` : ''}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** The experiment kind for the shared column spec. */
function sampleKind(experimentType: string | null | undefined): SampleKind {
  if (isCoreFloodType(experimentType)) return 'core-flood'
  if (isHphtType(experimentType)) return 'hpht'
  return 'other'
}

interface Props {
  experimentId: string
  experimentFk: number
  /** Day parsed from a -t<days> token on the experiment ID (issue #81). */
  idTimepointDays?: number | null
  /** `conditions.experiment_type`. Core Flood results are entered on the run page. */
  experimentType?: string | null
  /** The experiment's start date; a new result's Day counts from it. */
  experimentStart?: string | null
  /** The experiment's base ID, for the run page link and run-level queries. */
  baseExperimentId?: string | null
}

/** Results tab: the segment's timepoints in the shared samples table (issue #163). */
export function ResultsTab({
  experimentId,
  idTimepointDays,
  experimentType,
  experimentStart,
  baseExperimentId,
}: Props) {
  /** 'new' to add a result, a result to edit it, null when the form is closed. */
  const [entry, setEntry] = useState<ResultWithFlags | 'new' | null>(null)
  const coreFlood = isCoreFloodType(experimentType)
  const runPath = runPathFor(experimentType, baseExperimentId ?? experimentId)
  const [mode, setMode] = useState<'individual' | 'grouped'>('individual')

  const { data: replicateGroup } = useQuery({
    queryKey: ['replicate-group', experimentId],
    queryFn: () => experimentsApi.getReplicateGroup(experimentId),
  })
  const baseId = replicateGroup?.base_experiment_id ?? experimentId

  // Issue #101: `replicateGroup` comes from the letter-only /{id}/replicate-group
  // wrapper (deliberately pinned), so it reports zero members for a letterless
  // '-t<days>' vial and the grouped view was unreachable for those sets. The
  // group endpoint counts vials as well as letters, so gate on it too. Same
  // query key GroupedResultsView uses, so this is one request per page.
  const { data: groupDetail } = useQuery({
    queryKey: ['replicate-group-detail', baseId],
    queryFn: () => experimentsApi.getGroup(baseId),
    // A 404 is a legitimate answer (see the same query in ExperimentDetail/index).
    retry: false,
  })
  const vialCount = groupDetail?.member_count ?? 0
  // ">1" for vials: one vial has nothing to aggregate across. Lettered sets keep
  // their original ">0 members" test so a single-letter group still offers it.
  const hasGroup = (replicateGroup?.members.length ?? 0) > 0 || vialCount > 1
  const groupedCount = Math.max(replicateGroup?.members.length ?? 0, vialCount)

  const { data: results, isLoading } = useQuery({
    queryKey: ['experiment-results', experimentId],
    queryFn: () => experimentsApi.getResults(experimentId),
  })

  // The series ICP, read once here for the table's ICP flags and passed to the chart
  // below, so the tab makes one request (issue #163).
  const { data: seriesIcp } = useQuery({
    queryKey: ['experiment-icp', experimentId],
    queryFn: () => experimentsApi.getIcp(experimentId),
  })
  const icpByResult = useMemo(
    () => new Map((seriesIcp?.rows ?? []).map((r) => [r.result_id, r.elements])),
    [seriesIcp],
  )

  if (isLoading) return <PageSpinner />

  return (
    <div>
      {/* Action bar */}
      <div className="flex items-center justify-between gap-2 px-4 py-2 border-b border-surface-border">
        <div />
        <div className="flex items-center gap-2">
          {hasGroup && (
            <div className="flex items-center rounded border border-surface-border overflow-hidden text-xs">
              <button
                className={`px-2.5 py-1 ${mode === 'individual' ? 'bg-surface-raised text-ink-primary' : 'text-ink-secondary hover:text-ink-primary'}`}
                onClick={() => setMode('individual')}
              >
                Individual
              </button>
              <button
                className={`px-2.5 py-1 ${mode === 'grouped' ? 'bg-surface-raised text-ink-primary' : 'text-ink-secondary hover:text-ink-primary'}`}
                onClick={() => setMode('grouped')}
              >
                Grouped (n={groupedCount})
              </button>
            </div>
          )}
          {coreFlood ? (
            // Core flood samples need flow and permeability, which only the run page records;
            // the line under the action bar tells the user so (issue #161, NAV-13).
            runPath && (
              <Link
                to={runPath}
                className="inline-flex items-center h-7 px-3 rounded text-xs font-medium border border-surface-border text-ink-primary hover:bg-surface-raised"
              >
                Add or edit samples on the run page
              </Link>
            )
          ) : (
            // HPHT segments reach their run through the breadcrumb and segment strip
            // (#156), so the Results tab no longer repeats the link (issue #162).
            <Button variant="primary" size="sm" onClick={() => setEntry('new')}>
              + Add Results
            </Button>
          )}
        </div>
      </div>

      {coreFlood && (
        <p className="px-4 pt-3 text-xs text-ink-muted">
          Core flood samples record flow and permeability, which only the run page captures.
        </p>
      )}

      {mode === 'grouped' && hasGroup ? (
        <div className="p-4">
          <GroupedResultsView baseExperimentId={baseId} />
        </div>
      ) : (
        <>
          {/* Empty state */}
          {!results?.length && (
            <p className="text-sm text-ink-muted p-4 text-center">No results recorded</p>
          )}

          {results && results.length > 0 && (
            <div className="p-4">
              <RunSamplesTable
                rows={results.map((r) => fromResult(r, experimentId))}
                scope="segment"
                kind={sampleKind(experimentType)}
                // Only primary rows are editable, matching the PATCH guard; core
                // flood samples are edited on the run page.
                onEdit={coreFlood ? undefined : (r: ResultWithFlags) => setEntry(r)}
                canEdit={(row: SampleRow<ResultWithFlags>) => row.isPrimary}
                icpByResult={icpByResult}
                detailsExtra={(row) => (row.source.has_scalar ? <ScalarExtras resultId={row.resultId} /> : null)}
              />
            </div>
          )}
        </>
      )}

      {/* Issue #143: whole-series ICP chart, below the table in both modes. */}
      <IcpSection experimentId={experimentId} icp={seriesIcp} />

      <ResultEntryModal
        open={entry !== null}
        onClose={() => setEntry(null)}
        experimentId={experimentId}
        experimentType={experimentType}
        experimentStart={experimentStart}
        idTimepointDays={idTimepointDays}
        baseId={baseExperimentId}
        results={results}
        editing={entry !== null && entry !== 'new' ? entry : undefined}
      />
    </div>
  )
}
