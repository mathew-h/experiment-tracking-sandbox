import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Button, Badge, FileUpload, Spinner, useToast } from '@/components/ui'
import { bulkUploadsApi, BulkUploadResult, TemplateType } from '@/api/bulkUploads'

// ─── Minimal inline icons ────────────────────────────────────────────────────
function IconChevron({ open }: { open: boolean }) {
  return (
    <svg
      width={16} height={16} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
      className={`text-ink-muted transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}

function IconDownload() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  )
}

function IconRefresh() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
    >
      <polyline points="23 4 23 10 17 10" />
      <polyline points="1 20 1 14 7 14" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10" />
      <path d="M20.49 15a9 9 0 0 1-14.85 3.36L1 14" />
    </svg>
  )
}

// ─── Component ───────────────────────────────────────────────────────────────

export interface UploadRowProps {
  id: string
  title: string
  description: string
  helpText?: string
  accept: string
  uploadFn: (file: File) => Promise<BulkUploadResult>
  templateType?: TemplateType
  /** Optional mode passed to the template download endpoint (e.g. 'experiment' for XRD) */
  templateMode?: string
  /** If provided, shows a "Sync from SharePoint" button above the file zone */
  syncFn?: () => Promise<BulkUploadResult>
  /** Optional content rendered inside the expanded panel (chips, extra fields, etc.) */
  topContent?: React.ReactNode
  isOpen: boolean
  onToggle: () => void
}

/** Single row in the bulk upload table — file picker, upload trigger, and status display. */
export function UploadRow({
  title,
  description,
  helpText,
  accept,
  uploadFn,
  templateType,
  templateMode,
  syncFn,
  topContent,
  isOpen,
  onToggle,
}: UploadRowProps) {
  const [result, setResult] = useState<BulkUploadResult | null>(null)
  const [showAllErrors, setShowAllErrors] = useState(false)
  const [showAllWarnings, setShowAllWarnings] = useState(false)
  const { success, error: toastError } = useToast()

  const uploadMutation = useMutation({
    mutationFn: uploadFn,
    onSuccess: (data) => {
      setResult(data)
      success(`Upload complete — ${data.created} created, ${data.updated} updated`)
    },
    onError: (err: Error) => {
      toastError('Upload failed', err.message)
    },
  })

  const syncMutation = useMutation({
    mutationFn: () => syncFn!(),
    onSuccess: (data) => {
      setResult(data)
      success(`Sync complete — ${data.created} created, ${data.updated} updated`)
    },
    onError: (err: Error) => {
      toastError('Sync failed', err.message)
    },
  })

  const templateMutation = useMutation({
    mutationFn: () => bulkUploadsApi.downloadTemplate(templateType!, templateMode),
    onError: (err: Error) => {
      toastError('Download failed', err.message)
    },
  })

  const isPending = uploadMutation.isPending || syncMutation.isPending
  const lastStatus = result
    ? result.errors.length > 0 ? 'error' : 'success'
    : null

  return (
    <div className="border border-surface-border rounded-lg overflow-hidden">
      {/* ── Header — always visible ─────────────────────────────────────── */}
      <button
        className="w-full flex items-center justify-between px-4 py-3 bg-surface-primary hover:bg-surface-secondary transition-colors text-left"
        onClick={onToggle}
        aria-expanded={isOpen}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-sm font-medium text-ink-primary shrink-0">{title}</span>
          <span className="text-xs text-ink-muted truncate hidden sm:block">{description}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {lastStatus === 'success' && <Badge variant="success">Uploaded</Badge>}
          {lastStatus === 'error' && (
            <Badge variant="error">{result!.errors.length} error{result!.errors.length !== 1 ? 's' : ''}</Badge>
          )}
          {isPending && <Spinner size="sm" />}
          <IconChevron open={isOpen} />
        </div>
      </button>

      {/* ── Expanded content ─────────────────────────────────────────────── */}
      <div className={`overflow-hidden transition-all duration-200 ${isOpen ? 'max-h-[900px]' : 'max-h-0'}`}>
        <div className="px-4 py-3 border-t border-surface-border space-y-3 bg-surface-primary">

          {/* Help text */}
          {(helpText || description) && (
            <p className="text-xs text-ink-muted leading-relaxed">{helpText ?? description}</p>
          )}

          {/* Optional top content — next-ID chips, extra fields, etc. */}
          {topContent}

          {/* Sync button row (Master Results only) */}
          {syncFn && (
            <div className="flex items-center gap-2 flex-wrap">
              <Button
                variant="outline"
                size="sm"
                onClick={() => { setResult(null); syncMutation.mutate() }}
                disabled={isPending}
                leftIcon={<IconRefresh />}
              >
                Sync from SharePoint
              </Button>
              <span className="text-xs text-ink-muted">or upload a file below</span>
            </div>
          )}

          {/* File drop zone */}
          <FileUpload
            accept={accept}
            onFiles={([file]) => { setResult(null); uploadMutation.mutate(file) }}
            disabled={isPending}
            hint={`Accepted: ${accept}`}
          />

          {/* Template download */}
          {templateType && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => templateMutation.mutate()}
              disabled={templateMutation.isPending}
              leftIcon={<IconDownload />}
            >
              {templateMutation.isPending ? 'Downloading…' : 'Download Template'}
            </Button>
          )}

          {/* Processing spinner */}
          {isPending && (
            <div className="flex items-center gap-2 text-xs text-ink-secondary">
              <Spinner size="sm" />
              Processing…
            </div>
          )}

          {/* ── Result summary ──────────────────────────────────────────── */}
          {result && !isPending && (
            <div className="space-y-2">
              <div className="flex flex-wrap gap-2">
                <Badge variant="success">Created: {result.created}</Badge>
                <Badge variant="default">Updated: {result.updated}</Badge>
                <Badge variant="warning">Skipped: {result.skipped}</Badge>
                {result.errors.length > 0 && (
                  <Badge variant="error">Errors: {result.errors.length}</Badge>
                )}
                {result.warnings.length > 0 && (
                  <Badge variant="warning">Warnings: {result.warnings.length}</Badge>
                )}
              </div>

              {/* Error list */}
              {result.errors.length > 0 && (
                <div className="p-3 rounded bg-red-500/5 border border-red-500/20 space-y-1">
                  {(showAllErrors ? result.errors : result.errors.slice(0, 5)).map((e, i) => (
                    <p key={i} className="text-2xs text-red-400 font-mono-data">{e}</p>
                  ))}
                  {result.errors.length > 5 && (
                    <button
                      className="text-2xs text-ink-muted underline mt-1 hover:text-ink-secondary"
                      onClick={() => setShowAllErrors((v) => !v)}
                    >
                      {showAllErrors
                        ? 'Show less'
                        : `Show ${result.errors.length - 5} more errors`}
                    </button>
                  )}
                </div>
              )}

              {/* Warnings list */}
              {result.warnings.length > 0 && (
                <div className="p-3 rounded bg-yellow-500/5 border border-yellow-500/20 space-y-1">
                  {(showAllWarnings ? result.warnings : result.warnings.slice(0, 5)).map((w, i) => (
                    <p key={i} className="text-2xs text-yellow-500">{w}</p>
                  ))}
                  {result.warnings.length > 5 && (
                    <button
                      className="text-2xs text-ink-muted underline mt-1 hover:text-ink-secondary"
                      onClick={() => setShowAllWarnings((v) => !v)}
                    >
                      {showAllWarnings
                        ? 'Show less'
                        : `Show ${result.warnings.length - 5} more warnings`}
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
