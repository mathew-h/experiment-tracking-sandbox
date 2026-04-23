import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ResultsTab } from '../ResultsTab'
import type { ResultWithFlags } from '@/api/experiments'
import * as experimentsApiModule from '@/api/experiments'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    getResults: vi.fn(),
    updateBackgroundAmmonium: vi.fn(),
  },
}))

vi.mock('@/api/results', () => ({
  resultsApi: {
    getScalar: vi.fn(),
    getIcp: vi.fn(),
  },
}))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

const baseResult: ResultWithFlags = {
  id: 1,
  experiment_fk: 10,
  time_post_reaction_days: 7,
  time_post_reaction_bucket_days: 7,
  cumulative_time_post_reaction_days: 7,
  is_primary_timepoint_result: true,
  description: 'T7',
  created_at: '2026-04-01T00:00:00Z',
  has_scalar: false,
  has_icp: false,
  has_brine_modification: false,
  brine_modification_description: null,
  grams_per_ton_yield: null,
  h2_grams_per_ton_yield: null,
  h2_micromoles: null,
  gross_ammonium_concentration_mM: null,
  background_ammonium_concentration_mM: null,
  final_conductivity_mS_cm: null,
  final_ph: null,
  scalar_measurement_date: null,
  ferrous_iron_yield_h2_pct: null,
  ferrous_iron_yield_nh3_pct: null,
  xrd_run_date: null,
}

describe('ResultsTab — new columns', () => {
  it('renders Fe²⁺ NH₃ (%) column header', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([baseResult])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(await screen.findByText('Fe²⁺ NH₃ (%)')).toBeInTheDocument()
  })

  it('renders Fe²⁺ H₂ (%) column header', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([baseResult])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(await screen.findByText('Fe²⁺ H₂ (%)')).toBeInTheDocument()
  })

  it('renders 24.6% for ferrous_iron_yield_nh3_pct = 24.6', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, ferrous_iron_yield_nh3_pct: 24.6 },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(await screen.findByText('24.6%')).toBeInTheDocument()
  })

  it('renders 16.8% for ferrous_iron_yield_h2_pct = 16.8', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, ferrous_iron_yield_h2_pct: 16.8 },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(await screen.findByText('16.8%')).toBeInTheDocument()
  })

  it('renders XRD badge when xrd_run_date is set', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, xrd_run_date: '2026-04-15T00:00:00Z' },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(await screen.findByText('XRD')).toBeInTheDocument()
  })

  it('does not render XRD badge when xrd_run_date is null', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([baseResult])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    await screen.findByText('T+7')
    expect(screen.queryByText('XRD')).not.toBeInTheDocument()
  })
})
