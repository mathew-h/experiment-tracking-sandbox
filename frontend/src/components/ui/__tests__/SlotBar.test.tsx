import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { SlotBar } from '../SlotBar'

describe('SlotBar', () => {
  it('renders 16 ticks with 8 ongoing, 4 queued, 4 empty', () => {
    const { container } = render(
      <SlotBar
        total={16}
        segments={[
          { count: 8, className: 'bg-status-ongoing', label: 'ongoing' },
          { count: 4, className: 'bg-status-queued', label: 'queued' },
        ]}
      />
    )
    const ticks = container.querySelectorAll('[role="img"] > div')
    expect(ticks.length).toBe(16)
    const ongoing = Array.from(ticks).filter((t) => t.className.includes('bg-status-ongoing'))
    const queued = Array.from(ticks).filter((t) => t.className.includes('bg-status-queued'))
    const empty = Array.from(ticks).filter((t) => t.className.includes('bg-surface-overlay'))
    expect(ongoing.length).toBe(8)
    expect(queued.length).toBe(4)
    expect(empty.length).toBe(4)
  })

  it('renders no empty ticks when fully occupied', () => {
    const { container } = render(
      <SlotBar total={3} segments={[{ count: 3, className: 'bg-status-ongoing', label: 'ongoing' }]} />
    )
    const ticks = container.querySelectorAll('[role="img"] > div')
    const empty = Array.from(ticks).filter((t) => t.className.includes('bg-surface-overlay'))
    expect(empty.length).toBe(0)
  })

  it('clamps over-supplied segments to total', () => {
    const { container } = render(
      <SlotBar total={3} segments={[{ count: 10, className: 'bg-status-ongoing', label: 'ongoing' }]} />
    )
    const ticks = container.querySelectorAll('[role="img"] > div')
    expect(ticks.length).toBe(3)
  })
})
