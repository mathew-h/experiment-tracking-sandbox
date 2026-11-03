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
    // Second to last, just above Notes review.
    const navHrefs = within(screen.getByRole('navigation')).getAllByRole('link').map((a) => a.getAttribute('href'))
    expect(navHrefs.slice(-2)).toEqual(['/core-floods', '/notes/review'])
  })
})
