import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { UploadRow } from './BulkUploadRow'
import { SampleConflictModal } from '@/components/SampleConflictModal'
import { bulkUploadsApi, ConflictCheckResult, BulkUploadResult, isConflictCheckResult } from '@/api/bulkUploads'
import { useToast } from '@/components/ui'

interface ActlabsUploadRowProps {
  isOpen: boolean
  onToggle: () => void
}

export function ActlabsUploadRow({ isOpen, onToggle }: ActlabsUploadRowProps) {
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [conflicts, setConflicts] = useState<ConflictCheckResult['conflicts'] | null>(null)
  const { success, error: toastError } = useToast()

  const confirmMutation = useMutation({
    mutationFn: ({ file, resolutions }: { file: File; resolutions: Record<string, string> }) =>
      bulkUploadsApi.uploadActlabsRock(file, resolutions) as Promise<BulkUploadResult>,
    onSuccess: (data) => {
      success(`Upload complete — ${data.created} created, ${data.updated} updated`)
      setPendingFile(null)
    },
    onError: (err: Error) => {
      toastError('Upload failed', err.message)
      setPendingFile(null)
    },
  })

  const uploadFn = async (file: File): Promise<BulkUploadResult> => {
    const result = await bulkUploadsApi.uploadActlabsRock(file)
    if (isConflictCheckResult(result)) {
      setPendingFile(file)
      setConflicts(result.conflicts)
      // Throw so UploadRow's onError fires — we handle the result ourselves via the modal
      throw new Error('__conflicts__')
    }
    return result as BulkUploadResult
  }

  const handleConflictConfirm = (resolutions: Record<string, string>) => {
    if (!pendingFile) return
    setConflicts(null)
    confirmMutation.mutate({ file: pendingFile, resolutions })
  }

  const handleConflictCancel = () => {
    setConflicts(null)
    setPendingFile(null)
  }

  return (
    <>
      <UploadRow
        id="actlabs-rock"
        title="ActLabs Rock Analysis"
        description="Import ActLabs titration report (Excel or CSV)"
        helpText="Accepts ActLabs standard report format. Row 3 = analyte symbols, Row 4 = units. Values like '<0.01', 'nd', 'na' are handled. Analytes are auto-created from file headers."
        accept=".xlsx,.xls,.csv"
        uploadFn={uploadFn}
        onUploadError={(err) => {
          if (err.message !== '__conflicts__') toastError('Upload failed', err.message)
        }}
        isOpen={isOpen}
        onToggle={onToggle}
      />
      <SampleConflictModal
        open={conflicts !== null}
        conflicts={conflicts ?? []}
        onConfirm={handleConflictConfirm}
        onCancel={handleConflictCancel}
      />
    </>
  )
}
