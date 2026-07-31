import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ResultsTab } from '../ResultsTab'
import type { ResultWithFlags } from '@/api/experiments'
import * as experimentsApiModule from '@/api/experiments'
import * as resultsApiModule from '@/api/results'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    getResults: vi.fn(),
    setBackgroundAmmonium: vi.fn(),
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
  h2_concentration: null,
  h2_grams_per_ton_yield: null,
  h2_micromoles: null,
  gross_ammonium_concentration_mM: null,
  background_ammonium_concentration_mM: null,
  final_conductivity_mS_cm: null,
  final_ph: null,
  scalar_measurement_date: null,
  ferrous_iron_yield_h2_pct: null,
  ferrous_iron_yield_nh3_pct: null,
  nmr_run_date: null,
  icp_run_date: null,
  gc_run_date: null,
  xrd_run_date: null,
}

describe('ResultsTab — H2-first columns', () => {
  it('renders the H₂ (ppm) column header', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([baseResult])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(await screen.findByText('H₂ (ppm)')).toBeInTheDocument()
  })

  it('renders the H₂ (ppm) value from the /results payload', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, h2_concentration: 512 },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(await screen.findByText('512.0')).toBeInTheDocument()
  })

  it('renders no NH₄ text anywhere in the table', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, gross_ammonium_concentration_mM: 3.2, ferrous_iron_yield_nh3_pct: 24.6 },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    await screen.findByText('T+7')
    expect(screen.queryByText(/NH₄/)).not.toBeInTheDocument()
  })

  it('does not render the Background NH₄ action-bar button', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([baseResult])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    await screen.findByText('T+7')
    expect(screen.queryByText(/Background NH₄/)).not.toBeInTheDocument()
  })

  it('renders Fe²⁺ H₂ (%) column header', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([baseResult])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(await screen.findByText('Fe²⁺ H₂ (%)')).toBeInTheDocument()
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

  it('renders MOD badge in the main row when has_brine_modification is true', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, has_brine_modification: true, brine_modification_description: 'Added HCl' },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(await screen.findAllByText('MOD')).not.toHaveLength(0)
  })

  it('does not render MOD badge when has_brine_modification is false', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([baseResult])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    await screen.findByText('T+7')
    expect(screen.queryByText('MOD')).not.toBeInTheDocument()
  })

  it('shows the GC run date in the expanded row when it is set', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, has_scalar: true, h2_concentration: 512, gc_run_date: '2026-07-29T00:00:00Z' },
    ])
    vi.mocked(resultsApiModule.resultsApi.getScalar).mockResolvedValue(null)
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    const row = await screen.findByText('T+7')
    fireEvent.click(row)
    expect(await screen.findByText('Instrument Run Dates')).toBeInTheDocument()
    expect(await screen.findByText('2026-07-29')).toBeInTheDocument()
  })

  it('flags a missing GC run date when the row has an H2 reading', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, has_scalar: true, h2_concentration: 512, gc_run_date: null },
    ])
    vi.mocked(resultsApiModule.resultsApi.getScalar).mockResolvedValue(null)
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    const row = await screen.findByText('T+7')
    fireEvent.click(row)
    expect(await screen.findByText('not recorded')).toBeInTheDocument()
    expect(
      await screen.findByText(/not counted by the Dashboard's GC Measurements card/)
    ).toBeInTheDocument()
  })

  it('does not flag a missing GC run date when the row has no H2 reading', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, has_scalar: true, h2_concentration: null, gc_run_date: null },
    ])
    vi.mocked(resultsApiModule.resultsApi.getScalar).mockResolvedValue(null)
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    const row = await screen.findByText('T+7')
    fireEvent.click(row)
    expect(screen.queryByText('not recorded')).not.toBeInTheDocument()
  })

  it('shows the missing-GC flag even while the scalar fetch is still pending', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, has_scalar: true, h2_concentration: 512, gc_run_date: null },
    ])
    // Never-resolving promise (same idiom as Dashboard.test.tsx:82) — pins that the
    // run-dates block does not wait behind the scalar query's loading spinner.
    vi.mocked(resultsApiModule.resultsApi.getScalar).mockReturnValue(new Promise(() => {}))
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    const row = await screen.findByText('T+7')
    fireEvent.click(row)
    expect(await screen.findByText('not recorded')).toBeInTheDocument()
  })

  it('renders set NMR and XRD run dates without rendering the unset ICP date', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      {
        ...baseResult,
        nmr_run_date: '2026-05-01T00:00:00Z',
        xrd_run_date: '2026-06-15T00:00:00Z',
        icp_run_date: null,
        h2_concentration: null,
        gc_run_date: null,
      },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    const row = await screen.findByText('T+7')
    fireEvent.click(row)
    const heading = await screen.findByText('Instrument Run Dates')
    const section = heading.parentElement as HTMLElement
    expect(within(section).getByText('2026-05-01')).toBeInTheDocument()
    expect(within(section).getByText('2026-06-15')).toBeInTheDocument()
    expect(within(section).queryByText(/^ICP:/)).not.toBeInTheDocument()
  })
})
