import { describe, it, expect, vi } from 'vitest'
import { render as rtlRender, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import type { CoreFloodSample } from '@/api/coreFloods'
import { SamplesTable } from '../SamplesTable'

// Side-sample IDs are links since issue #158, so every render needs a router.
const render = (ui: React.ReactElement) => rtlRender(ui, { wrapper: MemoryRouter })

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
  permeability_flow_rate_mL_min: null,
  notes: [],
  ...over,
})

const noIcp = new Map<number, Record<string, number>>()

describe('SamplesTable', () => {
  it('renders newest first', () => {
    const samples = [
      sample({ result_id: 1, sample_tube_number: 21 }),
      sample({ result_id: 2, sample_tube_number: 22 }),
    ]
    render(<SamplesTable samples={samples} variant={false} onEdit={vi.fn()} icpByResult={noIcp} />)
    const rows = screen.getAllByRole('row').slice(2)
    expect(within(rows[0]).getByText('22')).toBeInTheDocument()
    expect(within(rows[1]).getByText('21')).toBeInTheDocument()
  })

  it('shows grouped headers GC, Solution, Core flood', () => {
    render(<SamplesTable samples={[]} variant={false} onEdit={vi.fn()} icpByResult={noIcp} />)
    for (const name of ['GC', 'Solution', 'Core flood']) {
      expect(screen.getByRole('columnheader', { name })).toBeInTheDocument()
    }
    expect(screen.queryByText('Cum. H₂ (g/t)')).not.toBeInTheDocument()
  })

  it('shows HOLD on flow 0 and PERM when a test rate is set', () => {
    const samples = [
      sample({ result_id: 1, flow_rate_mL_min: 0 }),
      sample({ result_id: 2, permeability_flow_rate_mL_min: 0.5 }),
    ]
    render(<SamplesTable samples={samples} variant={false} onEdit={vi.fn()} icpByResult={noIcp} />)
    expect(screen.getAllByText('HOLD')).toHaveLength(1)
    expect(screen.getAllByText('PERM')).toHaveLength(1)
  })

  it('result note cell joins notes and shows MOD', () => {
    const notes = [
      { id: 1, note_type: 'result_note' as const, note_text: 'clear', created_by: null },
      { id: 2, note_type: 'observation' as const, note_text: 'bubbles', created_by: null },
      { id: 3, note_type: 'modification' as const, note_text: 'edited', created_by: null },
    ]
    render(
      <SamplesTable samples={[sample({ notes })]} variant={false} onEdit={vi.fn()} icpByResult={noIcp} />,
    )
    expect(screen.getByTitle('clear · bubbles')).toHaveTextContent('clear · bubbles')
    expect(screen.getByText('MOD')).toBeInTheDocument()
  })

  it('ICP expander only on rows with ICP and does not open edit', async () => {
    const onEdit = vi.fn()
    const icp = new Map([[2, { fe: 12.4, si: 3 }]])
    const samples = [sample({ result_id: 1 }), sample({ result_id: 2 })]
    render(<SamplesTable samples={samples} variant={false} onEdit={onEdit} icpByResult={icp} />)
    const buttons = screen.getAllByRole('button', { name: /Show ICP for/ })
    expect(buttons).toHaveLength(1)
    await userEvent.click(buttons[0])
    expect(onEdit).not.toHaveBeenCalled()
    expect(screen.getByText('Fe 12.4')).toBeInTheDocument()
    expect(screen.getByText('Si 3')).toBeInTheDocument()
  })

  it('row click opens edit', async () => {
    const onEdit = vi.fn()
    const s = sample({ result_id: 1 })
    render(<SamplesTable samples={[s]} variant={false} onEdit={onEdit} icpByResult={noIcp} />)
    await userEvent.click(screen.getAllByRole('row')[2])
    expect(onEdit).toHaveBeenCalledWith(s)
  })

  it('Enter on a row opens edit', async () => {
    const onEdit = vi.fn()
    const s = sample({ result_id: 1 })
    render(<SamplesTable samples={[s]} variant={false} onEdit={onEdit} icpByResult={noIcp} />)
    screen.getAllByRole('row')[2].focus()
    await userEvent.keyboard('{Enter}')
    expect(onEdit).toHaveBeenCalledWith(s)
  })

  it('Enter on the ICP expander does not open edit', async () => {
    const onEdit = vi.fn()
    const icp = new Map([[1, { fe: 1 }]])
    render(<SamplesTable samples={[sample({ result_id: 1 })]} variant={false} onEdit={onEdit} icpByResult={icp} />)
    screen.getByRole('button', { name: /Show ICP for/ }).focus()
    await userEvent.keyboard('{Enter}')
    expect(onEdit).not.toHaveBeenCalled()
    expect(screen.getByText('Fe 1')).toBeInTheDocument()
  })

  it('ICP elements render in ICP_ELEMENTS order', async () => {
    const icp = new Map([[1, { si: 1, fe: 2 }]])
    render(<SamplesTable samples={[sample({ result_id: 1 })]} variant={false} onEdit={vi.fn()} icpByResult={icp} />)
    await userEvent.click(screen.getByRole('button', { name: /Show ICP for/ }))
    const fe = screen.getByText('Fe 2')
    const si = screen.getByText('Si 1')
    expect(fe.compareDocumentPosition(si) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('expander labels are unique per row (date and tube)', () => {
    const icp = new Map([[1, { fe: 1 }], [2, { fe: 1 }]])
    const samples = [
      sample({ result_id: 1, sample_tube_number: 7 }),
      sample({ result_id: 2, sample_tube_number: 8 }),
    ]
    render(<SamplesTable samples={samples} variant={false} onEdit={vi.fn()} icpByResult={icp} />)
    expect(screen.getByRole('button', { name: /^Show ICP for .+, tube 7$/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Show ICP for .+, tube 8$/ })).toBeInTheDocument()
  })

  it('variant expander label names the experiment and date', () => {
    const icp = new Map([[1, { fe: 1 }]])
    const s = sample({ result_id: 1, experiment_id: 'CF_020-5_Bypass1', is_variant: true })
    render(<SamplesTable samples={[s]} variant onEdit={vi.fn()} icpByResult={icp} />)
    expect(
      screen.getByRole('button', { name: /^Show ICP for CF_020-5_Bypass1 \d{4}-\d{2}-\d{2}$/ }),
    ).toBeInTheDocument()
  })

  it('the leading group-header cell is not an empty column header', () => {
    render(<SamplesTable samples={[]} variant={false} onEdit={vi.fn()} icpByResult={noIcp} />)
    const empty = screen.getAllByRole('columnheader').filter((h) => (h.textContent ?? '') === '')
    expect(empty).toHaveLength(0)
  })

  it('the expander and date columns are sticky', () => {
    const icp = new Map([[1, { fe: 1 }]])
    render(<SamplesTable samples={[sample({ result_id: 1 })]} variant={false} onEdit={vi.fn()} icpByResult={icp} />)
    const cells = within(screen.getAllByRole('row')[2]).getAllByRole('cell')
    expect(cells[0].className).toMatch(/sticky left-0/)
    expect(cells[1].className).toMatch(/sticky/)
    expect(screen.getByRole('columnheader', { name: 'Date' }).className).toMatch(/sticky/)
  })
})

describe('SamplesTable side-sample IDs (issue #158)', () => {
  it('links the side-sample ID without firing the row edit', async () => {
    const onEdit = vi.fn()
    const s = sample({ result_id: 1, experiment_id: 'CF_020-5_Bypass1', is_variant: true })
    render(<SamplesTable samples={[s]} variant onEdit={onEdit} icpByResult={new Map()} />)
    const link = screen.getByRole('link', { name: 'CF_020-5_Bypass1' })
    expect(link).toHaveAttribute('href', '/experiments/CF_020-5_Bypass1')
    await userEvent.click(link)
    expect(onEdit).not.toHaveBeenCalled()
  })
})
