import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
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

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0 },
      mutations: { retry: false },
    },
  })
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  )
}
