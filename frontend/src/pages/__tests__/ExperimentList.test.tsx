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
    base_experiment_id: null,
    parent_experiment_fk: null,
    replicate_label: null,
    is_outlier: false,
    id_timepoint_days: null,
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

  it('resets to page 1 when description filter is typed on page 2', async () => {
    const user = userEvent.setup()
    render(<ExperimentListPage />, { wrapper })

    // Wait for initial load and navigate to page 2
    await waitFor(() => expect(screen.getByText('Page 1 of 4')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '→' }))
    await waitFor(() => expect(screen.getByText('Page 2 of 4')).toBeInTheDocument())

    // Type in the description filter
    const descInput = screen.getByPlaceholderText('Description…')
    await user.type(descInput, 'magnetite')

    // After typing, must be back on page 1 and API called with skip=0 and description passed through
    await waitFor(() => expect(screen.getByText(/Page 1 of/)).toBeInTheDocument())
    const lastCall = vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]
    expect(lastCall?.skip).toBe(0)
    expect(lastCall?.description).toBe('magnetite')
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

function makeGroupedItem(): ExperimentListItem {
  const base = {
    status: 'ONGOING' as const, researcher: null, date: null, sample_id: null,
    created_at: '2026-07-01T00:00:00Z', experiment_type: 'Serum', reactor_number: null,
    additives_summary: null, condition_note: null,
    base_experiment_id: null as string | null, parent_experiment_fk: null as number | null,
    replicate_label: null as string | null, is_outlier: false,
    id_timepoint_days: null as number | null,
  }
  return {
    ...base, id: 1, experiment_id: 'SERUM_001', experiment_number: 100,
    replicates: ['a', 'b', 'c'].map((letter, i) => ({
      ...base, id: 10 + i, experiment_id: `SERUM_001${letter}`, experiment_number: 101 + i,
      base_experiment_id: 'SERUM_001', parent_experiment_fk: 1, replicate_label: letter,
    })),
  }
}

describe('ExperimentListPage — replicate grouping', () => {
  beforeEach(() => {
    vi.mocked(experimentsApi.list).mockResolvedValue({
      items: [makeGroupedItem()], total: 1, skip: 0, limit: 25,
    })
  })
  afterEach(() => { vi.clearAllMocks() })

  it('sends group_replicates=true by default and renders the group summary', async () => {
    render(<ExperimentListPage />, { wrapper })
    await waitFor(() => expect(screen.getByText('SERUM_001')).toBeInTheDocument())
    expect(vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]?.group_replicates).toBe(true)
    expect(screen.getByText('3 replicates: a, b, c')).toBeInTheDocument()
    expect(screen.queryByText('SERUM_001a')).not.toBeInTheDocument()
  })

  it('expands a group to show child rows', async () => {
    const user = userEvent.setup()
    render(<ExperimentListPage />, { wrapper })
    await waitFor(() => expect(screen.getByText('SERUM_001')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /expand replicates/i }))
    expect(screen.getByText('SERUM_001a')).toBeInTheDocument()
    expect(screen.getByText('SERUM_001c')).toBeInTheDocument()
  })

  it('turning the toggle off sends group_replicates undefined', async () => {
    const user = userEvent.setup()
    render(<ExperimentListPage />, { wrapper })
    await waitFor(() => expect(screen.getByText('SERUM_001')).toBeInTheDocument())
    await user.click(screen.getByRole('checkbox', { name: /group replicates/i }))
    await waitFor(() => {
      expect(vi.mocked(experimentsApi.list).mock.calls.at(-1)![0]?.group_replicates).toBeUndefined()
    })
  })
})

describe('ExperimentListPage — id_timepoint_days chip', () => {
  const base = {
    status: 'ONGOING' as const, researcher: null, date: null, sample_id: null,
    created_at: '2026-07-01T00:00:00Z', experiment_type: 'Serum', reactor_number: null,
    additives_summary: null, condition_note: null,
    base_experiment_id: null as string | null, parent_experiment_fk: null as number | null,
    replicate_label: null as string | null, is_outlier: false,
  }

  afterEach(() => { vi.clearAllMocks() })

  it('renders a day chip when id_timepoint_days is set, and none when null', async () => {
    vi.mocked(experimentsApi.list).mockResolvedValue({
      items: [
        { ...base, id: 1, experiment_id: 'SERUM_001a-t7', experiment_number: 100, id_timepoint_days: 7 },
        { ...base, id: 2, experiment_id: 'SERUM_002', experiment_number: 101, id_timepoint_days: null },
      ],
      total: 2, skip: 0, limit: 25,
    })

    render(<ExperimentListPage />, { wrapper })

    await waitFor(() => expect(screen.getByText('SERUM_001a-t7')).toBeInTheDocument())
    expect(screen.getByText('day 7')).toBeInTheDocument()
    expect(screen.getByText('SERUM_002')).toBeInTheDocument()
    expect(screen.getAllByText(/^day /)).toHaveLength(1)
  })
})
