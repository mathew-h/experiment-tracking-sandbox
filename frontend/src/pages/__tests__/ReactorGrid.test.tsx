import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
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
