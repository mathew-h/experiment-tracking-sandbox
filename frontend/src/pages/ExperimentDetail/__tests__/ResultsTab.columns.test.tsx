import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '@/components/ui'
import { ResultsTab } from '../ResultsTab'
import type { ResultWithFlags } from '@/api/experiments'
import * as experimentsApiModule from '@/api/experiments'
import * as resultsApiModule from '@/api/results'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    getResults: vi.fn(),
    getIcp: vi.fn().mockResolvedValue({ rows: [], segment_starts: [] }),
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
  created_at: '2026-04-01T00:00:00Z',
  has_scalar: false,
  has_icp: false,
  has_modification_note: false,
  notes: [],
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

  it('renders MOD badge in the main row when has_modification_note is true', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, has_modification_note: true, notes: [{ id: 5, note_text: 'Added HCl', note_type: 'modification', result_id: 1, created_by: null, needs_review: false, created_at: '2026-04-01T00:00:00Z', updated_at: null }] },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(await screen.findAllByText('MOD')).not.toHaveLength(0)
  })

  it('does not render MOD badge when has_modification_note is false', async () => {
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
    expect(screen.queryByText('Instrument Run Dates')).not.toBeInTheDocument()
  })

  it('shows the missing-GC flag even while the scalar fetch is still pending', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, has_scalar: true, h2_concentration: 512, gc_run_date: null },
    ])
    // Never-resolving promise (same idiom as Dashboard.test.tsx:82) — pins that the
    // run-dates block does not wait behind the scalar query's loading spinner.
    // mockReturnValueOnce, not mockReturnValue: this mock must not leak into
    // later tests in the file (there is no clearMocks/restoreMocks configured).
    vi.mocked(resultsApiModule.resultsApi.getScalar).mockReturnValueOnce(new Promise(() => {}))
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

describe('ResultsTab — ICP over time (issue #143)', () => {
  it('renders the series ICP chart below the results table', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([baseResult])
    vi.mocked(experimentsApiModule.experimentsApi.getIcp).mockResolvedValueOnce({
      rows: [{
        result_id: 1, experiment_id: 'HPHT_001', is_variant: false,
        cumulative_time_post_reaction_days: 7, sample_date: null, elements: { fe: 3 },
      }],
      segment_starts: [],
    })
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    const heading = await screen.findByRole('heading', { name: 'ICP over time' })
    const header = screen.getByText('H₂ (ppm)')
    // DOCUMENT_POSITION_FOLLOWING: the chart comes after the table header.
    expect(header.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(experimentsApiModule.experimentsApi.getIcp).toHaveBeenCalledWith('HPHT_001')
  })
})

describe('ResultsTab — tube, edit and core flood entry (issue #148)', () => {
  function wrapFull(ui: React.ReactElement) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return render(
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <MemoryRouter>{ui}</MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )
  }

  it('renders a Tube column after Sample Date with the tube number', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, sample_tube_number: 14 },
    ])
    wrapFull(<ResultsTab experimentId="HPHT_001" experimentFk={10} experimentType="HPHT" />)
    const tube = await screen.findByText('Tube')
    const headers = Array.from(tube.parentElement!.children).map((c) => c.textContent)
    expect(headers.indexOf('Tube')).toBe(headers.indexOf('Sample Date') + 1)
    expect(screen.getByText('14')).toBeInTheDocument()
  })

  it('offers Edit on an expanded primary row and opens the edit form', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([baseResult])
    wrapFull(<ResultsTab experimentId="HPHT_001" experimentFk={10} experimentType="HPHT" />)
    fireEvent.click(await screen.findByText('T+7'))
    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    expect(await screen.findByText('Edit result — T+7')).toBeInTheDocument()
  })

  it('offers no Edit on a non-primary row', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, is_primary_timepoint_result: false },
    ])
    wrapFull(<ResultsTab experimentId="HPHT_001" experimentFk={10} experimentType="HPHT" />)
    fireEvent.click(await screen.findByText('T+7'))
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
  })

  it('links a Core Flood experiment to its run page instead of + Add Results, with no Edit', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([baseResult])
    wrapFull(
      <ResultsTab
        experimentId="CF_007-2"
        experimentFk={10}
        experimentType="Core Flood"
        baseExperimentId="CF_007"
      />,
    )
    const link = await screen.findByRole('link', { name: 'Open run page' })
    expect(link).toHaveAttribute('href', '/core-floods/CF_007')
    expect(screen.queryByRole('button', { name: '+ Add Results' })).not.toBeInTheDocument()
    fireEvent.click(await screen.findByText('T+7'))
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
  })

  it('links an HPHT experiment to its run page and keeps + Add Results (issue #150)', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([])
    wrapFull(
      <ResultsTab
        experimentId="HPHT_297-2"
        experimentFk={11}
        experimentType="HPHT"
        baseExperimentId="HPHT_297"
      />,
    )
    const link = await screen.findByRole('link', { name: 'Open run page' })
    expect(link).toHaveAttribute('href', '/hpht/HPHT_297')
    expect(screen.getByRole('button', { name: '+ Add Results' })).toBeInTheDocument()
  })

  it('keeps + Add Results for a non-core-flood experiment', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([])
    wrapFull(<ResultsTab experimentId="SERUM_001" experimentFk={10} experimentType="Serum" />)
    expect(await screen.findByRole('button', { name: '+ Add Results' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Open run page' })).not.toBeInTheDocument()
  })
})
