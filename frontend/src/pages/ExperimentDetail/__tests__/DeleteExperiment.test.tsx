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
    getDeleteImpact: vi.fn(),
    delete: vi.fn(),
  },
}))
vi.mock('@/api/conditions', () => ({
  conditionsApi: { getByExperiment: vi.fn().mockRejectedValue(new Error('none')) },
}))

import { ExperimentDetailPage } from '../index'
import { experimentsApi } from '@/api/experiments'
import type { ExperimentDetail, DeleteImpact } from '@/api/experiments'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
})

const BASE_DETAIL: ExperimentDetail = {
  id: 5, experiment_id: 'SERUM_050', experiment_number: 150, status: 'ONGOING',
  researcher: null, date: null, sample_id: null, base_experiment_id: null,
  parent_experiment_fk: null, replicate_label: null, is_outlier: false,
  id_timepoint_days: null, created_at: '2026-07-01T00:00:00Z', updated_at: null,
  conditions: null, notes: [], modifications: [],
}

const EMPTY_IMPACT: DeleteImpact = {
  experiment_id: 'SERUM_050',
  conditions: 0,
  results: 0, scalar_results: 0, icp_results: 0, result_files: 0, notes: 0,
  additives: 0, external_analyses: 0, xrd_phases: 0, change_requests: 0,
  total: 0, background_for: [], replicate_children: [],
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/experiments/SERUM_050']}>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <Routes>
            <Route path="/experiments/:id" element={<ExperimentDetailPage />} />
            <Route path="/experiments" element={<div>Experiments List</div>} />
          </Routes>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
  vi.mocked(experimentsApi.get).mockResolvedValue(BASE_DETAIL)
  vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
    base_experiment_id: 'SERUM_050', parent: null, members: [],
  })
  vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue(EMPTY_IMPACT)
  vi.mocked(experimentsApi.delete).mockResolvedValue({
    experiment_id: 'SERUM_050', deleted: true, impact: EMPTY_IMPACT,
  })
})

describe('experiment deletion from the detail page', () => {
  it('exposes a Delete Experiment action', async () => {
    renderPage()
    expect(
      await screen.findByRole('button', { name: /delete experiment/i }),
    ).toBeInTheDocument()
  })

  it('opens the confirmation dialog rather than deleting immediately', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /delete experiment/i }))
    expect(await screen.findByText(/permanently delete/i)).toBeInTheDocument()
    expect(experimentsApi.delete).not.toHaveBeenCalled()
  })

  it('deletes and navigates back to the list on success', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /delete experiment/i }))
    await user.click(await screen.findByRole('button', { name: /^delete$/i }))
    await waitFor(() => expect(experimentsApi.delete).toHaveBeenCalledWith('SERUM_050'))
    expect(await screen.findByText('Experiments List')).toBeInTheDocument()
  })

  it('evicts the experiment and delete-impact caches and refreshes group-rollup, not the dead rollup key', async () => {
    const removeSpy = vi.spyOn(queryClient, 'removeQueries')
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /delete experiment/i }))
    await user.click(await screen.findByRole('button', { name: /^delete$/i }))
    await waitFor(() => expect(experimentsApi.delete).toHaveBeenCalledWith('SERUM_050'))

    // Every cache keyed by the experiment ID must be evicted, not invalidated:
    // the freed ID can be reused, so a stale entry must not be readable at all.
    for (const key of [
      'experiment', 'delete-impact', 'conditions', 'additives',
      'experiment-results', 'changeRequests', 'reactorModificationRecent',
      'xrd', 'external-analysis', 'replicate-group',
    ]) {
      expect(removeSpy).toHaveBeenCalledWith({ queryKey: [key, 'SERUM_050'] })
    }
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['group-rollup'] })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['rollup'] })

    removeSpy.mockRestore()
    invalidateSpy.mockRestore()
  })
})
