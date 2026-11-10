import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ExperimentIcp, IcpRow } from '@/api/icp'

vi.mock('@/api/experiments', () => ({
  experimentsApi: { getIcp: vi.fn() },
}))

import { experimentsApi } from '@/api/experiments'
import { IcpSection } from '../IcpSection'

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

const row = (over: Partial<IcpRow>): IcpRow => ({
  result_id: 1, experiment_id: 'SERUM_010-t1', is_variant: false,
  cumulative_time_post_reaction_days: 1, sample_date: null,
  elements: { ca: 10, cu: 2 }, ...over,
})

beforeEach(() => {
  vi.clearAllMocks()
})

describe('IcpSection (issue #143)', () => {
  it('opens collapsed with the sample count, and shows the chart when opened (issue #161)', async () => {
    const body: ExperimentIcp = {
      rows: [
        row({ result_id: 1, experiment_id: 'SERUM_010-t1' }),
        row({ result_id: 2, experiment_id: 'SERUM_010-t3', cumulative_time_post_reaction_days: 3 }),
      ],
      segment_starts: [],
    }
    vi.mocked(experimentsApi.getIcp).mockResolvedValue(body)
    wrap(<IcpSection experimentId="SERUM_010-t3" />)
    const toggle = await screen.findByRole('button', { name: /^ICP over time/ })
    expect(experimentsApi.getIcp).toHaveBeenCalledWith('SERUM_010-t3')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(toggle).toHaveTextContent('2 samples · 2 experiments in series')
    expect(screen.queryByRole('button', { name: 'All' })).not.toBeInTheDocument()
    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('button', { name: 'All' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Log scale' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ca' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Cu' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('renders nothing when the series has no ICP data', async () => {
    vi.mocked(experimentsApi.getIcp).mockResolvedValue({ rows: [], segment_starts: [] })
    const { container } = wrap(<IcpSection experimentId="HPHT_001" />)
    await waitFor(() => expect(experimentsApi.getIcp).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when the request fails', async () => {
    vi.mocked(experimentsApi.getIcp).mockRejectedValue(new Error('boom'))
    const { container } = wrap(<IcpSection experimentId="HPHT_001" />)
    await waitFor(() => expect(experimentsApi.getIcp).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })
})
