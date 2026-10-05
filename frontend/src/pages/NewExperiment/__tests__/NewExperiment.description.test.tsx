/** Issue #122 PR-B0: the wizard's Step 1 text is the experiment's `description`
 *  note (design decision 7), and creating an experiment refreshes the dashboard
 *  so the new reactor card shows it without a reload. */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import { experimentsApi } from '@/api/experiments'
import { NewExperimentPage } from '../index'

const { mockNavigate } = vi.hoisted(() => ({ mockNavigate: vi.fn() }))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    nextId: vi.fn(() => Promise.resolve({ next_id: 'HPHT_900' })),
    checkExists: vi.fn(() => Promise.resolve({ exists: false })),
    list: vi.fn(() => Promise.resolve({ items: [], total: 0 })),
    create: vi.fn(() => Promise.resolve({ id: 42, experiment_id: 'HPHT_900' })),
    addNote: vi.fn(() => Promise.resolve({})),
    createReplicates: vi.fn(),
  },
}))

vi.mock('@/api/conditions', () => ({
  conditionsApi: {
    create: vi.fn(() => Promise.resolve({})),
    getByExperiment: vi.fn(),
  },
}))

vi.mock('@/api/chemicals', () => ({
  chemicalsApi: {
    listCompounds: vi.fn(() => Promise.resolve([])),
    listExperimentAdditives: vi.fn(() => Promise.resolve([])),
    upsertAdditive: vi.fn(),
  },
}))

vi.mock('@/api/samples', () => ({
  samplesApi: {
    list: vi.fn(() => Promise.resolve({ items: [], total: 0 })),
  },
}))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const utils = render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>{ui}</MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
  return { ...utils, qc }
}

/** Drive the four-step wizard to submission. `description` is typed into the
 *  Step 1 "Experiment Description (optional)" textarea when given. */
async function createExperiment(user: ReturnType<typeof userEvent.setup>, description?: string) {
  await user.selectOptions(screen.getByLabelText(/experiment type/i), 'HPHT')
  await waitFor(() =>
    expect((screen.getByLabelText(/^experiment id/i) as HTMLInputElement).value).toBe('HPHT_900'),
  )
  if (description !== undefined) {
    await user.type(screen.getByPlaceholderText(/describe the experiment/i), description)
  }
  const next1 = screen.getByRole('button', { name: /next: conditions/i })
  // Step 1's Next waits on the 300 ms debounced ID-availability check.
  await waitFor(() => expect(next1).not.toBeDisabled(), { timeout: 2000 })
  await user.click(next1)
  await user.click(screen.getByRole('button', { name: /next: additives/i }))
  await user.click(screen.getByRole('button', { name: /next: review/i }))
  await user.click(screen.getByRole('button', { name: /create experiment/i }))
  await waitFor(() => expect(experimentsApi.create).toHaveBeenCalled())
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('NewExperimentPage — description note', () => {
  it('saves the Step 1 description as a note typed description', async () => {
    const user = userEvent.setup()
    wrap(<NewExperimentPage />)
    await createExperiment(user, 'Baseline serpentinite run')
    await waitFor(() =>
      expect(experimentsApi.addNote).toHaveBeenCalledWith(
        'HPHT_900', 'Baseline serpentinite run', { note_type: 'description' },
      ),
    )
    expect(experimentsApi.addNote).toHaveBeenCalledTimes(1)
  })

  it('writes no note when the description is blank', async () => {
    const user = userEvent.setup()
    wrap(<NewExperimentPage />)
    await createExperiment(user)
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/experiments/HPHT_900'))
    expect(experimentsApi.addNote).not.toHaveBeenCalled()
  })

  it('writes no note when the description is only whitespace', async () => {
    const user = userEvent.setup()
    wrap(<NewExperimentPage />)
    await createExperiment(user, '   ')
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/experiments/HPHT_900'))
    expect(experimentsApi.addNote).not.toHaveBeenCalled()
  })

  it('invalidates the dashboard and experiments queries on success', async () => {
    const user = userEvent.setup()
    const { qc } = wrap(<NewExperimentPage />)
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    await createExperiment(user, 'Baseline serpentinite run')
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['dashboard'] }))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['experiments'] })
  })
})
