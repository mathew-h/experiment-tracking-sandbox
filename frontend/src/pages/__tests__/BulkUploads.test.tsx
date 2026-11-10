import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
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

    await userEvent.click(screen.getByRole('button', { name: /New Experiments/i }))

    const newExperimentsHelpText = screen
      .getAllByText(/-t<days>/)
      .find((el) => el.textContent?.includes('SERUM_001a-t0'))
    expect(newExperimentsHelpText).toBeInTheDocument()
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

describe('BulkUploadsPage — ICP upload names what it wrote to (issue #162)', () => {
  it('lists the touched experiments as Results-tab links after a drop', async () => {
    const { bulkUploadsApi } = await import('@/api/bulkUploads')
    vi.mocked(bulkUploadsApi.uploadIcpOes).mockResolvedValue({
      created: 1, updated: 1, skipped: 0, errors: [], warnings: [], feedbacks: [],
      message: 'ICP-OES: 1 created, 1 updated',
      touched: [
        { experiment_id: 'HPHT_297-2', time_post_reaction_days: 3 },
        { experiment_id: 'SERUM_001a-t5', time_post_reaction_days: 5 },
      ],
    })
    render(
      <MemoryRouter>
        <BulkUploadsPage />
      </MemoryRouter>,
      { wrapper },
    )
    await userEvent.click(screen.getByRole('button', { name: /ICP-OES Data/ }))
    const row = screen.getByRole('button', { name: /ICP-OES Data/ }).parentElement as HTMLElement
    const input = row.querySelector('input[type="file"]') as HTMLInputElement
    await userEvent.upload(input, new File(['x'], 'icp.csv', { type: 'text/csv' }))
    expect(await screen.findByText('Wrote to 2 experiments')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'HPHT_297-2' })).toHaveAttribute(
      'href', '/experiments/HPHT_297-2?tab=results')
    expect(screen.getByRole('link', { name: 'SERUM_001a-t5' })).toHaveAttribute(
      'href', '/experiments/SERUM_001a-t5?tab=results')
  })
})
