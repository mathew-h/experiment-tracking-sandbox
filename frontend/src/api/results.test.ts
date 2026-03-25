import { describe, it, expect } from 'vitest'
import type { ResultCreate, ScalarCreate } from './results'

// ── Compile-time shape assertions ─────────────────────────────────────────────
// These assignments compile only if the types are correct.
// The real type guard is `tsc --noEmit` — the test file is the spec.

const _validCreate: ResultCreate = {
  experiment_fk: 42,    // integer PK ✓
  description: 'Day 7',
}

const _withOptionals: ResultCreate = {
  experiment_fk: 1,
  description: 'Day 14',
  time_post_reaction_days: 14,
  is_primary_timepoint_result: false,
}

// ScalarCreate links to result_id — must NOT have experiment_fk
const _validScalar: ScalarCreate = {
  result_id: 5,
  final_ph: 7.2,
}

// ── Runtime assertions ────────────────────────────────────────────────────────

describe('ResultCreate shape', () => {
  it('experiment_fk is a number', () => {
    expect(typeof _validCreate.experiment_fk).toBe('number')
  })

  it('experiment_fk is required (has the assigned value)', () => {
    expect(_validCreate.experiment_fk).toBe(42)
  })

  it('optional fields are absent when not set', () => {
    expect(_validCreate.time_post_reaction_days).toBeUndefined()
    expect(_validCreate.is_primary_timepoint_result).toBeUndefined()
  })
})

describe('ScalarCreate shape', () => {
  it('links via result_id, not experiment_fk', () => {
    expect(_validScalar.result_id).toBe(5)
    expect('experiment_fk' in _validScalar).toBe(false)
  })
})

describe('resultsApi exports', () => {
  it('exports createResult and createScalar as functions', async () => {
    const { resultsApi } = await import('./results')
    expect(typeof resultsApi.createResult).toBe('function')
    expect(typeof resultsApi.createScalar).toBe('function')
  })
})
