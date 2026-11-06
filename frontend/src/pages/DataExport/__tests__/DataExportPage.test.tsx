import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '@/components/ui'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    list: vi.fn(),
    exportSelection: vi.fn(),
  },
}))

import { DataExportPage } from '../index'
import { experimentsApi } from '@/api/experiments'
import type { ExperimentListItem } from '@/api/experiments'

function item(over: Partial<ExperimentListItem>): ExperimentListItem {
  return {
    id: 1, experiment_id: 'X', experiment_number: 1, status: 'COMPLETED',
    researcher: null, date: '2026-10-01', sample_id: null, created_at: '2026-10-01T00:00:00Z',
    experiment_type: 'HPHT', reactor_number: null, additives_summary: null, description: null,
    base_experiment_id: null, parent_experiment_fk: null, replicate_label: null,
    is_outlier: false, id_timepoint_days: null, group_display_id: null, vial_count: 1,
    ...over,
  }
}

const CF = item({ id: 1, experiment_id: 'CF_027', experiment_type: 'Core Flood' })
const HPHT = item({ id: 2, experiment_id: 'HPHT_001' })
const SERUM = item({
  id: 3, experiment_id: 'SERUM_X_001-t1', experiment_type: 'Serum',
  group_display_id: 'SERUM_X_001', vial_count: 3,
})
const ALL = [CF, HPHT, SERUM]

function page(items: ExperimentListItem[], total = items.length) {
  return { items, total, skip: 0, limit: 500 }
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <DataExportPage />
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('DataExportPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(experimentsApi.list).mockResolvedValue(page(ALL))
    vi.mocked(experimentsApi.exportSelection).mockResolvedValue('data_export_2026-11-06.xlsx')
  })

  it('lists filtered experiments with vial counts', async () => {
    renderPage()
    expect(await screen.findByText('CF_027')).toBeInTheDocument()
    expect(screen.getByText('HPHT_001')).toBeInTheDocument()
    expect(screen.getByText('SERUM_X_001 · 3 vials')).toBeInTheDocument()
    expect(experimentsApi.list).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 500, group_replicates: false }),
    )
  })

  it('passes the additive filter to the list', async () => {
    renderPage()
    await screen.findByText('CF_027')
    await userEvent.type(screen.getByLabelText('Additive'), 'nickel')
    await waitFor(() =>
      expect(experimentsApi.list).toHaveBeenCalledWith(
        expect.objectContaining({ additive: 'nickel' }),
      ),
    )
  })

  it('exports the selection with the series flag', async () => {
    renderPage()
    await userEvent.click(await screen.findByLabelText('Select CF_027'))
    await userEvent.click(screen.getByLabelText('Select SERUM_X_001'))
    await userEvent.click(screen.getByRole('button', { name: 'Export' }))
    await waitFor(() =>
      expect(experimentsApi.exportSelection).toHaveBeenCalledWith(['CF_027', 'SERUM_X_001-t1'], true),
    )
    expect(await screen.findByText('Export downloaded')).toBeInTheDocument()
  })

  it('turning off Include whole series sends false', async () => {
    renderPage()
    await userEvent.click(await screen.findByLabelText('Select HPHT_001'))
    await userEvent.click(screen.getByLabelText('Include whole series'))
    await userEvent.click(screen.getByRole('button', { name: 'Export' }))
    await waitFor(() =>
      expect(experimentsApi.exportSelection).toHaveBeenCalledWith(['HPHT_001'], false),
    )
  })

  it('select all shown selects every row', async () => {
    renderPage()
    await userEvent.click(await screen.findByLabelText('Select all shown'))
    expect(screen.getByText('3 selected')).toBeInTheDocument()
  })

  it('keeps a selection when the filter hides it', async () => {
    renderPage()
    await userEvent.click(await screen.findByLabelText('Select CF_027'))
    vi.mocked(experimentsApi.list).mockResolvedValue(page([HPHT]))
    await userEvent.type(screen.getByLabelText('Experiment ID'), 'HPHT')
    await waitFor(() => expect(screen.queryByText('CF_027')).not.toBeInTheDocument())
    expect(screen.getByText('1 selected')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Export' }))
    await waitFor(() =>
      expect(experimentsApi.exportSelection).toHaveBeenCalledWith(['CF_027'], true),
    )
  })

  it('disables Export with nothing selected and Clear selection resets', async () => {
    renderPage()
    await screen.findByText('CF_027')
    expect(screen.getByRole('button', { name: 'Export' })).toBeDisabled()
    await userEvent.click(screen.getByLabelText('Select CF_027'))
    expect(screen.getByRole('button', { name: 'Export' })).toBeEnabled()
    await userEvent.click(screen.getByRole('button', { name: 'Clear selection' }))
    expect(screen.getByRole('button', { name: 'Export' })).toBeDisabled()
  })

  it("shows the server's reason when the export is rejected", async () => {
    vi.mocked(experimentsApi.exportSelection).mockRejectedValue(
      new Error('Unknown experiment IDs: CF_027'),
    )
    renderPage()
    await userEvent.click(await screen.findByLabelText('Select CF_027'))
    await userEvent.click(screen.getByRole('button', { name: 'Export' }))
    expect(await screen.findByText('Export failed')).toBeInTheDocument()
    expect(screen.getByText('Unknown experiment IDs: CF_027')).toBeInTheDocument()
  })

  it('warns when results are truncated', async () => {
    vi.mocked(experimentsApi.list).mockResolvedValue(page(ALL, 812))
    renderPage()
    expect(
      await screen.findByText('Showing 3 of 812. Narrow your filters to see the rest.'),
    ).toBeInTheDocument()
  })
})
