import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '@/components/ui'

vi.mock('@/api/experiments', () => ({
  experimentsApi: { createReplicates: vi.fn(), getReplicateGroup: vi.fn() },
}))

import { CreateReplicatesModal } from './CreateReplicatesModal'
import { experimentsApi } from '@/api/experiments'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
})
function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>{children}</ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
  vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
    base_experiment_id: 'SERUM_001',
    parent: { id: 1, experiment_id: 'SERUM_001', replicate_label: null, status: 'ONGOING' },
    members: [{ id: 2, experiment_id: 'SERUM_001a', replicate_label: 'a', status: 'ONGOING' }],
  })
})

describe('CreateReplicatesModal', () => {
  it('previews the next letters after existing members', async () => {
    render(
      <CreateReplicatesModal open onClose={() => {}} baseExperimentId="SERUM_001" />,
      { wrapper },
    )
    // "a" exists, so count=3 previews b, c, d
    await waitFor(() =>
      expect(screen.getByText(/SERUM_001b, SERUM_001c, SERUM_001d/)).toBeInTheDocument()
    )
  })

  it('submits base + count and reports created IDs', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.createReplicates).mockResolvedValue({
      created: [], skipped: [],
    })
    render(
      <CreateReplicatesModal open onClose={() => {}} baseExperimentId="SERUM_001" />,
      { wrapper },
    )
    await user.click(screen.getByRole('button', { name: /create replicates/i }))
    await waitFor(() =>
      expect(experimentsApi.createReplicates).toHaveBeenCalledWith({
        base_experiment_id: 'SERUM_001',
        count: 3,
      })
    )
  })
})
