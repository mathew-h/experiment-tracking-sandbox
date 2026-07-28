import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    getGroup: vi.fn(),
    getGroupRollup: vi.fn(),
    getResults: vi.fn(),
  },
}))

import { ReplicateGroupPage } from '../index'
import { experimentsApi } from '@/api/experiments'
import type { ReplicateGroupDetail } from '@/api/experiments'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 0 } },
})

function renderAtBase(baseId: string) {
  return render(
    <MemoryRouter initialEntries={[`/experiments/groups/${baseId}`]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/experiments/groups/:baseId" element={<ReplicateGroupPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

const ORPHAN_GROUP: ReplicateGroupDetail = {
  base_experiment_id: 'SERUM_001',
  parent: null,
  members: [
    {
      id: 2, experiment_id: 'SERUM_001a', replicate_label: 'a', status: 'ONGOING', is_outlier: false,
      id_timepoint_days: null, researcher: 'MH', date: null, result_count: 2, conditions: {},
    },
    {
      id: 3, experiment_id: 'SERUM_001b', replicate_label: 'b', status: 'ONGOING', is_outlier: false,
      id_timepoint_days: null, researcher: 'MH', date: null, result_count: 2, conditions: {},
    },
    {
      id: 4, experiment_id: 'SERUM_001c', replicate_label: 'c', status: 'COMPLETED', is_outlier: false,
      id_timepoint_days: null, researcher: 'MH', date: null, result_count: 2, conditions: {},
    },
  ],
  member_count: 3,
  shared_conditions: { experiment_type: 'Serum' },
  divergent_fields: [],
  additives_summary: 'Magnetite 1 g',
  additive_names: 'Magnetite',
  additives_diverge: false,
}

beforeEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
  vi.mocked(experimentsApi.getGroupRollup).mockResolvedValue([])
  vi.mocked(experimentsApi.getResults).mockResolvedValue([])
})

describe('ReplicateGroupPage', () => {
  it('renders an orphan set (no parent) with the read-only notice and each member link', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(ORPHAN_GROUP)
    renderAtBase('SERUM_001')

    await waitFor(() =>
      expect(screen.getByText('This is a grouped experiment view — you may only edit individual replicates.'))
        .toBeInTheDocument()
    )

    expect(screen.getByRole('heading', { name: 'SERUM_001' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'SERUM_001a' })).toHaveAttribute('href', '/experiments/SERUM_001a')
    expect(screen.getByRole('link', { name: 'SERUM_001b' })).toHaveAttribute('href', '/experiments/SERUM_001b')
    expect(screen.getByRole('link', { name: 'SERUM_001c' })).toHaveAttribute('href', '/experiments/SERUM_001c')
    // No parent row rendered when parent is null.
    expect(screen.queryByText('0 (parent)')).not.toBeInTheDocument()
  })

  it('shows the additive summary when additives do not diverge', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(ORPHAN_GROUP)
    renderAtBase('SERUM_001')
    await waitFor(() => expect(screen.getByText('Magnetite 1 g')).toBeInTheDocument())
  })

  it('renders a divergent field as "varies" in the shared panel and per-member in the table', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue({
      ...ORPHAN_GROUP,
      divergent_fields: ['temperature_c'],
      members: ORPHAN_GROUP.members.map((m, i) => ({
        ...m,
        conditions: { temperature_c: 60 + i },
      })),
    })
    renderAtBase('SERUM_001')

    await waitFor(() => expect(screen.getByRole('columnheader', { name: 'Temperature C' })).toBeInTheDocument())
    expect(screen.getByText(/varies/i)).toBeInTheDocument()
    expect(screen.getByText('60')).toBeInTheDocument()
    expect(screen.getByText('61')).toBeInTheDocument()
    expect(screen.getByText('62')).toBeInTheDocument()
  })

  it('shows the explicit "additives vary" message and no summary when additives_diverge is true', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue({
      ...ORPHAN_GROUP,
      additives_diverge: true,
      additives_summary: null,
      additive_names: null,
    })
    renderAtBase('SERUM_001')

    await waitFor(() =>
      expect(screen.getByText('Additives vary across replicates — see individual experiments'))
        .toBeInTheDocument()
    )
    expect(screen.queryByText('Magnetite 1 g')).not.toBeInTheDocument()
  })

  it('renders the parent row labeled as replicate 0 when a parent exists', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue({
      ...ORPHAN_GROUP,
      parent: { id: 1, experiment_id: 'SERUM_001', replicate_label: null, status: 'ONGOING', is_outlier: false },
    })
    renderAtBase('SERUM_001')
    await waitFor(() => expect(screen.getByText('0 (parent)')).toBeInTheDocument())
  })

  it('renders a not-found message instead of crashing when the group 404s', async () => {
    vi.mocked(experimentsApi.getGroup).mockRejectedValue(new Error('404'))
    renderAtBase('UNKNOWN_BASE')
    await waitFor(() => expect(screen.getByText('Replicate group not found')).toBeInTheDocument())
  })

  it('issues the group query against the base ID, not a per-experiment endpoint', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(ORPHAN_GROUP)
    renderAtBase('SERUM_001')
    await waitFor(() => expect(experimentsApi.getGroup).toHaveBeenCalledWith('SERUM_001'))
    await waitFor(() => expect(experimentsApi.getGroupRollup).toHaveBeenCalledWith('SERUM_001'))
  })
})
