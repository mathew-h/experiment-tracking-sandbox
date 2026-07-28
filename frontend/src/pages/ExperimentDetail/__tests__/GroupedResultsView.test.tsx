import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    getGroupRollup: vi.fn(),
    getGroup: vi.fn(),
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
    mean_h2_ppm: 500.0, sd_h2_ppm: 25.0,
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
  vi.mocked(experimentsApi.getGroupRollup).mockResolvedValue(ROLLUP)
  vi.mocked(experimentsApi.getGroup).mockResolvedValue({
    base_experiment_id: 'SERUM_001',
    parent: { id: 1, experiment_id: 'SERUM_001', replicate_label: null, status: 'ONGOING', is_outlier: false },
    members: [
      {
        id: 2, experiment_id: 'SERUM_001a', replicate_label: 'a', status: 'ONGOING', is_outlier: false,
        id_timepoint_days: null, researcher: null, date: null, result_count: 1, conditions: {},
      },
      {
        id: 3, experiment_id: 'SERUM_001b', replicate_label: 'b', status: 'ONGOING', is_outlier: true,
        id_timepoint_days: null, researcher: null, date: null, result_count: 1, conditions: {},
      },
    ],
    member_count: 2,
    shared_conditions: {},
    divergent_fields: [],
    additives_summary: null,
    additive_names: null,
    additives_diverge: false,
  })
  vi.mocked(experimentsApi.getResults).mockResolvedValue([])
})

describe('GroupedResultsView', () => {
  it('issues queries against the group endpoints off a base ID', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(experimentsApi.getGroup).toHaveBeenCalledWith('SERUM_001')
    expect(experimentsApi.getGroupRollup).toHaveBeenCalledWith('SERUM_001')
  })

  it('renders mean_h2_ppm as mean ± sd with n', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByText('500.0 ± 25.0')).toBeInTheDocument()
  })

  it('renders — when mean_h2_ppm is null', async () => {
    vi.mocked(experimentsApi.getGroupRollup).mockResolvedValue([
      { ...ROLLUP[0], mean_h2_ppm: null, sd_h2_ppm: null },
    ])
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    // Table columns: Time, n, H₂ (ppm), H₂ (µmol), H₂ (g/t), Fe²⁺ → H₂ (%), pH
    const cells = screen.getAllByRole('cell')
    expect(cells[2]).toHaveTextContent('—')
  })

  it('renders no NH₄ column headers in the rollup table', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.queryByRole('columnheader', { name: /NH₄/ })).not.toBeInTheDocument()
  })

  it('links to each replicate page for drill-in', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'SERUM_001a' })).toHaveAttribute(
      'href', '/experiments/SERUM_001a'
    )
  })

  it('defaults the metric selector to H₂ (ppm)', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    const select = screen.getByLabelText(/metric/i) as HTMLSelectElement
    expect(select.value).toBe('h2_ppm')
    expect(select.options[select.selectedIndex].text).toBe('H₂ (ppm)')
  })

  it('lists exactly the five H₂-first metric options', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    const select = screen.getByLabelText(/metric/i) as HTMLSelectElement
    const texts = Array.from(select.options).map((o) => o.text)
    expect(texts).toEqual(['H₂ (ppm)', 'H₂ (µmol)', 'H₂ (g/t)', 'Fe²⁺ → H₂ (%)', 'pH'])
  })

  it('changes plotted metric via the selector', async () => {
    const user = userEvent.setup()
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    await user.selectOptions(screen.getByLabelText(/metric/i), 'ph')
    expect(screen.getByText('8.10')).toBeInTheDocument()
  })

  it('annotates outlier members in drill-in links', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByRole('link', { name: /SERUM_001b.*outlier/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'SERUM_001a' })).toBeInTheDocument()
  })

  it('shows H₂ (g/t) and Fe²⁺ → H₂ (%) mean ± sd columns (issue #83)', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByRole('columnheader', { name: 'H₂ (g/t)' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Fe²⁺ → H₂ (%)' })).toBeInTheDocument()
    expect(screen.getByText('12.3 ± 2.5')).toBeInTheDocument()
    expect(screen.getByText('1.23 ± 0.45')).toBeInTheDocument()
  })
})
