import { describe, it, expect } from 'vitest'
import { slotLabelsFor, slotToConditions } from '../reactorSlots'

describe('reactorSlots (issue #147)', () => {
  it('splits a picked label into number and series', () => {
    expect(slotToConditions('P03', 'HPHT')).toEqual({ reactor_number: 3, reactor_series: 'P' })
    expect(slotToConditions('R12', 'hpht')).toEqual({ reactor_number: 12, reactor_series: null })
    expect(slotToConditions('CF02', 'Core Flood')).toEqual({ reactor_number: 2, reactor_series: null })
  })

  it('rejects a label that is not one of the type\'s slots', () => {
    expect(slotToConditions('P03', 'Core Flood')).toBeNull()
    expect(slotToConditions('R03', 'Serum')).toBeNull()
    expect(slotToConditions('', 'HPHT')).toBeNull()
  })

  it('has no slots for non-occupancy types', () => {
    expect(slotLabelsFor('Serum')).toEqual([])
    expect(slotLabelsFor(null)).toEqual([])
  })
})
