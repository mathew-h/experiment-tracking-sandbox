import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge } from '../Badge'

describe('StatusBadge', () => {
  it('renders QUEUED with warning/queued variant styling', () => {
    const { container } = render(<StatusBadge status="QUEUED" />)
    const badge = container.firstElementChild as HTMLElement
    expect(badge.className).toContain('bg-status-queued')
    expect(badge.className).toContain('text-status-queued')
    expect(screen.getByText('QUEUED')).toBeTruthy()
  })

  it('renders ONGOING with ongoing variant styling', () => {
    const { container } = render(<StatusBadge status="ONGOING" />)
    const badge = container.firstElementChild as HTMLElement
    expect(badge.className).toContain('bg-status-ongoing')
  })

  it('renders unknown status with default variant', () => {
    const { container } = render(<StatusBadge status="UNKNOWN" />)
    const badge = container.firstElementChild as HTMLElement
    expect(badge.className).toContain('bg-surface-overlay')
  })
})
