import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'
import { within } from '@testing-library/react'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    list: vi.fn(),
    getGroup: vi.fn(),
    setGroupH2Background: vi.fn(),
    clearGroupH2Background: vi.fn(),
    getGroupH2BackgroundRollup: vi.fn(),
  },
}))

import { H2BackgroundRow } from '../H2BackgroundRow'
import { experimentsApi } from '@/api/experiments'
import type {
  ExperimentListItem,
  H2BackgroundLink,
  H2BackgroundRollup,
  ReplicateGroupDetail,
} from '@/api/experiments'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 0 } },
})

function renderRow(link: H2BackgroundLink | null) {
  return render(
    <QueryClientProvider client={queryClient}>
      <H2BackgroundRow baseId="SERUM_010" link={link} />
    </QueryClientProvider>,
  )
}

function item(experiment_id: string, base: string | null): ExperimentListItem {
  return { experiment_id, base_experiment_id: base, experiment_type: 'Serum' } as ExperimentListItem
}

function rollupRow(bkg_n_values: number | null): H2BackgroundRollup {
  return {
    base_experiment_id: 'SERUM_010',
    time_post_reaction_bucket_days: 7,
    n_values: 3,
    bkg_time_bucket_days: null,
    bkg_time_gap_days: null,
    bkg_n_values: bkg_n_values,
    bkg_mean_h2_micromoles: null,
    bkg_sd_h2_micromoles: null,
    mean_net_h2_micromoles: null,
    sd_net_h2_micromoles: null,
    mean_net_h2_grams_per_ton: null,
    sd_net_h2_grams_per_ton: null,
    mean_net_fe_yield_h2_pct: null,
    sd_net_fe_yield_h2_pct: null,
    below_background: null,
  }
}

const GROUP_LINK: H2BackgroundLink = {
  mode: 'group', background_ref: 'SERUM_009', created_by: null, updated_at: null,
}

beforeEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
  vi.mocked(experimentsApi.getGroupH2BackgroundRollup).mockResolvedValue([rollupRow(2)])
  vi.mocked(experimentsApi.getGroup).mockResolvedValue({ member_count: 4 } as ReplicateGroupDetail)
  vi.mocked(experimentsApi.list).mockResolvedValue({
    items: [item('SERUM_009a', 'SERUM_009'), item('SERUM_009b', 'SERUM_009')],
    total: 2, skip: 0, limit: 50,
  })
})

async function searchAndPick(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Set' }))
  await user.type(screen.getByRole('textbox'), 'SERUM_009')
  await user.click(await screen.findByRole('button', { name: 'SERUM_009a' }))
}

describe('H2BackgroundRow', () => {
  it('renders None and a Set button without a link', () => {
    renderRow(null)
    expect(screen.getByText(/H₂ background:/)).toBeInTheDocument()
    expect(screen.getByText('None')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Set' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Clear' })).not.toBeInTheDocument()
  })

  it('renders the group-mode link with Change and Clear', () => {
    renderRow(GROUP_LINK)
    expect(screen.getByText('SERUM_009 · whole group')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Change' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Set' })).not.toBeInTheDocument()
  })

  it('renders the vial-mode link text', () => {
    renderRow({ ...GROUP_LINK, background_ref: 'SERUM_009a', mode: 'vial' })
    expect(screen.getByText('SERUM_009a · single vial')).toBeInTheDocument()
  })

  it('sets a whole-group background from a search result', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.setGroupH2Background).mockResolvedValue(GROUP_LINK)
    renderRow(null)
    await searchAndPick(user)
    expect(experimentsApi.list).toHaveBeenCalledWith({
      search: 'SERUM_009',
    })
    await user.click(screen.getByRole('radio', { name: 'Whole group (SERUM_009, 4 vials)' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(experimentsApi.setGroupH2Background).toHaveBeenCalledWith('SERUM_010', {
        experiment_id: 'SERUM_009a', mode: 'group',
      }),
    )
  })

  it('sets a single-vial background', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.setGroupH2Background).mockResolvedValue({ ...GROUP_LINK, mode: 'vial' })
    renderRow(null)
    await searchAndPick(user)
    await user.click(screen.getByRole('radio', { name: 'This vial only (SERUM_009a and its -t vials)' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(experimentsApi.setGroupH2Background).toHaveBeenCalledWith('SERUM_010', {
        experiment_id: 'SERUM_009a', mode: 'vial',
      }),
    )
  })

  it('shows the server detail on a 422', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.setGroupH2Background).mockRejectedValue({
      response: { status: 422, data: { detail: 'Background has no H2 data' } },
    })
    renderRow(null)
    await searchAndPick(user)
    await user.click(screen.getByRole('radio', { name: 'Whole group (SERUM_009, 4 vials)' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Background has no H2 data')).toBeInTheDocument()
  })

  it('asks for confirmation before clearing, and only confirming calls the API', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.clearGroupH2Background).mockResolvedValue(undefined)
    renderRow(GROUP_LINK)
    await user.click(screen.getByRole('button', { name: 'Clear' }))
    expect(experimentsApi.clearGroupH2Background).not.toHaveBeenCalled()
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('Clear H₂ background')).toBeInTheDocument()
    expect(
      within(dialog).getByText(
        'Remove the H₂ background link for SERUM_010? Background-adjusted H₂ values for this group will no longer be shown.',
      ),
    ).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Clear' }))
    await waitFor(() =>
      expect(experimentsApi.clearGroupH2Background).toHaveBeenCalledWith('SERUM_010'),
    )
  })

  it('does not clear when the confirmation is cancelled', async () => {
    const user = userEvent.setup()
    renderRow(GROUP_LINK)
    await user.click(screen.getByRole('button', { name: 'Clear' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }))
    expect(experimentsApi.clearGroupH2Background).not.toHaveBeenCalled()
  })

  it('shows the server detail next to the row when clear fails', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.clearGroupH2Background).mockRejectedValue({
      response: { data: { detail: 'Clear refused' } },
    })
    renderRow(GROUP_LINK)
    await user.click(screen.getByRole('button', { name: 'Clear' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Clear' }))
    expect(await screen.findByText('Clear refused')).toBeInTheDocument()
  })

  it('invalidates the detail, rollup and background-rollup queries after clear', async () => {
    const user = userEvent.setup()
    const spy = vi.spyOn(queryClient, 'invalidateQueries')
    vi.mocked(experimentsApi.clearGroupH2Background).mockResolvedValue(undefined)
    renderRow(GROUP_LINK)
    await user.click(screen.getByRole('button', { name: 'Clear' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Clear' }))
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(3))
    const keys = spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey)
    expect(keys).toContainEqual(['replicate-group-detail', 'SERUM_010'])
    expect(keys).toContainEqual(['group-rollup', 'SERUM_010'])
    expect(keys).toContainEqual(['group-h2-bkg-rollup', 'SERUM_010'])
    spy.mockRestore()
  })

  it('invalidates all three queries and closes the modal after a save', async () => {
    const user = userEvent.setup()
    const spy = vi.spyOn(queryClient, 'invalidateQueries')
    vi.mocked(experimentsApi.setGroupH2Background).mockResolvedValue(GROUP_LINK)
    renderRow(null)
    await searchAndPick(user)
    await user.click(screen.getByRole('radio', { name: 'Whole group (SERUM_009, 4 vials)' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const keys = spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey)
    expect(keys).toContainEqual(['replicate-group-detail', 'SERUM_010'])
    expect(keys).toContainEqual(['group-rollup', 'SERUM_010'])
    expect(keys).toContainEqual(['group-h2-bkg-rollup', 'SERUM_010'])
    spy.mockRestore()
  })

  it('labels a pick with no base_experiment_id by its own experiment id', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.list).mockResolvedValue({
      items: [item('SERUM_009-t5', null)], total: 1, skip: 0, limit: 50,
    })
    vi.mocked(experimentsApi.getGroup).mockResolvedValue({ member_count: 1 } as ReplicateGroupDetail)
    renderRow(null)
    await user.click(screen.getByRole('button', { name: 'Set' }))
    await user.type(screen.getByRole('textbox'), 'SERUM_009')
    await user.click(await screen.findByRole('button', { name: 'SERUM_009-t5' }))
    expect(await screen.findByRole('radio', { name: 'Whole group (SERUM_009-t5, 1 vial)' })).toBeInTheDocument()
    expect(experimentsApi.getGroup).toHaveBeenCalledWith('SERUM_009-t5')
  })

  it('falls back to a count-free label while the group fetch fails', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.getGroup).mockRejectedValue(new Error('nope'))
    renderRow(null)
    await searchAndPick(user)
    expect(screen.getByRole('radio', { name: 'Whole group (SERUM_009)' })).toBeInTheDocument()
  })


  it('warns when the linked background has no H2 data', async () => {
    vi.mocked(experimentsApi.getGroupH2BackgroundRollup).mockResolvedValue([rollupRow(null)])
    renderRow(GROUP_LINK)
    const warning = await screen.findByText('background has no H₂ data')
    expect(warning).toHaveClass('text-status-warning')
  })

  it('does not warn when a rollup row has background data', async () => {
    renderRow(GROUP_LINK)
    await waitFor(() => expect(experimentsApi.getGroupH2BackgroundRollup).toHaveBeenCalled())
    expect(screen.queryByText('background has no H₂ data')).not.toBeInTheDocument()
  })

  it('searches without experiment_type and offers only serum-type results', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.list).mockResolvedValue({
      items: [
        { experiment_id: 'SERUM_009a', base_experiment_id: 'SERUM_009', experiment_type: 'SERUM' },
        { experiment_id: 'HPHT_009a', base_experiment_id: 'HPHT_009', experiment_type: 'HPHT' },
        { experiment_id: 'SERUM_009b', base_experiment_id: 'SERUM_009', experiment_type: 'Serum Vial' },
      ] as ExperimentListItem[],
      total: 3, skip: 0, limit: 50,
    })
    renderRow(null)
    await user.click(screen.getByRole('button', { name: 'Set' }))
    await user.type(screen.getByRole('textbox'), '009')
    expect(await screen.findByRole('button', { name: 'SERUM_009a' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'SERUM_009b' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'HPHT_009a' })).not.toBeInTheDocument()
    expect(experimentsApi.list).toHaveBeenCalledWith({ search: '009' })
  })
})

describe('H2BackgroundRow — issue #152 flagged backgrounds first', () => {
  it('lists flagged backgrounds before other matches, with a badge', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.list).mockResolvedValue({
      items: [
        item('SERUM_009a', 'SERUM_009'),
        { ...item('SERUM_008a', 'SERUM_008'), is_background: true },
        item('SERUM_007a', 'SERUM_007'),
      ],
      total: 3, skip: 0, limit: 50,
    })
    renderRow(null)
    await user.click(screen.getByRole('button', { name: 'Set' }))
    await user.type(screen.getByRole('textbox'), 'SERUM_00')
    await screen.findByRole('button', { name: /SERUM_008a/ })
    const names = within(screen.getByRole('list')).getAllByRole('button').map((b) => b.textContent)
    // Stable sort: the flagged one moves up, the others keep the list's order.
    expect(names).toEqual(['SERUM_008aBackground', 'SERUM_009a', 'SERUM_007a'])
  })
})
