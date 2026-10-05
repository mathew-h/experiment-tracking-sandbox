import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { NoteBadge, noteBadgeVariant } from './NoteBadge'

describe('NoteBadge', () => {
  it('renders the full type label', () => {
    render(<NoteBadge type="result_note" />)
    expect(screen.getByTestId('note-badge')).toHaveTextContent('Result note')
  })

  it('maps types to the variants /notes/review used', () => {
    expect(noteBadgeVariant('modification')).toBe('warning')
    expect(noteBadgeVariant('description')).toBe('info')
    expect(noteBadgeVariant('observation')).toBe('default')
    expect(noteBadgeVariant('result_note')).toBe('default')
  })

  it('only a modification carries the status dot', () => {
    const { container, rerender } = render(<NoteBadge type="modification" />)
    expect(container.querySelector('.rounded-full')).not.toBeNull()
    rerender(<NoteBadge type="observation" />)
    expect(container.querySelector('.rounded-full')).toBeNull()
  })
})
