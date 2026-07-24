import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
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
    uploadPXRF: vi.fn(),
    downloadTemplate: vi.fn(),
  },
  isConflictCheckResult: (r: unknown) => (r as { status?: string })?.status === 'warnings',
}))

import { BulkUploadsPage } from '../BulkUploads'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: 0 },
    mutations: { retry: false },
  },
})

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  queryClient.clear()
})

describe('BulkUploadsPage — master results widget (issue #74)', () => {
  it('shows drag-and-drop instructions with the master tracker path and no sync button', async () => {
    render(<BulkUploadsPage />, { wrapper })

    await userEvent.click(screen.getByRole('button', { name: /Master Results Sync/i }))

    expect(
      screen.getByText(/01_R&D\\02_Results\\Master_Reactor_Sampling_Tracker_v2\.xlsx/)
    ).toBeInTheDocument()
    expect(screen.queryByText('Sync from SharePoint')).toBeNull()
  })
})
