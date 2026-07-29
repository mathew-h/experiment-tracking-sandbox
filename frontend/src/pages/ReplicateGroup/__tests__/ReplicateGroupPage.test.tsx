import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import userEvent from '@testing-library/user-event'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    getGroup: vi.fn(),
    getGroupRollup: vi.fn(),
    getResults: vi.fn(),
  },
}))

import { ReplicateGroupPage } from '../index'
import { experimentsApi } from '@/api/experiments'
import type {
  ReplicateGroupDetail,
  ReplicateGroupMemberDetail,
  ReplicateLetterGroup,
} from '@/api/experiments'

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

const ORPHAN_MEMBERS: ReplicateGroupMemberDetail[] = [
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
]

const ORPHAN_GROUP: ReplicateGroupDetail = {
  base_experiment_id: 'SERUM_001',
  parent: null,
  members: ORPHAN_MEMBERS,
  member_count: 3,
  replicate_count: 3,
  replicates: [
    { replicate_label: 'a', vials: [ORPHAN_MEMBERS[0]] },
    { replicate_label: 'b', vials: [ORPHAN_MEMBERS[1]] },
    { replicate_label: 'c', vials: [ORPHAN_MEMBERS[2]] },
  ],
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
    const updatedMembers = ORPHAN_GROUP.members.map((m, i) => ({
      ...m,
      conditions: { temperature_c: 60 + i },
    }))
    vi.mocked(experimentsApi.getGroup).mockResolvedValue({
      ...ORPHAN_GROUP,
      divergent_fields: ['temperature_c'],
      members: updatedMembers,
      // Table rows now come from `replicates` (issue #98), which must carry
      // the same updated conditions as `members` for this fixture to be internally consistent.
      replicates: ORPHAN_GROUP.replicates.map((r, i) => ({
        ...r,
        vials: [updatedMembers[i]],
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
      parent: {
        id: 1, experiment_id: 'SERUM_001', replicate_label: null, status: 'ONGOING', is_outlier: false,
        id_timepoint_days: null, researcher: null, date: null, result_count: 0, conditions: {},
      },
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

  it('does not render shared-condition labels whose value is null', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue({
      ...ORPHAN_GROUP,
      shared_conditions: {
        experiment_type: 'Serum',
        temperature_c: 90,
        co2_partial_pressure_MPa: null,
        confining_pressure: null,
      },
    })
    renderAtBase('SERUM_001')

    await waitFor(() => expect(screen.getByText('Temperature C:')).toBeInTheDocument())
    expect(screen.queryByText('Co2 Partial Pressure MPa:')).not.toBeInTheDocument()
    expect(screen.queryByText('Confining Pressure:')).not.toBeInTheDocument()
  })

  it('rounds a long float to 3 decimal places', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue({
      ...ORPHAN_GROUP,
      shared_conditions: {
        ...ORPHAN_GROUP.shared_conditions,
        total_ferrous_iron_g: 0.4088873141807,
      },
    })
    renderAtBase('SERUM_001')

    await waitFor(() => expect(screen.getByText('0.409')).toBeInTheDocument())
  })

  it('renders an integer-valued condition without a trailing decimal', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue({
      ...ORPHAN_GROUP,
      shared_conditions: {
        ...ORPHAN_GROUP.shared_conditions,
        temperature_c: 90,
        initial_ph: 8,
      },
    })
    renderAtBase('SERUM_001')

    await waitFor(() => expect(screen.getByText('90')).toBeInTheDocument())
    expect(screen.getByText('8')).toBeInTheDocument()
    expect(screen.queryByText('90.000')).not.toBeInTheDocument()
  })

  it('still renders a divergent field label and the "varies" text when its shared value is absent', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue({
      ...ORPHAN_GROUP,
      divergent_fields: ['temperature_c'],
      members: ORPHAN_GROUP.members.map((m, i) => ({
        ...m,
        conditions: { temperature_c: 60 + i },
      })),
    })
    renderAtBase('SERUM_001')

    await waitFor(() => expect(screen.getByText('Temperature C:')).toBeInTheDocument())
    expect(screen.getByText('varies — see members table')).toBeInTheDocument()
  })
})

describe('ReplicateGroupPage — issue #98 letter nesting', () => {
  function vial(
    id: number, experimentId: string, day: number | null,
  ): ReplicateGroupMemberDetail {
    return {
      id, experiment_id: experimentId, replicate_label: 'a',
      status: 'ONGOING', is_outlier: false,
      id_timepoint_days: day, researcher: null, date: null,
      result_count: 1, conditions: {},
    }
  }

  function groupWith(
    baseId: string, replicates: ReplicateLetterGroup[],
  ): ReplicateGroupDetail {
    const members = replicates.flatMap((r) => r.vials)
    return {
      base_experiment_id: baseId, parent: null, members,
      member_count: members.length, replicates,
      replicate_count: replicates.length,
      shared_conditions: {}, divergent_fields: [],
      additives_summary: null, additive_names: null, additives_diverge: false,
    }
  }

  it('header counts letters, not vials', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(
      groupWith('SERUM_001', [
        { replicate_label: 'a', vials: [vial(1, 'SERUM_001a-t1', 1), vial(2, 'SERUM_001a-t3', 3)] },
      ]),
    )
    renderAtBase('SERUM_001')
    // 2 vials, 1 letter -> the header must say "1 replicate".
    await waitFor(() => expect(screen.getByText('1 replicate')).toBeInTheDocument())
  })

  it('a multi-vial letter is one collapsed row that expands to its vials', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(
      groupWith('SERUM_001', [
        { replicate_label: 'a', vials: [vial(1, 'SERUM_001a-t1', 1), vial(2, 'SERUM_001a-t3', 3)] },
      ]),
    )
    renderAtBase('SERUM_001')

    await waitFor(() => expect(screen.getByText('2 vials')).toBeInTheDocument())
    expect(screen.queryByText('SERUM_001a-t1')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /expand replicate a/i }))
    expect(screen.getByRole('link', { name: 'SERUM_001a-t1' })).toBeInTheDocument()
    expect(screen.getByText('T+3')).toBeInTheDocument()
  })

  it('a single-vial letter renders as a plain row with no expander (D10)', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(
      groupWith('SERUM_002', [
        { replicate_label: 'a', vials: [vial(1, 'SERUM_002a', null)] },
      ]),
    )
    renderAtBase('SERUM_002')
    await waitFor(() =>
      expect(screen.getByRole('link', { name: 'SERUM_002a' })).toBeInTheDocument()
    )
    expect(screen.queryByRole('button', { name: /expand replicate/i })).not.toBeInTheDocument()
  })

  it('a parent with its own results renders real cells, not em dashes', async () => {
    const group = groupWith('SERUM_003', [
      { replicate_label: 'a', vials: [vial(2, 'SERUM_003a', null)] },
    ])
    vi.mocked(experimentsApi.getGroup).mockResolvedValue({
      ...group,
      parent: {
        id: 1, experiment_id: 'SERUM_003', replicate_label: null, status: 'ONGOING',
        is_outlier: false, id_timepoint_days: 5, researcher: 'MH', date: null,
        result_count: 4, conditions: {},
      },
    })
    renderAtBase('SERUM_003')
    await waitFor(() => expect(screen.getByText('0 (parent)')).toBeInTheDocument())
    // Previously hard-coded '—' because `parent` was the narrow member type.
    expect(screen.getByText('T+5')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
  })
})
