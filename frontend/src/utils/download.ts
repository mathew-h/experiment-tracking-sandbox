/** Save a Blob to the user's downloads under `filename` (the browser picks the folder). */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

/**
 * The filename from a Content-Disposition header (`attachment; filename="x.xlsx"`),
 * or `fallback` when the header is missing or has no filename.
 */
export function filenameFromDisposition(header: unknown, fallback: string): string {
  if (typeof header !== 'string') return fallback
  const match = /filename="?([^";]+)"?/i.exec(header)
  return match ? match[1].trim() : fallback
}

/**
 * A readable message for a failed blob-typed request. With `responseType: 'blob'`
 * axios delivers the error body as a Blob, so the server's `detail` has to be read
 * out of it; falls back to `err.message`, then 'Export failed'.
 */
export async function blobErrorMessage(err: unknown): Promise<string> {
  if (typeof err !== 'object' || err === null) return 'Export failed'
  const { message, response } = err as { message?: unknown; response?: { data?: unknown } }
  const fallback = typeof message === 'string' && message ? message : 'Export failed'
  const data = response?.data
  if (!(data instanceof Blob)) return fallback
  try {
    const body: unknown = JSON.parse(await data.text())
    const detail = (body as { detail?: unknown } | null)?.detail
    return typeof detail === 'string' ? detail : fallback
  } catch {
    return fallback
  }
}
