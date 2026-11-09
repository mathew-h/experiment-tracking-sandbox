import { Fragment, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { SegmentLink } from './SegmentLink'
import type { RunWrites } from './runWrites'

/** Experiment IDs as links, comma separated (issue #158). */
export function SegmentIdList({ ids, inherit = false }: { ids: string[]; inherit?: boolean }) {
  return (
    <>
      {ids.map((id, i) => (
        <Fragment key={id}>
          {i > 0 && ', '}
          <SegmentLink id={id} inherit={inherit} />
        </Fragment>
      ))}
    </>
  )
}

interface RunNotFoundProps {
  /** Run kind in the message: "HPHT", "core flood". */
  kind: string
  /** The ID from the URL. */
  requestedId: string
  writes: RunWrites
  /** Name of the run list: "HPHT", "Core Floods". */
  listLabel: string
}

/** A run URL that names no run of this kind. The ID may still be an experiment
 *  of another kind, so offer its detail page as well as the list (issue #158). */
export function RunNotFound({ kind, requestedId, writes, listLabel }: RunNotFoundProps) {
  return (
    <div className="space-y-2 py-4">
      <p className="text-sm text-ink-primary">No {kind} run {requestedId}</p>
      <div className="flex flex-wrap gap-4 text-sm">
        <Link to={writes.listPath} className="text-red-400 hover:text-red-300">
          Back to {listLabel}
        </Link>
        <Link to={`/experiments/${encodeURIComponent(requestedId)}`} className="text-red-400 hover:text-red-300">
          Open experiment {requestedId}
        </Link>
      </div>
    </div>
  )
}

/** The API resolves a segment or variant ID to its run (issue #158). When the URL
 *  held one, replace it with the run's base ID so each run has one address and
 *  one cache entry; the loaded run is copied to that entry to skip a refetch. */
export function useCanonicalRunUrl(
  requestedId: string,
  run: { base_id: string } | undefined,
  writes: RunWrites,
): void {
  const navigate = useNavigate()
  const qc = useQueryClient()
  useEffect(() => {
    if (!run || run.base_id === requestedId) return
    qc.setQueryData(writes.runQueryKey(run.base_id), run)
    navigate(writes.runPath(run.base_id), { replace: true })
  }, [run, requestedId, writes, navigate, qc])
}
