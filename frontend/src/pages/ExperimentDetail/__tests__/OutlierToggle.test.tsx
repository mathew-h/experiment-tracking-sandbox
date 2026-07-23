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

const BASE_DETAIL: ExperimentDetail = {
  id: 2,
  experiment_id: 'SERUM_001a',
  experiment_number: 101,
  status: 'ONGOING',
  researcher: null,
  date: null,
  sample_id: null,
  base_experiment_id: 'SERUM_001',
  parent_experiment_fk: 1,
  replicate_label: 'a',
  is_outlier: false,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: null,
  conditions: null,
  notes: [],
  modifications: [],
}

beforeEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
  vi.mocked(experimentsApi.get).mockResolvedValue(BASE_DETAIL)
  vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
    base_experiment_id: 'SERUM_001',
    parent: { id: 1, experiment_id: 'SERUM_001', replicate_label: null, status: 'ONGOING', is_outlier: false },
    members: [{ id: 2, experiment_id: 'SERUM_001a', replicate_label: 'a', status: 'ONGOING', is_outlier: false }],
  })
  vi.mocked(experimentsApi.patch).mockResolvedValue({ ...BASE_DETAIL, is_outlier: true })
})

describe('outlier toggle', () => {
  it('shows Mark as outlier for a replicate member and patches on click', async () => {
    const user = userEvent.setup()
    renderPage('SERUM_001a')
    const btn = await screen.findByRole('button', { name: /mark as outlier/i })
    await user.click(btn)
    await waitFor(() =>
      expect(experimentsApi.patch).toHaveBeenCalledWith('SERUM_001a', { is_outlier: true }),
    )
  })

  it('shows badge and Include in rollup when flagged', async () => {
    vi.mocked(experimentsApi.get).mockResolvedValue({ ...BASE_DETAIL, is_outlier: true })
    renderPage('SERUM_001a')
    expect(await screen.findByRole('button', { name: /include in rollup/i })).toBeInTheDocument()
    expect(screen.getByText(/excluded from group stats/i)).toBeInTheDocument()
  })

  it('hides the toggle for a standalone experiment', async () => {
    vi.mocked(experimentsApi.get).mockResolvedValue({
      ...BASE_DETAIL, experiment_id: 'SERUM_099', base_experiment_id: null,
      parent_experiment_fk: null, replicate_label: null,
    })
    vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
      base_experiment_id: 'SERUM_099',
      parent: { id: 9, experiment_id: 'SERUM_099', replicate_label: null, status: 'ONGOING', is_outlier: false },
      members: [],
    })
    renderPage('SERUM_099')
    await screen.findByRole('heading', { name: 'SERUM_099' })
    expect(screen.queryByRole('button', { name: /mark as outlier/i })).not.toBeInTheDocument()
  })
})
