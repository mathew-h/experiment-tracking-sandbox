import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { CoreFloodRun, CoreFloodSample, CoreFloodSegment } from '@/api/coreFloods'
import { ToastProvider } from '@/components/ui'

vi.mock('@/api/coreFloods', () => ({
  coreFloodsApi: { get: vi.fn(), createSample: vi.fn(), updateSample: vi.fn() },
}))

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    patchStatus: vi.fn(),
    patch: vi.fn(),
    get: vi.fn(),
    checkExists: vi.fn(),
    patchNote: vi.fn(),
    addNote: vi.fn(),
  },
}))
vi.mock('@/api/conditions', () => ({ conditionsApi: { patch: vi.fn() } }))

import { coreFloodsApi } from '@/api/coreFloods'
import { experimentsApi } from '@/api/experiments'
import { conditionsApi } from '@/api/conditions'
import { CoreFloodRunPage } from '../CoreFloodRunPage'

const segment = (over: Partial<CoreFloodSegment>): CoreFloodSegment => ({
  id: 1,
  experiment_id: 'CF_020',
  status: 'COMPLETED',
  date: '2026-10-23T00:00:00',
  parent_experiment_id: null,
  is_variant: false,
  description: 'First segment',
  conditions_id: 1,
  pore_volume_mL: 12.5,
  rock_mass_g: 100,
  reactor_slot: 'CF01',
  ...over,
})

const sample = (over: Partial<CoreFloodSample>): CoreFloodSample => ({
  result_id: 1,
  experiment_id: 'CF_020',
  experiment_fk: 1,
  run_base_id: 'CF_020',
  is_variant: false,
  time_post_reaction_days: 1,
  cumulative_time_post_reaction_days: 1,
  sample_date: '2026-10-24T00:00:00',
  gc_run_date: null,
  sample_tube_number: 7,
  flow_rate_mL_min: 0.5,
  nitrogen_flow_rate_mL_min: null,
  inlet_pressure_psi: null,
  outlet_pressure_psi: null,
  sampling_volume_mL: 3.25,
  h2_concentration: 100,
  gas_sampling_volume_ml: null,
  gas_sampling_pressure_MPa: null,
  h2_micromoles: 1.5,
  h2_mass_ug: null,
  h2_grams_per_ton_yield: 2.5,
  final_ph: 7.1,
  final_conductivity_mS_cm: 4.2,
  pore_volume_mL: 12.5,
  interval_days: 1,
  cumulative_liquid_volume_mL: 3.25,
  cumulative_pore_volumes: 0.26,
  cumulative_h2_grams_per_ton: 2.5,
  h2_grams_per_ton_per_day: 2.5,
  is_hold_interval: false,
  ...over,
})

const RUN: CoreFloodRun = {
  base_id: 'CF_020',
  warnings: [],
  segments: [
    segment({}),
    segment({
      id: 2,
      experiment_id: 'CF_020-2',
      status: 'ONGOING',
      parent_experiment_id: 'CF_020',
      reactor_slot: 'CF02',
      pore_volume_mL: null,
      description: null,
    }),
    segment({
      id: 3,
      experiment_id: 'CF_020-5_Bypass1',
      status: 'COMPLETED',
      parent_experiment_id: 'CF_020-2',
      is_variant: true,
      reactor_slot: null,
    }),
  ],
  samples: [
    // legacy row: no cumulative time, no liquid volume
    sample({
      result_id: 10,
      cumulative_time_post_reaction_days: null,
      sampling_volume_mL: null,
      sample_tube_number: 11,
      cumulative_pore_volumes: null,
    }),
    sample({
      result_id: 11,
      experiment_id: 'CF_020-2',
      sample_tube_number: 12,
      flow_rate_mL_min: 0,
      cumulative_time_post_reaction_days: 5,
      cumulative_h2_grams_per_ton: 42.12349,
      cumulative_pore_volumes: 1.23456,
    }),
    sample({
      result_id: 12,
      experiment_id: 'CF_020-5_Bypass1',
      is_variant: true,
      sample_tube_number: 13,
      cumulative_h2_grams_per_ton: null,
      cumulative_pore_volumes: null,
      h2_grams_per_ton_per_day: null,
    }),
  ],
}

function Probe() {
  return <div data-testid="path">{useLocation().pathname}</div>
}

function renderPage(path = '/core-floods/CF_020') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <Routes>
            <Route path="/core-floods/:baseId" element={<CoreFloodRunPage />} />
          </Routes>
          <Probe />
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('CoreFloodRunPage', () => {
  beforeEach(() => {
    vi.mocked(coreFloodsApi.get).mockReset()
    vi.mocked(coreFloodsApi.get).mockResolvedValue(RUN)
  })

  it('variants render in Side samples without cumulative values', async () => {
    renderPage()
    const region = await screen.findByRole('region', { name: 'Side samples (blanks, bypass)' })
    expect(within(region).getByText('CF_020-5_Bypass1')).toBeInTheDocument()
    expect(within(region).queryByText('Cum. H₂ (g/t)')).not.toBeInTheDocument()
    expect(within(region).queryByText('Pore volumes')).not.toBeInTheDocument()
    expect(within(region).queryByText('g/t/day')).not.toBeInTheDocument()
    // the variant is not in the main samples table
    const main = screen.getByRole('region', { name: 'Samples' })
    expect(within(main).queryByText('CF_020-5_Bypass1')).not.toBeInTheDocument()
  })

  it('a zero flow shows a HOLD badge', async () => {
    renderPage()
    const main = await screen.findByRole('region', { name: 'Samples' })
    expect(within(main).getAllByText('HOLD')).toHaveLength(1)
  })

  it('legacy nulls render as dashes, in server order', async () => {
    renderPage()
    const main = await screen.findByRole('region', { name: 'Samples' })
    const rows = within(main).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(2)
    const cells = within(rows[0]).getAllByRole('cell')
    expect(cells[1]).toHaveTextContent('—') // Day
    expect(cells[5]).toHaveTextContent('—') // Liquid vol
    expect(within(rows[0]).getByText('11')).toBeInTheDocument()
    expect(within(rows[1]).getByText('12')).toBeInTheDocument()
  })

  it('header shows the server cumulative values', async () => {
    renderPage()
    const label = await screen.findByText('Cumulative H₂ to date')
    expect(label.parentElement).toHaveTextContent('42.123')
    expect(screen.getByText('Pore volumes to date').parentElement).toHaveTextContent('1.235')
    expect(screen.getByText('Rig').parentElement).toHaveTextContent('CF02')
    expect(screen.getByText('Ongoing', { ignore: 'option' }).parentElement).toHaveTextContent('CF_020-2')
  })

  it('shows not-found for a 404', async () => {
    vi.mocked(coreFloodsApi.get).mockRejectedValue(
      Object.assign(new Error('nope'), { response: { status: 404 } }),
    )
    renderPage('/core-floods/CF_999')
    expect(await screen.findByText('No core flood run CF_999')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /core floods/i })).toHaveAttribute('href', '/core-floods')
  })

  it('opens the modal from Add sample and from a row click', async () => {
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: '+ Add sample' }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })

  it('a non-variant sample row opens the modal in edit mode', async () => {
    renderPage()
    const main = await screen.findByRole('region', { name: 'Samples' })
    await userEvent.click(within(main).getAllByRole('row')[2])
    expect(await screen.findByRole('dialog', { name: 'Edit sample — CF_020-2' })).toBeInTheDocument()
  })
})

const withWarnings = (warnings: CoreFloodRun['warnings'], segments?: CoreFloodSegment[]): CoreFloodRun => ({
  ...RUN,
  warnings,
  segments: segments ?? RUN.segments,
})

describe('CoreFloodRunPage segment edits and cleanup', () => {
  beforeEach(() => {
    vi.mocked(coreFloodsApi.get).mockReset()
    vi.mocked(coreFloodsApi.get).mockResolvedValue(RUN)
    vi.mocked(experimentsApi.patchStatus).mockReset()
    vi.mocked(experimentsApi.patch).mockReset()
    vi.mocked(experimentsApi.checkExists).mockReset()
    vi.mocked(experimentsApi.checkExists).mockResolvedValue({ exists: false })
    vi.mocked(conditionsApi.patch).mockReset()
  })

  it('a multiple_ongoing warning shows the status action', async () => {
    vi.mocked(coreFloodsApi.get).mockResolvedValue(
      withWarnings([{ code: 'multiple_ongoing', experiment_ids: ['CF_020', 'CF_020-2'] }]),
    )
    vi.mocked(experimentsApi.patchStatus).mockResolvedValue({} as never)
    renderPage()
    const card = (await screen.findByRole('heading', { name: 'Cleanup' })).closest('section')!
    expect(within(card).getAllByRole('combobox')).toHaveLength(2)
    for (const id of ['CF_020', 'CF_020-2']) {
      const label = within(card).getByText(id, { selector: 'span' })
      expect(within(label.parentElement!).getByRole('combobox', { name: `Status of ${id}` })).toBeInTheDocument()
    }
    await userEvent.selectOptions(
      within(card).getByRole('combobox', { name: 'Status of CF_020-2' }),
      'COMPLETED',
    )
    expect(experimentsApi.patchStatus).toHaveBeenCalledWith('CF_020-2', 'COMPLETED')
  })

  it('set pore volume for all segments patches each missing segment', async () => {
    vi.mocked(coreFloodsApi.get).mockResolvedValue(
      withWarnings(
        [{ code: 'missing_pore_volume', experiment_ids: ['CF_020', 'CF_020-2'] }],
        [segment({ id: 1, conditions_id: 11 }), segment({ id: 2, experiment_id: 'CF_020-2', conditions_id: 12 })],
      ),
    )
    vi.mocked(conditionsApi.patch).mockResolvedValue({} as never)
    renderPage()
    await userEvent.type(await screen.findByLabelText('Pore volume for all segments'), '42')
    await userEvent.click(screen.getByRole('button', { name: 'Set pore volume for all segments' }))
    await waitFor(() => expect(conditionsApi.patch).toHaveBeenCalledTimes(2))
    expect(conditionsApi.patch).toHaveBeenCalledWith(11, { pore_volume_mL: 42 })
    expect(conditionsApi.patch).toHaveBeenCalledWith(12, { pore_volume_mL: 42 })
  })

  it('renaming the only segment moves the URL to the new run', async () => {
    const lone = withWarnings([], [segment({ id: 9, experiment_id: 'CF_020_5_Brine' })])
    vi.mocked(coreFloodsApi.get).mockImplementation(async (id) =>
      id === 'CF_020' ? RUN : { ...lone, base_id: id },
    )
    vi.mocked(experimentsApi.patch).mockResolvedValue({
      experiment_id: 'CF_020-5_Brine',
      base_experiment_id: 'CF_020',
    } as never)
    renderPage('/core-floods/CF_020_5')
    await userEvent.click(await screen.findByRole('button', { name: 'Rename CF_020_5_Brine' }))
    const input = screen.getByLabelText('New experiment ID')
    await userEvent.clear(input)
    await userEvent.type(input, 'CF_020-5_Brine')
    const save = screen.getByRole('button', { name: 'Save' })
    await waitFor(() => expect(save).toBeEnabled())
    await userEvent.click(save)
    await waitFor(() => expect(screen.getByTestId('path')).toHaveTextContent('/core-floods/CF_020'))
    expect(experimentsApi.patch).toHaveBeenCalledWith('CF_020_5_Brine', { experiment_id: 'CF_020-5_Brine' })
    await waitFor(() => expect(coreFloodsApi.get).toHaveBeenLastCalledWith('CF_020'))
  })

  it('renaming one of several segments refetches the run in place', async () => {
    const renamed: CoreFloodRun = {
      ...RUN,
      segments: RUN.segments.map((s) => (s.id === 2 ? { ...s, experiment_id: 'CF_020-3' } : s)),
    }
    vi.mocked(experimentsApi.patch).mockImplementation(async () => {
      vi.mocked(coreFloodsApi.get).mockResolvedValue(renamed)
      return { experiment_id: 'CF_020-3', base_experiment_id: 'CF_020' } as never
    })
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Rename CF_020-2' }))
    const input = screen.getByLabelText('New experiment ID')
    await userEvent.clear(input)
    await userEvent.type(input, 'CF_020-3')
    const save = screen.getByRole('button', { name: 'Save' })
    await waitFor(() => expect(save).toBeEnabled())
    await userEvent.click(save)
    const seg = await screen.findByRole('region', { name: 'Segments' })
    await waitFor(() => expect(within(seg).getByText('CF_020-3')).toBeInTheDocument())
    expect(coreFloodsApi.get).toHaveBeenLastCalledWith('CF_020')
    expect(screen.getByTestId('path')).toHaveTextContent('/core-floods/CF_020')
  })

  it('a rejected status change shows the server detail', async () => {
    vi.mocked(experimentsApi.patchStatus).mockRejectedValue(new Error('Reactor CF01 is occupied by CF_026'))
    renderPage()
    await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Status of CF_020' }), 'ONGOING')
    expect(await screen.findByText('Reactor CF01 is occupied by CF_026')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Status of CF_020' })).toHaveValue('COMPLETED')
  })

  it('a partial pore volume failure still refreshes and names the failed segment', async () => {
    vi.mocked(coreFloodsApi.get).mockResolvedValue(
      withWarnings(
        [{ code: 'missing_pore_volume', experiment_ids: ['CF_020', 'CF_020-2'] }],
        [segment({ id: 1, conditions_id: 11 }), segment({ id: 2, experiment_id: 'CF_020-2', conditions_id: 12 })],
      ),
    )
    vi.mocked(conditionsApi.patch).mockImplementation(async (id) => {
      if (id === 12) throw new Error('boom')
      return {} as never
    })
    renderPage()
    await userEvent.type(await screen.findByLabelText('Pore volume for all segments'), '42')
    const before = vi.mocked(coreFloodsApi.get).mock.calls.length
    await userEvent.click(screen.getByRole('button', { name: 'Set pore volume for all segments' }))
    expect(await screen.findByText(/CF_020-2 \(boom\)/)).toBeInTheDocument()
    await waitFor(() => expect(vi.mocked(coreFloodsApi.get).mock.calls.length).toBeGreaterThan(before))
  })

  it('cleanup buttons name their segment', async () => {
    vi.mocked(coreFloodsApi.get).mockResolvedValue(
      withWarnings([
        { code: 'multiple_roots', experiment_ids: ['CF_020', 'CF_020-2'] },
        { code: 'sample_missing_flow_rate', experiment_ids: ['CF_020'] },
      ], [segment({}), segment({ id: 2, experiment_id: 'CF_020-2' })]),
    )
    vi.mocked(coreFloodsApi.get).mockResolvedValue({
      ...(await coreFloodsApi.get('x')),
      samples: [sample({ result_id: 50, flow_rate_mL_min: null })],
    })
    renderPage()
    const card = (await screen.findByRole('heading', { name: 'Cleanup' })).closest('section')!
    expect(within(card).getByRole('button', { name: 'Rename CF_020-2' })).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: /^Edit CF_020 · / })).toBeInTheDocument()
  })

  it('Describe then Cancel returns the cell to the description button', async () => {
    vi.mocked(experimentsApi.get).mockResolvedValue({ notes: [] } as never)
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Edit description of CF_020' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
    expect(await screen.findByRole('button', { name: 'Edit description of CF_020' })).toBeInTheDocument()
    expect(screen.queryByTestId('description-editor')).not.toBeInTheDocument()
  })

  it('a failed description fetch shows the error and a way back', async () => {
    vi.mocked(experimentsApi.get).mockRejectedValue(new Error('nope'))
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Edit description of CF_020' }))
    expect(await screen.findByText(/Could not load description: nope/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.getByRole('button', { name: 'Edit description of CF_020' })).toBeInTheDocument()
  })
})
