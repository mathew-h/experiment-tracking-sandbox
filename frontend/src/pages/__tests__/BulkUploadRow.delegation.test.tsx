import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
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
    await waitFor(() => expect(screen.getByText(/Upload complete/)).toBeInTheDocument())
  })

  it('delegates and renders no result summary when an override is supplied', async () => {
    const onUploadSuccess = vi.fn()
    renderRow(onUploadSuccess)
    await dropFile()
    await waitFor(() => expect(onUploadSuccess).toHaveBeenCalledWith(DRY_RUN))
    expect(screen.queryByText('Created: 5')).not.toBeInTheDocument()
    expect(screen.queryByText(/Uploaded/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Upload complete/)).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Issue #162 (NAV-22): the row lists the experiments an upload wrote to.
// ---------------------------------------------------------------------------

function renderWith(result: BulkUploadResult) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <ToastProvider>
          <UploadRow
            id="icp" title="ICP-OES Data" description="d" accept=".xlsx"
            uploadFn={() => Promise.resolve(result)}
            isOpen onToggle={vi.fn()}
          />
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

const COMMITTED: BulkUploadResult = {
  created: 3, updated: 0, skipped: 0, errors: [], warnings: [], feedbacks: [],
  message: 'ICP-OES: 3 created, 0 updated', dry_run: false,
  touched: [
    { experiment_id: 'HPHT_297-2', time_post_reaction_days: 1 },
    { experiment_id: 'HPHT_297-2', time_post_reaction_days: 3 },
    { experiment_id: 'SERUM_001a-t5', time_post_reaction_days: 5 },
  ],
}

describe('UploadRow — touched experiments (issue #162)', () => {
  it('names each experiment written to, linked to its Results tab, with the day', async () => {
    renderWith(COMMITTED)
    await dropFile()
    expect(await screen.findByText('Wrote to 2 experiments')).toBeInTheDocument()
    const links = screen.getAllByRole('link', { name: 'HPHT_297-2' })
    expect(links).toHaveLength(2)
    expect(links[0]).toHaveAttribute('href', '/experiments/HPHT_297-2?tab=results')
    expect(links[0].parentElement).toHaveTextContent('HPHT_297-2 · day 1')
    expect(links[1].parentElement).toHaveTextContent('HPHT_297-2 · day 3')
    expect(screen.getByRole('link', { name: 'SERUM_001a-t5' })).toHaveAttribute(
      'href', '/experiments/SERUM_001a-t5?tab=results')
  })

  it('says "Would write to" on a dry run', async () => {
    renderWith({ ...COMMITTED, dry_run: true })
    await dropFile()
    expect(await screen.findByText('Would write to 2 experiments')).toBeInTheDocument()
  })

  it('shows 20 entries, then "and n more" expands the rest in place', async () => {
    const touched = Array.from({ length: 23 }, (_, i) => ({
      experiment_id: `HPHT_${String(i + 1).padStart(3, '0')}`, time_post_reaction_days: 1,
    }))
    renderWith({ ...COMMITTED, touched })
    await dropFile()
    expect(await screen.findByText('Wrote to 23 experiments')).toBeInTheDocument()
    expect(screen.getAllByRole('link')).toHaveLength(20)
    await userEvent.click(screen.getByRole('button', { name: 'and 3 more' }))
    expect(screen.getAllByRole('link')).toHaveLength(23)
  })

  it('shows nothing when the upload touched nothing', async () => {
    renderWith({ ...COMMITTED, created: 0, touched: [] })
    await dropFile()
    await screen.findByText('Created: 0')
    expect(screen.queryByText(/write to|Wrote to/)).not.toBeInTheDocument()
  })
})
