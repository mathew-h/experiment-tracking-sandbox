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

// Issue #163: the Results tab renders the shared RunSamplesTable (segment scope);
// column order, formatting and the DETAILS section are covered in
// components/results/__tests__/RunSamplesTable.test.tsx. These pin the tab's wiring.
const row = () => screen.findByTestId('sample-1')

describe('ResultsTab — samples table (issue #163)', () => {
  it('renders the shared segment-scope headers', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([baseResult])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    await row()
    const heads = screen.getAllByRole('columnheader').map((h) => h.textContent)
    expect(heads).toEqual(expect.arrayContaining(['Date', 'Day', 'Tube', 'Result note', 'H₂ ppm', 'Fe²⁺ H₂ %']))
    expect(heads).not.toContain('Segment')
  })

  it('renders the H₂ (ppm) and Fe²⁺ H₂ values from the /results payload', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, h2_concentration: 512, ferrous_iron_yield_h2_pct: 16.8 },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(within(await row()).getByText('512')).toBeInTheDocument()
    expect(within(await row()).getByText('16.8')).toBeInTheDocument()
  })

  it('renders no NH₄ text anywhere in the table', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, gross_ammonium_concentration_mM: 3.2, ferrous_iron_yield_nh3_pct: 24.6 },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    await row()
    expect(screen.queryByText(/NH₄/)).not.toBeInTheDocument()
  })

  it('does not render the Background NH₄ action-bar button', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([baseResult])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    await row()
    expect(screen.queryByText(/Background NH₄/)).not.toBeInTheDocument()
  })

  it('shows MOD only for a result with a modification note', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, has_modification_note: true, notes: [{ id: 5, note_text: 'Added HCl', note_type: 'modification', result_id: 1, created_by: null, needs_review: false, created_at: '2026-04-01T00:00:00Z', updated_at: null }] },
      { ...baseResult, id: 2 },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(within(await row()).getByRole('button', { name: /^Show modification for/ })).toBeInTheDocument()
    expect(within(screen.getByTestId('sample-2')).queryByRole('button', { name: /^Show modification for/ })).toBeNull()
  })

  it('takes the ICP flag from the series ICP query, fetched once for table and chart', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([baseResult])
    vi.mocked(experimentsApiModule.experimentsApi.getIcp).mockClear()
    vi.mocked(experimentsApiModule.experimentsApi.getIcp).mockResolvedValueOnce({
      rows: [{
        result_id: 1, experiment_id: 'HPHT_001', is_variant: false,
        cumulative_time_post_reaction_days: 7, sample_date: null, elements: { fe: 3 },
      }],
      segment_starts: [],
    })
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    const flag = await within(await row()).findByRole('button', { name: /^Show ICP for/ })
    fireEvent.click(flag)
    expect(await screen.findByText('Fe 3')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /^ICP over time/ })).toBeInTheDocument()
    expect(experimentsApiModule.experimentsApi.getIcp).toHaveBeenCalledTimes(1)
  })

  it('DETAILS shows the GC run date and the XRD run date', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, h2_concentration: 512, gc_run_date: '2026-07-29T00:00:00Z', xrd_run_date: '2026-04-15T00:00:00Z' },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    fireEvent.click(within(await row()).getByRole('button', { name: /^Show details for/ }))
    const details = screen.getByRole('region', { name: 'Sample details' })
    expect(details).toHaveTextContent('GC: 2026-07-29')
    expect(details).toHaveTextContent('XRD: 2026-04-15')
  })

  it('DETAILS shows the missing-GC flag even while the scalar fetch is still pending', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, has_scalar: true, h2_concentration: 512, gc_run_date: null },
    ])
    // Never-resolving promise: pins that the run-dates block does not wait behind
    // the scalar query. mockReturnValueOnce so it cannot leak into later tests.
    vi.mocked(resultsApiModule.resultsApi.getScalar).mockReturnValueOnce(new Promise(() => {}))
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    fireEvent.click(within(await row()).getByRole('button', { name: /^Show details for/ }))
    expect(await screen.findByText('not recorded')).toBeInTheDocument()
  })

  it('DETAILS loads DO and Fe(II) from the scalar row', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, has_scalar: true },
    ])
    vi.mocked(resultsApiModule.resultsApi.getScalar).mockClear()
    vi.mocked(resultsApiModule.resultsApi.getScalar).mockResolvedValueOnce({
      final_dissolved_oxygen_mg_L: 2.5, ferrous_iron_yield: 0.4,
    } as never)
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(resultsApiModule.resultsApi.getScalar).not.toHaveBeenCalled()
    fireEvent.click(within(await row()).getByRole('button', { name: /^Show details for/ }))
    expect(await screen.findByText('Scalar Results')).toBeInTheDocument()
    const details = screen.getByRole('region', { name: 'Sample details' })
    expect(details).toHaveTextContent('DO: 2.5 mg/L')
    expect(details).toHaveTextContent('Fe(II): 0.4')
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
    // Issue #161: the section is a Collapsible, so its header is a toggle button.
    const heading = await screen.findByRole('button', { name: /^ICP over time/ })
    const header = screen.getByRole('columnheader', { name: 'H₂ ppm' })
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

  it('renders a Tube column after Day with the tube number', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, sample_tube_number: 14 },
    ])
    wrapFull(<ResultsTab experimentId="HPHT_001" experimentFk={10} experimentType="HPHT" />)
    await screen.findByTestId('sample-1')
    const heads = screen.getAllByRole('columnheader').map((h) => h.textContent)
    expect(heads.indexOf('Tube')).toBe(heads.indexOf('Day') + 1)
    expect(within(screen.getByTestId('sample-1')).getByText('14')).toBeInTheDocument()
  })

  it('a click on a primary row opens the edit form (issue #163: row click, as on the run pages)', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([baseResult])
    wrapFull(<ResultsTab experimentId="HPHT_001" experimentFk={10} experimentType="HPHT" />)
    fireEvent.click(await screen.findByTestId('sample-1'))
    expect(await screen.findByText('Edit result — T+7')).toBeInTheDocument()
  })

  it('offers no Edit on a non-primary row', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, is_primary_timepoint_result: false },
    ])
    wrapFull(<ResultsTab experimentId="HPHT_001" experimentFk={10} experimentType="HPHT" />)
    fireEvent.click(await screen.findByTestId('sample-1'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
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
    // Issue #161 (NAV-13): the link names the action and the tab says why it lives there.
    const link = await screen.findByRole('link', { name: 'Add or edit samples on the run page' })
    expect(link).toHaveAttribute('href', '/core-floods/CF_007')
    expect(
      screen.getByText('Core flood samples record flow and permeability, which only the run page captures.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '+ Add Results' })).not.toBeInTheDocument()
    fireEvent.click(await screen.findByTestId('sample-1'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('keeps + Add Results on an HPHT experiment with no run-page link (issue #162)', async () => {
    // The breadcrumb and segment strip carry the run link since #156 (decision 6 in #154).
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([])
    wrapFull(
      <ResultsTab
        experimentId="HPHT_297-2"
        experimentFk={11}
        experimentType="HPHT"
        baseExperimentId="HPHT_297"
      />,
    )
    expect(await screen.findByRole('button', { name: '+ Add Results' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Open run page' })).not.toBeInTheDocument()
    expect(screen.queryByText(/only the run page captures/)).not.toBeInTheDocument()
  })

  it('keeps + Add Results for a non-core-flood experiment', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([])
    wrapFull(<ResultsTab experimentId="SERUM_001" experimentFk={10} experimentType="Serum" />)
    expect(await screen.findByRole('button', { name: '+ Add Results' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Open run page' })).not.toBeInTheDocument()
  })
})
