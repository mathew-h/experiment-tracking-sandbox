import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'

vi.mock('@/api/experiments', () => ({
  experimentsApi: { exportAll: vi.fn() },
}))

import { experimentsApi } from '@/api/experiments'
import { ExportAllButton } from './ExportAllButton'

function renderButton(experimentId = 'CF_027-2') {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <ExportAllButton experimentId={experimentId} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('ExportAllButton', () => {
  beforeEach(() => {
    vi.mocked(experimentsApi.exportAll).mockReset()
  })

  it('downloads the lineage workbook and confirms with the filename', async () => {
    vi.mocked(experimentsApi.exportAll).mockResolvedValue('CF_027_export_2026-11-06.xlsx')
    renderButton()
    await userEvent.click(screen.getByRole('button', { name: 'Export all' }))
    expect(experimentsApi.exportAll).toHaveBeenCalledWith('CF_027-2')
    expect(await screen.findByText('Export downloaded')).toBeInTheDocument()
    expect(screen.getByText('CF_027_export_2026-11-06.xlsx')).toBeInTheDocument()
  })

  it('shows a loading state while the export is in flight', async () => {
    let resolve: (v: string) => void = () => {}
    vi.mocked(experimentsApi.exportAll).mockReturnValue(
      new Promise<string>((r) => { resolve = r }),
    )
    renderButton()
    await userEvent.click(screen.getByRole('button', { name: 'Export all' }))
    const busy = await screen.findByRole('button', { name: /Exporting/ })
    expect(busy).toBeDisabled()
    resolve('x.xlsx')
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Export all' })).toBeEnabled())
  })

  it('shows an error toast when the request fails', async () => {
    vi.mocked(experimentsApi.exportAll).mockRejectedValue(
      new Error('Request failed with status code 500'))
    renderButton()
    await userEvent.click(screen.getByRole('button', { name: 'Export all' }))
    expect(await screen.findByText('Export failed')).toBeInTheDocument()
    expect(screen.getByText('Request failed with status code 500')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Export all' })).toBeEnabled()
  })
})
