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
    getGroup: vi.fn(),
    getGroupRollup: vi.fn(),
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

describe('detail header group strip — issue #101: letterless timepoint vials', () => {
  it('links to the group for a letterless vial whose stem has several vials', async () => {
    vi.mocked(experimentsApi.get).mockResolvedValue({
      ...BASE_DETAIL,
      id: 30,
      experiment_id: 'SERUM_pH_002-t1',
      base_experiment_id: 'SERUM_pH_002',
      replicate_label: null,
      id_timepoint_days: 1,
    })
    // The letter-only wrapper reports this vial as its own parent with no members.
    vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
      base_experiment_id: 'SERUM_pH_002',
      parent: {
        id: 30, experiment_id: 'SERUM_pH_002-t1', replicate_label: null,
        status: 'ONGOING', is_outlier: false,
      },
      members: [],
    })
    vi.mocked(experimentsApi.getGroup).mockResolvedValue({
      base_experiment_id: 'SERUM_pH_002', parent: null,
      members: [1, 3, 7].map((day, i) => ({
        id: 30 + i, experiment_id: `SERUM_pH_002-t${day}`, replicate_label: null,
        status: 'ONGOING' as const, is_outlier: false, id_timepoint_days: day,
        researcher: null, date: null, result_count: 1, conditions: {},
      })),
      member_count: 3, replicates: [], replicate_count: 0,
      shared_conditions: {}, divergent_fields: [],
      additives_summary: null, additive_names: null, additives_diverge: false,
    })

    renderPage('SERUM_pH_002-t1')

    const groupLink = await screen.findByRole('link', { name: 'SERUM_pH_002' })
    expect(groupLink).toHaveAttribute('href', '/experiments/groups/SERUM_pH_002')
    // It is not a replicate, so no "Replicate x" label may appear.
    expect(screen.queryByText(/^Replicate /)).not.toBeInTheDocument()
  })

  it('renders no group link for a lone letterless vial', async () => {
    vi.mocked(experimentsApi.get).mockResolvedValue({
      ...BASE_DETAIL,
      id: 40,
      experiment_id: 'SERUM_pH_050-t5',
      base_experiment_id: 'SERUM_pH_050',
      replicate_label: null,
      id_timepoint_days: 5,
    })
    vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
      base_experiment_id: 'SERUM_pH_050',
      parent: {
        id: 40, experiment_id: 'SERUM_pH_050-t5', replicate_label: null,
        status: 'ONGOING', is_outlier: false,
      },
      members: [],
    })
    vi.mocked(experimentsApi.getGroup).mockResolvedValue({
      base_experiment_id: 'SERUM_pH_050', parent: null,
      members: [{
        id: 40, experiment_id: 'SERUM_pH_050-t5', replicate_label: null,
        status: 'ONGOING', is_outlier: false, id_timepoint_days: 5,
        researcher: null, date: null, result_count: 0, conditions: {},
      }],
      member_count: 1, replicates: [], replicate_count: 0,
      shared_conditions: {}, divergent_fields: [],
      additives_summary: null, additive_names: null, additives_diverge: false,
    })

    renderPage('SERUM_pH_050-t5')

    await screen.findByRole('heading', { name: 'SERUM_pH_050-t5' })
    expect(screen.queryByRole('link', { name: 'SERUM_pH_050' })).not.toBeInTheDocument()
  })
})
