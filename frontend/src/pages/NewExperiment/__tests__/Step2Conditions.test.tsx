import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { Step2Conditions, type Step2Data } from '../Step2Conditions'
import type { ExperimentType } from '../fieldVisibility'
import { VIAL_SIZE_ERROR } from '../vialSize'

const empty: Step2Data = {
  temperature_c: '', initial_ph: '', rock_mass_g: '', water_volume_mL: '',
  serum_vial_size_mL: '',
  particle_size: '', feedstock: '', reactor_slot: '', stir_speed_rpm: '',
  initial_conductivity_mS_cm: '', room_temp_pressure_psi: '', rxn_temp_pressure_psi: '',
  co2_partial_pressure_MPa: '', core_height_cm: '', core_width_cm: '',
  confining_pressure: '', pore_pressure: '', pore_volume_mL: '',
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

describe('Step2Conditions — pore volume', () => {
  const LABEL = 'Pore Volume (mL)'
  const ERR = 'Must be greater than 0'

  it('shows the field for Core Flood', () => {
    renderStep2('Core Flood')
    expect(screen.getByLabelText(LABEL)).toBeInTheDocument()
  })

  it.each<ExperimentType>(['Serum', 'HPHT', 'Autoclave'])('hides the field for %s', (type) => {
    renderStep2(type)
    expect(screen.queryByLabelText(LABEL)).not.toBeInTheDocument()
  })

  it.each(['0', '-3'])('blocks Next with an inline error for %s', (bad) => {
    const { next, onNext } = renderStep2('Core Flood', { pore_volume_mL: bad })
    expect(screen.getByText(ERR)).toBeInTheDocument()
    expect(next).toBeDisabled()
    fireEvent.click(next)
    expect(onNext).not.toHaveBeenCalled()
  })

  it('allows Next for a valid value and for blank', () => {
    const { next } = renderStep2('Core Flood', { pore_volume_mL: '25' })
    expect(next).toBeEnabled()
    expect(screen.queryByText(ERR)).not.toBeInTheDocument()
    cleanup()
    expect(renderStep2('Core Flood').next).toBeEnabled()
  })

  it('does not block Next on a hidden stale 0 after a type switch', () => {
    const { next } = renderStep2('HPHT', { pore_volume_mL: '0' })
    expect(next).toBeEnabled()
    expect(screen.queryByText(ERR)).not.toBeInTheDocument()
  })
})

describe('Step2Conditions — reactor slot picker (issue #147)', () => {
  const optionValues = () =>
    Array.from((screen.getByLabelText('Reactor') as HTMLSelectElement).options)
      .map((o) => o.value)
      .filter(Boolean)

  it('lists R01-R16 then P01-P06 for HPHT', () => {
    renderStep2('HPHT')
    const values = optionValues()
    expect(values).toHaveLength(22)
    expect(values.slice(0, 2)).toEqual(['R01', 'R02'])
    expect(values.slice(-6)).toEqual(['P01', 'P02', 'P03', 'P04', 'P05', 'P06'])
    expect(screen.getByRole('option', { name: 'P03 (Parr)' })).toBeInTheDocument()
  })

  it('lists only CF01-CF03 for Core Flood', () => {
    renderStep2('Core Flood')
    expect(optionValues()).toEqual(['CF01', 'CF02', 'CF03'])
  })

  it.each<ExperimentType>(['Serum', 'Autoclave'])('shows no reactor picker for %s', (type) => {
    renderStep2(type)
    expect(screen.queryByLabelText('Reactor')).not.toBeInTheDocument()
  })

  it('reports the picked label through onChange', () => {
    const { onChange } = renderStep2('HPHT')
    fireEvent.change(screen.getByLabelText('Reactor'), { target: { value: 'P02' } })
    expect(onChange).toHaveBeenCalledWith({ reactor_slot: 'P02' })
  })
})
