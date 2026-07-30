import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import type { BulkUploadResult, ConflictCheckResult } from '@/api/bulkUploads'
import { UploadRow } from '../BulkUploadRow'

const DRY_RUN: BulkUploadResult = {
  created: 5, updated: 2, skipped: 0, errors: [], warnings: [], feedbacks: [],
  message: '[DRY RUN] 5 created, 2 updated, 0 skipped', dry_run: true,
  plan: { creates: [], renames: [], overwrites: [], skips: [], conflicts: [], counts: {} },
  plan_hash: 'h1',
}

function renderRow(onUploadSuccess?: (d: BulkUploadResult | ConflictCheckResult) => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <UploadRow
          id="t" title="Test Upload" description="d" accept=".xlsx"
          uploadFn={() => Promise.resolve(DRY_RUN)}
          onUploadSuccess={onUploadSuccess}
          isOpen onToggle={vi.fn()}
        />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

async function dropFile() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  await userEvent.upload(input, new File(['x'], 'f.xlsx'))
}

describe('UploadRow — onUploadSuccess override', () => {
  it('renders its own result badges when no override is supplied', async () => {
    renderRow()
    await dropFile()
    await waitFor(() => expect(screen.getByText('Created: 5')).toBeInTheDocument())
  })

  it('delegates and renders no result summary when an override is supplied', async () => {
    const onUploadSuccess = vi.fn()
    renderRow(onUploadSuccess)
    await dropFile()
    await waitFor(() => expect(onUploadSuccess).toHaveBeenCalledWith(DRY_RUN))
    expect(screen.queryByText('Created: 5')).not.toBeInTheDocument()
    expect(screen.queryByText(/Uploaded/)).not.toBeInTheDocument()
  })
})
