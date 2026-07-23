import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
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

  it('shows the resolved base from the replicate group, not the on-screen experiment', async () => {
    // Simulate a derivation/treatment page: the on-screen ID differs from the
    // group's actual base_experiment_id resolved from the backend.
    vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
      base_experiment_id: 'HPHT_001',
      parent: { id: 1, experiment_id: 'HPHT_001', replicate_label: null, status: 'ONGOING' },
      members: [],
    })
    render(
      <CreateReplicatesModal open onClose={() => {}} baseExperimentId="HPHT_001-2" />,
      { wrapper },
    )
    // Waits for the group query to resolve and the resolved base (not the
    // on-screen "HPHT_001-2" prop) to render — an exact match distinguishes
    // "HPHT_001" from "HPHT_001-2".
    await waitFor(() => expect(screen.getByText('HPHT_001')).toBeInTheDocument())
    expect(screen.getByText(/Replicates are created under/)).toBeInTheDocument()
    // Preview IDs are also derived from the resolved base, not the prop.
    await waitFor(() =>
      expect(screen.getByText(/HPHT_001a, HPHT_001b, HPHT_001c/)).toBeInTheDocument()
    )
  })

  it('resets count to 3 when closed via cancel and reopened', async () => {
    const user = userEvent.setup()
    let isOpen = true
    const onClose = vi.fn(() => { isOpen = false })
    const { rerender } = render(
      <CreateReplicatesModal open={isOpen} onClose={onClose} baseExperimentId="SERUM_001" />,
      { wrapper },
    )
    const countInput = await screen.findByLabelText(/how many/i)
    fireEvent.change(countInput, { target: { value: '7' } })
    await waitFor(() => expect(countInput).toHaveValue(7))

    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onClose).toHaveBeenCalled()

    // Simulate the parent closing then reopening the modal.
    rerender(
      <CreateReplicatesModal open={false} onClose={onClose} baseExperimentId="SERUM_001" />,
    )
    rerender(
      <CreateReplicatesModal open onClose={onClose} baseExperimentId="SERUM_001" />,
    )

    const reopenedInput = await screen.findByLabelText(/how many/i)
    expect(reopenedInput).toHaveValue(3)
  })
})
