import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import { ConditionsTab } from '../ConditionsTab'
import * as chemicalsApi from '@/api/chemicals'
import { conditionsApi, type ConditionsResponse } from '@/api/conditions'
import type { AxiosResponse } from 'axios'

// Minimal stubs
vi.mock('@/api/chemicals', () => ({
  chemicalsApi: {
    listExperimentAdditives: vi.fn(() => Promise.resolve([
      { id: 1, compound_id: 10, compound: { name: 'Magnetite' }, amount: 5, unit: 'g', mass_in_grams: 5 },
    ])),
    listCompounds: vi.fn(() => Promise.resolve([])),
    deleteAdditiveById: vi.fn(() => Promise.resolve()),
  },
}))
vi.mock('@/api/conditions', () => ({
  conditionsApi: {
    getByExperiment: vi.fn(() => Promise.resolve(null)),
    patch: vi.fn(() => Promise.resolve({})),
  },
}))
vi.mock('@/components/ui', async () => {
  const actual = await vi.importActual<typeof import('@/components/ui')>('@/components/ui')
  return actual
})

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
  )
}

// Minimal conditions object to render the additives section
const mockConditions = {
  id: 1,
  experiment_id: 'HPHT_001',
  experiment_fk: 1,
  experiment_type: 'HPHT',
  temperature_c: null,
  initial_ph: null,
  rock_mass_g: null,
  water_volume_mL: null,
  water_to_rock_ratio: null,
  particle_size: null,
  feedstock: null,
  reactor_number: null,
  stir_speed_rpm: null,
  initial_conductivity_mS_cm: null,
  room_temp_pressure_psi: null,
  rxn_temp_pressure_psi: null,
  co2_partial_pressure_MPa: null,
  confining_pressure: null,
  pore_pressure: null,
  core_height_cm: null,
  core_width_cm: null,
}

/** The API sends null for unset optionals, which ConditionsResponse (it extends the
 *  write payload) types as `?: number`; so fixtures keep their real nulls and are
 *  cast here once, rather than hiding the whole object behind `any` (issue #106). */
const conditionsRow = (c: object) => c as unknown as ConditionsResponse

describe('ConditionsTab additives action buttons', () => {
  it('renders edit and delete buttons with aria-labels', async () => {
    wrap(<ConditionsTab conditions={conditionsRow(mockConditions)} experimentId="HPHT_001" experimentFk={1} />)

    const editBtn = await screen.findByRole('button', { name: /edit additive/i })
    const deleteBtn = await screen.findByRole('button', { name: /delete additive/i })

    expect(editBtn).toBeInTheDocument()
    expect(deleteBtn).toBeInTheDocument()
  })

  it('edit and delete buttons are not aria-hidden', async () => {
    wrap(<ConditionsTab conditions={conditionsRow(mockConditions)} experimentId="HPHT_001" experimentFk={1} />)

    const editBtn = await screen.findByRole('button', { name: /edit additive/i })
    expect(editBtn).not.toHaveAttribute('aria-hidden', 'true')
  })

  it('clicking delete opens confirm modal without firing mutation', async () => {
    const user = userEvent.setup()
    const deleteFn = vi.fn(() => Promise.resolve({ data: undefined, status: 204, statusText: 'No Content', headers: {}, config: {} } as unknown as AxiosResponse))
    vi.mocked(chemicalsApi.chemicalsApi.deleteAdditiveById).mockImplementation(deleteFn)

    wrap(<ConditionsTab conditions={conditionsRow(mockConditions)} experimentId="HPHT_001" experimentFk={1} />)

    const deleteBtn = await screen.findByRole('button', { name: /delete additive/i })
    await user.click(deleteBtn)

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(deleteFn).not.toHaveBeenCalled()
  })
})

describe('ConditionsTab — serum vial size', () => {
  const serum = { ...mockConditions, experiment_type: 'Serum', serum_vial_size_mL: 120 }

  it('shows the read row when set', () => {
    wrap(<ConditionsTab conditions={conditionsRow(serum)} experimentId="SERUM_001" experimentFk={1} />)
    expect(screen.getByText('Serum Vial Size')).toBeInTheDocument()
    expect(screen.getByText('120 mL')).toBeInTheDocument()
  })

  it('shows no read row when null', () => {
    wrap(<ConditionsTab conditions={conditionsRow({ ...serum, serum_vial_size_mL: null })} experimentId="SERUM_001" experimentFk={1} />)
    expect(screen.queryByText('Serum Vial Size')).not.toBeInTheDocument()
  })

  async function openEditModal() {
    await userEvent.click(screen.getByRole('button', { name: /^edit$/i }))
  }

  it('edit modal shows the input for Serum, seeded with the stored value', async () => {
    wrap(<ConditionsTab conditions={conditionsRow(serum)} experimentId="SERUM_001" experimentFk={1} />)
    await openEditModal()
    expect(screen.getByLabelText('Serum Vial Size (mL)')).toHaveValue(120)
  })

  it('edit modal shows the input for a Serum with no stored value', async () => {
    wrap(<ConditionsTab conditions={conditionsRow({ ...serum, serum_vial_size_mL: null })} experimentId="SERUM_001" experimentFk={1} />)
    await openEditModal()
    expect(screen.getByLabelText('Serum Vial Size (mL)')).toHaveValue(null)
  })

  it('edit modal hides the input for HPHT with no stored value', async () => {
    wrap(<ConditionsTab conditions={conditionsRow(mockConditions)} experimentId="HPHT_001" experimentFk={1} />)
    await openEditModal()
    expect(screen.queryByLabelText('Serum Vial Size (mL)')).not.toBeInTheDocument()
  })

  it('edit modal shows the input for HPHT when a value is already stored', async () => {
    wrap(<ConditionsTab conditions={conditionsRow({ ...mockConditions, serum_vial_size_mL: 60 })} experimentId="HPHT_001" experimentFk={1} />)
    await openEditModal()
    expect(screen.getByLabelText('Serum Vial Size (mL)')).toHaveValue(60)
  })

  it('keeps the input visible while the user clears a stored value', async () => {
    wrap(<ConditionsTab conditions={conditionsRow({ ...mockConditions, serum_vial_size_mL: 60 })} experimentId="HPHT_001" experimentFk={1} />)
    await openEditModal()
    await userEvent.clear(screen.getByLabelText('Serum Vial Size (mL)'))
    expect(screen.getByLabelText('Serum Vial Size (mL)')).toBeInTheDocument()
  })

  it('omits a hidden vial size from the save payload after switching to HPHT', async () => {
    wrap(<ConditionsTab conditions={conditionsRow({ ...serum, serum_vial_size_mL: null })} experimentId="SERUM_001" experimentFk={1} />)
    await openEditModal()
    await userEvent.type(screen.getByLabelText('Serum Vial Size (mL)'), '120')
    await userEvent.selectOptions(screen.getByLabelText('Experiment Type'), 'HPHT')
    expect(screen.queryByLabelText('Serum Vial Size (mL)')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() => expect(conditionsApi.patch).toHaveBeenCalled())
    const payload = vi.mocked(conditionsApi.patch).mock.calls[0][1]
    expect(payload).not.toHaveProperty('serum_vial_size_mL')
    expect(payload).toHaveProperty('experiment_type', 'HPHT')
  })
})

describe('ConditionsTab — pore volume', () => {
  const core = { ...mockConditions, experiment_type: 'Core Flood', pore_volume_mL: 42 }

  it('shows the read row with unit', () => {
    wrap(<ConditionsTab conditions={conditionsRow(core)} experimentId="CF_001" experimentFk={1} />)
    expect(screen.getByText('Pore Volume')).toBeInTheDocument()
    expect(screen.getByText('42 mL')).toBeInTheDocument()
  })

  it('edit modal input is seeded with the stored value', async () => {
    wrap(<ConditionsTab conditions={conditionsRow(core)} experimentId="CF_001" experimentFk={1} />)
    await userEvent.click(screen.getByRole('button', { name: /^edit$/i }))
    expect(screen.getByLabelText('Pore Volume (mL)')).toHaveValue(42)
  })

  it('edit modal shows the input for a Core Flood with no stored value', async () => {
    wrap(<ConditionsTab conditions={conditionsRow({ ...core, pore_volume_mL: null })} experimentId="CF_001" experimentFk={1} />)
    await userEvent.click(screen.getByRole('button', { name: /^edit$/i }))
    expect(screen.getByLabelText('Pore Volume (mL)')).toHaveValue(null)
  })

  it('edit modal hides the input for a Serum with no stored value', async () => {
    const serum = { ...mockConditions, experiment_type: 'Serum', pore_volume_mL: null }
    wrap(<ConditionsTab conditions={conditionsRow(serum)} experimentId="SERUM_001" experimentFk={1} />)
    await userEvent.click(screen.getByRole('button', { name: /^edit$/i }))
    expect(screen.queryByLabelText('Pore Volume (mL)')).not.toBeInTheDocument()
  })

  it('edit modal shows the input for a Serum when a value is already stored', async () => {
    const serum = { ...mockConditions, experiment_type: 'Serum', pore_volume_mL: 15 }
    wrap(<ConditionsTab conditions={conditionsRow(serum)} experimentId="SERUM_001" experimentFk={1} />)
    await userEvent.click(screen.getByRole('button', { name: /^edit$/i }))
    expect(screen.getByLabelText('Pore Volume (mL)')).toHaveValue(15)
  })

  it('omits a hidden pore volume from the save payload after switching to HPHT', async () => {
    wrap(<ConditionsTab conditions={conditionsRow({ ...core, pore_volume_mL: null })} experimentId="CF_001" experimentFk={1} />)
    await userEvent.click(screen.getByRole('button', { name: /^edit$/i }))
    await userEvent.type(screen.getByLabelText('Pore Volume (mL)'), '30')
    await userEvent.selectOptions(screen.getByLabelText('Experiment Type'), 'HPHT')
    expect(screen.queryByLabelText('Pore Volume (mL)')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() => expect(conditionsApi.patch).toHaveBeenCalled())
    const payload = vi.mocked(conditionsApi.patch).mock.calls.at(-1)![1]
    expect(payload).not.toHaveProperty('pore_volume_mL')
    expect(payload).toHaveProperty('experiment_type', 'HPHT')
  })
})

describe('ConditionsTab — reactor slot (issue #147)', () => {
  const parr = { ...mockConditions, reactor_number: 3, reactor_series: 'P', reactor_slot: 'P03' }

  async function editAndSave(picked?: string) {
    await userEvent.click(screen.getByRole('button', { name: /^edit$/i }))
    if (picked !== undefined) await userEvent.selectOptions(screen.getByLabelText('Reactor'), picked)
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() => expect(conditionsApi.patch).toHaveBeenCalled())
    return vi.mocked(conditionsApi.patch).mock.calls.at(-1)![1]
  }

  it('shows the slot label, not the bare number', () => {
    wrap(<ConditionsTab conditions={conditionsRow(parr)} experimentId="HPHT_001" experimentFk={1} />)
    expect(screen.getByText('P03')).toBeInTheDocument()
  })

  it('seeds the picker with the stored slot and leaves it out of an unrelated save', async () => {
    vi.mocked(conditionsApi.patch).mockClear()
    wrap(<ConditionsTab conditions={conditionsRow(parr)} experimentId="HPHT_001" experimentFk={1} />)
    await userEvent.click(screen.getByRole('button', { name: /^edit$/i }))
    expect(screen.getByLabelText('Reactor')).toHaveValue('P03')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() => expect(conditionsApi.patch).toHaveBeenCalled())
    const payload = vi.mocked(conditionsApi.patch).mock.calls[0][1]
    expect(payload).not.toHaveProperty('reactor_number')
    expect(payload).not.toHaveProperty('reactor_series')
  })

  it('sends number and series when moving from P03 to R05', async () => {
    vi.mocked(conditionsApi.patch).mockClear()
    wrap(<ConditionsTab conditions={conditionsRow(parr)} experimentId="HPHT_001" experimentFk={1} />)
    const payload = await editAndSave('R05')
    expect(payload).toMatchObject({ reactor_number: 5, reactor_series: null })
  })

  it('sends the Parr series when picking P02', async () => {
    vi.mocked(conditionsApi.patch).mockClear()
    wrap(
      <ConditionsTab
        conditions={conditionsRow({ ...mockConditions, reactor_number: 7, reactor_slot: 'R07' })}
        experimentId="HPHT_001"
        experimentFk={1}
      />,
    )
    const payload = await editAndSave('P02')
    expect(payload).toMatchObject({ reactor_number: 2, reactor_series: 'P' })
  })
})
