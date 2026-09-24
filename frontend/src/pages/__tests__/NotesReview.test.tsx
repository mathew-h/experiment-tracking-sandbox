/** Issue #122 PR-A: the global review queue page. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import type { ReviewNoteItem, ReviewQueueResponse } from '@/api/experiments'

vi.mock('@/api/experiments', async () => {
  const actual = await vi.importActual<typeof import('@/api/experiments')>('@/api/experiments')
  return {
    ...actual,
    experimentsApi: {
      getReviewQueue: vi.fn(),
      bulkPatchNotes: vi.fn(() => Promise.resolve({ count: 2, ids: [1, 2] })),
      bulkDeleteNotes: vi.fn(() => Promise.resolve({ count: 1, ids: [3] })),
    },
  }
})

import { NotesReviewPage } from '../NotesReview'
import { experimentsApi } from '@/api/experiments'

function item(p: Partial<ReviewNoteItem> & { id: number; note_text: string; experiment_id: string }): ReviewNoteItem {
  return {
    note_type: 'observation', result_id: null, created_by: 'reclassify_notes_020', needs_review: true,
    created_at: '2026-09-08T12:00:00Z', updated_at: null, experiment_fk: 1, researcher: 'MH',
    time_post_reaction_days: null, ...p,
  }
}

const ITEMS: ReviewNoteItem[] = [
  item({ id: 1, note_text: 't=0', experiment_id: 'SERUM_001a', result_id: 10, time_post_reaction_days: 0 }),
  item({ id: 2, note_text: 't=0', experiment_id: 'SERUM_001b', result_id: 11, time_post_reaction_days: 0 }),
  item({ id: 3, note_text: 'End of exp.', experiment_id: 'HPHT_040', researcher: 'JW' }),
]

const RESPONSE: ReviewQueueResponse = {
  items: ITEMS, total: 3, skip: 0, limit: 500,
  distinct_texts: [{ text: 't=0', count: 2 }, { text: 'End of exp.', count: 1 }],
}

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ToastProvider><NotesReviewPage /></ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.mocked(experimentsApi.getReviewQueue).mockReset()
  vi.mocked(experimentsApi.getReviewQueue).mockResolvedValue(RESPONSE)
  vi.mocked(experimentsApi.bulkPatchNotes).mockClear()
  vi.mocked(experimentsApi.bulkDeleteNotes).mockClear()
})

describe('NotesReviewPage', () => {
  it('renders rows with experiment links, T+day and type badges, fetching 500 at a time', async () => {
    wrap()
    await waitFor(() => expect(screen.getByRole('link', { name: 'SERUM_001a' })).toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'SERUM_001a' })).toHaveAttribute('href', '/experiments/SERUM_001a')
    expect(screen.getAllByText('T+0')).toHaveLength(2)
    expect(screen.getAllByText('Observation').length).toBeGreaterThanOrEqual(3)
    expect(screen.getByText(/3 open/)).toBeInTheDocument()
    expect(experimentsApi.getReviewQueue).toHaveBeenCalledWith(expect.objectContaining({ limit: 500, skip: 0 }))
  })

  it('selecting rows and confirming Mark reviewed calls the bulk API with those ids', async () => {
    const user = userEvent.setup()
    wrap()
    await screen.findByRole('link', { name: 'SERUM_001a' })
    await user.click(screen.getByRole('checkbox', { name: /select note 1/i }))
    await user.click(screen.getByRole('checkbox', { name: /select note 2/i }))
    expect(screen.getByText('2 selected')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /mark reviewed/i }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/2 notes/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: /^mark reviewed$/i }))
    await waitFor(() =>
      expect(experimentsApi.bulkPatchNotes).toHaveBeenCalledWith({ ids: [1, 2], needs_review: false }),
    )
    await waitFor(() => expect(screen.queryByText('2 selected')).not.toBeInTheDocument())
    await waitFor(() => expect(experimentsApi.getReviewQueue).toHaveBeenCalledTimes(2))
  })

  it('a bulk error keeps the modal in sync: closes it and refetches so stale ids drop out', async () => {
    const user = userEvent.setup()
    vi.mocked(experimentsApi.bulkPatchNotes).mockRejectedValueOnce(new Error('Notes not found: [2]'))
    wrap()
    await screen.findByRole('link', { name: 'SERUM_001a' })
    await user.click(screen.getByRole('checkbox', { name: /select note 1/i }))
    await user.click(screen.getByRole('checkbox', { name: /select note 2/i }))
    await user.click(screen.getByRole('button', { name: /mark reviewed/i }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: /^mark reviewed$/i }))
    await waitFor(() => expect(experimentsApi.bulkPatchNotes).toHaveBeenCalledWith({ ids: [1, 2], needs_review: false }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(experimentsApi.getReviewQueue).toHaveBeenCalledTimes(2))
  })

  it('a distinct-text chip adds every row with that text to the selection without toggling', async () => {
    const user = userEvent.setup()
    wrap()
    await screen.findByRole('link', { name: 'SERUM_001a' })
    // Pre-select note 3, which the chip does NOT match — a replace
    // implementation would drop it; a union implementation keeps it. Clicking
    // the chip twice must also stay idempotent (still 3 selected, not 5).
    await user.click(screen.getByRole('checkbox', { name: /select note 3/i }))
    await user.click(screen.getByRole('button', { name: /select all 2 reading/i }))
    await user.click(screen.getByRole('button', { name: /select all 2 reading/i }))
    expect(screen.getByText('3 selected')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /select note 1/i })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /select note 2/i })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /select note 3/i })).toBeChecked()
  })

  it('Retype sends note_type and clears the review flag', async () => {
    const user = userEvent.setup()
    wrap()
    await screen.findByRole('link', { name: 'SERUM_001a' })
    await user.click(screen.getByRole('checkbox', { name: /select all/i }))
    await user.selectOptions(screen.getByLabelText(/retype to/i), 'modification')
    await user.click(screen.getByRole('button', { name: /^retype$/i }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: /^retype$/i }))
    await waitFor(() =>
      expect(experimentsApi.bulkPatchNotes).toHaveBeenCalledWith({ ids: [1, 2, 3], note_type: 'modification', needs_review: false }),
    )
  })

  it('Delete confirms with the count then calls bulkDeleteNotes', async () => {
    const user = userEvent.setup()
    wrap()
    await screen.findByRole('link', { name: 'HPHT_040' })
    await user.click(screen.getByRole('checkbox', { name: /select note 3/i }))
    await user.click(screen.getByRole('button', { name: /^delete$/i }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/1 note/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: /^delete$/i }))
    await waitFor(() => expect(experimentsApi.bulkDeleteNotes).toHaveBeenCalledWith([3]))
  })

  it('filters are passed to the API', async () => {
    const user = userEvent.setup()
    wrap()
    await screen.findByRole('link', { name: 'SERUM_001a' })
    await user.selectOptions(screen.getByLabelText(/^type$/i), 'modification')
    await waitFor(() =>
      expect(experimentsApi.getReviewQueue).toHaveBeenLastCalledWith(expect.objectContaining({ note_type: 'modification' })),
    )
    fireEvent.change(screen.getByLabelText(/search text/i), { target: { value: 'brine' } })
    await waitFor(
      () => expect(experimentsApi.getReviewQueue).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'brine' })),
      { timeout: 2000 },
    )
  })

  it('says when the loaded set is truncated', async () => {
    vi.mocked(experimentsApi.getReviewQueue).mockResolvedValue({ ...RESPONSE, total: 1288 })
    wrap()
    await waitFor(() => expect(screen.getByText(/showing first 3 of 1288/i)).toBeInTheDocument())
  })

  it('does not show a bogus open count when the load fails', async () => {
    vi.mocked(experimentsApi.getReviewQueue).mockRejectedValue(new Error('boom'))
    wrap()
    await waitFor(() => expect(screen.getByText(/failed to load/i)).toBeInTheDocument())
    expect(screen.queryByText(/0 open/)).not.toBeInTheDocument()
  })

  it('a blank-text chip gets a readable title instead of a mangled empty-string replace', async () => {
    const blankItem = item({ id: 4, note_text: '', experiment_id: 'HPHT_041' })
    vi.mocked(experimentsApi.getReviewQueue).mockResolvedValue({
      items: [blankItem],
      total: 1,
      skip: 0,
      limit: 500,
      distinct_texts: [{ text: '', count: 1 }],
    })
    wrap()
    await screen.findByRole('link', { name: 'HPHT_041' })
    expect(screen.getByRole('button', { name: /select all 1 reading/i })).toHaveAttribute(
      'title',
      'Select all 1 reading "(blank)"',
    )
  })
})
