import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { CoreFloodRunListItem } from '@/api/coreFloods'

vi.mock('@/api/coreFloods', () => ({
  coreFloodsApi: { list: vi.fn() },
}))

import { coreFloodsApi } from '@/api/coreFloods'
import { CoreFloodListPage } from '../CoreFloodListPage'

const item = (over: Partial<CoreFloodRunListItem> = {}): CoreFloodRunListItem => ({
  base_id: 'CF_027',
  segment_count: 3,
  ongoing_experiment_ids: [],
  rig: 'CF02',
  sample_count: 5,
  first_sample_date: '2026-10-23T00:00:00',
  last_sample_date: '2026-11-03T00:00:00',
  latest_cumulative_h2_grams_per_ton: 12.3456,
  warning_count: 0,
  description: null,
  ...over,
})

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <CoreFloodListPage />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('CoreFloodListPage', () => {
  beforeEach(() => {
    vi.mocked(coreFloodsApi.list).mockReset()
    vi.mocked(coreFloodsApi.list).mockResolvedValue([item()])
  })

  it('defaults to Active and switches to All', async () => {
    renderPage()
    await waitFor(() => expect(coreFloodsApi.list).toHaveBeenCalledWith({ scope: 'active' }))
    await userEvent.click(screen.getByRole('button', { name: 'All' }))
    await waitFor(() =>
      expect(coreFloodsApi.list).toHaveBeenLastCalledWith({ scope: 'all' }),
    )
  })

  it('links runs', async () => {
    renderPage()
    expect(await screen.findByRole('link', { name: 'CF_027' })).toHaveAttribute(
      'href',
      '/core-floods/CF_027',
    )
  })

  it('shows description column and no segments, H₂ or warnings columns', async () => {
    vi.mocked(coreFloodsApi.list).mockResolvedValue([item({ description: 'Brine at 200C' })])
    renderPage()
    expect(await screen.findByText('Brine at 200C')).toBeInTheDocument()
    for (const name of ['Run', 'Description', 'Rig', 'Samples', 'Last sample', 'Status']) {
      expect(screen.getByRole('columnheader', { name })).toBeInTheDocument()
    }
    for (const name of ['Segments', 'Warnings', 'Cum. H₂ (g/t)']) {
      expect(screen.queryByRole('columnheader', { name })).not.toBeInTheDocument()
    }
  })

  it('shows Ongoing status for runs with an ongoing segment', async () => {
    vi.mocked(coreFloodsApi.list).mockResolvedValue([
      item({ base_id: 'CF_027', ongoing_experiment_ids: ['CF_027-2'] }),
      item({ base_id: 'CF_026' }),
    ])
    renderPage()
    expect(await screen.findByText('Ongoing')).toBeInTheDocument()
    expect(screen.getByText('Completed')).toBeInTheDocument()
  })

  it('shows an empty state', async () => {
    vi.mocked(coreFloodsApi.list).mockResolvedValue([])
    renderPage()
    expect(await screen.findByText('No active core floods')).toBeInTheDocument()
  })
})
