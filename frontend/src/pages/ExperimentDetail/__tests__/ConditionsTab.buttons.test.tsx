import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import { ConditionsTab } from '../ConditionsTab'
import * as chemicalsApi from '@/api/chemicals'

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
} as any

describe('ConditionsTab additives action buttons', () => {
  it('renders edit and delete buttons with aria-labels', async () => {
    wrap(<ConditionsTab conditions={mockConditions} experimentId="HPHT_001" experimentFk={1} />)

    const editBtn = await screen.findByRole('button', { name: /edit additive/i })
    const deleteBtn = await screen.findByRole('button', { name: /delete additive/i })

    expect(editBtn).toBeInTheDocument()
    expect(deleteBtn).toBeInTheDocument()
  })

  it('edit and delete buttons are not aria-hidden', async () => {
    wrap(<ConditionsTab conditions={mockConditions} experimentId="HPHT_001" experimentFk={1} />)

    const editBtn = await screen.findByRole('button', { name: /edit additive/i })
    expect(editBtn).not.toHaveAttribute('aria-hidden', 'true')
  })

  it('clicking delete opens confirm modal without firing mutation', async () => {
    const user = userEvent.setup()
    const deleteFn = vi.fn(() => Promise.resolve({ data: undefined, status: 204, statusText: 'No Content', headers: {}, config: {} } as any))
    vi.mocked(chemicalsApi.chemicalsApi.deleteAdditiveById).mockImplementation(deleteFn)

    wrap(<ConditionsTab conditions={mockConditions} experimentId="HPHT_001" experimentFk={1} />)

    const deleteBtn = await screen.findByRole('button', { name: /delete additive/i })
    await user.click(deleteBtn)

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(deleteFn).not.toHaveBeenCalled()
  })
})

describe('ConditionsTab — serum vial size', () => {
  const serum = { ...mockConditions, experiment_type: 'Serum', serum_vial_size_mL: 120 }

  it('shows the read row when set', () => {
    wrap(<ConditionsTab conditions={serum} experimentId="SERUM_001" experimentFk={1} />)
    expect(screen.getByText('Serum Vial Size')).toBeInTheDocument()
    expect(screen.getByText('120 mL')).toBeInTheDocument()
  })

  it('shows no read row when null', () => {
    wrap(<ConditionsTab conditions={{ ...serum, serum_vial_size_mL: null }} experimentId="SERUM_001" experimentFk={1} />)
    expect(screen.queryByText('Serum Vial Size')).not.toBeInTheDocument()
  })

  async function openEditModal() {
    await userEvent.click(screen.getByRole('button', { name: /^edit$/i }))
  }

  it('edit modal shows the input for Serum, seeded with the stored value', async () => {
    wrap(<ConditionsTab conditions={serum} experimentId="SERUM_001" experimentFk={1} />)
    await openEditModal()
    expect(screen.getByLabelText('Serum Vial Size (mL)')).toHaveValue(120)
  })

  it('edit modal shows the input for a Serum with no stored value', async () => {
    wrap(<ConditionsTab conditions={{ ...serum, serum_vial_size_mL: null }} experimentId="SERUM_001" experimentFk={1} />)
    await openEditModal()
    expect(screen.getByLabelText('Serum Vial Size (mL)')).toHaveValue(null)
  })

  it('edit modal hides the input for HPHT with no stored value', async () => {
    wrap(<ConditionsTab conditions={mockConditions} experimentId="HPHT_001" experimentFk={1} />)
    await openEditModal()
    expect(screen.queryByLabelText('Serum Vial Size (mL)')).not.toBeInTheDocument()
  })

  it('edit modal shows the input for HPHT when a value is already stored', async () => {
    wrap(<ConditionsTab conditions={{ ...mockConditions, serum_vial_size_mL: 60 }} experimentId="HPHT_001" experimentFk={1} />)
    await openEditModal()
    expect(screen.getByLabelText('Serum Vial Size (mL)')).toHaveValue(60)
  })

  it('keeps the input visible while the user clears a stored value', async () => {
    wrap(<ConditionsTab conditions={{ ...mockConditions, serum_vial_size_mL: 60 }} experimentId="HPHT_001" experimentFk={1} />)
    await openEditModal()
    await userEvent.clear(screen.getByLabelText('Serum Vial Size (mL)'))
    expect(screen.getByLabelText('Serum Vial Size (mL)')).toBeInTheDocument()
  })
})
