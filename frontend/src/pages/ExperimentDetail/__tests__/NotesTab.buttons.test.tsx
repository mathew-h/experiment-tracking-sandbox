import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import { NotesTab } from '../NotesTab'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    addNote: vi.fn(),
    patchNote: vi.fn(),
    deleteNote: vi.fn(() => Promise.resolve()),
  },
}))
vi.mock('@/components/ui', async () => {
  const actual = await vi.importActual<typeof import('@/components/ui')>('@/components/ui')
  return actual
})

const sampleNotes = [
  { id: 1, note_text: 'First note', created_at: '2026-01-01T00:00:00Z', updated_at: null },
  { id: 2, note_text: 'Second note', created_at: '2026-01-02T00:00:00Z', updated_at: null },
]

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
  )
}

describe('NotesTab action buttons', () => {
  it('renders edit buttons with aria-label for each note', () => {
    wrap(<NotesTab experimentId="HPHT_001" notes={sampleNotes} />)
    const editBtns = screen.getAllByRole('button', { name: /edit note/i })
    expect(editBtns).toHaveLength(2)
  })

  it('renders delete buttons with aria-label for each note', () => {
    wrap(<NotesTab experimentId="HPHT_001" notes={sampleNotes} />)
    const deleteBtns = screen.getAllByRole('button', { name: /delete note/i })
    expect(deleteBtns).toHaveLength(2)
  })

  it('clicking delete opens confirm modal without firing mutation', async () => {
    const user = userEvent.setup()
    const { experimentsApi } = await import('@/api/experiments')
    const deleteFn = vi.fn(() => Promise.resolve({ data: undefined, status: 204, statusText: 'No Content', headers: {}, config: {} } as any))
    vi.mocked(experimentsApi.deleteNote).mockImplementation(deleteFn)

    wrap(<NotesTab experimentId="HPHT_001" notes={sampleNotes} />)

    const deleteBtn = screen.getAllByRole('button', { name: /delete note/i })[0]
    await user.click(deleteBtn)

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(deleteFn).not.toHaveBeenCalled()
  })
})
