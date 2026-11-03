import { describe, expect, it } from 'vitest'
import type { CoreFloodSample } from '@/api/coreFloods'
import { labDateOf } from '@/utils/labDate'
import {
  FIELD_BY_KEY,
  buildCreateBody,
  buildPatchBody,
  emptyForm,
  fmt,
  formFromSample,
  validateForm,
  withSampleDate,
} from '../fields'

function sample(over: Partial<CoreFloodSample> = {}): CoreFloodSample {
  return {
    result_id: 1,
    experiment_id: 'CF_020',
    experiment_fk: 1,
    run_base_id: 'CF_020',
    is_variant: false,
    time_post_reaction_days: 3,
    cumulative_time_post_reaction_days: 3,
    sample_date: '2026-10-26T00:00:00',
    gc_run_date: '2026-10-27T00:00:00',
    sample_tube_number: 4,
    flow_rate_mL_min: 0.5,
    nitrogen_flow_rate_mL_min: null,
    inlet_pressure_psi: 120,
    outlet_pressure_psi: null,
    sampling_volume_mL: 12.5,
    h2_concentration: 800,
    gas_sampling_volume_ml: 5,
    gas_sampling_pressure_MPa: 0.99974,
    h2_micromoles: null,
    h2_mass_ug: null,
    h2_grams_per_ton_yield: null,
    final_ph: 8.1,
    final_conductivity_mS_cm: null,
    pore_volume_mL: 30,
    interval_days: null,
    cumulative_liquid_volume_mL: null,
    cumulative_pore_volumes: null,
    cumulative_h2_grams_per_ton: null,
    h2_grams_per_ton_per_day: null,
    is_hold_interval: null,
    ...over,
  }
}

describe('pressure units', () => {
  it('145 psi is about 1.0 MPa on the wire', () => {
    expect(FIELD_BY_KEY.gas_sampling_pressure_MPa.toWire('145')).toBeCloseTo(0.99974, 4)
    const body = buildCreateBody({
      ...emptyForm(),
      measurement_date: '2026-11-03',
      flow_rate_mL_min: '0.5',
      gas_sampling_pressure_MPa: '145',
    })
    expect(body.gas_sampling_pressure_MPa).toBeCloseTo(0.99974, 4)
  })
})

describe('withSampleDate', () => {
  const free = { segmentStart: null, gcEdited: false, dayEdited: false }

  it('GC date follows the sample date until edited', () => {
    expect(withSampleDate(emptyForm(), '2026-11-03', free).gc_run_date).toBe('2026-11-03')
    const edited = { ...emptyForm(), gc_run_date: '2026-11-04' }
    expect(
      withSampleDate(edited, '2026-11-03', { ...free, gcEdited: true }).gc_run_date,
    ).toBe('2026-11-04')
  })

  it('Day is prefilled from the segment start in lab calendar days', () => {
    for (const start of ['2026-10-23T00:00:00', '2026-10-23T04:00:00Z', '2026-10-23T14:04:00']) {
      const f = withSampleDate(emptyForm(), '2026-11-03', { ...free, segmentStart: start })
      expect(f.time_post_reaction_days).toBe('11')
    }
    const same = withSampleDate(emptyForm(), '2026-11-03', {
      ...free,
      segmentStart: '2026-11-03T14:04:00',
    })
    expect(same.time_post_reaction_days).toBe('0')
    const kept = withSampleDate(
      { ...emptyForm(), time_post_reaction_days: '7' },
      '2026-11-03',
      { segmentStart: '2026-10-23T00:00:00', gcEdited: false, dayEdited: true },
    )
    expect(kept.time_post_reaction_days).toBe('7')
  })

  it('clears the day when there is no start or the date is invalid', () => {
    const f = { ...emptyForm(), time_post_reaction_days: '5' }
    expect(withSampleDate(f, '2026-11-03', free).time_post_reaction_days).toBe('')
    expect(
      withSampleDate(f, '', { ...free, segmentStart: '2026-10-23T00:00:00' }).time_post_reaction_days,
    ).toBe('')
  })
})

describe('labDateOf', () => {
  it('reads an aware instant in lab time', () => {
    expect(labDateOf('2026-11-04T03:00:00Z')).toBe('2026-11-03')
  })
  it('takes the first 10 chars of a naive string', () => {
    expect(labDateOf('2026-10-23T00:00:00')).toBe('2026-10-23')
  })
})

describe('patch bodies', () => {
  it('an untouched edit builds an empty patch', () => {
    const f = formFromSample(sample({ gas_sampling_pressure_MPa: 0.99974 }))
    expect(buildPatchBody(f, f)).toEqual({})
    expect(buildPatchBody(f, formFromSample(sample({ gas_sampling_pressure_MPa: 0.99974 })))).toEqual({})
  })

  it('a pH-only edit patches only final_ph', () => {
    const f = formFromSample(sample())
    expect(buildPatchBody(f, { ...f, final_ph: '7.4' })).toEqual({ final_ph: 7.4 })
  })

  it('clearing an optional field sends null', () => {
    const f = formFromSample(sample())
    expect(buildPatchBody(f, { ...f, final_ph: '' })).toEqual({ final_ph: null })
  })

  it('never includes the day', () => {
    const f = formFromSample(sample())
    expect(buildPatchBody(f, { ...f, time_post_reaction_days: '9' })).toEqual({})
  })
})

describe('validation', () => {
  const ok = { ...emptyForm(), measurement_date: '2026-11-03', flow_rate_mL_min: '0' }

  it('accepts a minimal form, including flow 0', () => {
    expect(validateForm(ok)).toEqual({})
  })
  it('requires sample date and flow', () => {
    const e = validateForm(emptyForm())
    expect(e.measurement_date).toBe('Required')
    expect(e.flow_rate_mL_min).toBe('Required')
  })
  it('rejects non-numbers', () => {
    expect(validateForm({ ...ok, final_ph: '1,5' }).final_ph).toBe('Must be a number')
    expect(validateForm({ ...ok, final_ph: 'abc' }).final_ph).toBe('Must be a number')
  })
  it('tube must be a positive whole number', () => {
    expect(validateForm({ ...ok, sample_tube_number: '0' }).sample_tube_number).toBe('Must be > 0')
    expect(validateForm({ ...ok, sample_tube_number: '2.5' }).sample_tube_number).toBe(
      'Must be a whole number',
    )
  })
  it('volume must be >= 0', () => {
    expect(validateForm({ ...ok, sampling_volume_mL: '-1' }).sampling_volume_mL).toBe('Must be ≥ 0')
  })
  it('day, when given, must be a number >= 0', () => {
    expect(validateForm({ ...ok, time_post_reaction_days: '-2' }).time_post_reaction_days).toBe(
      'Must be ≥ 0',
    )
    expect(validateForm({ ...ok, time_post_reaction_days: '3.5' })).toEqual({})
  })
  it('dates must be YYYY-MM-DD', () => {
    expect(validateForm({ ...ok, gc_run_date: '11/03/2026' }).gc_run_date).toBeDefined()
  })
})

describe('buildCreateBody', () => {
  it('omits blank optional fields and keeps the day when given', () => {
    const body = buildCreateBody({
      ...emptyForm(),
      measurement_date: '2026-11-03',
      flow_rate_mL_min: '0',
      time_post_reaction_days: '11',
      sample_tube_number: '4',
    })
    expect(body).toEqual({
      measurement_date: '2026-11-03',
      flow_rate_mL_min: 0,
      time_post_reaction_days: 11,
      sample_tube_number: 4,
    })
  })
})

describe('fmt', () => {
  it('renders missing values as a dash', () => {
    expect(fmt(null)).toBe('—')
    expect(fmt(undefined)).toBe('—')
    expect(fmt(NaN)).toBe('—')
    expect(fmt(0)).toBe('0')
    expect(fmt(1.23456)).toBe('1.235')
  })
})
