import React from 'react'
import { describe, it, expect, vi, beforeEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'

vi.mock('@/api/bulkUploads', () => ({
  bulkUploadsApi: {
    getNextIds: vi.fn().mockResolvedValue({ HPHT: 1, Serum: 1, CF: 1, Autoclave: 1 }),
    uploadMasterResults: vi.fn(),
    uploadIcpOes: vi.fn(),
    uploadXrdMineralogy: vi.fn(),
    uploadScalarResults: vi.fn(),
    uploadNewExperiments: vi.fn(),
    uploadTimepointModifications: vi.fn(),
    uploadRockInventory: vi.fn(),
    uploadChemicalInventory: vi.fn(),
    uploadElementalComposition: vi.fn(),
    uploadActlabsRock: vi.fn(),
    uploadExperimentStatus: vi.fn(),
    uploadExperimentDeletion: vi.fn(),
    uploadPXRF: vi.fn(),
    downloadTemplate: vi.fn(),
  },
  isConflictCheckResult: (r: unknown) => (r as { status?: string })?.status === 'warnings',
}))

import { bulkUploadsApi } from '@/api/bulkUploads'
import { BulkUploadsPage } from '../BulkUploads'

const ROW_TITLE = /Delete Experiments/i

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
  })
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  )
}

/** Expand the less-used section and open the deletion row. */
async function openDeletionRow() {
  render(<BulkUploadsPage />, { wrapper })
  await userEvent.click(screen.getByRole('button', { name: /Less-used uploads/i }))
  await userEvent.click(screen.getByRole('button', { name: ROW_TITLE }))
}

async function dropFile(file: File) {
  const inputs = Array.from(
    document.querySelectorAll('input[type="file"]'),
  ) as HTMLInputElement[]
  // The deletion row is the last one rendered, so its input is the last input.
  await userEvent.upload(inputs[inputs.length - 1], file)
}

const CSV = new File(
  ['experiment_id\nBDEL_001\nBDEL_002\n\n'],
  'cleanup.csv',
  { type: 'text/csv' },
)

const confirmSpy = vi.spyOn(window, 'confirm')

beforeEach(() => {
  vi.clearAllMocks()
  confirmSpy.mockReturnValue(true)
})

afterAll(() => {
  confirmSpy.mockRestore()
})

describe('BulkUploadsPage — bulk experiment deletion row (issue #109)', () => {
  it('is hidden until the less-used section is expanded', async () => {
    render(<BulkUploadsPage />, { wrapper })

    expect(screen.queryByText(ROW_TITLE)).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: /Less-used uploads/i }))

    expect(screen.getByText(ROW_TITLE)).toBeInTheDocument()
  })

  it('confirms with the row count parsed from a CSV before deleting anything', async () => {
    vi.mocked(bulkUploadsApi.uploadExperimentDeletion).mockResolvedValue({
      created: 0, updated: 2, skipped: 0, errors: [], warnings: [], feedbacks: [], message: 'ok',
    })

    await openDeletionRow()
    await dropFile(CSV)

    await waitFor(() => expect(confirmSpy).toHaveBeenCalledTimes(1))
    expect(confirmSpy.mock.calls[0][0]).toContain('2')
    expect(confirmSpy.mock.calls[0][0]).toMatch(/cannot be undone/i)
    await waitFor(() =>
      expect(bulkUploadsApi.uploadExperimentDeletion).toHaveBeenCalledWith(CSV),
    )
  })

  it('does not call the endpoint when the confirmation is dismissed', async () => {
    confirmSpy.mockReturnValue(false)

    await openDeletionRow()
    await dropFile(CSV)

    await waitFor(() => expect(confirmSpy).toHaveBeenCalled())
    expect(bulkUploadsApi.uploadExperimentDeletion).not.toHaveBeenCalled()
  })

  it('names the file in the confirmation when the count cannot be read client-side', async () => {
    vi.mocked(bulkUploadsApi.uploadExperimentDeletion).mockResolvedValue({
      created: 0, updated: 1, skipped: 0, errors: [], warnings: [], feedbacks: [], message: 'ok',
    })

    await openDeletionRow()
    await dropFile(new File(['binary'], 'cleanup.xlsx'))

    await waitFor(() => expect(confirmSpy).toHaveBeenCalledTimes(1))
    expect(confirmSpy.mock.calls[0][0]).toContain('cleanup.xlsx')
  })

  it('labels the result badges for deletion, not for an upsert', async () => {
    vi.mocked(bulkUploadsApi.uploadExperimentDeletion).mockResolvedValue({
      created: 0,
      updated: 2,
      skipped: 1,
      errors: ['BDEL_LOCKED: row is locked'],
      warnings: ['Deleted: BDEL_001', 'Deleted: BDEL_002', 'Not found, nothing deleted: BDEL_TYPO'],
      feedbacks: [],
      message: 'Deleted 2 experiment(s), 1 not found, 1 failed',
    })

    await openDeletionRow()
    await dropFile(CSV)

    await waitFor(() => expect(screen.getByText('Deleted: 2')).toBeInTheDocument())
    expect(screen.getByText('Not found: 1')).toBeInTheDocument()
    expect(screen.queryByText(/^Created:/)).toBeNull()
  })

  it('shows the deleted, missing and failed IDs after the response', async () => {
    vi.mocked(bulkUploadsApi.uploadExperimentDeletion).mockResolvedValue({
      created: 0,
      updated: 2,
      skipped: 1,
      errors: ['BDEL_LOCKED: row is locked'],
      warnings: ['Deleted: BDEL_001', 'Deleted: BDEL_002', 'Not found, nothing deleted: BDEL_TYPO'],
      feedbacks: [],
      message: 'Deleted 2 experiment(s), 1 not found, 1 failed',
    })

    await openDeletionRow()
    await dropFile(CSV)

    await waitFor(() => expect(screen.getByText('Deleted: BDEL_001')).toBeInTheDocument())
    expect(screen.getByText('Deleted: BDEL_002')).toBeInTheDocument()
    expect(screen.getByText('Not found, nothing deleted: BDEL_TYPO')).toBeInTheDocument()
    expect(screen.getByText('BDEL_LOCKED: row is locked')).toBeInTheDocument()
  })
})
