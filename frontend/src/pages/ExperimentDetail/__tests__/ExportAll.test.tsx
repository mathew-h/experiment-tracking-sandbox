import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '@/components/ui'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    get: vi.fn(),
    getReplicateGroup: vi.fn(),
    getResults: vi.fn(),
    getRollup: vi.fn(),
    exportAll: vi.fn(),
  },
}))
vi.mock('@/api/conditions', () => ({
  conditionsApi: { getByExperiment: vi.fn().mockRejectedValue(new Error('none')) },
}))

import { ExperimentDetailPage } from '../index'
import { experimentsApi } from '@/api/experiments'
import type { ExperimentDetail } from '@/api/experiments'

const DETAIL: ExperimentDetail = {
  id: 7, experiment_id: 'HPHT_070-2', experiment_number: 170, status: 'COMPLETED',
  researcher: null, date: null, sample_id: null, base_experiment_id: 'HPHT_070',
  parent_experiment_fk: 6, replicate_label: null, is_outlier: false,
  id_timepoint_days: null, created_at: '2026-07-01T00:00:00Z', updated_at: null,
  conditions: null, notes: [], modifications: [],
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <MemoryRouter initialEntries={['/experiments/HPHT_070-2']}>
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <Routes>
            <Route path="/experiments/:id" element={<ExperimentDetailPage />} />
          </Routes>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('Experiment Detail: Export all', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(experimentsApi.get).mockResolvedValue(DETAIL)
    vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
      base_experiment_id: 'HPHT_070', parent: null, members: [],
    })
  })

  it('shows the button and exports this experiment (the server expands the lineage)', async () => {
    vi.mocked(experimentsApi.exportAll).mockResolvedValue('HPHT_070_export_2026-11-06.xlsx')
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Export all' }))
    expect(experimentsApi.exportAll).toHaveBeenCalledWith('HPHT_070-2')
    expect(await screen.findByText('HPHT_070_export_2026-11-06.xlsx')).toBeInTheDocument()
  })

  it('reports a failed export', async () => {
    vi.mocked(experimentsApi.exportAll).mockRejectedValue(new Error('Network Error'))
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Export all' }))
    expect(await screen.findByText('Export failed')).toBeInTheDocument()
  })
})
