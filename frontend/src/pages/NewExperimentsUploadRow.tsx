import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/components/ui'
import { UploadRow } from './BulkUploadRow'
import { UploadPlanModal } from '@/components/bulkUploads/UploadPlanModal'
import type { PlanModalView } from '@/components/bulkUploads/UploadPlanModal'
import { bulkUploadsApi, isConflictCheckResult } from '@/api/bulkUploads'
import type { BulkUploadResult, ConflictCheckResult } from '@/api/bulkUploads'

const HELP_TEXT =
  'Dropping a file previews it — nothing is written until you review the plan and press Commit. ' +
  "Use the template for correct column formatting. The file must have an 'experiments' sheet; a 'conditions' sheet is optional. " +
  'Replicates: write a lowercase letter after the number (SERUM_001a, _001b, _001c) — the bare SERUM_001 (or SERUM_001-0) is replicate 0, the group parent. ' +
  'Replicate timepoints are separate vials: encode the sample day in the ID with -t<days> (SERUM_001a-t0, SERUM_001a-t7, decimals allowed like -t0.5). ' +
  'The day is locked to the ID for all results. ' +
  'To rename experiments, fill old_experiment_id AND set overwrite=TRUE — the preview will tell you if a rename would instead create a duplicate.'

export interface NewExperimentsUploadRowProps {
  isOpen: boolean
  onToggle: () => void
  /** Larger header treatment — passed through to UploadRow */
  prominent?: boolean
  /** Next-ID chips, rendered inside the expanded panel */
  topContent?: React.ReactNode
}

/** Two-phase New Experiments upload (issue #100 items 6-9).
 *
 *  A dropped file ALWAYS previews via `dry_run=true`; the only path that writes is the
 *  Commit button in the review modal, which replays the previewed `plan_hash` so a
 *  workbook or database edited in between is refused rather than applied. */
export function NewExperimentsUploadRow({
  isOpen,
  onToggle,
  prominent = false,
  topContent,
}: NewExperimentsUploadRowProps) {
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<BulkUploadResult | null>(null)
  const [view, setView] = useState<PlanModalView>('review')
  const { success, error: toastError } = useToast()
  const queryClient = useQueryClient()

  const close = () => {
    setFile(null)
    setResult(null)
    setView('review')
  }

  /** A 200 with errors and no plan is the parser-crash path
   *  (backend/api/routers/bulk_uploads.py:189) — there is nothing to review.
   *  `isConflictCheckResult` guards the cast: that shape (Actlabs-only today, no
   *  `errors` field) can't reach `uploadNewExperiments` in practice, but a blind
   *  `as BulkUploadResult` would throw on `res.errors[0]` if it ever did. */
  const handlePreview = (data: BulkUploadResult | ConflictCheckResult) => {
    if (isConflictCheckResult(data)) {
      toastError('Preview failed', data.message)
      setFile(null)
      return
    }
    if (!data.plan) {
      toastError('Preview failed', data.errors[0] ?? data.message)
      setFile(null)
      return
    }
    setResult(data)
    setView('review')
  }

  const commitMutation = useMutation({
    mutationFn: ({ f, planHash }: { f: File; planHash: string }) =>
      bulkUploadsApi.uploadNewExperiments(f, { planHash }),
    onSuccess: (data, vars) => {
      if (!data.plan) {
        toastError('Upload failed', data.errors[0] ?? data.message)
        close()
        return
      }
      setResult(data)

      // Structural test, mirroring the only two things that populate the server's
      // plan gate. NOT `errors.length > 0` — a successful commit also returns the
      // parser's own row errors, so that would report "nothing applied" for an
      // upload that applied most of the file.
      const rejected = data.plan.conflicts.length > 0 || data.plan_hash !== vars.planHash
      if (rejected) {
        setView('stale')
        return
      }

      setView('done')
      // Because this row supplies `onUploadSuccess`, UploadRow never renders its own
      // "Uploaded" badge or result panel (BulkUploadRow.tsx onSuccess early-returns) —
      // so once the researcher closes this modal, this toast is the only thing on the
      // page confirming the write happened. Wording deliberately avoids "Upload
      // complete" (the modal's own done-view title) so the two don't collide on the
      // same text — this exact collision broke this handler once already.
      success('Experiments created', `${data.created} created, ${data.updated} updated`)
      // Creating experiments moves the next-ID chips (staleTime 60s) and the
      // experiment list / dashboard (global staleTime 30s, frontend/src/main.tsx)
      // — without this, both can serve a stale list missing the new rows for up
      // to 30s after a successful commit.
      queryClient.invalidateQueries({ queryKey: ['nextIds'] })
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
    },
    onError: (err: Error) => {
      // Keep the modal on its current view so the reviewed plan is not lost.
      toastError('Upload failed', err.message)
    },
  })

  return (
    <>
      <UploadRow
        id="new-experiments"
        title="New Experiments"
        description="Bulk-create experiments from a structured Excel template — previews before writing"
        helpText={HELP_TEXT}
        accept=".xlsx,.xls"
        uploadFn={(f) => {
          setFile(f)
          return bulkUploadsApi.uploadNewExperiments(f, { dryRun: true })
        }}
        onUploadSuccess={handlePreview}
        templateType="new-experiments"
        topContent={topContent}
        prominent={prominent}
        isOpen={isOpen}
        onToggle={onToggle}
      />
      {result?.plan && (
        <UploadPlanModal
          // Remounting on a new hash resets the modal's re-arm checkbox.
          key={result.plan_hash ?? 'no-hash'}
          open
          view={view}
          result={result}
          committing={commitMutation.isPending}
          onCommit={() => {
            if (file && result.plan_hash) {
              commitMutation.mutate({ f: file, planHash: result.plan_hash })
            } else {
              // Should be unreachable — Commit is only enabled once a preview has
              // set both `file` and `result.plan_hash`. Surface it rather than let
              // the click silently do nothing if a malformed response ever gets here.
              toastError('Cannot commit', 'The previewed file or plan hash is missing — try dropping the file again.')
            }
          }}
          // Block backdrop-click/Escape dismissal mid-commit — Cancel is already
          // disabled in the modal's footer for the same reason (no mid-flight exit).
          onClose={commitMutation.isPending ? () => {} : close}
        />
      )}
    </>
  )
}
