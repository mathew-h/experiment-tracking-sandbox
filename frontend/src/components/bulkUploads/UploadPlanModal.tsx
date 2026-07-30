import { useState } from 'react'
import { Modal, Button, Badge } from '@/components/ui'
import { UploadPlanPanel } from './UploadPlanPanel'
import type { BulkUploadResult } from '@/api/bulkUploads'

export type PlanModalView = 'review' | 'stale' | 'done'

export interface UploadPlanModalProps {
  open: boolean
  view: PlanModalView
  /** The previewed, rejected, or committed response. Carries a non-null plan. */
  result: BulkUploadResult
  committing: boolean
  onCommit: () => void
  onClose: () => void
}

/** Review surface for a bulk-upload plan (issue #100 items 6-9).
 *
 *  Three views: `review` (preview a dry run), `stale` (the server refused the commit
 *  because the plan changed — requires explicit re-arming), and `done` (committed).
 *
 *  The re-arm checkbox is local state and is reset by the PARENT remounting this
 *  component on a new `plan_hash` (`key={result.plan_hash}`) — not by an effect, and
 *  not on every response, only a changed hash. This is safe because a hash-mismatch
 *  rejection always changes the key (the server returns the fresh file's own hash,
 *  which differs from the one that was replayed), and a conflict rejection — where
 *  the hash can stay the same — is disabled by the conflict gate below regardless of
 *  `reviewed`, so a carried-over checkbox value can never re-arm Commit on its own. */
export function UploadPlanModal({ open, view, result, committing, onCommit, onClose }: UploadPlanModalProps) {
  const [reviewed, setReviewed] = useState(false)
  const plan = result.plan

  const conflicts = plan?.conflicts.length ?? 0
  const changeCount = plan
    ? plan.creates.length + plan.renames.length + plan.overwrites.length
    : 0

  // The conflict gate always wins — re-arming a stale plan cannot override it.
  const commitDisabled = conflicts > 0 || (view === 'stale' && !reviewed) || committing

  const footer = view === 'done' ? (
    <Button variant="secondary" onClick={onClose}>Close</Button>
  ) : (
    <>
      {conflicts > 0 && (
        <span className="text-2xs text-status-error mr-auto max-w-md leading-relaxed">
          {conflicts} conflict{conflicts !== 1 ? 's' : ''} must be fixed in the workbook
          before this file can be committed — nothing will be applied until then.
        </span>
      )}
      <Button variant="ghost" onClick={onClose} disabled={committing}>Cancel</Button>
      <Button variant="primary" onClick={onCommit} disabled={commitDisabled} loading={committing}>
        {committing ? 'Committing…' : `Commit ${changeCount} change${changeCount !== 1 ? 's' : ''}`}
      </Button>
    </>
  )

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={view === 'done' ? 'Upload complete' : 'Review upload plan'}
      description={
        view === 'done'
          ? undefined
          : 'Nothing has been written yet. Review what this file would do, then commit.'
      }
      size="xl"
      footer={footer}
    >
      {view === 'stale' && (
        <div className="mb-3 p-3 rounded border bg-status-warning/10 border-status-warning/30 space-y-2">
          <p className="text-xs font-medium text-status-warning">
            Nothing was applied — the plan changed since you previewed it.
          </p>
          {result.errors.map((e, i) => (
            <p key={i} className="text-2xs text-ink-secondary leading-relaxed">{e}</p>
          ))}
          <label className="flex items-center gap-2 cursor-pointer select-none pt-1">
            <input
              type="checkbox"
              className="w-3.5 h-3.5 rounded accent-red-500"
              checked={reviewed}
              onChange={(e) => setReviewed(e.target.checked)}
            />
            <span className="text-xs text-ink-secondary">I&apos;ve reviewed the updated plan</span>
          </label>
        </div>
      )}

      {view === 'done' ? (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Badge variant="success">Created: {result.created}</Badge>
            <Badge variant="default">Updated: {result.updated}</Badge>
            <Badge variant="warning">Skipped: {result.skipped}</Badge>
          </div>
          {result.errors.length > 0 && (
            <div className="p-3 rounded bg-status-error/5 border border-status-error/20 space-y-1">
              {result.errors.map((e, i) => (
                <p key={i} className="text-2xs text-status-error font-mono-data">{e}</p>
              ))}
            </div>
          )}
          {result.warnings.length > 0 && (
            <div className="p-3 rounded bg-status-warning/5 border border-status-warning/20 space-y-1">
              {result.warnings.map((w, i) => (
                <p key={i} className="text-2xs text-status-warning">{w}</p>
              ))}
            </div>
          )}
        </div>
      ) : (
        plan && <UploadPlanPanel plan={plan} />
      )}
    </Modal>
  )
}
