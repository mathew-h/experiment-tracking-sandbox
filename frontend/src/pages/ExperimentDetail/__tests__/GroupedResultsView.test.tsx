import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    getRollup: vi.fn(),
    getReplicateGroup: vi.fn(),
    getResults: vi.fn(),
  },
}))

import { GroupedResultsView } from '../GroupedResultsView'
import { experimentsApi } from '@/api/experiments'
import type { RollupTimepoint } from '@/api/experiments'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 0 } },
})
function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </MemoryRouter>
  )
}

const ROLLUP: RollupTimepoint[] = [
  {
    base_experiment_id: 'SERUM_001', time_post_reaction_bucket_days: 7, n_replicates: 3,
    mean_gross_ammonium_mM: 2.0, median_gross_ammonium_mM: 2.0, sd_gross_ammonium_mM: 1.0,
    mean_net_ammonium_mM: 1.5, sd_net_ammonium_mM: 0.5,
    mean_h2_micromoles: null, sd_h2_micromoles: null,
    mean_h2_grams_per_ton: 12.3, sd_h2_grams_per_ton: 2.5,
    mean_fe_yield_h2_pct: 1.23, sd_fe_yield_h2_pct: 0.45,
    mean_fe_yield_nh3_pct: null, sd_fe_yield_nh3_pct: null,
    mean_grams_per_ton_yield: 40.0, sd_grams_per_ton_yield: 4.0, mean_final_ph: 8.1,
  },
]

beforeEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
  vi.mocked(experimentsApi.getRollup).mockResolvedValue(ROLLUP)
  vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
    base_experiment_id: 'SERUM_001',
    parent: { id: 1, experiment_id: 'SERUM_001', replicate_label: null, status: 'ONGOING', is_outlier: false },
    members: [
      { id: 2, experiment_id: 'SERUM_001a', replicate_label: 'a', status: 'ONGOING', is_outlier: false },
      { id: 3, experiment_id: 'SERUM_001b', replicate_label: 'b', status: 'ONGOING', is_outlier: true },
    ],
  })
  vi.mocked(experimentsApi.getResults).mockResolvedValue([])
})

describe('GroupedResultsView', () => {
  it('renders rollup stats table with mean ± sd and n', async () => {
    render(<GroupedResultsView experimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByText('2.00 ± 1.00')).toBeInTheDocument()
  })

  it('links to each replicate page for drill-in', async () => {
    render(<GroupedResultsView experimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'SERUM_001a' })).toHaveAttribute(
      'href', '/experiments/SERUM_001a'
    )
  })

  it('changes plotted metric via the selector', async () => {
    const user = userEvent.setup()
    render(<GroupedResultsView experimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    await user.selectOptions(screen.getByLabelText(/metric/i), 'ph')
    expect(screen.getByText('8.10')).toBeInTheDocument()
  })

  it('annotates outlier members in drill-in links', async () => {
    render(<GroupedResultsView experimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByRole('link', { name: /SERUM_001b.*outlier/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'SERUM_001a' })).toBeInTheDocument()
  })

  it('shows H₂ (g/t) and Fe²⁺ → H₂ (%) mean ± sd columns (issue #83)', async () => {
    render(<GroupedResultsView experimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByRole('columnheader', { name: 'H₂ (g/t)' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Fe²⁺ → H₂ (%)' })).toBeInTheDocument()
    expect(screen.getByText('12.3 ± 2.5')).toBeInTheDocument()
    expect(screen.getByText('1.23 ± 0.45')).toBeInTheDocument()
  })
})
