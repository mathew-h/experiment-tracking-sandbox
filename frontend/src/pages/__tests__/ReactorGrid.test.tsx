import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import type { ReactorCardData } from '@/api/dashboard'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    patchStatus: vi.fn(),
    patch: vi.fn(),
    getRecentChangeRequests: vi.fn(),
    createChangeRequest: vi.fn(),
  },
}))

import { ReactorGrid } from '../ReactorGrid'
import { experimentsApi } from '@/api/experiments'

function makeCard(overrides: Partial<ReactorCardData> = {}): ReactorCardData {
  return {
    reactor_number: 5,
    reactor_label: 'R05',
    experiment_id: 'HPHT_MH_072',
    experiment_db_id: 142,
    status: 'ONGOING',
    experiment_type: 'HPHT',
    sample_id: null,
    description: null,
    researcher: null,
    started_at: null,
    days_running: 3,
    temperature_c: 200,
    volume_mL: null,
    material: null,
    vendor: null,
    todays_modification: null,
    ...overrides,
  }
}

function renderGrid(cards: ReactorCardData[], rSlotCount = 16, cfSlotCount = 3) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <ReactorGrid cards={cards} rSlotCount={rSlotCount} cfSlotCount={cfSlotCount} />
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>
  )
}

describe('ReactorCard — todays_modification (issue #72)', () => {
  it('renders the modification text with the "Modified today:" label when set', () => {
    renderGrid([makeCard({ todays_modification: 'Swapped stir shaft' })])
    expect(screen.getByText('Modified today:')).toBeInTheDocument()
    expect(screen.getByText(/Swapped stir shaft/)).toBeInTheDocument()
  })

  it('renders no modification block when todays_modification is null', () => {
    renderGrid([makeCard({ todays_modification: null })])
    expect(screen.queryByText('Modified today:')).toBeNull()
  })

  it('exposes the full text via the title attribute for hover', () => {
    const long =
      'A very long modification text that will be line-clamped on the card face but fully visible on hover'
    renderGrid([makeCard({ todays_modification: long })])
    const block = screen.getByTitle(long)
    expect(block).toHaveTextContent('Modified today:')
  })
})

describe('ReactorGrid — slot counts derived from props (issue #85)', () => {
  it('renders 19 slots (16 R + 3 CF) and includes CF03', () => {
    const { container } = renderGrid([])
    const labels = Array.from(container.querySelectorAll('p.font-mono-data.text-xl')).map(
      (el) => el.textContent
    )
    expect(labels.length).toBe(19)
    expect(labels).toContain('CF03')
    expect(labels).toContain('R16')
  })

  it('renders a different total when rSlotCount/cfSlotCount props change', () => {
    const { container } = renderGrid([], 2, 1)
    const labels = Array.from(container.querySelectorAll('p.font-mono-data.text-xl')).map(
      (el) => el.textContent
    )
    expect(labels.length).toBe(3)
    expect(labels).toEqual(['R01', 'R02', 'CF01'])
  })
})

describe('StatusBadge — reactor occupancy 409 (issue #97)', () => {
  it('shows the server message when a status change is rejected as a double-booking', async () => {
    const detail =
      "Reactor R05 is already occupied by ONGOING experiment 'HPHT_222' (started 2026-07-24). Complete or cancel it before starting 'HPHT_MH_072'."
    // The axios response interceptor (frontend/src/api/client.ts) already copies
    // response.data.detail onto error.message by the time onError sees it, so a
    // faithful mock sets .message to the detail itself, not the generic Axios
    // "Request failed with status code 409" text (which never reaches onError
    // in real usage).
    vi.mocked(experimentsApi.patchStatus).mockRejectedValueOnce(
      Object.assign(new Error(detail), {
        response: { status: 409, data: { detail } },
      })
    )

    renderGrid([makeCard({ status: 'QUEUED' })])

    fireEvent.click(screen.getByTitle('Change status'))
    fireEvent.click(screen.getByRole('button', { name: 'ONGOING' }))

    await waitFor(() =>
      expect(
        screen.getByText(/already occupied by ONGOING experiment 'HPHT_222'/)
      ).toBeInTheDocument()
    )
  })

  it('falls back to a generic message when the error carries no detail', async () => {
    // No response.data.detail means the interceptor never touches .message, so
    // an error with an empty message models the case the `|| 'Could not update
    // status'` fallback exists for.
    vi.mocked(experimentsApi.patchStatus).mockRejectedValueOnce(
      Object.assign(new Error(''), { response: undefined })
    )

    renderGrid([makeCard({ status: 'QUEUED' })])

    fireEvent.click(screen.getByTitle('Change status'))
    fireEvent.click(screen.getByRole('button', { name: 'ONGOING' }))

    await waitFor(() =>
      expect(screen.getByText('Could not update status')).toBeInTheDocument()
    )
  })
})
