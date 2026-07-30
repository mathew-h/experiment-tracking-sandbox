import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'

vi.mock('@/api/bulkUploads', () => ({
  bulkUploadsApi: { uploadNewExperiments: vi.fn(), downloadTemplate: vi.fn() },
  isConflictCheckResult: () => false,
}))

import { NewExperimentsUploadRow } from '../NewExperimentsUploadRow'
import { bulkUploadsApi } from '@/api/bulkUploads'
import type { BulkUploadResult, UploadPlan } from '@/api/bulkUploads'

const PLAN: UploadPlan = {
  creates: [
    { row: 2, experiment_id: 'HPHT_001', parent_id: null, copied_from: null },
    { row: 3, experiment_id: 'HPHT_002', parent_id: null, copied_from: null },
  ],
  renames: [], overwrites: [], skips: [], conflicts: [], counts: {},
}

function res(over: Partial<BulkUploadResult> = {}, plan: UploadPlan | null = PLAN): BulkUploadResult {
  return {
    created: 0, updated: 0, skipped: 0, errors: [], warnings: [], feedbacks: [],
    message: '', dry_run: true, plan, plan_hash: 'hash-1', ...over,
  }
}

let client: QueryClient

function renderRow() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <NewExperimentsUploadRow isOpen onToggle={vi.fn()} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

async function dropFile() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  await userEvent.upload(input, new File(['x'], 'exp.xlsx'))
}

const mockUpload = () => vi.mocked(bulkUploadsApi.uploadNewExperiments)

beforeEach(() => { vi.clearAllMocks() })

describe('NewExperimentsUploadRow — preview phase', () => {
  it('previews with dry_run and never commits on a file drop', async () => {
    mockUpload().mockResolvedValue(res())
    renderRow()
    await dropFile()
    await waitFor(() => expect(mockUpload()).toHaveBeenCalledTimes(1))
    expect(mockUpload()).toHaveBeenCalledWith(expect.any(File), { dryRun: true })
  })

  it('opens the review modal showing the plan', async () => {
    mockUpload().mockResolvedValue(res())
    renderRow()
    await dropFile()
    await waitFor(() => expect(screen.getByText(/Review upload plan/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /Commit 2 changes/ })).toBeEnabled()
  })

  it('does not open the modal when the parser crashed and returned no plan', async () => {
    mockUpload().mockResolvedValue(res({ errors: ['Missing experiments sheet'], message: 'Upload failed' }, null))
    renderRow()
    await dropFile()
    await waitFor(() => expect(screen.getByText(/Missing experiments sheet/)).toBeInTheDocument())
    expect(screen.queryByText(/Review upload plan/i)).not.toBeInTheDocument()
  })
})

describe('NewExperimentsUploadRow — commit phase', () => {
  it('replays the previewed plan hash and omits dry_run', async () => {
    mockUpload().mockResolvedValue(res())
    renderRow()
    await dropFile()
    await waitFor(() => screen.getByRole('button', { name: /Commit 2 changes/ }))

    mockUpload().mockResolvedValue(res({ created: 2, dry_run: false, plan_hash: 'hash-1' }))
    await userEvent.click(screen.getByRole('button', { name: /Commit 2 changes/ }))

    await waitFor(() => expect(mockUpload()).toHaveBeenCalledTimes(2))
    expect(mockUpload()).toHaveBeenLastCalledWith(expect.any(File), { planHash: 'hash-1' })
  })

  it('shows the committed counts and invalidates the next-ID chips', async () => {
    mockUpload().mockResolvedValue(res())
    renderRow()
    await dropFile()
    await waitFor(() => screen.getByRole('button', { name: /Commit 2 changes/ }))

    const spy = vi.spyOn(client, 'invalidateQueries')
    mockUpload().mockResolvedValue(res({ created: 2, updated: 0, dry_run: false, plan_hash: 'hash-1' }))
    await userEvent.click(screen.getByRole('button', { name: /Commit 2 changes/ }))

    await waitFor(() => expect(screen.getByText(/Upload complete/i)).toBeInTheDocument())
    expect(screen.getByText('Created: 2')).toBeInTheDocument()
    expect(spy).toHaveBeenCalledWith({ queryKey: ['nextIds'] })
  })

  it('treats a committed upload with parser row errors as done, not stale', async () => {
    mockUpload().mockResolvedValue(res())
    renderRow()
    await dropFile()
    await waitFor(() => screen.getByRole('button', { name: /Commit 2 changes/ }))

    // 8 rows committed, 2 rows errored — plan_hash unchanged, no conflicts.
    mockUpload().mockResolvedValue(res({
      created: 8, updated: 0, skipped: 0, dry_run: false, plan_hash: 'hash-1',
      errors: ['Row 12: invalid status "RUNNING"'],
    }))
    await userEvent.click(screen.getByRole('button', { name: /Commit 2 changes/ }))

    await waitFor(() => expect(screen.getByText(/Upload complete/i)).toBeInTheDocument())
    expect(screen.getByText('Created: 8')).toBeInTheDocument()
    expect(screen.queryByText(/Nothing was applied/i)).not.toBeInTheDocument()
  })
})

describe('NewExperimentsUploadRow — stale plan', () => {
  it('shows the stale view when the returned hash differs from the previewed one', async () => {
    mockUpload().mockResolvedValue(res())
    renderRow()
    await dropFile()
    await waitFor(() => screen.getByRole('button', { name: /Commit 2 changes/ }))

    mockUpload().mockResolvedValue(res({
      dry_run: false, plan_hash: 'hash-2',
      errors: ["Plan changed since preview: previewed plan hash 'hash-1' does not match this file's plan 'hash-2'"],
    }))
    await userEvent.click(screen.getByRole('button', { name: /Commit 2 changes/ }))

    await waitFor(() => expect(screen.getByText(/Nothing was applied/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /Commit/ })).toBeDisabled()
  })

  it('shows the stale view when the fresh plan has conflicts', async () => {
    mockUpload().mockResolvedValue(res())
    renderRow()
    await dropFile()
    await waitFor(() => screen.getByRole('button', { name: /Commit 2 changes/ }))

    mockUpload().mockResolvedValue(res({
      dry_run: false, plan_hash: 'hash-1',
      errors: ['Row 4: [chain_rename_conflict] target already exists'],
    }, { ...PLAN, conflicts: [{ row: 4, kind: 'chain_rename_conflict', detail: 'target already exists' }] }))
    await userEvent.click(screen.getByRole('button', { name: /Commit 2 changes/ }))

    await waitFor(() => expect(screen.getByText(/Nothing was applied/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /Commit/ })).toBeDisabled()
  })

  it('re-arms commit only after the researcher confirms the new plan', async () => {
    mockUpload().mockResolvedValue(res())
    renderRow()
    await dropFile()
    await waitFor(() => screen.getByRole('button', { name: /Commit 2 changes/ }))

    mockUpload().mockResolvedValue(res({ dry_run: false, plan_hash: 'hash-2', errors: ['Plan changed since preview'] }))
    await userEvent.click(screen.getByRole('button', { name: /Commit 2 changes/ }))
    await waitFor(() => screen.getByText(/Nothing was applied/i))

    await userEvent.click(screen.getByRole('checkbox', { name: /reviewed the updated plan/i }))
    expect(screen.getByRole('button', { name: /Commit 2 changes/ })).toBeEnabled()
  })
})
