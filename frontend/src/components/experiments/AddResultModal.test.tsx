import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AddResultModal } from './AddResultModal'
import * as resultsModule from '@/api/results'

// Stub response used by multiple tests
const STUB_RESULT: resultsModule.ExperimentResult = {
  id: 99,
  experiment_fk: 42,
  description: 'Test',
  time_post_reaction_days: null,
  time_post_reaction_bucket_days: null,
  cumulative_time_post_reaction_days: null,
  is_primary_timepoint_result: true,
  created_at: new Date().toISOString(),
}

function renderModal(props: Partial<React.ComponentProps<typeof AddResultModal>> = {}) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <AddResultModal
        experimentPk={42}
        experimentStringId="HPHT_001"
        open={true}
        onClose={vi.fn()}
        {...props}
      />
    </QueryClientProvider>
  )
}

describe('AddResultModal', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders title and form fields when open', () => {
    renderModal()
    expect(screen.getByText('Add Result Timepoint')).toBeInTheDocument()
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/days post-reaction/i)).toBeInTheDocument()
  })

  it('does not render when closed', () => {
    renderModal({ open: false })
    expect(screen.queryByText('Add Result Timepoint')).not.toBeInTheDocument()
  })

  it('requires description — shows error when submit clicked with empty description', async () => {
    renderModal()
    fireEvent.click(screen.getByText('Save Timepoint'))
    await waitFor(() => {
      expect(screen.getByText('Description is required')).toBeInTheDocument()
    })
  })

  it('sends experiment_fk as the INTEGER prop value — never the string experimentStringId', async () => {
    // THE CORE CONTRACT TEST.
    // experimentPk=42 (integer), experimentStringId="HPHT_001" (string).
    // The payload must send experiment_fk=42, not "HPHT_001".

    // The spy intercepts correctly because AddResultModal calls resultsApi.createResult(...)
    // through the module object reference — not a destructured local copy.
    // If the component is ever refactored to `const { createResult } = resultsApi`, this spy
    // would stop intercepting and the test would silently time out.
    const mockCreate = vi
      .spyOn(resultsModule.resultsApi, 'createResult')
      .mockResolvedValue(STUB_RESULT)

    renderModal({ experimentPk: 42, experimentStringId: 'HPHT_001' })
    fireEvent.change(screen.getByLabelText(/description/i), {
      target: { value: 'Day 7 sampling' },
    })
    fireEvent.click(screen.getByText('Save Timepoint'))

    await waitFor(() => expect(mockCreate).toHaveBeenCalledOnce())

    const payload = mockCreate.mock.calls[0][0]
    expect(payload.experiment_fk).toBe(42)               // integer ✓
    expect(typeof payload.experiment_fk).toBe('number')  // not string ✓
    expect(payload.experiment_fk).not.toBe('HPHT_001')   // not the URL string ✓
    expect(payload.description).toBe('Day 7 sampling')
  })

  it('calls onClose after successful submit', async () => {
    const onClose = vi.fn()
    vi.spyOn(resultsModule.resultsApi, 'createResult').mockResolvedValue(STUB_RESULT)

    renderModal({ onClose })
    fireEvent.change(screen.getByLabelText(/description/i), { target: { value: 'Day 1' } })
    fireEvent.click(screen.getByText('Save Timepoint'))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('shows API error message on failure', async () => {
    vi.spyOn(resultsModule.resultsApi, 'createResult').mockRejectedValue(
      new Error('Experiment with id=42 not found')
    )

    renderModal()
    fireEvent.change(screen.getByLabelText(/description/i), { target: { value: 'Bad call' } })
    fireEvent.click(screen.getByText('Save Timepoint'))

    await waitFor(() => {
      expect(screen.getByText(/experiment with id=42 not found/i)).toBeInTheDocument()
    })
  })

  it('calls onClose when Cancel is clicked (no submit)', () => {
    const onClose = vi.fn()
    renderModal({ onClose })
    fireEvent.click(screen.getByText('Cancel'))
    expect(onClose).toHaveBeenCalled()
  })

  it('validates days-post-reaction as a number when provided', async () => {
    renderModal()
    fireEvent.change(screen.getByLabelText(/description/i), { target: { value: 'Day x' } })
    // jsdom sanitises type="number" inputs and discards non-numeric values when
    // set via event.target.value normally.  We use Object.defineProperty to
    // force the string through so the React onChange handler receives it and
    // the component's isNaN() validation branch is exercised.
    // This works because fireEvent propagates e.target.value directly from the patched
    // element property, bypassing jsdom's number sanitization.
    // If jsdom behavior changes, the fallback is: install @testing-library/user-event
    // and use `await userEvent.type(daysInput, 'not-a-number')` instead.
    const daysInput = screen.getByLabelText(/days post-reaction/i)
    Object.defineProperty(daysInput, 'value', {
      writable: true,
      configurable: true,
      value: 'not-a-number',
    })
    fireEvent.change(daysInput)
    fireEvent.click(screen.getByText('Save Timepoint'))
    await waitFor(() => {
      expect(screen.getByText('Must be a number')).toBeInTheDocument()
    })
  })
})
