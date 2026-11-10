import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useLocation, useNavigationType } from 'react-router-dom'
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
import type { ExperimentDetail } from '@/api/experiments'

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
})

describe('experiment detail tab strip (issue #122 PR-B)', () => {
  it('has no Reactor Modifications tab; Notes and Entry Logs remain', async () => {
    renderPage()
    expect(await screen.findByRole('button', { name: /^notes/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /entry logs/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /reactor modifications/i })).toBeNull()
  })
})

describe('experiment detail tab strip (issue #143)', () => {
  it('labels the analysis tab XRD', async () => {
    renderPage()
    expect(await screen.findByRole('button', { name: /^xrd$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^analysis$/i })).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Issue #162 (NAV-21): the active tab lives in ?tab=, so links can open a tab.
// ---------------------------------------------------------------------------

function LocationProbe() {
  const location = useLocation()
  const navType = useNavigationType()
  return <div data-testid="probe" data-search={location.search} data-nav={navType} />
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <Routes>
            <Route
              path="/experiments/:id"
              element={<><ExperimentDetailPage /><LocationProbe /></>}
            />
          </Routes>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

async function activeTab() {
  await screen.findByRole('button', { name: /^xrd$/i })
  return screen
    .getAllByRole('button', { pressed: true })
    .map((b) => b.textContent)
}

describe('experiment detail ?tab= (issue #162)', () => {
  beforeEach(() => {
    vi.mocked(experimentsApi.getResults).mockResolvedValue([])
  })

  it.each([
    ['?tab=results', 'Results'],
    ['?tab=RESULTS', 'Results'],
    ['?tab=notes', 'Notes'],
    ['?tab=xrd', 'XRD'],
    ['?tab=logs', 'Entry Logs'],
    ['?tab=conditions', 'Conditions'],
    ['?tab=bogus', 'Conditions'],
    ['', 'Conditions'],
  ])('%s opens %s', async (query, tab) => {
    renderAt(`/experiments/SERUM_050${query}`)
    expect(await activeTab()).toEqual([tab])
  })

  it('opens the Results tab content for ?tab=results', async () => {
    renderAt('/experiments/SERUM_050?tab=results')
    await screen.findByRole('button', { name: '+ Add Results' })
    expect(experimentsApi.getResults).toHaveBeenCalledWith('SERUM_050')
  })

  it('a tab click writes ?tab= by replacing the history entry', async () => {
    renderAt('/experiments/SERUM_050?keep=1')
    await activeTab()
    await userEvent.click(screen.getByRole('button', { name: /^notes/i }))
    const probe = screen.getByTestId('probe')
    expect(probe.dataset.search).toBe('?keep=1&tab=notes')
    expect(probe.dataset.nav).toBe('REPLACE')
    expect(await activeTab()).toEqual(['Notes'])
  })
})
