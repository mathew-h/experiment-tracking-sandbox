import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { CoreFloodRun, CoreFloodSample, CoreFloodSegment } from '@/api/coreFloods'
import { ToastProvider } from '@/components/ui'

vi.mock('@/api/coreFloods', () => ({
  coreFloodsApi: { get: vi.fn(), createSample: vi.fn(), updateSample: vi.fn() },
}))

import { coreFloodsApi } from '@/api/coreFloods'
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

function renderPage(path = '/core-floods/CF_020') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <Routes>
            <Route path="/core-floods/:baseId" element={<CoreFloodRunPage />} />
          </Routes>
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
    expect(screen.getByText('Ongoing').parentElement).toHaveTextContent('CF_020-2')
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
})
