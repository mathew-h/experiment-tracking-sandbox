import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
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
import type { ExperimentDetail, ReplicateGroup } from '@/api/experiments'

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
  parent_experiment_fk: null,
  replicate_label: 'a',
  is_outlier: false,
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
})

describe('detail header group strip', () => {
  it('renders for a lettered replicate in an orphan set: Group link and sibling chips', async () => {
    vi.mocked(experimentsApi.get).mockResolvedValue({
      ...BASE_DETAIL,
      id: 12,
      experiment_id: 'SERUM_001b',
      replicate_label: 'b',
    })
    const group: ReplicateGroup = {
      base_experiment_id: 'SERUM_001',
      parent: null,
      members: [
        { id: 11, experiment_id: 'SERUM_001a', replicate_label: 'a', status: 'ONGOING', is_outlier: false },
        { id: 12, experiment_id: 'SERUM_001b', replicate_label: 'b', status: 'ONGOING', is_outlier: false },
        { id: 13, experiment_id: 'SERUM_001c', replicate_label: 'c', status: 'ONGOING', is_outlier: false },
      ],
    }
    vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue(group)

    renderPage('SERUM_001b')

    const groupLink = await screen.findByRole('link', { name: 'SERUM_001' })
    expect(groupLink).toHaveAttribute('href', '/experiments/groups/SERUM_001')

    const chipA = screen.getByRole('link', { name: 'a' })
    expect(chipA).toHaveAttribute('href', '/experiments/SERUM_001a')
    const chipC = screen.getByRole('link', { name: 'c' })
    expect(chipC).toHaveAttribute('href', '/experiments/SERUM_001c')

    // Current chip (b) is inactive — rendered as text, not a link
    expect(screen.queryByRole('link', { name: 'b' })).not.toBeInTheDocument()
    expect(screen.getByText('[b]')).toBeInTheDocument()

    expect(screen.getByText(/replicate b/i)).toBeInTheDocument()
  })

  it('renders nothing for a non-replicate, member-less experiment', async () => {
    vi.mocked(experimentsApi.get).mockResolvedValue({
      ...BASE_DETAIL,
      id: 9,
      experiment_id: 'SERUM_099',
      base_experiment_id: null,
      parent_experiment_fk: null,
      replicate_label: null,
    })
    vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
      base_experiment_id: 'SERUM_099',
      parent: {
        id: 9,
        experiment_id: 'SERUM_099',
        replicate_label: null,
        status: 'ONGOING',
        is_outlier: false,
      },
      members: [],
    })

    renderPage('SERUM_099')

    await screen.findByRole('heading', { name: 'SERUM_099' })
    expect(screen.queryByRole('link', { name: 'SERUM_099' })).not.toBeInTheDocument()
    expect(screen.queryByText(/^Replicate /)).not.toBeInTheDocument()
  })

  it('renders both chips when two members share a letter (letter + timepoint vial)', async () => {
    vi.mocked(experimentsApi.get).mockResolvedValue({
      ...BASE_DETAIL,
      id: 21,
      experiment_id: 'SERUM_001a',
      replicate_label: 'a',
    })
    const group: ReplicateGroup = {
      base_experiment_id: 'SERUM_001',
      parent: null,
      members: [
        { id: 21, experiment_id: 'SERUM_001a', replicate_label: 'a', status: 'ONGOING', is_outlier: false },
        { id: 22, experiment_id: 'SERUM_001a-t7', replicate_label: 'a', status: 'ONGOING', is_outlier: false },
      ],
    }
    vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue(group)

    renderPage('SERUM_001a')

    // Current experiment (id 21) is the inactive bracketed chip
    expect(await screen.findByText('[a]')).toBeInTheDocument()
    // Sibling (id 22) shares the same label text but renders as its own link, keyed by id
    const siblingChip = screen.getByRole('link', { name: 'a' })
    expect(siblingChip).toHaveAttribute('href', '/experiments/SERUM_001a-t7')
  })
})
