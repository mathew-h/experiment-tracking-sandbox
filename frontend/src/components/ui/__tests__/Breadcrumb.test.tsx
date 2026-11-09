import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Breadcrumb } from '../Breadcrumb'

describe('Breadcrumb', () => {
  it('renders linked items as links and the last item as text', () => {
    render(
      <MemoryRouter>
        <Breadcrumb items={[{ label: 'Experiments', to: '/experiments' }, { label: 'HPHT_297-2', mono: true }]} />
      </MemoryRouter>,
    )
    const nav = screen.getByRole('navigation', { name: 'Breadcrumb' })
    expect(nav).toHaveTextContent('Experiments›HPHT_297-2')
    expect(screen.getByRole('link', { name: 'Experiments' })).toHaveAttribute('href', '/experiments')
    expect(screen.queryByRole('link', { name: 'HPHT_297-2' })).toBeNull()
    expect(screen.getByText('HPHT_297-2')).toHaveClass('font-mono-data')
    expect(screen.getByText('Experiments')).not.toHaveClass('font-mono-data')
  })

  it('puts one separator between items and none around a single item', () => {
    const { rerender } = render(
      <MemoryRouter>
        <Breadcrumb items={[{ label: 'HPHT', to: '/hpht' }]} />
      </MemoryRouter>,
    )
    expect(screen.getByRole('navigation')).toHaveTextContent(/^HPHT$/)
    expect(screen.getByRole('link', { name: 'HPHT' })).toHaveAttribute('href', '/hpht')

    rerender(
      <MemoryRouter>
        <Breadcrumb items={[{ label: 'A', to: '/a' }, { label: 'B', to: '/b' }, { label: 'C' }]} />
      </MemoryRouter>,
    )
    expect(screen.getByRole('navigation')).toHaveTextContent(/^A›B›C$/)
  })

  it('keeps the breadcrumb text style and accepts extra classes', () => {
    render(
      <MemoryRouter>
        <Breadcrumb className="mb-1" items={[{ label: 'Experiments', to: '/experiments' }]} />
      </MemoryRouter>,
    )
    const line = screen.getByRole('navigation').firstElementChild
    expect(line).toHaveClass('text-xs', 'text-ink-muted', 'mb-1')
  })
})
