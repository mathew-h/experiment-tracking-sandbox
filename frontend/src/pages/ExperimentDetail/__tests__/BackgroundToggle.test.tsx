import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '@/components/ui'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    get: vi.fn(),
    patch: vi.fn(),
    getReplicateGroup: vi.fn(),
    getResults: vi.fn(),
    getRollup: vi.fn(),
  },
}))
vi.mock('@/api/conditions', () => ({
  conditionsApi: { getByExperiment: vi.fn().mockRejectedValue(new Error('none')) },
}))

import { ExperimentDetailPage } from '../index'
import { experimentsApi } from '@/api/experiments'
import type { ExperimentDetail } from '@/api/experiments'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
})

function renderPage(experimentId: string) {
  return render(
    <MemoryRouter initialEntries={[`/experiments/${experimentId}`]}>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <Routes>
            <Route path="/experiments/:id" element={<ExperimentDetailPage />} />
          </Routes>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

// A standalone experiment: the background toggle shows even outside a replicate set.
const DETAIL: ExperimentDetail = {
  id: 9,
  experiment_id: 'SERUM_BG_002',
  experiment_number: 909,
  status: 'ONGOING',
  researcher: null,
  date: null,
  sample_id: null,
  base_experiment_id: null,
  parent_experiment_fk: null,
  replicate_label: null,
  is_outlier: false,
  is_background: false,
  id_timepoint_days: null,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: null,
  conditions: null,
  notes: [],
  modifications: [],
}

beforeEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
  vi.mocked(experimentsApi.get).mockResolvedValue(DETAIL)
  vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
    base_experiment_id: 'SERUM_BG_002',
    parent: { id: 9, experiment_id: 'SERUM_BG_002', replicate_label: null, status: 'ONGOING', is_outlier: false },
    members: [],
  })
  vi.mocked(experimentsApi.patch).mockResolvedValue({ ...DETAIL, is_background: true })
})

describe('background toggle (issue #152)', () => {
  it('patches is_background on a standalone experiment', async () => {
    const user = userEvent.setup()
    renderPage('SERUM_BG_002')
    await user.click(await screen.findByRole('button', { name: 'Mark as background' }))
    await waitFor(() =>
      expect(experimentsApi.patch).toHaveBeenCalledWith('SERUM_BG_002', { is_background: true }),
    )
  })

  it('shows the badge and the unmark action when flagged', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.get).mockResolvedValue({ ...DETAIL, is_background: true })
    renderPage('SERUM_BG_002')
    expect(await screen.findByText('Background')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Unmark background' }))
    await waitFor(() =>
      expect(experimentsApi.patch).toHaveBeenCalledWith('SERUM_BG_002', { is_background: false }),
    )
  })
})
