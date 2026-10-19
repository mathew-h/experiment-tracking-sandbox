import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { Step2Conditions, type Step2Data } from '../Step2Conditions'
import type { ExperimentType } from '../fieldVisibility'
import { VIAL_SIZE_ERROR } from '../vialSize'

const empty: Step2Data = {
  temperature_c: '', initial_ph: '', rock_mass_g: '', water_volume_mL: '',
  serum_vial_size_mL: '',
  particle_size: '', feedstock: '', reactor_number: '', stir_speed_rpm: '',
  initial_conductivity_mS_cm: '', room_temp_pressure_psi: '', rxn_temp_pressure_psi: '',
  co2_partial_pressure_MPa: '', core_height_cm: '', core_width_cm: '',
  confining_pressure: '', pore_pressure: '',
}

function renderStep2(type: ExperimentType | '', patch: Partial<Step2Data> = {}, onChange = vi.fn()) {
  const onNext = vi.fn()
  render(
    <Step2Conditions
      data={{ ...empty, ...patch }}
      experimentType={type}
      onChange={onChange}
      onBack={vi.fn()}
      onNext={onNext}
    />,
  )
  return { onNext, onChange, next: screen.getByRole('button', { name: /next: additives/i }) }
}

describe('Step2Conditions — serum vial size', () => {
  it('shows the field for Serum', () => {
    renderStep2('Serum')
    expect(screen.getByLabelText('Serum Vial Size (mL)')).toBeInTheDocument()
  })

  it.each<ExperimentType>(['HPHT', 'Autoclave', 'Core Flood'])('hides the field for %s', (type) => {
    renderStep2(type)
    expect(screen.queryByLabelText('Serum Vial Size (mL)')).not.toBeInTheDocument()
  })

  it('reports edits through onChange', () => {
    const { onChange } = renderStep2('Serum')
    fireEvent.change(screen.getByLabelText('Serum Vial Size (mL)'), { target: { value: '60' } })
    expect(onChange).toHaveBeenCalledWith({ serum_vial_size_mL: '60' })
  })

  it.each(['0', '-1', '120.5'])('blocks Next with an inline error for %s', (bad) => {
    const { next, onNext } = renderStep2('Serum', { serum_vial_size_mL: bad })
    expect(screen.getByText(VIAL_SIZE_ERROR)).toBeInTheDocument()
    expect(next).toBeDisabled()
    fireEvent.click(next)
    expect(onNext).not.toHaveBeenCalled()
  })

  it('allows Next for a valid value and for blank', () => {
    const { next } = renderStep2('Serum', { serum_vial_size_mL: '120' })
    expect(next).toBeEnabled()
    expect(screen.queryByText(VIAL_SIZE_ERROR)).not.toBeInTheDocument()
  })

  it('does not block Next on a hidden invalid value after a type switch', () => {
    const { next } = renderStep2('HPHT', { serum_vial_size_mL: '120.5' })
    expect(next).toBeEnabled()
    expect(screen.queryByText(VIAL_SIZE_ERROR)).not.toBeInTheDocument()
  })
})
