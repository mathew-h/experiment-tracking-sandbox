import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import type { ExperimentDetail, ReplicateGroup } from '@/api/experiments'
import { Badge, Breadcrumb, type BreadcrumbItem } from '@/components/ui'
import { SegmentLink } from '@/components/runs/SegmentLink'
import { runPathFor } from '@/utils/experimentId'
import { isInReplicateSet, runKindFor, stripOrder } from './runContext'

interface RunContextHeaderProps {
  experiment: Pick<ExperimentDetail, 'id' | 'experiment_id' | 'base_experiment_id' | 'replicate_label'>
  experimentType: string | null | undefined
  /** Letter-only replicate set of the experiment (`GET .../replicate-group`). */
  replicateGroup: ReplicateGroup | undefined
  /** Vial count of the stem's group (`GET /experiments/groups/{base}`, issue #101). */
  groupMemberCount: number | undefined
  /** The ID row (heading or rename editor, status, badges), rendered between
   *  the breadcrumb and the strip. */
  children: ReactNode
}

const STRIP = 'text-xs text-ink-muted flex flex-wrap items-center gap-x-1.5'
const PARENT_LINK = 'text-red-400 hover:text-red-300 font-mono-data'
const CURRENT = 'font-semibold text-ink-primary'

/** Detail-page header that names where an experiment sits: its run (HPHT or
 *  Core Flood segment), its replicate group (serum vial), or neither. Renders
 *  the breadcrumb, then `children`, then the run or group strip (issue #156). */
export function RunContextHeader({
  experiment,
  experimentType,
  replicateGroup,
  groupMemberCount,
  children,
}: RunContextHeaderProps) {
  const baseId = experiment.base_experiment_id
  const runPath = runPathFor(experimentType, baseId)
  const kind = runPath ? runKindFor(experimentType) : null

  // Same key and fetch as the run page, so opening a segment from its run
  // reads the strip from cache. A 404 (no run for this base) hides the strip.
  const { data: run } = useQuery({
    queryKey: kind && baseId ? kind.writes.runQueryKey(baseId) : ['run-context', null],
    queryFn: () => kind!.fetch(baseId!),
    enabled: Boolean(kind && baseId),
    retry: false,
  })

  const inReplicateSet = isInReplicateSet(
    experiment.replicate_label,
    replicateGroup?.members.length,
    groupMemberCount,
  )
  const groupBaseId = replicateGroup?.base_experiment_id ?? baseId ?? experiment.experiment_id
  const groupPath = `/experiments/groups/${encodeURIComponent(groupBaseId)}`

  const items: BreadcrumbItem[] = [{ label: 'Experiments', to: '/experiments' }]
  // A run outranks a group: no experiment is both today, and the run is the richer page.
  if (runPath && baseId) items.push({ label: `Run ${baseId}`, to: runPath, mono: true })
  else if (inReplicateSet) items.push({ label: `Group ${groupBaseId}`, to: groupPath, mono: true })
  items.push({ label: experiment.experiment_id, mono: true })

  return (
    <>
      <Breadcrumb className="mb-1" items={items} />

      {children}

      {runPath && run && run.segments.length > 0 && (
        <p role="group" aria-label={`Run ${baseId}`} className={STRIP}>
          <span>
            Run{' '}
            <Link to={runPath} className={PARENT_LINK}>
              {baseId}
            </Link>
          </span>
          <span>·</span>
          <span className="flex flex-wrap items-center gap-1 font-mono-data">
            {stripOrder(run.segments).map((s) => (
              <span key={s.id} className="inline-flex items-center gap-1">
                {s.experiment_id === experiment.experiment_id ? (
                  <span className={CURRENT}>[{s.experiment_id}]</span>
                ) : (
                  <SegmentLink id={s.experiment_id} />
                )}
                {s.status?.toUpperCase() === 'ONGOING' && <Badge variant="ongoing">Ongoing</Badge>}
              </span>
            ))}
          </span>
        </p>
      )}

      {!runPath && inReplicateSet && (
        <p className={STRIP}>
          {experiment.replicate_label !== null && (
            <>
              <span>Replicate {experiment.replicate_label}</span>
              <span>·</span>
            </>
          )}
          <span>
            Group{' '}
            <Link to={groupPath} className={PARENT_LINK}>
              {groupBaseId}
            </Link>
          </span>
          {replicateGroup && replicateGroup.members.length > 0 && (
            <>
              <span>·</span>
              <span className="flex flex-wrap items-center gap-1 font-mono-data">
                {replicateGroup.members.map((member) =>
                  member.id === experiment.id ? (
                    <span key={member.id} className={CURRENT}>
                      [{member.replicate_label ?? member.experiment_id}]
                    </span>
                  ) : (
                    <SegmentLink key={member.id} id={member.experiment_id}>
                      {member.replicate_label ?? member.experiment_id}
                    </SegmentLink>
                  ),
                )}
              </span>
            </>
          )}
        </p>
      )}
    </>
  )
}
