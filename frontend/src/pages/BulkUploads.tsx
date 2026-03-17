import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { bulkUploadsApi, BulkUploadResult } from '@/api/bulkUploads'
import { Card, CardHeader, CardBody, FileUpload, Badge, useToast } from '@/components/ui'

type UploadType = 'scalar-results' | 'new-experiments' | 'pxrf' | 'aeris-xrd'

interface UploadCardProps {
  title: string
  description: string
  accept: string
  type: UploadType
}

const uploadFns: Record<UploadType, (file: File) => Promise<BulkUploadResult>> = {
  'scalar-results':  (f) => bulkUploadsApi.uploadScalarResults(f),
  'new-experiments': (f) => bulkUploadsApi.uploadNewExperiments(f),
  'pxrf':            (f) => bulkUploadsApi.uploadPXRF(f),
  'aeris-xrd':       (f) => bulkUploadsApi.uploadAerisXRD(f),
}

function UploadCard({ title, description, accept, type }: UploadCardProps) {
  const [result, setResult] = useState<BulkUploadResult | null>(null)
  const { success, error: toastError } = useToast()

  const mutation = useMutation({
    mutationFn: (file: File) => uploadFns[type](file),
    onSuccess: (data) => {
      setResult(data)
      success(`Upload complete — ${data.rows_inserted} rows inserted`)
    },
    onError: (err: Error) => {
      toastError('Upload failed', err.message)
    },
  })

  return (
    <Card padding="none">
      <CardHeader label={title} />
      <CardBody className="space-y-4">
        <p className="text-xs text-ink-muted">{description}</p>
        <FileUpload
          accept={accept}
          onFiles={([file]) => { setResult(null); mutation.mutate(file) }}
          disabled={mutation.isPending}
          hint={`Accepted: ${accept}`}
        />

        {mutation.isPending && (
          <div className="flex items-center gap-2 text-xs text-ink-secondary">
            <span className="animate-spin w-3.5 h-3.5 border-2 border-surface-border border-t-red-500 rounded-full" />
            Processing…
          </div>
        )}

        {result && (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-2">
              <Badge variant="default">Processed: {result.rows_processed}</Badge>
              <Badge variant="success">Inserted: {result.rows_inserted}</Badge>
              <Badge variant="warning">Skipped: {result.rows_skipped}</Badge>
              {result.errors.length > 0 && <Badge variant="error">Errors: {result.errors.length}</Badge>}
            </div>
            {result.errors.length > 0 && (
              <div className="p-3 rounded bg-red-500/5 border border-red-500/20 space-y-1">
                {result.errors.slice(0, 5).map((e, i) => (
                  <p key={i} className="text-2xs text-red-400 font-mono-data">{e}</p>
                ))}
                {result.errors.length > 5 && (
                  <p className="text-2xs text-ink-muted">…and {result.errors.length - 5} more</p>
                )}
              </div>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  )
}

export function BulkUploadsPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-ink-primary">Bulk Uploads</h1>
        <p className="text-xs text-ink-muted mt-0.5">Upload analytical data from instrument exports</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <UploadCard
          type="scalar-results"
          title="Scalar Results"
          description="Upload solution chemistry measurements (pH, conductivity, ammonium, H₂, ICP) from Excel exports."
          accept=".xlsx,.xls,.csv"
        />
        <UploadCard
          type="new-experiments"
          title="New Experiments"
          description="Bulk-create experiments from a structured Excel template."
          accept=".xlsx,.xls,.csv"
        />
        <UploadCard
          type="pxrf"
          title="pXRF Readings"
          description="Upload portable XRF scan data from the instrument CSV export."
          accept=".csv,.xlsx"
        />
        <UploadCard
          type="aeris-xrd"
          title="Aeris XRD"
          description="Upload Aeris XRD mineral phase data (time-series format)."
          accept=".csv,.xlsx,.xls"
        />
      </div>
    </div>
  )
}

