import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import type { CoreFloodSample, CoreFloodSegment } from '@/api/coreFloods'

vi.mock('@/api/coreFloods', () => ({
  coreFloodsApi: {
    createSample: vi.fn(),
    updateSample: vi.fn(),
  },
}))

import { coreFloodsApi } from '@/api/coreFloods'
import { CoreFloodSampleModal } from '../CoreFloodSampleModal'
import { SAMPLE_FIELDS } from '../fields'

const createSample = vi.mocked(coreFloodsApi.createSample)
const updateSample = vi.mocked(coreFloodsApi.updateSample)

function segment(over: Partial<CoreFloodSegment> = {}): CoreFloodSegment {
  return {
    id: 1,
    experiment_id: 'CF_020-3',
    status: 'ONGOING',
    date: '2026-10-23T00:00:00',
    parent_experiment_id: null,
    is_variant: false,
    description: null,
    conditions_id: 1,
    pore_volume_mL: 10,
    rock_mass_g: 100,
    reactor_slot: 'CF01',
    ...over,
  }
}

function sample(over: Partial<CoreFloodSample> = {}): CoreFloodSample {
  return {
    result_id: 77,
    experiment_id: 'CF_020-3',
    experiment_fk: 1,
    run_base_id: 'CF_020',
    is_variant: false,
    time_post_reaction_days: 5,
    cumulative_time_post_reaction_days: 5,
    sample_date: '2026-10-28T00:00:00',
    gc_run_date: '2026-10-28T00:00:00',
    sample_tube_number: null,
    flow_rate_mL_min: 0.5,
    nitrogen_flow_rate_mL_min: null,
    inlet_pressure_psi: 1500,
    outlet_pressure_psi: null,
    sampling_volume_mL: null,
    h2_concentration: null,
    gas_sampling_volume_ml: null,
    gas_sampling_pressure_MPa: null,
    h2_micromoles: null,
    h2_mass_ug: null,
    h2_grams_per_ton_yield: null,
    final_ph: 7,
    final_conductivity_mS_cm: null,
    pore_volume_mL: 10,
    interval_days: null,
    cumulative_liquid_volume_mL: null,
    cumulative_pore_volumes: null,
    cumulative_h2_grams_per_ton: null,
    h2_grams_per_ton_per_day: null,
    is_hold_interval: false,
    permeability_flow_rate_mL_min: null,
    notes: [],
    ...over,
  }
}

function renderModal(props: Partial<React.ComponentProps<typeof CoreFloodSampleModal>> = {}) {
  const onClose = vi.fn()
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const view = render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <CoreFloodSampleModal
          open
          onClose={onClose}
          baseId="CF_020"
          segments={[segment()]}
          samples={[sample()]}
          {...props}
        />
      </ToastProvider>
    </QueryClientProvider>,
  )
  return { onClose, ...view }
}

const submit = () => userEvent.click(screen.getByRole('button', { name: /^(add sample|save)$/i }))

beforeEach(() => {
  vi.clearAllMocks()
  createSample.mockResolvedValue(sample())
  updateSample.mockResolvedValue(sample())
})

describe('CoreFloodSampleModal — add', () => {
  it('prefills flow from the previous sample and requires it', async () => {
    renderModal()
    const flow = screen.getByLabelText('Flow rate (mL/min)') as HTMLInputElement
    expect(flow.value).toBe('0.5')
    await userEvent.clear(flow)
    await submit()
    expect(screen.getByText('Required')).toBeInTheDocument()
    expect(createSample).not.toHaveBeenCalled()
  })

  it('submitting runs one createSample call', async () => {
    const { onClose } = renderModal()
    fireEvent.change(screen.getByLabelText('Sample date'), { target: { value: '2026-11-03' } })
    await submit()
    await waitFor(() => expect(createSample).toHaveBeenCalledTimes(1))
    expect(createSample).toHaveBeenCalledWith(
      'CF_020-3',
      expect.objectContaining({
        measurement_date: '2026-11-03',
        time_post_reaction_days: 11,
        flow_rate_mL_min: 0.5,
      }),
    )
    const allowed = new Set<string>(SAMPLE_FIELDS.map((f) => f.key))
    for (const key of Object.keys(createSample.mock.calls[0][1])) {
      expect(allowed.has(key)).toBe(true)
    }
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('a same-day sample warns, and replacing takes a second click', async () => {
    renderModal({ samples: [sample({ time_post_reaction_days: 11, sample_date: '2026-11-03T00:00:00' })] })
    fireEvent.change(screen.getByLabelText('Sample date'), { target: { value: '2026-11-03' } })
    expect(
      screen.getByText(/CF_020-3 already has a sample on day 11 \(2026-11-03\)\. Saving replaces it in the run\. Enter a fractional day \(e\.g\. 11\.5\) to keep both\./),
    ).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Add sample' }))
    expect(createSample).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Replace existing sample' }))
    await waitFor(() => expect(createSample).toHaveBeenCalledTimes(1))
  })

  it('changing the day after arming disarms the replace confirm', async () => {
    renderModal({ samples: [sample({ time_post_reaction_days: 11, sample_date: '2026-11-03T00:00:00' })] })
    fireEvent.change(screen.getByLabelText('Sample date'), { target: { value: '2026-11-03' } })
    await userEvent.click(screen.getByRole('button', { name: 'Add sample' }))
    fireEvent.change(screen.getByLabelText('Day (days)'), { target: { value: '11.5' } })
    expect(screen.queryByText(/already has a sample on day/)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Add sample' }))
    await waitFor(() => expect(createSample).toHaveBeenCalledTimes(1))
  })

  it('a fractional day next to a same-day sample posts on one click', async () => {
    renderModal({ samples: [sample({ time_post_reaction_days: 11, sample_date: '2026-11-03T00:00:00' })] })
    fireEvent.change(screen.getByLabelText('Sample date'), { target: { value: '2026-11-03' } })
    fireEvent.change(screen.getByLabelText('Day (days)'), { target: { value: '11.5' } })
    expect(screen.queryByText(/already has a sample on day/)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Add sample' }))
    await waitFor(() => expect(createSample).toHaveBeenCalledTimes(1))
  })

  it('the Day hint names the segment start in add mode', () => {
    renderModal()
    expect(screen.getByText('Days since CF_020-3 started (2026-10-23)')).toBeInTheDocument()
  })

  it('a segment with no start date blocks a blank day', async () => {
    renderModal({ segments: [segment({ date: null })] })
    await submit()
    expect(screen.getByText('Required — CF_020-3 has no start date')).toBeInTheDocument()
    expect(createSample).not.toHaveBeenCalled()
  })

  it('several ONGOING segments make the researcher choose', async () => {
    renderModal({
      segments: [
        segment(),
        segment({ id: 2, experiment_id: 'CF_020-4', date: '2026-10-30T00:00:00' }),
      ],
    })
    await submit()
    expect(screen.getByText('Choose a segment')).toBeInTheDocument()
    expect(createSample).not.toHaveBeenCalled()
  })

  it('picking a segment clears the segment error', async () => {
    renderModal({
      segments: [
        segment(),
        segment({ id: 2, experiment_id: 'CF_020-4', date: '2026-10-30T00:00:00' }),
      ],
    })
    await submit()
    expect(screen.getByText('Choose a segment')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Segment'), 'CF_020-4')
    expect(screen.queryByText('Choose a segment')).not.toBeInTheDocument()
    expect((screen.getByLabelText('Day (days)') as HTMLInputElement).value).not.toBe('')
  })

  it('a 422 shows the server detail in the modal', async () => {
    createSample.mockRejectedValue(
      Object.assign(new Error('sample dated before the start'), { response: { status: 422 } }),
    )
    const { onClose } = renderModal()
    await submit()
    expect(await screen.findByText('sample dated before the start')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })
})

describe('CoreFloodSampleModal — edit', () => {
  it('an edit that changes only pH sends {final_ph}', async () => {
    renderModal({ editing: sample() })
    expect(screen.getByLabelText('Day (days)')).toBeDisabled()
    expect(screen.getByText("Day can't be edited here")).toBeInTheDocument()
    const ph = screen.getByLabelText('pH')
    await userEvent.clear(ph)
    await userEvent.type(ph, '7.4')
    await submit()
    await waitFor(() => expect(updateSample).toHaveBeenCalledTimes(1))
    expect(updateSample).toHaveBeenCalledWith(77, { final_ph: 7.4 })
    expect(createSample).not.toHaveBeenCalled()
  })

  it('changing the sample date says the day stays', async () => {
    renderModal({ editing: sample() })
    fireEvent.change(screen.getByLabelText('Sample date'), { target: { value: '2026-10-29' } })
    expect(
      screen.getByText("Day stays 5 — the day can't be changed after a sample is created."),
    ).toBeInTheDocument()
    expect(screen.queryByText("Day can't be edited here")).not.toBeInTheDocument()
  })

  it('an untouched edit sends nothing', async () => {
    const { onClose } = renderModal({ editing: sample() })
    await submit()
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(updateSample).not.toHaveBeenCalled()
  })

  it('clearing flow in edit shows Required and sends nothing', async () => {
    renderModal({ editing: sample() })
    await userEvent.clear(screen.getByLabelText('Flow rate (mL/min)'))
    await submit()
    expect(screen.getByText('Required')).toBeInTheDocument()
    expect(updateSample).not.toHaveBeenCalled()
  })

  it('edits a historical row missing flow and date, sending only pH', async () => {
    renderModal({
      editing: sample({ flow_rate_mL_min: null, sample_date: null, gc_run_date: null }),
    })
    const ph = screen.getByLabelText('pH')
    await userEvent.clear(ph)
    await userEvent.type(ph, '7.4')
    await submit()
    await waitFor(() => expect(updateSample).toHaveBeenCalledTimes(1))
    expect(updateSample).toHaveBeenCalledWith(77, { final_ph: 7.4 })
  })
})

describe('CoreFloodSampleModal — regrouped form', () => {
  it('renders GC, Solution and Core flood groups with their fields', () => {
    renderModal()
    const gc = within(screen.getByRole('region', { name: 'GC' }))
    for (const l of [/H₂ \(ppm\)/, /Gas pressure/, /Gas volume/, /GC run date/]) {
      expect(gc.getByLabelText(l)).toBeInTheDocument()
    }
    const sol = within(screen.getByRole('region', { name: 'Solution' }))
    for (const l of [/^pH/, /Conductivity/, /Liquid sample volume/]) {
      expect(sol.getByLabelText(l)).toBeInTheDocument()
    }
    const cf = within(screen.getByRole('region', { name: 'Core flood' }))
    for (const l of [
      'Hold since last sample',
      /^Flow rate/,
      /Permeability test flow rate/,
      /Inlet pressure/,
      /Outlet pressure/,
      /N₂ flow/,
    ]) {
      expect(cf.getByLabelText(l)).toBeInTheDocument()
    }
  })

  it('hold checkbox sets flow to 0 and disables it; unchecking restores', async () => {
    renderModal({ editing: sample({ flow_rate_mL_min: 0.1 }) })
    const flow = screen.getByLabelText('Flow rate (mL/min)') as HTMLInputElement
    const hold = screen.getByLabelText('Hold since last sample')
    expect(hold).not.toBeChecked()
    await userEvent.click(hold)
    expect(flow.value).toBe('0')
    expect(flow).toBeDisabled()
    expect(screen.getByLabelText(/Permeability test flow rate/)).toHaveFocus()
    await userEvent.click(hold)
    expect(flow.value).toBe('0.1')
    expect(flow).not.toBeDisabled()
  })

  it('starts checked when flow is 0', () => {
    renderModal({ editing: sample({ flow_rate_mL_min: 0 }) })
    expect(screen.getByLabelText('Hold since last sample')).toBeChecked()
  })

  it('hold toggle round-trip leaves patch empty', async () => {
    renderModal({ editing: sample({ flow_rate_mL_min: 0.1 }) })
    const hold = screen.getByLabelText('Hold since last sample')
    await userEvent.click(hold)
    await userEvent.click(hold)
    const ph = screen.getByLabelText('pH')
    await userEvent.clear(ph)
    await userEvent.type(ph, '7.4')
    await submit()
    await waitFor(() => expect(updateSample).toHaveBeenCalledTimes(1))
    expect(updateSample.mock.calls[0][1]).not.toHaveProperty('flow_rate_mL_min')
  })

  it('blocks save when pressures have no test rate', async () => {
    renderModal({ samples: [sample({ flow_rate_mL_min: 0 })] })
    expect(screen.getByLabelText('Hold since last sample')).toBeChecked()
    await userEvent.type(screen.getByLabelText(/Inlet pressure/), '1520')
    await submit()
    expect(
      screen.getByText('Enter the test flow rate used for these pressures'),
    ).toBeInTheDocument()
    expect(createSample).not.toHaveBeenCalled()
  })

  it('typing a pressure fills the test rate from the flow', async () => {
    renderModal()
    await userEvent.type(screen.getByLabelText(/Inlet pressure/), '1')
    expect((screen.getByLabelText(/Permeability test flow rate/) as HTMLInputElement).value).toBe('0.5')
  })

  it('sends result_note on create', async () => {
    renderModal()
    await userEvent.type(screen.getByLabelText('Result note'), '  clear liquid ')
    await submit()
    await waitFor(() => expect(createSample).toHaveBeenCalledTimes(1))
    expect(createSample.mock.calls[0][1]).toHaveProperty('result_note', 'clear liquid')
  })

  it('omits result_note on create when blank', async () => {
    renderModal()
    await submit()
    await waitFor(() => expect(createSample).toHaveBeenCalledTimes(1))
    expect(createSample.mock.calls[0][1]).not.toHaveProperty('result_note')
  })

  const withNotes = () =>
    sample({
      notes: [
        { id: 1, note_type: 'result_note', note_text: 'first', created_by: null },
        { id: 2, note_type: 'observation', note_text: 'bubbles seen', created_by: null },
      ],
    })

  it('omits result_note on edit when unchanged', async () => {
    renderModal({ editing: withNotes() })
    expect((screen.getByLabelText('Result note') as HTMLTextAreaElement).value).toBe('first')
    const ph = screen.getByLabelText('pH')
    await userEvent.clear(ph)
    await userEvent.type(ph, '7.4')
    await submit()
    await waitFor(() => expect(updateSample).toHaveBeenCalledTimes(1))
    expect(updateSample).toHaveBeenCalledWith(77, { final_ph: 7.4 })
  })

  it('sends null when the note is cleared, and a changed note alone is a change', async () => {
    renderModal({ editing: withNotes() })
    await userEvent.clear(screen.getByLabelText('Result note'))
    await submit()
    await waitFor(() => expect(updateSample).toHaveBeenCalledTimes(1))
    expect(updateSample).toHaveBeenCalledWith(77, { result_note: null })
  })

  it('lists other notes read-only', () => {
    renderModal({ editing: withNotes() })
    expect(screen.getByText('bubbles seen')).toBeInTheDocument()
    expect(screen.getByText('Observation')).toBeInTheDocument()
    expect(screen.getAllByRole('textbox', { name: /note/i })).toHaveLength(1)
    expect(screen.queryByText('first', { selector: 'p, li, span' })).not.toBeInTheDocument()
  })
})

describe('CoreFloodSampleModal — legacy pressure rows', () => {
  it('edit of a legacy row with pressures but no test rate saves other changes', async () => {
    renderModal({ editing: sample() })
    const ph = screen.getByLabelText('pH')
    await userEvent.clear(ph)
    await userEvent.type(ph, '7.4')
    await submit()
    await waitFor(() => expect(updateSample).toHaveBeenCalledWith(77, { final_ph: 7.4 }))
  })

  it('edit that changes a pressure without a test rate is blocked', async () => {
    renderModal({ editing: sample({ flow_rate_mL_min: 0 }) })
    const inlet = screen.getByLabelText(/Inlet pressure/)
    await userEvent.clear(inlet)
    await userEvent.type(inlet, '1600')
    await submit()
    expect(screen.getByText('Enter the test flow rate used for these pressures')).toBeInTheDocument()
    expect(updateSample).not.toHaveBeenCalled()
  })
})

describe('CoreFloodSampleModal — hold derived from flow', () => {
  it('create after a hold sample opens with Hold checked and flow disabled', () => {
    renderModal({ samples: [sample({ flow_rate_mL_min: 0 })] })
    expect(screen.getByLabelText('Hold since last sample')).toBeChecked()
    expect(screen.getByLabelText('Flow rate (mL/min)')).toBeDisabled()
  })

  it('typing 0 into flow checks Hold', async () => {
    renderModal()
    const flow = screen.getByLabelText('Flow rate (mL/min)')
    await userEvent.clear(flow)
    await userEvent.type(flow, '0')
    expect(screen.getByLabelText('Hold since last sample')).toBeChecked()
  })
})
