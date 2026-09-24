import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { email: 'mh@addisenergy.com', displayName: 'MH' }, signOut: vi.fn() }),
}))
vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    getReviewQueue: vi.fn(() => Promise.resolve({ items: [], total: 1288, skip: 0, limit: 1, distinct_texts: [] })),
  },
}))

import { AppLayout } from '../AppLayout'
import { experimentsApi } from '@/api/experiments'

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <AppLayout />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('AppLayout review-queue badge', () => {
  it('links to /notes/review and shows the open count', async () => {
    wrap()
    const link = screen.getByRole('link', { name: /notes review/i })
    expect(link).toHaveAttribute('href', '/notes/review')
    await waitFor(() => expect(screen.getByText('1288')).toBeInTheDocument())
    expect(experimentsApi.getReviewQueue).toHaveBeenCalledWith({ limit: 1 })
  })

  it('hides the badge when the queue is empty', async () => {
    vi.mocked(experimentsApi.getReviewQueue).mockResolvedValueOnce({ items: [], total: 0, skip: 0, limit: 1, distinct_texts: [] })
    wrap()
    await waitFor(() => expect(experimentsApi.getReviewQueue).toHaveBeenCalled())
    expect(screen.queryByTestId('review-count-badge')).not.toBeInTheDocument()
  })
})
