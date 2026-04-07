import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    getChangeRequests: vi.fn(),
  },
}))

import { ChangeRequestsTab } from '../ChangeRequestsTab'
import { experimentsApi } from '@/api/experiments'

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('ChangeRequestsTab', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders empty state when API returns []', async () => {
    vi.mocked(experimentsApi.getChangeRequests).mockResolvedValue([])
    render(<ChangeRequestsTab experimentId="TEST_001" />, { wrapper })
    expect(await screen.findByText('No change requests tracked for this experiment.')).toBeTruthy()
  })

  it('renders entries with correct fields', async () => {
    vi.mocked(experimentsApi.getChangeRequests).mockResolvedValue([
      {
        id: 1,
        reactor_label: 'R05',
        requested_change: 'Check pressure gauge',
        notion_status: 'In Progress',
        carried_forward: true,
        sync_date: '2026-04-01',
        created_at: '2026-04-01T06:00:00Z',
      },
    ])
    render(<ChangeRequestsTab experimentId="TEST_001" />, { wrapper })
    expect(await screen.findByText('R05')).toBeTruthy()
    expect(screen.getByText('Check pressure gauge')).toBeTruthy()
    expect(screen.getByText('In Progress')).toBeTruthy()
    expect(screen.getByText('Carried Forward')).toBeTruthy()
  })

  it('does not show Carried Forward badge when false', async () => {
    vi.mocked(experimentsApi.getChangeRequests).mockResolvedValue([
      {
        id: 2,
        reactor_label: 'R07',
        requested_change: 'Sample and clean',
        notion_status: 'Completed',
        carried_forward: false,
        sync_date: '2026-04-02',
        created_at: '2026-04-02T06:00:00Z',
      },
    ])
    render(<ChangeRequestsTab experimentId="TEST_001" />, { wrapper })
    expect(await screen.findByText('Completed')).toBeTruthy()
    expect(screen.queryByText('Carried Forward')).toBeNull()
  })
})
