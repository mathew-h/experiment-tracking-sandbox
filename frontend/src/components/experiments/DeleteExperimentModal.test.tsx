import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'

vi.mock('@/api/experiments', () => ({
  experimentsApi: { getDeleteImpact: vi.fn(), delete: vi.fn() },
}))

import { DeleteExperimentModal } from './DeleteExperimentModal'
import { experimentsApi } from '@/api/experiments'
import type { DeleteImpact } from '@/api/experiments'

const EMPTY_IMPACT: DeleteImpact = {
  experiment_id: 'SERUM_001a',
  conditions: 0, results: 0, scalar_results: 0, icp_results: 0, result_files: 0,
  notes: 0, additives: 0, external_analyses: 0, xrd_phases: 0,
  change_requests: 0, total: 0, background_for: [], replicate_children: [],
}

const HEAVY_IMPACT: DeleteImpact = {
  ...EMPTY_IMPACT,
  results: 3, scalar_results: 3, icp_results: 2, notes: 1, xrd_phases: 4,
  total: 13, background_for: ['SERUM_002a'], replicate_children: ['SERUM_001a-2'],
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
})

function renderModal(onDeleted = vi.fn(), onClose = vi.fn()) {
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <DeleteExperimentModal
          open
          experimentId="SERUM_001a"
          onClose={onClose}
          onDeleted={onDeleted}
        />
      </ToastProvider>
    </QueryClientProvider>,
  )
  return { onDeleted, onClose }
}

beforeEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
  vi.mocked(experimentsApi.delete).mockResolvedValue({
    experiment_id: 'SERUM_001a', deleted: true, impact: HEAVY_IMPACT,
  })
})

describe('DeleteExperimentModal', () => {
  it('itemizes the impact counts, hiding zero rows', async () => {
    vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue(HEAVY_IMPACT)
    renderModal()
    expect(await screen.findByText(/3 result timepoints/i)).toBeInTheDocument()
    expect(screen.getByText(/4 XRD phase rows/i)).toBeInTheDocument()
    expect(screen.queryByText(/result files/i)).not.toBeInTheDocument()
  })

  it('names the experiments that will be decoupled', async () => {
    vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue(HEAVY_IMPACT)
    renderModal()
    expect(await screen.findByText(/SERUM_002a/)).toBeInTheDocument()
    expect(screen.getByText(/SERUM_001a-2/)).toBeInTheDocument()
  })

  it('keeps Delete disabled until the exact id is typed when impact is non-zero', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue(HEAVY_IMPACT)
    renderModal()

    // Wait for the impact query to resolve and the body to render before
    // grabbing the button — otherwise the button query can resolve against
    // the pre-load render (Delete exists but disabled) rather than confirming
    // its state once impact has actually loaded.
    const input = await screen.findByLabelText(/type the experiment id/i)
    const confirmBtn = screen.getByRole('button', { name: /^delete$/i })
    expect(confirmBtn).toBeDisabled()

    await user.type(input, 'SERUM_001')
    expect(confirmBtn).toBeDisabled()

    await user.type(input, 'a')
    await waitFor(() => expect(confirmBtn).toBeEnabled())

    await user.click(confirmBtn)
    await waitFor(() => expect(experimentsApi.delete).toHaveBeenCalledWith('SERUM_001a'))
  })

  it('does not require a typed id when nothing depends on the experiment', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue(EMPTY_IMPACT)
    renderModal()

    expect(await screen.findByText(/no dependent records/i)).toBeInTheDocument()
    expect(screen.queryByLabelText(/type the experiment id/i)).not.toBeInTheDocument()

    const confirmBtn = screen.getByRole('button', { name: /^delete$/i })
    expect(confirmBtn).toBeEnabled()
    await user.click(confirmBtn)
    await waitFor(() => expect(experimentsApi.delete).toHaveBeenCalledWith('SERUM_001a'))
  })

  it('itemizes a conditions-only impact and still demands the typed id', async () => {
    // The commonest live shape (44 dev-DB experiments). Before `conditions` was
    // counted this rendered "nothing else is affected" and enabled Delete on a
    // single click while a full setup record was destroyed.
    const user = userEvent.setup()
    vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue({
      ...EMPTY_IMPACT, conditions: 1, total: 1,
    })
    renderModal()

    expect(await screen.findByText(/1 conditions record/i)).toBeInTheDocument()
    expect(screen.queryByText(/no dependent records/i)).not.toBeInTheDocument()

    const confirmBtn = screen.getByRole('button', { name: /^delete$/i })
    expect(confirmBtn).toBeDisabled()
    await user.type(await screen.findByLabelText(/type the experiment id/i), 'SERUM_001a')
    await waitFor(() => expect(confirmBtn).toBeEnabled())
  })

  it('demands the typed id when nothing is destroyed but something is decoupled', async () => {
    vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue({
      ...EMPTY_IMPACT, total: 0, background_for: ['SERUM_009a'],
    })
    renderModal()

    expect(await screen.findByLabelText(/type the experiment id/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^delete$/i })).toBeDisabled()
  })

  it('cancel is a no-op — closes without deleting', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue(HEAVY_IMPACT)
    const { onClose, onDeleted } = renderModal()

    await user.click(await screen.findByRole('button', { name: /cancel/i }))
    expect(onClose).toHaveBeenCalled()
    expect(experimentsApi.delete).not.toHaveBeenCalled()
    expect(onDeleted).not.toHaveBeenCalled()
  })

  it('calls onDeleted with the server response on success', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue(EMPTY_IMPACT)
    const { onDeleted } = renderModal()

    await user.click(await screen.findByRole('button', { name: /^delete$/i }))
    await waitFor(() =>
      expect(onDeleted).toHaveBeenCalledWith(
        expect.objectContaining({ experiment_id: 'SERUM_001a', deleted: true }),
      ),
    )
  })

  it('surfaces a server error and does not call onDeleted', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue(EMPTY_IMPACT)
    vi.mocked(experimentsApi.delete).mockRejectedValue({
      response: { data: { detail: 'Experiment not found' } },
    })
    const { onDeleted } = renderModal()

    await user.click(await screen.findByRole('button', { name: /^delete$/i }))
    expect(await screen.findByText(/experiment not found/i)).toBeInTheDocument()
    expect(onDeleted).not.toHaveBeenCalled()
  })

  it('shows an error and keeps Delete disabled when the impact fetch fails', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.getDeleteImpact).mockRejectedValue(new Error('network error'))
    const { onClose } = renderModal()

    expect(
      await screen.findByText(/could not load what this deletion would affect/i),
    ).toBeInTheDocument()

    const confirmBtn = screen.getByRole('button', { name: /^delete$/i })
    expect(confirmBtn).toBeDisabled()

    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onClose).toHaveBeenCalled()
    expect(experimentsApi.delete).not.toHaveBeenCalled()
  })
})
