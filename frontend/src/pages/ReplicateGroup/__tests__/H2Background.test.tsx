import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    list: vi.fn(),
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
  return { experiment_id, base_experiment_id: base } as ExperimentListItem
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
      search: 'SERUM_009', experiment_type: 'Serum',
    })
    await user.click(screen.getByRole('radio', { name: 'Whole group (SERUM_009, 2 vials)' }))
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
    await user.click(screen.getByRole('radio', { name: 'Whole group (SERUM_009, 2 vials)' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Background has no H2 data')).toBeInTheDocument()
  })

  it('clears the background', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.clearGroupH2Background).mockResolvedValue(undefined)
    renderRow(GROUP_LINK)
    await user.click(screen.getByRole('button', { name: 'Clear' }))
    await waitFor(() =>
      expect(experimentsApi.clearGroupH2Background).toHaveBeenCalledWith('SERUM_010'),
    )
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
})
