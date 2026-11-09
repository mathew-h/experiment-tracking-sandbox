/** Issue #148: the result entry form (add and edit). Replaces
 *  AddResultsModal.timepoint.test.tsx; its -t lock cases are ported below. */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import type { ExperimentNote, ResultWithFlags } from '@/api/experiments'
import * as experimentsApiModule from '@/api/experiments'
import * as resultsApiModule from '@/api/results'
import { PSI_TO_MPA } from '@/utils/units'
import { ResultEntryModal } from '../ResultEntryModal'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    createResult: vi.fn(() => Promise.resolve({})),
    updateResult: vi.fn(() => Promise.resolve({})),
  },
}))

vi.mock('@/api/results', () => ({
  resultsApi: { getScalar: vi.fn() },
}))

vi.mock('@/utils/labDate', async () => {
  const actual = await vi.importActual<typeof import('@/utils/labDate')>('@/utils/labDate')
  return { ...actual, labTodayISO: () => '2026-11-07' }
})

const api = vi.mocked(experimentsApiModule.experimentsApi)
const getScalar = vi.mocked(resultsApiModule.resultsApi.getScalar)

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  )
}

function note(over: Partial<ExperimentNote>): ExperimentNote {
  return {
    id: 1,
    experiment_fk: 10,
    note_text: '',
    note_type: 'result_note',
    result_id: 5,
    needs_review: false,
    created_at: '2026-11-01T10:00:00Z',
    updated_at: null,
    ...over,
  } as ExperimentNote
}

const result: ResultWithFlags = {
  id: 5,
  experiment_fk: 10,
  time_post_reaction_days: 6,
  time_post_reaction_bucket_days: 6,
  cumulative_time_post_reaction_days: 6,
  is_primary_timepoint_result: true,
  created_at: '2026-11-07T00:00:00Z',
  has_scalar: true,
  has_icp: false,
  has_modification_note: true,
  notes: [
    note({ id: 1, note_text: 'liquid cloudy', note_type: 'result_note' }),
    note({ id: 2, note_text: 'brine swapped', note_type: 'modification' }),
    note({ id: 3, note_text: 'from upload', note_type: 'observation' }),
  ],
  grams_per_ton_yield: null,
  h2_concentration: 500,
  h2_grams_per_ton_yield: null,
  h2_micromoles: null,
  gross_ammonium_concentration_mM: null,
  background_ammonium_concentration_mM: null,
  final_conductivity_mS_cm: 12,
  final_ph: 7.1,
  scalar_measurement_date: '2026-11-07T00:00:00',
  ferrous_iron_yield_h2_pct: null,
  ferrous_iron_yield_nh3_pct: null,
  nmr_run_date: null,
  icp_run_date: null,
  gc_run_date: '2026-11-07T00:00:00',
  xrd_run_date: null,
  sample_tube_number: 4,
}

const scalar = {
  id: 9,
  result_id: 5,
  final_ph: 7.1,
  final_conductivity_mS_cm: 12,
  final_dissolved_oxygen_mg_L: null,
  gross_ammonium_concentration_mM: null,
  background_ammonium_concentration_mM: null,
  grams_per_ton_yield: null,
  ferrous_iron_yield: null,
  h2_concentration: 500,
  h2_micromoles: null,
  h2_grams_per_ton_yield: null,
  measurement_date: '2026-11-07T00:00:00',
  sampling_volume_mL: 2,
  gc_run_date: '2026-11-07T00:00:00',
  gas_sampling_volume_ml: 5,
  // 14.5 psi, stored with float noise; must not count as an edit.
  gas_sampling_pressure_MPa: 14.5 * PSI_TO_MPA + 1e-9,
}

const addProps = {
  open: true,
  onClose: () => {},
  experimentId: 'HPHT_001',
  experimentType: 'HPHT',
  experimentStart: '2026-11-01T00:00:00',
  idTimepointDays: null,
}

beforeEach(() => {
  vi.clearAllMocks()
  getScalar.mockResolvedValue(scalar)
})

describe('ResultEntryModal — add', () => {
  it('submits exactly one POST with tube, description, MPa pressure and GC date', async () => {
    const user = userEvent.setup()
    wrap(<ResultEntryModal {...addProps} />)
    await user.type(screen.getByLabelText('Tube #'), '12')
    await user.type(screen.getByLabelText('Result Note/Sample Description'), 'liquid cloudy')
    await user.type(screen.getByLabelText('Gas pressure (psi)'), '100')
    await user.type(screen.getByLabelText('H₂ (ppm)'), '450')
    await user.click(screen.getByRole('button', { name: 'Save Results' }))

    await vi.waitFor(() => expect(api.createResult).toHaveBeenCalledTimes(1))
    expect(api.updateResult).not.toHaveBeenCalled()
    const [id, body] = api.createResult.mock.calls[0]
    expect(id).toBe('HPHT_001')
    expect(body).toMatchObject({
      measurement_date: '2026-11-07',
      gc_run_date: '2026-11-07',
      time_post_reaction_days: 6,
      sample_tube_number: 12,
      h2_concentration: 450,
      result_note: 'liquid cloudy',
    })
    expect(body.gas_sampling_pressure_MPa).toBeCloseTo(100 * PSI_TO_MPA, 9)
    expect(body).not.toHaveProperty('modification_note')
    expect(body).not.toHaveProperty('final_ph')
  })

  it('omits the auto-filled GC date when no gas reading is entered', async () => {
    const user = userEvent.setup()
    wrap(<ResultEntryModal {...addProps} experimentType="Serum" />)
    await user.type(screen.getByLabelText('pH'), '8.1')
    await user.type(screen.getByLabelText('NH₄ (mM)'), '2.4')
    await user.click(screen.getByRole('button', { name: 'Save Results' }))
    await vi.waitFor(() => expect(api.createResult).toHaveBeenCalledTimes(1))
    const body = api.createResult.mock.calls[0][1]
    expect(body).toMatchObject({ measurement_date: '2026-11-07', final_ph: 8.1 })
    expect(body).not.toHaveProperty('gc_run_date')
  })

  it('keeps a GC date the researcher typed even without a gas reading', async () => {
    const user = userEvent.setup()
    wrap(<ResultEntryModal {...addProps} experimentType="Serum" />)
    const gc = screen.getByLabelText('GC run date')
    await user.clear(gc)
    await user.type(gc, '2026-11-08')
    await user.click(screen.getByRole('button', { name: 'Save Results' }))
    await vi.waitFor(() => expect(api.createResult).toHaveBeenCalledTimes(1))
    expect(api.createResult.mock.calls[0][1].gc_run_date).toBe('2026-11-08')
  })

  it('prefills Day from the experiment start and follows the sample date until edited', async () => {
    const user = userEvent.setup()
    wrap(<ResultEntryModal {...addProps} />)
    const day = screen.getByLabelText(/^day/i) as HTMLInputElement
    const date = screen.getByLabelText(/^sample date/i) as HTMLInputElement
    const gc = screen.getByLabelText('GC run date') as HTMLInputElement
    expect(day.value).toBe('6')
    await user.clear(date)
    await user.type(date, '2026-11-03')
    expect(day.value).toBe('2')
    expect(gc.value).toBe('2026-11-03')
    await user.clear(day)
    await user.type(day, '2.5')
    await user.clear(date)
    await user.type(date, '2026-11-04')
    expect(day.value).toBe('2.5')
  })

  it('defaults and locks Day when the ID carries a -t token', () => {
    wrap(<ResultEntryModal {...addProps} experimentId="SERUM_001a-t7" experimentType="Serum" idTimepointDays={7} />)
    const day = screen.getByLabelText(/^day/i) as HTMLInputElement
    expect(day.value).toBe('7')
    expect(day).toBeDisabled()
    expect(screen.getByText(/locked to day 7 from the experiment id/i)).toBeInTheDocument()
  })

  it('leaves Day editable and blank with no -t token and no start date', () => {
    wrap(<ResultEntryModal {...addProps} experimentId="SERUM_001a" experimentType="Serum" experimentStart={null} />)
    const day = screen.getByLabelText(/^day/i) as HTMLInputElement
    expect(day.value).toBe('')
    expect(day).not.toBeDisabled()
  })

  it('hides NH₄ for HPHT and shows it for Serum', () => {
    const { unmount } = wrap(<ResultEntryModal {...addProps} />)
    expect(screen.queryByLabelText('NH₄ (mM)')).not.toBeInTheDocument()
    unmount()
    wrap(<ResultEntryModal {...addProps} experimentType="Serum" />)
    expect(screen.getByLabelText('NH₄ (mM)')).toBeInTheDocument()
  })

  it('sends modification_note only when the Modification box has text', async () => {
    const user = userEvent.setup()
    wrap(<ResultEntryModal {...addProps} />)
    await user.click(screen.getByRole('button', { name: /modification/i }))
    await user.type(screen.getByLabelText('Modification note'), 'brine replaced with DI')
    await user.click(screen.getByRole('button', { name: 'Save Results' }))
    await vi.waitFor(() => expect(api.createResult).toHaveBeenCalledTimes(1))
    expect(api.createResult.mock.calls[0][1].modification_note).toBe('brine replaced with DI')
  })

  it('warns before replacing a same-day primary result and saves on the second click', async () => {
    const user = userEvent.setup()
    wrap(<ResultEntryModal {...addProps} results={[result]} />)
    expect(screen.getByText(/day 6 already has a result/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save Results' }))
    expect(api.createResult).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Replace existing result' }))
    await vi.waitFor(() => expect(api.createResult).toHaveBeenCalledTimes(1))
  })

  it('shows a server rejection inline', async () => {
    api.createResult.mockRejectedValueOnce(new Error('Time is locked to day 7'))
    const user = userEvent.setup()
    wrap(<ResultEntryModal {...addProps} />)
    await user.click(screen.getByRole('button', { name: 'Save Results' }))
    expect(await screen.findByText('Time is locked to day 7')).toBeInTheDocument()
  })
})

describe('ResultEntryModal — edit', () => {
  const editProps = { ...addProps, editing: result }

  it('sends only the changed field when just pH changes', async () => {
    const user = userEvent.setup()
    wrap(<ResultEntryModal {...editProps} />)
    const ph = (await screen.findByLabelText('pH')) as HTMLInputElement
    expect(ph.value).toBe('7.1')
    expect((screen.getByLabelText('Gas pressure (psi)') as HTMLInputElement).value).toBe('14.5')
    expect(screen.getByLabelText(/^day/i)).toBeDisabled()
    await user.clear(ph)
    await user.type(ph, '7.4')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await vi.waitFor(() => expect(api.updateResult).toHaveBeenCalledTimes(1))
    expect(api.updateResult).toHaveBeenCalledWith('HPHT_001', 5, { final_ph: 7.4 })
    expect(api.createResult).not.toHaveBeenCalled()
  })

  it('sends result_note "" when the note is cleared', async () => {
    const user = userEvent.setup()
    wrap(<ResultEntryModal {...editProps} />)
    const desc = (await screen.findByLabelText('Result Note/Sample Description')) as HTMLTextAreaElement
    expect(desc.value).toBe('liquid cloudy')
    await user.clear(desc)
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await vi.waitFor(() => expect(api.updateResult).toHaveBeenCalledTimes(1))
    expect(api.updateResult).toHaveBeenCalledWith('HPHT_001', 5, { result_note: '' })
  })

  it('adds a modification note and lists existing notes read-only', async () => {
    const user = userEvent.setup()
    wrap(<ResultEntryModal {...editProps} />)
    const list = await screen.findByTestId('existing-notes')
    expect(within(list).getByText('brine swapped')).toBeInTheDocument()
    expect(within(list).getByText('from upload')).toBeInTheDocument()
    expect(within(list).queryByRole('textbox')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /modification/i }))
    await user.type(screen.getByLabelText('Modification note'), 'topped up brine')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await vi.waitFor(() => expect(api.updateResult).toHaveBeenCalledTimes(1))
    expect(api.updateResult).toHaveBeenCalledWith('HPHT_001', 5, { modification_note: 'topped up brine' })
  })

  it('closes without a request when nothing changed', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    wrap(<ResultEntryModal {...editProps} onClose={onClose} />)
    await screen.findByLabelText('pH')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onClose).toHaveBeenCalled()
    expect(api.updateResult).not.toHaveBeenCalled()
  })

  it('shows NH₄ on an HPHT row that already holds a value', async () => {
    getScalar.mockResolvedValue({ ...scalar, gross_ammonium_concentration_mM: 0.4 })
    wrap(<ResultEntryModal {...editProps} />)
    expect(((await screen.findByLabelText('NH₄ (mM)')) as HTMLInputElement).value).toBe('0.4')
  })
})
