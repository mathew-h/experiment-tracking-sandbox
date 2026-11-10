import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { email: 'mh@addisenergy.com', displayName: 'MH' }, signOut: vi.fn() }),
}))
vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    getReviewQueue: vi.fn(() => Promise.resolve({ items: [], total: 0, skip: 0, limit: 1, distinct_texts: [] })),
  },
}))

import { AppLayout } from '../AppLayout'

describe('AppLayout navigation', () => {
  it('sidebar shows Core Floods', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <MemoryRouter initialEntries={['/core-floods']}>
        <QueryClientProvider client={qc}>
          <AppLayout />
        </QueryClientProvider>
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: /core floods/i })).toHaveAttribute('href', '/core-floods')
    expect(screen.getByRole('link', { name: /^experiments$/i })).not.toHaveClass('border-red-500')
    // Ordered by task (issue #159): the run lists follow Experiments.
    const navHrefs = within(screen.getByRole('navigation')).getAllByRole('link').map((a) => a.getAttribute('href'))
    expect(navHrefs).toEqual([
      '/', '/experiments', '/hpht', '/core-floods', '/experiments/new', '/bulk-uploads',
      '/samples', '/chemicals', '/data-export', '/notes/review',
    ])
  })

  it('sidebar shows HPHT directly above Core Floods (issue #150)', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <MemoryRouter initialEntries={['/hpht']}>
        <QueryClientProvider client={qc}>
          <AppLayout />
        </QueryClientProvider>
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: /^hpht$/i })).toHaveAttribute('href', '/hpht')
    const navHrefs = within(screen.getByRole('navigation')).getAllByRole('link').map((a) => a.getAttribute('href'))
    expect(navHrefs.indexOf('/core-floods') - navHrefs.indexOf('/hpht')).toBe(1)
  })
})
