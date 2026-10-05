// frontend/src/pages/NewExperiment/__tests__/Step4Review.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { Step4Review } from '../Step4Review'
import type { Step1Data } from '../Step1BasicInfo'
import type { Step2Data } from '../Step2Conditions'

function makeStep1(overrides: Partial<Step1Data> = {}): Step1Data {
  return {
    experimentType: '',
    experimentId: 'SERUM_001',
    sampleId: '',
    date: '',
    status: '',
    note: '',
    ...overrides,
  }
}

const step2: Step2Data = {
  temperature_c: '',
  initial_ph: '',
  rock_mass_g: '',
  water_volume_mL: '',
  particle_size: '',
  feedstock: '',
  reactor_number: '',
  stir_speed_rpm: '',
  initial_conductivity_mS_cm: '',
  room_temp_pressure_psi: '',
  rxn_temp_pressure_psi: '',
  co2_partial_pressure_MPa: '',
  core_height_cm: '',
  core_width_cm: '',
  confining_pressure: '',
  pore_pressure: '',
}

function renderStep4(step1: Step1Data) {
  return render(
    <Step4Review
      step1={step1}
      step2={step2}
      additives={[]}
      replicateCount={0}
      onReplicateCountChange={vi.fn()}
      onBack={vi.fn()}
      onSubmit={vi.fn()}
      isSubmitting={false}
    />,
  )
}

describe('Step4Review — description label', () => {
  it('labels a non-blank note "Description", not "Condition Note"', () => {
    renderStep4(makeStep1({ note: 'Baseline run' }))
    expect(screen.getByText('Description')).toBeInTheDocument()
    expect(screen.queryByText('Condition Note')).not.toBeInTheDocument()
  })

  it('shows neither label for a whitespace-only note', () => {
    renderStep4(makeStep1({ note: '   ' }))
    expect(screen.queryByText('Description')).not.toBeInTheDocument()
    expect(screen.queryByText('Condition Note')).not.toBeInTheDocument()
  })
})
