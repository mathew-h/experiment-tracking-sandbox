/** Issue #122 PR-C: the header description is the 'description' note, edited
 *  in place; a description-less experiment gets one from here. */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '@/components/ui'
import type { ExperimentDetail, ExperimentNote } from '@/api/experiments'
import * as experimentsApiModule from '@/api/experiments'
import { DescriptionEditor } from '../DescriptionEditor'
import { ExperimentDetailPage } from '../index'

vi.mock('@/api/experiments', async () => {
  const actual = await vi.importActual<typeof import('@/api/experiments')>('@/api/experiments')
  return {
    ...actual,
    experimentsApi: {
      get: vi.fn(),
      patch: vi.fn(),
      getReplicateGroup: vi.fn(() => Promise.resolve({ base_experiment_id: 'SERUM_050', parent: null, members: [] })),
      getGroup: vi.fn(() => Promise.reject(new Error('404'))),
      getResults: vi.fn(() => Promise.resolve([])),
      getRollup: vi.fn(),
      getDeleteImpact: vi.fn(),
      delete: vi.fn(),
      addNote: vi.fn(() => Promise.resolve({})),
      patchNote: vi.fn(() => Promise.resolve({ data: {} })),
    },
  }
})
vi.mock('@/api/conditions', () => ({
  conditionsApi: { getByExperiment: vi.fn().mockRejectedValue(new Error('none')) },
}))

const api = () => experimentsApiModule.experimentsApi

const DESC: ExperimentNote = {
  id: 41, note_text: 'Pyrite + Cu, 90 °C', note_type: 'description', result_id: null,
  created_by: null, needs_review: false, created_at: '2026-07-01T00:00:00Z', updated_at: null,
}

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } } })
  const utils = render(
    <MemoryRouter initialEntries={['/experiments/SERUM_050']}>
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <Routes>
            <Route path="/experiments/:id" element={ui} />
            <Route path="/experiments" element={<div>Experiments List</div>} />
          </Routes>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
  return { ...utils, qc }
}

beforeEach(() => { vi.clearAllMocks() })

describe('DescriptionEditor', () => {
  it('offers "Add description" when the experiment has none, and POSTs a description note', async () => {
    const user = userEvent.setup()
    const { qc } = wrap(<DescriptionEditor experimentId="SERUM_050" note={undefined} />)
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    await user.click(screen.getByRole('button', { name: /add description/i }))
    await user.type(screen.getByLabelText('Description'), 'Serum, Ni catalyst')
    await user.click(screen.getByRole('button', { name: /^save$/i }))
    expect(api().addNote).toHaveBeenCalledWith('SERUM_050', 'Serum, Ni catalyst', { note_type: 'description' })
    await vi.waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['experiment', 'SERUM_050'] }))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['experiments'] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['dashboard'] })
  })

  it('clicking the description opens the editor pre-filled, and Save PATCHes note_text on that note', async () => {
    const user = userEvent.setup()
    wrap(<DescriptionEditor experimentId="SERUM_050" note={DESC} />)
    await user.click(screen.getByRole('button', { name: /edit description/i }))
    const box = screen.getByLabelText('Description') as HTMLTextAreaElement
    expect(box.value).toBe('Pyrite + Cu, 90 °C')
    await user.clear(box)
    await user.type(box, 'Pyrite + Cu, 120 °C')
    await user.click(screen.getByRole('button', { name: /^save$/i }))
    expect(api().patchNote).toHaveBeenCalledWith('SERUM_050', 41, { note_text: 'Pyrite + Cu, 120 °C' })
    expect(api().addNote).not.toHaveBeenCalled()
  })

  it('Save is disabled for blank text and for unchanged text (Review Focus 3)', async () => {
    const user = userEvent.setup()
    wrap(<DescriptionEditor experimentId="SERUM_050" note={DESC} />)
    await user.click(screen.getByRole('button', { name: /edit description/i }))
    const save = screen.getByRole('button', { name: /^save$/i })
    expect(save).toBeDisabled()
    const box = screen.getByLabelText('Description')
    await user.clear(box)
    expect(save).toBeDisabled()
    await user.type(box, '   ')
    expect(save).toBeDisabled()
    await user.type(box, 'changed')
    expect(save).toBeEnabled()
    expect(api().patchNote).not.toHaveBeenCalled()
  })

  it('Escape cancels without a request; Ctrl+Enter saves', async () => {
    const user = userEvent.setup()
    wrap(<DescriptionEditor experimentId="SERUM_050" note={DESC} />)
    await user.click(screen.getByRole('button', { name: /edit description/i }))
    await user.type(screen.getByLabelText('Description'), ' more')
    await user.keyboard('{Escape}')
    expect(screen.queryByLabelText('Description')).not.toBeInTheDocument()
    expect(api().patchNote).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /edit description/i })).toHaveTextContent('Pyrite + Cu, 90 °C')

    await user.click(screen.getByRole('button', { name: /edit description/i }))
    await user.type(screen.getByLabelText('Description'), ' more')
    await user.keyboard('{Control>}{Enter}{/Control}')
    expect(api().patchNote).toHaveBeenCalledWith('SERUM_050', 41, { note_text: 'Pyrite + Cu, 90 °C more' })
  })

  it('a rejected save shows the server detail in a toast and stays in edit mode', async () => {
    const user = userEvent.setup()
    vi.mocked(api().patchNote).mockRejectedValueOnce(new Error('Note 41 not found'))
    wrap(<DescriptionEditor experimentId="SERUM_050" note={DESC} />)
    await user.click(screen.getByRole('button', { name: /edit description/i }))
    await user.type(screen.getByLabelText('Description'), '!')
    await user.click(screen.getByRole('button', { name: /^save$/i }))
    expect(await screen.findByText(/Note 41 not found/)).toBeInTheDocument()
    expect(screen.getByLabelText('Description')).toBeInTheDocument()
  })
})

describe('ExperimentDetailPage header wiring', () => {
  const BASE: ExperimentDetail = {
    id: 5, experiment_id: 'SERUM_050', experiment_number: 150, status: 'ONGOING',
    researcher: null, date: null, sample_id: null, base_experiment_id: null,
    parent_experiment_fk: null, replicate_label: null, is_outlier: false,
    id_timepoint_days: null, created_at: '2026-07-01T00:00:00Z', updated_at: null,
    conditions: null, notes: [], modifications: [],
  }

  it('shows "Add description" when the detail has no description note', async () => {
    vi.mocked(api().get).mockResolvedValue(BASE)
    wrap(<ExperimentDetailPage />)
    expect(await screen.findByRole('button', { name: /add description/i })).toBeInTheDocument()
  })

  it('renders the description note as the editable header text', async () => {
    vi.mocked(api().get).mockResolvedValue({ ...BASE, notes: [DESC] })
    wrap(<ExperimentDetailPage />)
    expect(await screen.findByRole('button', { name: /edit description/i })).toHaveTextContent('Pyrite + Cu, 90 °C')
    expect(screen.queryByRole('button', { name: /add description/i })).not.toBeInTheDocument()
  })
})
