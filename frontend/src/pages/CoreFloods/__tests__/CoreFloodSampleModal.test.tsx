import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
