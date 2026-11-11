import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation, useNavigationType } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { HphtRun } from '@/api/hpht'
import type { ResultWithFlags } from '@/api/experiments'
import { ToastProvider } from '@/components/ui'
import { RUN, segment } from './fixtures'

vi.mock('@/api/hpht', () => ({ hphtApi: { list: vi.fn(), get: vi.fn(), icp: vi.fn() } }))
vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    getResults: vi.fn(),
    createResult: vi.fn(),
    updateResult: vi.fn(),
    patchStatus: vi.fn(),
    patch: vi.fn(),
    get: vi.fn(),
    checkExists: vi.fn(),
    patchNote: vi.fn(),
    addNote: vi.fn(),
    exportAll: vi.fn(),
  },
}))
vi.mock('@/api/chemicals', () => ({ chemicalsApi: { listExperimentAdditives: vi.fn() } }))
vi.mock('@/api/results', () => ({ resultsApi: { getScalar: vi.fn() } }))

import { hphtApi } from '@/api/hpht'
import { experimentsApi } from '@/api/experiments'
import { chemicalsApi } from '@/api/chemicals'
import { resultsApi } from '@/api/results'
import { HphtRunPage } from '../HphtRunPage'

function result(id: number, day: number): ResultWithFlags {
  return {
    id,
    experiment_fk: 1,
    time_post_reaction_days: day,
    time_post_reaction_bucket_days: day,
    cumulative_time_post_reaction_days: day,
    is_primary_timepoint_result: true,
    created_at: '2026-09-02T00:00:00',
    has_scalar: true,
    has_icp: false,
    has_modification_note: false,
    notes: [],
    grams_per_ton_yield: null,
    h2_concentration: 1000,
    h2_grams_per_ton_yield: 0.1,
    h2_micromoles: 1.5,
    gross_ammonium_concentration_mM: null,
    background_ammonium_concentration_mM: null,
    final_conductivity_mS_cm: 4.2,
    final_ph: 7.1,
    scalar_measurement_date: '2026-09-05T00:00:00',
    ferrous_iron_yield_h2_pct: null,
    ferrous_iron_yield_nh3_pct: null,
    nmr_run_date: null,
    icp_run_date: null,
    gc_run_date: null,
    xrd_run_date: null,
    sample_tube_number: 4,
  }
}

function Probe() {
  return (
    <>
      <div data-testid="path">{useLocation().pathname}</div>
      <div data-testid="nav-type">{useNavigationType()}</div>
    </>
  )
}

function renderPage(run: HphtRun = RUN, path = `/hpht/${run.base_id}`) {
  vi.mocked(hphtApi.get).mockResolvedValue(run)
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <Routes>
            <Route path="/hpht/:baseId" element={<HphtRunPage />} />
          </Routes>
          <Probe />
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

const samplesRegion = async () =>
  (await screen.findByRole('heading', { name: 'Samples' })).closest('section') as HTMLElement

describe('HphtRunPage (issue #150)', () => {
  beforeEach(() => {
    vi.mocked(hphtApi.get).mockReset()
    vi.mocked(hphtApi.icp).mockReset()
    vi.mocked(hphtApi.icp).mockResolvedValue([])
    vi.mocked(experimentsApi.getResults).mockReset()
    vi.mocked(experimentsApi.getResults).mockResolvedValue([])
    vi.mocked(chemicalsApi.listExperimentAdditives).mockResolvedValue([])
    vi.mocked(resultsApi.getScalar).mockReset()
  })

  it('renders the header, reactor and conditions', async () => {
    renderPage()
    expect(await screen.findByRole('heading', { name: 'HPHT_297', level: 1 })).toBeInTheDocument()
    expect(screen.getByText('Reactor R07')).toBeInTheDocument()
    const badge = screen.getByText(/^Ongoing:/)
    expect(badge).toHaveTextContent('Ongoing: HPHT_297-2')
    expect(within(badge).getByRole('link', { name: 'HPHT_297-2' })).toHaveAttribute(
      'href', '/experiments/HPHT_297-2',
    )
    expect(screen.getByText('1500 psi')).toBeInTheDocument()
    // Issue #162: explicit, in case the detail page's default tab ever changes.
    expect(screen.getByRole('link', { name: 'Edit on Conditions tab' })).toHaveAttribute(
      'href', '/experiments/HPHT_297-2?tab=conditions',
    )
    // The segment the card describes is a link too, not caption text (epic #154).
    const heading = screen.getByRole('heading', { name: /^Conditions/, level: 2 })
    expect(within(heading).getByRole('link', { name: 'HPHT_297-2' })).toHaveAttribute(
      'href', '/experiments/HPHT_297-2',
    )
  })

  it('lists samples newest first with Tube and the result note, and a MOD badge', async () => {
    renderPage()
    const region = await samplesRegion()
    const rows = within(region).getAllByTestId(/^sample-/)
    expect(rows.map((r) => r.dataset.testid)).toEqual(['sample-12', 'sample-11', 'sample-10'])
    expect(within(region).getByRole('columnheader', { name: 'Tube' })).toBeInTheDocument()
    // Issue #163: one note header across the three tables.
    expect(within(region).getByRole('columnheader', { name: 'Result note' })).toBeInTheDocument()
    expect(within(rows[2]).getByText('First draw')).toBeInTheDocument()
    expect(within(rows[0]).getByText('MOD')).toBeInTheDocument()
    expect(within(rows[0]).getByText('5')).toBeInTheDocument()
  })

  it('MOD and ICP flags open the note and the readings, not the editor (issue #164)', async () => {
    vi.mocked(hphtApi.icp).mockResolvedValue([
      { result_id: 12, experiment_id: 'HPHT_297-2', is_variant: false, sample_date: null,
        cumulative_time_post_reaction_days: 5, elements: { fe: 4.5 } },
    ] as never)
    renderPage()
    const region = await samplesRegion()
    const row = within(region).getByTestId('sample-12')
    await userEvent.click(within(row).getByRole('button', { name: /^Show modification for/ }))
    expect(within(region).getByRole('region', { name: 'Modification notes' })).toHaveTextContent('Topped up brine')
    const icpFlag = await within(row).findByRole('button', { name: /^Show ICP for/ })
    await userEvent.click(icpFlag)
    expect(within(region).getByText('Fe 4.5')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    // No expander column: every button in the table is an ICP, MOD or DETAILS flag.
    expect(within(region).getAllByRole('button').every((b) => /^(ICP|MOD|DETAILS)/.test(b.textContent ?? ''))).toBe(true)
  })

  it('shows variants only under Side samples', async () => {
    renderPage()
    const region = await samplesRegion()
    expect(within(region).queryByTestId('sample-13')).not.toBeInTheDocument()
    expect(screen.queryByText('Desorption draw')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^Side samples/ }))
    const side = screen.getByRole('region', { name: 'Side samples' })
    expect(within(side).getByTestId('sample-13')).toHaveTextContent('Desorption draw')
    // Raw values only: no running-total columns.
    expect(within(side).queryByRole('columnheader', { name: 'Cum. H₂ g/t' })).not.toBeInTheDocument()
  })

  it('+ Add sample with one ongoing segment targets it with no segment select', async () => {
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: '+ Add sample' }))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByTestId('target-segment')).toHaveTextContent('HPHT_297-2')
    expect(within(dialog).queryByLabelText('Segment')).not.toBeInTheDocument()
    // Issue #161 (NAV-15): the dialog is named for the button that opened it.
    expect(within(dialog).getByRole('heading', { name: 'Add sample' })).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Save sample' })).toBeInTheDocument()
    expect(experimentsApi.getResults).toHaveBeenCalledWith('HPHT_297-2')
  })

  it('+ Add sample with two ongoing segments shows the segment select', async () => {
    const run: HphtRun = {
      ...RUN,
      segments: RUN.segments.map((s) => (s.id === 1 ? segment({ status: 'ONGOING' }) : s)),
    }
    renderPage(run)
    await userEvent.click(await screen.findByRole('button', { name: '+ Add sample' }))
    const dialog = await screen.findByRole('dialog')
    const select = await within(dialog).findByLabelText('Segment')
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toContain('HPHT_297-2 (ongoing)')
    expect(within(dialog).queryByTestId('target-segment')).not.toBeInTheDocument()
  })

  it('a row click opens edit mode for that result', async () => {
    vi.mocked(experimentsApi.getResults).mockResolvedValue([result(10, 1), result(11, 4)])
    vi.mocked(resultsApi.getScalar).mockResolvedValue({ id: 11, result_id: 11 } as never)
    renderPage()
    const region = await samplesRegion()
    await userEvent.click(within(region).getByTestId('sample-11'))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText(/^Edit sample — T\+4/)).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Save sample' })).toBeInTheDocument()
    expect(experimentsApi.getResults).toHaveBeenCalledWith('HPHT_297')
    await waitFor(() => expect(resultsApi.getScalar).toHaveBeenCalledWith(11))
    expect(within(dialog).queryByLabelText('Segment')).not.toBeInTheDocument()
  })

  it('renders a base_mismatch warning under Data checks', async () => {
    renderPage({ ...RUN, warnings: [{ code: 'base_mismatch', experiment_ids: ['HPHT_2970'] }] })
    await userEvent.click(await screen.findByRole('button', { name: /^Data checks/ }))
    const line = screen.getByTestId('warning-base_mismatch')
    expect(line).toHaveTextContent('HPHT_2970 does not follow the run')
    expect(line).toHaveTextContent('HPHT_297')
  })

  it('shows the 404 message for an unknown run', async () => {
    vi.mocked(hphtApi.get).mockRejectedValue(Object.assign(new Error('nf'), { response: { status: 404 } }))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <MemoryRouter initialEntries={['/hpht/NOPE']}>
        <QueryClientProvider client={qc}>
          <ToastProvider>
            <Routes>
              <Route path="/hpht/:baseId" element={<HphtRunPage />} />
            </Routes>
          </ToastProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    )
    expect(await screen.findByText('No HPHT run NOPE')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to HPHT' })).toHaveAttribute('href', '/hpht')
    expect(screen.getByRole('link', { name: 'Open experiment NOPE' })).toHaveAttribute('href', '/experiments/NOPE')
  })
})

describe('HphtRunPage links (issue #158)', () => {
  beforeEach(() => {
    vi.mocked(hphtApi.get).mockReset()
    vi.mocked(hphtApi.icp).mockReset()
    vi.mocked(hphtApi.icp).mockResolvedValue([])
    vi.mocked(experimentsApi.getResults).mockReset()
    vi.mocked(experimentsApi.getResults).mockResolvedValue([])
    vi.mocked(chemicalsApi.listExperimentAdditives).mockResolvedValue([])
  })

  it('opens Segments for a run with several segments and links them in the summary', async () => {
    renderPage()
    const seg = await screen.findByRole('button', { name: /^Segments/ })
    expect(seg).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('region', { name: 'Segments' })).toBeInTheDocument()
    const hrefs = within(seg.parentElement!).getAllByRole('link').map((a) => a.getAttribute('href'))
    expect(hrefs).toEqual(RUN.segments.map((s) => `/experiments/${s.experiment_id}`))
  })

  it('keeps Segments closed for a single-segment run', async () => {
    renderPage({ ...RUN, segments: [RUN.segments[0]] })
    expect(await screen.findByRole('button', { name: /^Segments/ })).toHaveAttribute('aria-expanded', 'false')
  })

  it('links the Segment column without opening the sample editor', async () => {
    renderPage()
    const region = await samplesRegion()
    const link = within(region).getAllByRole('link', { name: 'HPHT_297-2' })[0]
    expect(link).toHaveAttribute('href', '/experiments/HPHT_297-2')
    await userEvent.click(link)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('replaces a segment ID in the URL with the run base ID', async () => {
    renderPage(RUN, '/hpht/HPHT_297-2')
    await waitFor(() => expect(screen.getByTestId('path')).toHaveTextContent(/^\/hpht\/HPHT_297$/))
    expect(screen.getByTestId('nav-type')).toHaveTextContent('REPLACE')
    expect(await screen.findByRole('heading', { name: 'HPHT_297', level: 1 })).toBeInTheDocument()
  })
})
