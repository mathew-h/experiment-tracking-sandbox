import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    list: vi.fn(),
    patchStatus: vi.fn(),
  },
}))

import { ExperimentListPage } from '../ExperimentList'
import { experimentsApi } from '@/api/experiments'
import type { ExperimentListItem } from '@/api/experiments'

const TOTAL = 80
const LIMIT = 25

function makeItems(skip: number, limit: number): ExperimentListItem[] {
  const count = Math.min(limit, Math.max(0, TOTAL - skip))
  return Array.from({ length: count }, (_, i) => ({
    id: skip + i + 1,
    experiment_id: `EXP_${String(skip + i + 1).padStart(3, '0')}`,
    experiment_number: skip + i + 1,
    status: 'ONGOING' as const,
    researcher: null,
    date: null,
    sample_id: null,
    created_at: '2026-01-01T00:00:00Z',
    experiment_type: null,
    reactor_number: null,
    additives_summary: null,
    condition_note: null,
  }))
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: 0 },
    mutations: { retry: false },
  },
})

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  queryClient.clear()
})

describe('ExperimentListPage — pagination reset on filter', () => {
  beforeEach(() => {
    vi.mocked(experimentsApi.list).mockImplementation(async (params) => {
      const skip = params?.skip ?? 0
      const limit = params?.limit ?? LIMIT
      return { items: makeItems(skip, limit), total: TOTAL, skip, limit }
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('resets to page 1 when status filter is applied on page 2', async () => {
    render(<ExperimentListPage />, { wrapper })

    // Wait for initial page 1 load
    await waitFor(() => expect(screen.getByText('Page 1 of 4')).toBeInTheDocument())

    // Navigate to page 2
    fireEvent.click(screen.getByRole('button', { name: '→' }))
    await waitFor(() => expect(screen.getByText('Page 2 of 4')).toBeInTheDocument())

    // Apply status filter
    const statusSelect = screen.getByRole('combobox', { name: /status filter/i })
    fireEvent.change(statusSelect, { target: { value: 'COMPLETED' } })

    // Verify reset to page 1 and API called with skip=0
    await waitFor(() => expect(screen.getByText(/Page 1 of/)).toBeInTheDocument())
    const lastCall = vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]
    expect(lastCall?.skip).toBe(0)
    expect(lastCall?.status).toBe('COMPLETED')
  })

  it('resets to page 1 when experiment ID text filter is typed on page 2', async () => {
    const user = userEvent.setup()
    render(<ExperimentListPage />, { wrapper })

    // Wait for initial load and navigate to page 2
    await waitFor(() => expect(screen.getByText('Page 1 of 4')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '→' }))
    await waitFor(() => expect(screen.getByText('Page 2 of 4')).toBeInTheDocument())

    // Type in the experiment ID filter
    const idInput = screen.getByPlaceholderText('Experiment ID…')
    await user.type(idInput, 'HP')

    // After typing, must be back on page 1 and API called with skip=0
    await waitFor(() => expect(screen.getByText(/Page 1 of/)).toBeInTheDocument())
    const lastCall = vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]
    expect(lastCall?.skip).toBe(0)
    expect(lastCall?.search).toBe('HP')
  })

  it('resets to page 1 when filters are cleared', async () => {
    render(<ExperimentListPage />, { wrapper })

    await waitFor(() => expect(screen.getByText('Page 1 of 4')).toBeInTheDocument())

    // Apply a filter (lands on page 1)
    const statusSelect = screen.getByRole('combobox', { name: /status filter/i })
    fireEvent.change(statusSelect, { target: { value: 'ONGOING' } })
    await waitFor(() => expect(screen.getByText(/Page 1 of/)).toBeInTheDocument())

    // Navigate to page 2 within the filtered set
    fireEvent.click(screen.getByRole('button', { name: '→' }))
    await waitFor(() => expect(screen.getByText('Page 2 of 4')).toBeInTheDocument())

    // Clear filters
    const clearButton = screen.getByRole('button', { name: /clear/i })
    fireEvent.click(clearButton)

    // Must reset to page 1 and API called with skip=0 and no status filter
    await waitFor(() => expect(screen.getByText(/Page 1 of/)).toBeInTheDocument())
    const lastCall = vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]
    expect(lastCall?.skip).toBe(0)
    expect(lastCall?.status).toBeUndefined()
  })

  it('resets to page 1 when page size is changed on page 2', async () => {
    render(<ExperimentListPage />, { wrapper })

    await waitFor(() => expect(screen.getByText('Page 1 of 4')).toBeInTheDocument())

    // Navigate to page 2
    fireEvent.click(screen.getByRole('button', { name: '→' }))
    await waitFor(() => expect(screen.getByText('Page 2 of 4')).toBeInTheDocument())

    // Change page size to 50
    fireEvent.click(screen.getByRole('button', { name: '50' }))

    // Must reset to page 1 and API called with skip=0, limit=50
    await waitFor(() => expect(screen.getByText(/Page 1 of/)).toBeInTheDocument())
    const lastCall = vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]
    expect(lastCall?.skip).toBe(0)
    expect(lastCall?.limit).toBe(50)
  })

  it('paginates forward and backward without resetting when no filter changes', async () => {
    render(<ExperimentListPage />, { wrapper })

    await waitFor(() => expect(screen.getByText('Page 1 of 4')).toBeInTheDocument())

    // Go to page 2
    fireEvent.click(screen.getByRole('button', { name: '→' }))
    await waitFor(() => expect(screen.getByText('Page 2 of 4')).toBeInTheDocument())
    let lastCall = vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]
    expect(lastCall?.skip).toBe(25)

    // Go to page 3
    fireEvent.click(screen.getByRole('button', { name: '→' }))
    await waitFor(() => expect(screen.getByText('Page 3 of 4')).toBeInTheDocument())
    lastCall = vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]
    expect(lastCall?.skip).toBe(50)

    // Go back to page 2
    fireEvent.click(screen.getByRole('button', { name: '←' }))
    await waitFor(() => expect(screen.getByText('Page 2 of 4')).toBeInTheDocument())
    lastCall = vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]
    expect(lastCall?.skip).toBe(25)
  })
}) // closes describe block
