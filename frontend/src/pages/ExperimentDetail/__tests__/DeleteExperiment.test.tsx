import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '@/components/ui'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    get: vi.fn(),
    patch: vi.fn(),
    getReplicateGroup: vi.fn(),
    getResults: vi.fn(),
    getRollup: vi.fn(),
    getDeleteImpact: vi.fn(),
    delete: vi.fn(),
    exportAll: vi.fn(),
  },
}))
vi.mock('@/api/conditions', () => ({
  conditionsApi: { getByExperiment: vi.fn().mockRejectedValue(new Error('none')) },
}))

import { ExperimentDetailPage } from '../index'
import { experimentsApi } from '@/api/experiments'
import type { ExperimentDetail, DeleteImpact } from '@/api/experiments'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
})

const BASE_DETAIL: ExperimentDetail = {
  id: 5, experiment_id: 'SERUM_050', experiment_number: 150, status: 'ONGOING',
  researcher: null, date: null, sample_id: null, base_experiment_id: null,
  parent_experiment_fk: null, replicate_label: null, is_outlier: false,
  id_timepoint_days: null, created_at: '2026-07-01T00:00:00Z', updated_at: null,
  conditions: null, notes: [], modifications: [],
}

const EMPTY_IMPACT: DeleteImpact = {
  experiment_id: 'SERUM_050',
  conditions: 0,
  results: 0, scalar_results: 0, icp_results: 0, result_files: 0, notes: 0,
  additives: 0, external_analyses: 0, xrd_phases: 0,
  total: 0, background_for: [], h2_background_for: [], replicate_children: [],
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/experiments/SERUM_050']}>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <Routes>
            <Route path="/experiments/:id" element={<ExperimentDetailPage />} />
            <Route path="/experiments" element={<div>Experiments List</div>} />
          </Routes>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
  vi.mocked(experimentsApi.get).mockResolvedValue(BASE_DETAIL)
  vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
    base_experiment_id: 'SERUM_050', parent: null, members: [],
  })
  vi.mocked(experimentsApi.getDeleteImpact).mockResolvedValue(EMPTY_IMPACT)
  vi.mocked(experimentsApi.delete).mockResolvedValue({
    experiment_id: 'SERUM_050', deleted: true, impact: EMPTY_IMPACT,
  })
})

describe('experiment not found (issue #159)', () => {
  it('offers a way back to the list', async () => {
    vi.mocked(experimentsApi.get).mockRejectedValue(new Error('404'))
    renderPage()
    expect(await screen.findByText('Experiment not found')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to Experiments' })).toHaveAttribute('href', '/experiments')
  })
})

describe('experiment deletion from the detail page', () => {
  it('exposes a Delete Experiment action', async () => {
    renderPage()
    expect(
      await screen.findByRole('button', { name: /delete experiment/i }),
    ).toBeInTheDocument()
  })

  it('opens the confirmation dialog rather than deleting immediately', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /delete experiment/i }))
    expect(await screen.findByText(/permanently delete/i)).toBeInTheDocument()
    expect(experimentsApi.delete).not.toHaveBeenCalled()
  })

  it('deletes and navigates back to the list on success', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /delete experiment/i }))
    await user.click(await screen.findByRole('button', { name: /^delete$/i }))
    await waitFor(() => expect(experimentsApi.delete).toHaveBeenCalledWith('SERUM_050'))
    expect(await screen.findByText('Experiments List')).toBeInTheDocument()
  })

  it('evicts the experiment and delete-impact caches and refreshes group-rollup, not the dead rollup key', async () => {
    const removeSpy = vi.spyOn(queryClient, 'removeQueries')
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /delete experiment/i }))
    await user.click(await screen.findByRole('button', { name: /^delete$/i }))
    await waitFor(() => expect(experimentsApi.delete).toHaveBeenCalledWith('SERUM_050'))

    // Every cache keyed by the experiment ID must be evicted, not invalidated:
    // the freed ID can be reused, so a stale entry must not be readable at all.
    // Awaited, because the eviction is deliberately deferred until after the
    // navigation commits (see onDeleted in ../index.tsx).
    for (const key of [
      'experiment', 'delete-impact', 'conditions', 'additives',
      'experiment-results', 'xrd', 'external-analysis', 'replicate-group',
    ]) {
      await waitFor(() =>
        expect(removeSpy).toHaveBeenCalledWith({ queryKey: [key, 'SERUM_050'] }),
      )
    }
    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['group-rollup'] }),
    )
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['rollup'] })

    removeSpy.mockRestore()
    invalidateSpy.mockRestore()
  })

  it('refreshes the group caches keyed by base ID and evicts the series ICP (issue #105)', async () => {
    // Group caches are keyed by the BASE ID ('SERUM_050' here is its own base, but a
    // vial 'SERUM_050a-t5' would leave ['replicate-group-detail', 'SERUM_050']), so
    // an eviction by the deleted experiment ID cannot reach them.
    queryClient.setQueryData(['replicate-group-detail', 'SERUM_050_BASE'], { member_count: 3 })
    queryClient.setQueryData(['group-h2-bkg-rollup', 'SERUM_050_BASE'], [])
    queryClient.setQueryData(['experiment-icp', 'SERUM_050_SIBLING'], { rows: [], segment_starts: [] })
    const removeSpy = vi.spyOn(queryClient, 'removeQueries')
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /delete experiment/i }))
    await user.click(await screen.findByRole('button', { name: /^delete$/i }))
    await waitFor(() => expect(experimentsApi.delete).toHaveBeenCalledWith('SERUM_050'))

    await waitFor(() =>
      expect(removeSpy).toHaveBeenCalledWith({ queryKey: ['experiment-icp', 'SERUM_050'] }),
    )
    // The group page, its H₂ background rollup and a sibling's series ICP are all
    // marked stale, so their next render refetches instead of showing the deleted vial.
    for (const key of [
      ['replicate-group-detail', 'SERUM_050_BASE'],
      ['group-h2-bkg-rollup', 'SERUM_050_BASE'],
      ['experiment-icp', 'SERUM_050_SIBLING'],
    ]) {
      await waitFor(() => expect(queryClient.getQueryState(key)?.isInvalidated).toBe(true))
    }
    removeSpy.mockRestore()
  })

  it('evicts caches only after navigating away from the detail page', async () => {
    // Regression guard for the eviction ORDER. Several evicted keys are still
    // actively observed by this page, and removing/invalidating an active query
    // makes React Query refetch it — against an experiment the server just
    // deleted — which produced a burst of 404s in the console. The fix
    // navigates first so no observer survives to refetch.
    //
    // The 404 burst itself is timing-dependent and does not reproduce under
    // jsdom, so this asserts the code's ordering guarantee instead: at the
    // moment the first eviction runs, the list route must already be rendered.
    // Before the fix, the detail page was still mounted here.
    let detailStillMountedAtEviction: boolean | null = null
    const original = queryClient.removeQueries.bind(queryClient)
    const removeSpy = vi
      .spyOn(queryClient, 'removeQueries')
      .mockImplementation((filters?: Parameters<typeof original>[0]) => {
        if (detailStillMountedAtEviction === null) {
          detailStillMountedAtEviction = screen.queryByText('Experiments List') === null
        }
        return original(filters)
      })

    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /delete experiment/i }))
    await user.click(await screen.findByRole('button', { name: /^delete$/i }))
    await waitFor(() => expect(experimentsApi.delete).toHaveBeenCalledWith('SERUM_050'))
    expect(await screen.findByText('Experiments List')).toBeInTheDocument()

    await waitFor(() => expect(detailStillMountedAtEviction).not.toBeNull())
    expect(detailStillMountedAtEviction).toBe(false)

    removeSpy.mockRestore()
  })
})
