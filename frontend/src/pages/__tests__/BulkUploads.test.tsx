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

describe('BulkUploadsPage — layout (issue #74)', () => {
  const ACTIVE_TITLES = [
    'Master Results Sync',
    'ICP-OES Data',
    'XRD Mineralogy',
    'New Experiments',
    'Experiment Status Update',
    'ActLabs Rock Analysis',
  ]

  it('renders the six active widgets in order before the less-used section', () => {
    render(<BulkUploadsPage />, { wrapper })

    const labels = screen.getAllByRole('button').map((b) => b.textContent ?? '')
    const positions = [...ACTIVE_TITLES, 'Less-used uploads'].map((t) =>
      labels.findIndex((l) => l.includes(t))
    )
    expect(positions.every((p) => p >= 0)).toBe(true)
    expect(positions).toEqual([...positions].sort((a, b) => a - b))
  })

  it('hides demoted widgets until the less-used section is expanded', async () => {
    render(<BulkUploadsPage />, { wrapper })

    expect(screen.queryByText('Solution Chemistry')).toBeNull()
    expect(screen.queryByText('Timepoint Modifications')).toBeNull()
    expect(screen.queryByText('Rock Inventory')).toBeNull()
    expect(screen.queryByText('Chemical Inventory')).toBeNull()
    expect(screen.queryByText('Sample Chemical Composition')).toBeNull()
    expect(screen.queryByText('pXRF Readings')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: /Less-used uploads/i }))

    expect(screen.getByText('Solution Chemistry')).toBeInTheDocument()
    expect(screen.getByText('pXRF Readings')).toBeInTheDocument()
  })
})
