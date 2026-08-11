import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    getResults: vi.fn(),
    setBackgroundAmmonium: vi.fn(),
    getReplicateGroup: vi.fn(),
    getGroup: vi.fn(),
    getGroupRollup: vi.fn(),
  },
}))
vi.mock('@/api/results', () => ({
  resultsApi: { getScalar: vi.fn(), getIcp: vi.fn() },
}))

import { ResultsTab } from '../ResultsTab'
import { experimentsApi } from '@/api/experiments'
import type { ReplicateGroupDetail, ReplicateGroupMemberDetail } from '@/api/experiments'

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>,
  )
}

/** SERUM_pH_002-t1/-t3/-t7/-t20 — one experiment sampled four times, no letters. */
const VIALS: ReplicateGroupMemberDetail[] = [1, 3, 7, 20].map((day, i) => ({
  id: 30 + i, experiment_id: `SERUM_pH_002-t${day}`, replicate_label: null,
  status: 'COMPLETED', is_outlier: false, id_timepoint_days: day,
  researcher: null, date: null, result_count: 1, conditions: {},
}))

function groupWith(members: ReplicateGroupMemberDetail[]): ReplicateGroupDetail {
  return {
    base_experiment_id: 'SERUM_pH_002', parent: null,
    members, member_count: members.length,
    replicates: [], replicate_count: 0,
    shared_conditions: {}, divergent_fields: [],
    additives_summary: null, additive_names: null, additives_diverge: false,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(experimentsApi.getResults).mockResolvedValue([])
  vi.mocked(experimentsApi.getGroupRollup).mockResolvedValue([])
  // The pinned /{id}/replicate-group wrapper is letter-only, so it reports no
  // members for a letterless vial — it must not be what gates the toggle.
  vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
    base_experiment_id: 'SERUM_pH_002',
    parent: {
      id: 30, experiment_id: 'SERUM_pH_002-t1', replicate_label: null,
      status: 'COMPLETED', is_outlier: false,
    },
    members: [],
  })
})

describe('ResultsTab — issue #101: grouped view for a letterless vial set', () => {
  it('offers the grouped toggle for a vial whose stem has several vials', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(groupWith(VIALS))

    wrap(<ResultsTab experimentId="SERUM_pH_002-t1" experimentFk={30} />)

    const grouped = await screen.findByRole('button', { name: /grouped/i })
    expect(grouped).toHaveTextContent('4')
    expect(screen.getByRole('button', { name: /individual/i })).toBeInTheDocument()
  })

  it('switches to the grouped view when the toggle is clicked', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(groupWith(VIALS))
    const user = userEvent.setup()

    wrap(<ResultsTab experimentId="SERUM_pH_002-t1" experimentFk={30} />)

    await user.click(await screen.findByRole('button', { name: /grouped/i }))

    await waitFor(() =>
      expect(experimentsApi.getGroupRollup).toHaveBeenCalledWith('SERUM_pH_002'),
    )
  })

  it('offers no grouped toggle for a lone vial', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(groupWith([VIALS[0]]))

    wrap(<ResultsTab experimentId="SERUM_pH_002-t1" experimentFk={30} />)

    await waitFor(() => expect(experimentsApi.getGroup).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: /grouped/i })).not.toBeInTheDocument()
  })

  it('offers no grouped toggle for a standalone experiment', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(groupWith([]))

    wrap(<ResultsTab experimentId="SERUM_099" experimentFk={99} />)

    await waitFor(() => expect(experimentsApi.getGroup).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: /grouped/i })).not.toBeInTheDocument()
  })

  it('still offers the grouped toggle for a lettered replicate set', async () => {
    vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
      base_experiment_id: 'SERUM_001',
      parent: null,
      members: [
        { id: 2, experiment_id: 'SERUM_001a', replicate_label: 'a', status: 'ONGOING', is_outlier: false },
        { id: 3, experiment_id: 'SERUM_001b', replicate_label: 'b', status: 'ONGOING', is_outlier: false },
      ],
    })
    vi.mocked(experimentsApi.getGroup).mockResolvedValue({
      ...groupWith([]), base_experiment_id: 'SERUM_001',
    })

    wrap(<ResultsTab experimentId="SERUM_001a" experimentFk={2} />)

    expect(await screen.findByRole('button', { name: /grouped/i })).toBeInTheDocument()
  })
})
