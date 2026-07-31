import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import { dashboardApi } from '@/api/dashboard'
import type { DashboardData } from '@/api/dashboard'

vi.mock('@/api/dashboard', async () => {
  const actual = await vi.importActual('@/api/dashboard')
  return {
    ...actual,
    dashboardApi: { full: vi.fn(), reactorStatus: vi.fn(), timeline: vi.fn() },
  }
})
vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    patchStatus: vi.fn(),
    patch: vi.fn(),
    getRecentChangeRequests: vi.fn(),
    createChangeRequest: vi.fn(),
  },
}))

import { DashboardPage } from '../Dashboard'

function makeSummary(overrides: Partial<DashboardData['summary']> = {}): DashboardData['summary'] {
  return {
    reactors: { total: 16, ongoing: 8, queued: 4, empty: 4 },
    core_floods: { total: 3, ongoing: 1, queued: 0, empty: 2 },
    gc_measurements_7wd: 5,
    gc_experiments_7wd: 3,
    serum_vials_started_7wd: 4,
    serum_experiments_7wd: 2,
    workday_window_start: '2026-07-21',
    workday_window_end: '2026-07-29',
    ...overrides,
  }
}

function renderDashboard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <DashboardPage />
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>
  )
}

describe('DashboardPage — KPI cards (issue #85)', () => {
  it('renders the four new KPI labels', async () => {
    vi.mocked(dashboardApi.full).mockResolvedValue({
      summary: makeSummary(),
      reactors: [],
      timeline: [],
      recent_activity: [],
    })
    renderDashboard()
    // "Reactor Occupancy" (and the other 3 labels) render unconditionally, even
    // before `data` loads — waiting on a static label resolves instantly and
    // proves nothing about load state. Wait on the date-range subtitle instead,
    // which only renders once `data` is defined (see the `sub={data ? ... : undefined}`
    // ternary in Dashboard.tsx) — that's the real signal that the mocked
    // dashboardApi.full() promise has resolved and the component re-rendered.
    await waitFor(() =>
      expect(screen.getAllByText(/2026-07-21 – 2026-07-29/).length).toBeGreaterThanOrEqual(2)
    )
    expect(screen.getByText('Reactor Occupancy')).toBeInTheDocument()
    expect(screen.getByText('GC Measurements')).toBeInTheDocument()
    expect(screen.getByText('Serum Vials Started')).toBeInTheDocument()
    expect(screen.getByText('Core Floods Ongoing')).toBeInTheDocument()
  })

  it('shows em-dash placeholders and no crash while summary is undefined (loading state)', () => {
    vi.mocked(dashboardApi.full).mockReturnValue(new Promise(() => {}))
    renderDashboard()
    expect(screen.getByText('Reactor Occupancy')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('renders the reactor and core-flood tick bars with the right counts', async () => {
    vi.mocked(dashboardApi.full).mockResolvedValue({
      summary: makeSummary(),
      reactors: [],
      timeline: [],
      recent_activity: [],
    })
    const { container } = renderDashboard()
    // Bars only render once `data` is defined (`{data && <SlotBar .../>}`), so
    // waiting for exactly 2 `[role="img"]` elements to appear is itself the
    // data-loaded signal — unlike a static label, this cannot resolve early.
    await waitFor(() => expect(container.querySelectorAll('[role="img"]').length).toBe(2))
    const bars = container.querySelectorAll('[role="img"]')
    // First bar = reactors (16 total), second = core floods (3 total)
    expect(bars[0].querySelectorAll(':scope > div').length).toBe(16)
    expect(bars[1].querySelectorAll(':scope > div').length).toBe(3)
  })

  it('explains a zero GC count instead of implying an idle lab (issue #115)', async () => {
    vi.mocked(dashboardApi.full).mockResolvedValue({
      summary: makeSummary({ gc_measurements_7wd: 0, gc_experiments_7wd: 0 }),
      reactors: [],
      timeline: [],
      recent_activity: [],
    })
    renderDashboard()
    expect(
      await screen.findByText(/no GC Run Date recorded in this window/)
    ).toBeInTheDocument()
    expect(screen.queryByText(/across 0 experiments/)).not.toBeInTheDocument()
  })

  it('keeps the experiment-count subtitle when the GC count is non-zero', async () => {
    vi.mocked(dashboardApi.full).mockResolvedValue({
      summary: makeSummary({ gc_measurements_7wd: 5, gc_experiments_7wd: 3 }),
      reactors: [],
      timeline: [],
      recent_activity: [],
    })
    renderDashboard()
    expect(await screen.findByText(/across 3 experiments/)).toBeInTheDocument()
    expect(screen.queryByText(/no GC Run Date recorded/)).not.toBeInTheDocument()
  })
})
