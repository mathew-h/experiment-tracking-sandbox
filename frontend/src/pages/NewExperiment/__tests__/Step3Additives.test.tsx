// frontend/src/pages/NewExperiment/__tests__/Step3Additives.test.tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import { Step3Additives, generateId, type AdditiveRow } from '../Step3Additives'

vi.mock('@/api/chemicals', () => ({
  chemicalsApi: {
    listCompounds: vi.fn(() => Promise.resolve([])),
  },
}))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
  )
}

function makeRow(overrides: Partial<AdditiveRow> = {}): AdditiveRow {
  return { id: generateId(), compound_id: null, compound_name: '', amount: '', unit: 'g', ...overrides }
}

describe('Step3Additives validation', () => {
  it('calls onNext when all rows have compound_id', async () => {
    const onNext = vi.fn()
    const rows = [makeRow({ compound_id: 1, compound_name: 'Magnetite', amount: '5' })]
    wrap(<Step3Additives rows={rows} onChange={vi.fn()} onBack={vi.fn()} onNext={onNext} />)

    await userEvent.click(screen.getByRole('button', { name: /next/i }))

    expect(onNext).toHaveBeenCalledOnce()
  })

  it('calls onNext when rows is empty', async () => {
    const onNext = vi.fn()
    wrap(<Step3Additives rows={[]} onChange={vi.fn()} onBack={vi.fn()} onNext={onNext} />)

    await userEvent.click(screen.getByRole('button', { name: /next/i }))

    expect(onNext).toHaveBeenCalledOnce()
  })

  it('blocks onNext when a row has compound_name but no compound_id', async () => {
    const onNext = vi.fn()
    const rows = [makeRow({ compound_name: 'Unknown Stuff', amount: '5' })]
    wrap(<Step3Additives rows={rows} onChange={vi.fn()} onBack={vi.fn()} onNext={onNext} />)

    await userEvent.click(screen.getByRole('button', { name: /next/i }))

    expect(onNext).not.toHaveBeenCalled()
  })

  it('shows inline error on unresolved compound row', async () => {
    const rows = [makeRow({ compound_name: 'Unknown Stuff', amount: '5' })]
    wrap(<Step3Additives rows={rows} onChange={vi.fn()} onBack={vi.fn()} onNext={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /next/i }))

    expect(screen.getByText(/compound not found/i)).toBeInTheDocument()
  })

  it('fires an error toast when a row has unresolved compound_name', async () => {
    const rows = [makeRow({ compound_name: 'Unknown Stuff', amount: '5' })]
    wrap(<Step3Additives rows={rows} onChange={vi.fn()} onBack={vi.fn()} onNext={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /next/i }))

    await waitFor(() => {
      expect(screen.getByText(/resolve all compound names/i)).toBeInTheDocument()
    })
  })

  it('does not show inline error on a row with empty compound_name', async () => {
    const onNext = vi.fn()
    // Row with amount but no compound_name — valid (will be skipped at submission)
    const rows = [makeRow({ amount: '5' })]
    wrap(<Step3Additives rows={rows} onChange={vi.fn()} onBack={vi.fn()} onNext={onNext} />)

    await userEvent.click(screen.getByRole('button', { name: /next/i }))

    expect(onNext).toHaveBeenCalledOnce()
    expect(screen.queryByText(/compound not found/i)).not.toBeInTheDocument()
  })
})
