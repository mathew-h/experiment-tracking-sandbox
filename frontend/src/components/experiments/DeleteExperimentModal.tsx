import { useEffect, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import type { DeleteImpact, ExperimentDeleted } from '@/api/experiments'
import { Modal, Button, Input, PageSpinner, useToast } from '@/components/ui'

interface DeleteExperimentModalProps {
  open: boolean
  experimentId: string
  onClose: () => void
  onDeleted: (result: ExperimentDeleted) => void
}

/** Human-readable label per impact field, in the order shown. */
const IMPACT_ROWS: Array<[keyof DeleteImpact, string]> = [
  ['conditions', 'conditions record'],
  ['results', 'result timepoints'],
  ['scalar_results', 'scalar measurement rows'],
  ['icp_results', 'ICP measurement rows'],
  ['result_files', 'result files'],
  ['notes', 'notes'],
  ['additives', 'chemical additives'],
  ['external_analyses', 'external analyses'],
  ['xrd_phases', 'XRD phase rows'],
  ['change_requests', 'reactor change requests'],
]

/**
 * Confirmation dialog for deleting a single experiment (issue #99).
 *
 * Deletion is a hard delete and is available to any approved researcher, so
 * the guard rails live here: the dialog itemizes exactly what will be
 * destroyed (from GET /delete-impact) and requires the user to type the
 * experiment ID whenever anything depends on it. The audit trail is written
 * server-side into ModificationsLog.
 */
export function DeleteExperimentModal({
  open, experimentId, onClose, onDeleted,
}: DeleteExperimentModalProps) {
  const { error: toastError } = useToast()
  const [typed, setTyped] = useState('')
  const [serverError, setServerError] = useState<string | null>(null)

  // Reset the gate whenever the dialog opens or retargets, so a previously
  // typed confirmation can never carry over to another experiment.
  useEffect(() => {
    if (open) {
      setTyped('')
      setServerError(null)
    }
  }, [open, experimentId])

  const { data: impact, isLoading, isError } = useQuery({
    queryKey: ['delete-impact', experimentId],
    queryFn: () => experimentsApi.getDeleteImpact(experimentId),
    enabled: open && Boolean(experimentId),
  })

  const deleteMutation = useMutation({
    mutationFn: () => experimentsApi.delete(experimentId),
    onSuccess: (result) => onDeleted(result),
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      const msg = detail ?? 'Could not delete this experiment'
      setServerError(msg)
      // Message body is shown inline in the dialog (below); the toast is
      // title-only so the two channels don't render duplicate text.
      toastError('Delete failed')
    },
  })

  // Demand the typed ID whenever anything is destroyed OR decoupled — being
  // another experiment's ammonium background, or a replicate parent, is a
  // consequence worth confirming even though those rows survive.
  const needsTypedId =
    (impact?.total ?? 0) > 0 ||
    (impact?.background_for.length ?? 0) > 0 ||
    (impact?.replicate_children.length ?? 0) > 0
  const canDelete =
    Boolean(impact) && !deleteMutation.isPending &&
    (!needsTypedId || typed.trim() === experimentId)

  const rows = impact
    ? IMPACT_ROWS.filter(([key]) => (impact[key] as number) > 0)
    : []

  return (
    <Modal
      open={open}
      title="Delete Experiment"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            variant="danger"
            onClick={() => deleteMutation.mutate()}
            disabled={!canDelete}
          >
            Delete
          </Button>
        </>
      }
    >
      {isLoading && <PageSpinner />}

      {isError && (
        <p className="text-red-400 text-sm">
          Could not load what this deletion would affect. Close this dialog and try again.
        </p>
      )}

      {impact && (
        <div className="space-y-3 text-sm">
          <p className="text-ink-secondary">
            Permanently delete{' '}
            <span className="font-mono-data text-ink-primary">{experimentId}</span>?
            This cannot be undone from the app.
          </p>

          {rows.length > 0 ? (
            <div>
              <p className="text-ink-secondary">These records are deleted with it:</p>
              <ul className="mt-1 space-y-0.5 text-ink-muted">
                {rows.map(([key, label]) => (
                  <li key={key} className="tabular-nums">
                    {impact[key] as number} {label}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-ink-muted">No dependent records — nothing else is affected.</p>
          )}

          {impact.background_for.length > 0 && (
            <p className="text-ink-muted">
              Used as the ammonium background by{' '}
              <span className="font-mono-data">{impact.background_for.join(', ')}</span>.
              That reference is cleared; the stored background values are unchanged.
            </p>
          )}

          {impact.replicate_children.length > 0 && (
            <p className="text-ink-muted">
              Parent of{' '}
              <span className="font-mono-data">{impact.replicate_children.join(', ')}</span>.
              Those experiments survive and stay in their replicate group.
            </p>
          )}

          {needsTypedId && (
            <div>
              <label htmlFor="delete-confirm-id" className="block text-ink-secondary mb-1">
                Type the experiment ID to confirm
              </label>
              <Input
                id="delete-confirm-id"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                placeholder={experimentId}
                className="font-mono-data"
                autoFocus
              />
            </div>
          )}

          {serverError && <p className="text-red-400">{serverError}</p>}
        </div>
      )}
    </Modal>
  )
}
