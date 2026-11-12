import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { HphtRunListItem } from '@/api/hpht'

vi.mock('@/api/hpht', () => ({ hphtApi: { list: vi.fn(), get: vi.fn(), icp: vi.fn() } }))

import { hphtApi } from '@/api/hpht'
import { HphtListPage } from '../HphtListPage'

const item = (over: Partial<HphtRunListItem>): HphtRunListItem => ({
  base_id: 'HPHT_297',
  description: 'Olivine, 200 °C',
  segment_count: 2,
  ongoing_experiment_ids: ['HPHT_297-2'],
  reactor_slot: 'R07',
  sample_count: 4,
  last_sample_date: '2026-09-12T00:00:00',
  latest_cumulative_h2_grams_per_ton: 0.71234,
  warning_count: 0,
  ...over,
})

function renderPage(path = '/hpht') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <HphtListPage />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('HphtListPage (issue #150)', () => {
  beforeEach(() => {
    vi.mocked(hphtApi.list).mockReset()
    vi.mocked(hphtApi.list).mockResolvedValue([
      item({}),
      item({
        base_id: 'HPHT_Synth_001', reactor_slot: null, description: null,
        latest_cumulative_h2_grams_per_ton: null,
      }),
    ])
  })

  it('defaults to Active and shows the run columns', async () => {
    renderPage()
    const link = await screen.findByRole('link', { name: 'HPHT_297' })
    expect(link).toHaveAttribute('href', '/hpht/HPHT_297')
    expect(hphtApi.list).toHaveBeenCalledWith({ scope: 'active' })
    expect(screen.getByRole('button', { name: 'Active' })).toHaveAttribute('aria-pressed', 'true')
    for (const head of ['Run', 'Description', 'Reactor', 'Samples', 'Last sample', 'Cum. H₂ (g/t)', 'Status']) {
      expect(screen.getByRole('columnheader', { name: head })).toBeInTheDocument()
    }
    expect(screen.getByText('R07')).toBeInTheDocument()
    expect(screen.getByText('0.7')).toBeInTheDocument()
    expect(screen.getAllByText('Ongoing')).toHaveLength(2)
  })

  it('shows an empty Reactor cell for a run with no slot (HPHT_Synth_001)', async () => {
    renderPage()
    const row = (await screen.findByRole('link', { name: 'HPHT_Synth_001' })).closest('tr')!
    expect(row.querySelectorAll('td')[2]).toHaveTextContent('—')
  })

  it('switches to All and passes the search', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('link', { name: 'HPHT_297' })
    await user.click(screen.getByRole('button', { name: 'All' }))
    await waitFor(() => expect(hphtApi.list).toHaveBeenLastCalledWith({ scope: 'all' }))
    await user.type(screen.getByLabelText('Search runs'), '297')
    await waitFor(() => expect(hphtApi.list).toHaveBeenLastCalledWith({ scope: 'all', q: '297' }))
  })
})
