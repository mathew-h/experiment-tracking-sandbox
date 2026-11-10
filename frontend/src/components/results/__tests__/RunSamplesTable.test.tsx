import { describe, it, expect, vi } from 'vitest'
import { render as rtlRender, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import type { CoreFloodSample } from '@/api/coreFloods'
import type { HphtSample } from '@/api/hpht'
import type { ResultWithFlags } from '@/api/experiments'
import { RunSamplesTable, columnsFor } from '../RunSamplesTable'
import { fromCoreFlood, fromHpht, fromResult } from '../sampleRows'

// Segment IDs are links, so every render needs a router.
const render = (ui: React.ReactElement) => rtlRender(ui, { wrapper: MemoryRouter })

const cf = (over: Partial<CoreFloodSample>): CoreFloodSample => ({
  result_id: 1,
  experiment_id: 'CF_020',
  experiment_fk: 1,
  run_base_id: 'CF_020',
  is_variant: false,
  time_post_reaction_days: 1,
  cumulative_time_post_reaction_days: 1,
  sample_date: '2026-10-24T00:00:00',
  gc_run_date: '2026-10-24T00:00:00',
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

const hp = (over: Partial<HphtSample>): HphtSample => ({
  result_id: 1,
  experiment_id: 'HPHT_297',
  experiment_fk: 1,
  run_base_id: 'HPHT_297',
  is_variant: false,
  time_post_reaction_days: 3,
  cumulative_time_post_reaction_days: 3,
  sample_date: '2026-10-05T00:00:00',
  gc_run_date: '2026-10-05T00:00:00',
  sample_tube_number: 4,
  sampling_volume_mL: 2,
  h2_concentration: 450,
  gas_sampling_volume_ml: null,
  gas_sampling_pressure_MPa: null,
  h2_micromoles: 12,
  h2_mass_ug: null,
  h2_grams_per_ton_yield: 1.25,
  ferrous_iron_yield_h2_pct: 16.8,
  final_ph: 6.5,
  final_conductivity_mS_cm: 3,
  reactor_slot: 'R07',
  interval_days: 3,
  cumulative_h2_grams_per_ton: 4.5,
  h2_grams_per_ton_per_day: 1.5,
  cumulative_h2_micromoles: 40,
  cumulative_ferrous_iron_yield_h2_pct: 20,
  notes: [],
  ...over,
})

const result = (over: Partial<ResultWithFlags>): ResultWithFlags => ({
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
  h2_concentration: 512,
  h2_grams_per_ton_yield: 2,
  h2_micromoles: 3,
  gross_ammonium_concentration_mM: null,
  background_ammonium_concentration_mM: null,
  final_conductivity_mS_cm: 4,
  final_ph: 7,
  scalar_measurement_date: '2026-04-08T00:00:00',
  ferrous_iron_yield_h2_pct: 16.8,
  ferrous_iron_yield_nh3_pct: null,
  nmr_run_date: null,
  icp_run_date: null,
  gc_run_date: '2026-04-09T00:00:00',
  xrd_run_date: null,
  sample_tube_number: 14,
  ...over,
})

const noIcp = new Map<number, Record<string, number>>()

/** Header texts of the second header row (the first holds the groups). */
const heads = () =>
  within(screen.getAllByRole('row')[1]).getAllByRole('columnheader').map((h) => h.textContent)
const bodyRows = () => screen.getAllByRole('row').slice(2)

describe('RunSamplesTable — one column spec (issue #163)', () => {
  it('the three tables share the base columns in one order', () => {
    const base = ['Date', 'Day', 'Tube', 'Result note', 'H₂ ppm', 'H₂ µmol', 'H₂ g/t']
    const keys = (cols: ReturnType<typeof columnsFor>) =>
      cols.map((c) => c.label ?? c.head).filter((h) => base.includes(h as string))
    expect(keys(columnsFor('segment', 'hpht'))).toEqual(base)
    expect(keys(columnsFor('run', 'hpht'))).toEqual(base)
    expect(keys(columnsFor('run', 'core-flood'))).toEqual(base)
  })

  it('segment scope: no Segment or running totals', () => {
    render(<RunSamplesTable rows={[fromResult(result({}), 'HPHT_001')]} scope="segment" kind="hpht" icpByResult={noIcp} />)
    expect(heads()).toEqual([
      'Date', 'Day', 'Tube', 'Result note', 'H₂ ppm', 'H₂ µmol', 'H₂ g/t', 'Fe²⁺ H₂ %', 'pH', 'Cond.',
    ])
  })

  it('HPHT run scope: Segment first, running totals and Liq mL', () => {
    render(<RunSamplesTable rows={[fromHpht(hp({}))]} scope="run" kind="hpht" icpByResult={noIcp} />)
    expect(heads()).toEqual([
      'Segment', 'Date', 'Day', 'Tube', 'Result note', 'H₂ ppm', 'H₂ µmol', 'H₂ g/t', 'Cum. H₂ g/t',
      'g/t/day', 'Fe²⁺ H₂ %', 'pH', 'Cond.', 'Liq mL',
    ])
    for (const name of ['GC', 'Solution']) {
      expect(screen.getByRole('columnheader', { name })).toBeInTheDocument()
    }
    expect(screen.queryByRole('columnheader', { name: 'Core flood' })).not.toBeInTheDocument()
  })

  it('Core Flood run scope adds the Core flood group and has no Fe²⁺ column', () => {
    render(<RunSamplesTable rows={[fromCoreFlood(cf({}))]} scope="run" kind="core-flood" icpByResult={noIcp} />)
    expect(heads()).toEqual([
      'Segment', 'Date', 'Day', 'Tube', 'Result note', 'H₂ ppm', 'H₂ µmol', 'H₂ g/t', 'Cum. H₂ g/t',
      'g/t/day', 'pH', 'Cond.', 'Liq mL', 'Flow', 'Perm. flow', 'Inlet psi', 'Outlet psi',
    ])
    for (const name of ['GC', 'Solution', 'Core flood']) {
      expect(screen.getByRole('columnheader', { name })).toBeInTheDocument()
    }
  })

  it('side samples leave out the running totals', () => {
    render(<RunSamplesTable rows={[fromHpht(hp({ is_variant: true }))]} scope="run" kind="hpht" variant icpByResult={noIcp} />)
    expect(heads()).not.toContain('Cum. H₂ g/t')
    expect(heads()).not.toContain('g/t/day')
  })

  it('formats a value the same way in every scope', () => {
    render(
      <>
        <RunSamplesTable rows={[fromResult(result({ h2_concentration: 512.0 }), 'X')]} scope="segment" kind="hpht" icpByResult={noIcp} />
        <RunSamplesTable rows={[fromHpht(hp({ result_id: 2, h2_concentration: 512.0 }))]} scope="run" kind="hpht" icpByResult={noIcp} />
      </>,
    )
    expect(screen.getAllByText('512')).toHaveLength(2)
  })

  it('the leading group-header cell is not an empty column header', () => {
    render(<RunSamplesTable rows={[]} scope="run" kind="core-flood" icpByResult={noIcp} />)
    const empty = screen.getAllByRole('columnheader').filter((h) => (h.textContent ?? '') === '')
    expect(empty).toHaveLength(0)
  })

  it('shows emptyText when there are no rows', () => {
    render(<RunSamplesTable rows={[]} scope="run" kind="hpht" icpByResult={noIcp} emptyText="No samples yet" />)
    expect(screen.getByText('No samples yet')).toBeInTheDocument()
  })
})

describe('RunSamplesTable — cells', () => {
  it('keeps the row order it is given', () => {
    const rows = [cf({ result_id: 2, sample_tube_number: 22 }), cf({ result_id: 1, sample_tube_number: 21 })]
    render(<RunSamplesTable rows={rows.map(fromCoreFlood)} scope="run" kind="core-flood" icpByResult={noIcp} />)
    expect(within(bodyRows()[0]).getByText('22')).toBeInTheDocument()
    expect(within(bodyRows()[1]).getByText('21')).toBeInTheDocument()
  })

  it('shows HOLD on flow 0 and PERM when a test rate is set', () => {
    const rows = [cf({ result_id: 1, flow_rate_mL_min: 0 }), cf({ result_id: 2, permeability_flow_rate_mL_min: 0.5 })]
    render(<RunSamplesTable rows={rows.map(fromCoreFlood)} scope="run" kind="core-flood" icpByResult={noIcp} />)
    expect(screen.getAllByText('HOLD')).toHaveLength(1)
    expect(screen.getAllByText('PERM')).toHaveLength(1)
  })

  it('the result note joins result notes and observations and shows MOD', () => {
    const notes = [
      { id: 1, note_type: 'result_note' as const, note_text: 'clear', created_by: null },
      { id: 2, note_type: 'observation' as const, note_text: 'bubbles', created_by: null },
      { id: 3, note_type: 'modification' as const, note_text: 'edited', created_by: null },
    ]
    render(<RunSamplesTable rows={[fromCoreFlood(cf({ notes }))]} scope="run" kind="core-flood" icpByResult={noIcp} />)
    expect(screen.getByTitle('clear · bubbles')).toHaveTextContent('clear · bubbles')
    expect(screen.getByText('MOD')).toBeInTheDocument()
  })

  it('names and links each sample segment in the first column', () => {
    const rows = [cf({ result_id: 2, experiment_id: 'CF_020-3' }), cf({ result_id: 1, experiment_id: 'CF_020' })]
    render(<RunSamplesTable rows={rows.map(fromCoreFlood)} scope="run" kind="core-flood" icpByResult={noIcp} />)
    expect(within(bodyRows()[0]).getAllByRole('cell')[0]).toHaveTextContent('CF_020-3')
    expect(within(bodyRows()[0]).getByRole('link', { name: 'CF_020-3' })).toHaveAttribute('href', '/experiments/CF_020-3')
  })

  it('Segment then Date stay pinned on a run page; Date alone on the Results tab', () => {
    const { unmount } = render(
      <RunSamplesTable rows={[fromCoreFlood(cf({}))]} scope="run" kind="core-flood" icpByResult={noIcp} />,
    )
    let cells = within(bodyRows()[0]).getAllByRole('cell')
    expect(cells[0].className).toMatch(/sticky left-0/)
    expect(cells[1].className).toMatch(/sticky left-44/)
    expect(screen.getByRole('columnheader', { name: 'Segment' }).className).toMatch(/sticky left-0/)
    expect(screen.getByRole('columnheader', { name: 'Date' }).className).toMatch(/sticky left-44/)
    unmount()
    render(<RunSamplesTable rows={[fromResult(result({}), 'X')]} scope="segment" kind="hpht" icpByResult={noIcp} />)
    cells = within(bodyRows()[0]).getAllByRole('cell')
    expect(cells[0].className).toMatch(/sticky left-0/)
  })

  it('marks the primary result with ★ on the Results tab only', () => {
    render(
      <>
        <RunSamplesTable rows={[fromResult(result({}), 'X')]} scope="segment" kind="hpht" icpByResult={noIcp} />
        <RunSamplesTable rows={[fromHpht(hp({ result_id: 2 }))]} scope="run" kind="hpht" icpByResult={noIcp} />
      </>,
    )
    expect(screen.getAllByTitle('Primary result for this timepoint')).toHaveLength(1)
  })
})

describe('RunSamplesTable — one interaction model (issue #163)', () => {
  it('row click and Enter edit, handing back the page row', async () => {
    const onEdit = vi.fn()
    const s = cf({ result_id: 1 })
    render(<RunSamplesTable rows={[fromCoreFlood(s)]} scope="run" kind="core-flood" onEdit={onEdit} icpByResult={noIcp} />)
    await userEvent.click(bodyRows()[0])
    expect(onEdit).toHaveBeenLastCalledWith(s)
    bodyRows()[0].focus()
    await userEvent.keyboard('{Enter}')
    expect(onEdit).toHaveBeenCalledTimes(2)
  })

  it('a row canEdit rejects is not clickable', async () => {
    const onEdit = vi.fn()
    const r = result({ is_primary_timepoint_result: false })
    render(
      <RunSamplesTable
        rows={[fromResult(r, 'X')]} scope="segment" kind="hpht"
        onEdit={onEdit} canEdit={(row) => row.isPrimary} icpByResult={noIcp}
      />,
    )
    await userEvent.click(bodyRows()[0])
    expect(onEdit).not.toHaveBeenCalled()
    expect(bodyRows()[0]).not.toHaveAttribute('tabindex')
  })

  it('without onEdit no row is clickable', async () => {
    render(<RunSamplesTable rows={[fromResult(result({}), 'X')]} scope="segment" kind="core-flood" icpByResult={noIcp} />)
    expect(bodyRows()[0].className).not.toMatch(/cursor-pointer/)
  })

  it('the segment link and the flags never fire the row edit', async () => {
    const onEdit = vi.fn()
    const s = cf({ result_id: 1, experiment_id: 'CF_020-3' })
    render(
      <RunSamplesTable
        rows={[fromCoreFlood(s)]} scope="run" kind="core-flood" onEdit={onEdit}
        icpByResult={new Map([[1, { fe: 3 }]])}
      />,
    )
    await userEvent.click(screen.getByRole('link', { name: 'CF_020-3' }))
    await userEvent.click(screen.getByRole('button', { name: /^Show ICP for/ }))
    await userEvent.click(screen.getByRole('button', { name: /^Show details for/ }))
    screen.getByRole('button', { name: /^Show ICP for/ }).focus()
    await userEvent.keyboard('{Enter}')
    expect(onEdit).not.toHaveBeenCalled()
  })
})

describe('RunSamplesTable — ICP, MOD and DETAILS flags', () => {
  it('ICP only on rows with readings, in ICP_ELEMENTS order', async () => {
    const rows = [cf({ result_id: 2, sample_tube_number: 8 }), cf({ result_id: 1, sample_tube_number: 7 })]
    render(
      <RunSamplesTable
        rows={rows.map(fromCoreFlood)} scope="run" kind="core-flood"
        icpByResult={new Map([[2, { si: 1, fe: 2 }]])}
      />,
    )
    const flags = screen.getAllByRole('button', { name: /Show ICP for/ })
    expect(flags).toHaveLength(1)
    expect(flags[0]).toHaveAccessibleName(/, tube 8$/)
    await userEvent.click(flags[0])
    const fe = screen.getByText('Fe 2')
    expect(fe.compareDocumentPosition(screen.getByText('Si 1')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('a side sample flag names the experiment and date', () => {
    const s = cf({ result_id: 1, experiment_id: 'CF_020-5_Bypass1', is_variant: true })
    render(
      <RunSamplesTable rows={[fromCoreFlood(s)]} scope="run" kind="core-flood" variant icpByResult={new Map([[1, { fe: 1 }]])} />,
    )
    expect(screen.getByRole('button', { name: /^Show ICP for CF_020-5_Bypass1 \d{4}-\d{2}-\d{2}$/ })).toBeInTheDocument()
  })

  it('MOD opens the modification note', async () => {
    const s = cf({
      notes: [{ id: 9, note_type: 'modification', note_text: 'Swapped backpressure regulator', created_by: 'tech@x' }],
    })
    render(<RunSamplesTable rows={[fromCoreFlood(s)]} scope="run" kind="core-flood" icpByResult={noIcp} />)
    await userEvent.click(screen.getByRole('button', { name: /^Show modification for/ }))
    expect(screen.getByRole('region', { name: 'Modification notes' })).toHaveTextContent('Swapped backpressure regulator')
  })

  it('DETAILS on a run page shows the GC run date and every note', async () => {
    const s = hp({
      notes: [
        { id: 1, note_type: 'result_note', note_text: 'Cloudy', created_by: 'a@x' },
        { id: 2, note_type: 'modification', note_text: 'Topped up', created_by: null },
      ],
    })
    render(<RunSamplesTable rows={[fromHpht(s)]} scope="run" kind="hpht" icpByResult={noIcp} />)
    await userEvent.click(screen.getByRole('button', { name: /^Show details for/ }))
    const details = screen.getByRole('region', { name: 'Sample details' })
    expect(within(details).getByText('2026-10-05')).toBeInTheDocument()
    expect(within(details).getByTestId('timepoint-notes')).toHaveTextContent('Cloudy')
    expect(within(details).getByTestId('timepoint-notes')).toHaveTextContent('Topped up')
  })

  it('DETAILS on the Results tab shows set run dates, not unset ones', async () => {
    const r = result({ nmr_run_date: '2026-05-01T00:00:00Z', xrd_run_date: '2026-06-15T00:00:00Z', icp_run_date: null })
    render(<RunSamplesTable rows={[fromResult(r, 'X')]} scope="segment" kind="hpht" icpByResult={noIcp} />)
    await userEvent.click(screen.getByRole('button', { name: /^Show details for/ }))
    const details = screen.getByRole('region', { name: 'Sample details' })
    expect(details).toHaveTextContent('NMR: 2026-05-01')
    expect(details).toHaveTextContent('XRD: 2026-06-15')
    expect(details).not.toHaveTextContent('ICP:')
  })

  it('DETAILS warns when an H₂ reading has no GC run date', async () => {
    render(
      <RunSamplesTable rows={[fromHpht(hp({ gc_run_date: null, h2_concentration: 450 }))]} scope="run" kind="hpht" icpByResult={noIcp} />,
    )
    await userEvent.click(screen.getByRole('button', { name: /^Show details for/ }))
    expect(screen.getByText('not recorded')).toBeInTheDocument()
    expect(screen.getByText(/not counted by the Dashboard's GC Measurements card/)).toBeInTheDocument()
  })

  it('no DETAILS flag when a row has nothing to show', () => {
    render(
      <RunSamplesTable
        rows={[fromHpht(hp({ gc_run_date: null, h2_concentration: null, notes: [] }))]}
        scope="run" kind="hpht" icpByResult={noIcp}
      />,
    )
    expect(screen.queryByRole('button', { name: /^Show details for/ })).not.toBeInTheDocument()
  })

  it('page extras render inside DETAILS only once it is opened', async () => {
    const extra = vi.fn(() => <p>Extra values</p>)
    render(
      <RunSamplesTable
        rows={[fromResult(result({ gc_run_date: null, h2_concentration: null }), 'X')]}
        scope="segment" kind="hpht" icpByResult={noIcp} detailsExtra={extra}
      />,
    )
    expect(screen.queryByText('Extra values')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^Show details for/ }))
    expect(screen.getByText('Extra values')).toBeInTheDocument()
  })
})
