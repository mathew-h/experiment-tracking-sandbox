import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import type { ReactorCardData } from '@/api/dashboard'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    patchStatus: vi.fn(),
    patch: vi.fn(),
    addNote: vi.fn(() => Promise.resolve({})),
  },
}))

import { ReactorGrid, runPagePath } from '../ReactorGrid'
import { experimentsApi } from '@/api/experiments'

function makeCard(overrides: Partial<ReactorCardData> = {}): ReactorCardData {
  return {
    reactor_number: 5,
    reactor_label: 'R05',
    experiment_id: 'HPHT_MH_072',
    experiment_db_id: 142,
    base_experiment_id: 'HPHT_MH_072',
    status: 'ONGOING',
    experiment_type: 'HPHT',
    sample_id: null,
    description: null,
    researcher: null,
    started_at: null,
    days_running: 3,
    temperature_c: 200,
    volume_mL: null,
    material: null,
    vendor: null,
    todays_modification: null,
    latest_modification: null,
    last_sampled_date: null,
    cumulative_h2_grams_per_ton: null,
    ...overrides,
  }
}

function tree(cards: ReactorCardData[], rSlotCount = 16, cfSlotCount = 3) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <ReactorGrid cards={cards} rSlotCount={rSlotCount} cfSlotCount={cfSlotCount} />
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>
  )
}

function renderGrid(cards: ReactorCardData[], rSlotCount = 16, cfSlotCount = 3) {
  return render(tree(cards, rSlotCount, cfSlotCount))
}

describe('ReactorCard — todays_modification (issue #72)', () => {
  it('renders the modification text with the "Modified today:" label when set', () => {
    renderGrid([makeCard({ todays_modification: 'Swapped stir shaft' })])
    expect(screen.getByText('Modified today:')).toBeInTheDocument()
    expect(screen.getByText(/Swapped stir shaft/)).toBeInTheDocument()
  })

  it('renders no modification block when todays_modification is null', () => {
    renderGrid([makeCard({ todays_modification: null })])
    expect(screen.queryByText('Modified today:')).toBeNull()
  })

  it('exposes the full text via the title attribute for hover', () => {
    const long =
      'A very long modification text that will be line-clamped on the card face but fully visible on hover'
    renderGrid([makeCard({ todays_modification: long })])
    const block = screen.getByTitle(long)
    expect(block).toHaveTextContent('Modified today:')
  })
})

describe('ReactorGrid — slot counts derived from props (issue #85)', () => {
  it('renders 19 slots (16 R + 3 CF) and includes CF03', () => {
    const { container } = renderGrid([])
    const labels = Array.from(container.querySelectorAll('[data-testid="reactor-slot-label"]')).map(
      (el) => el.textContent
    )
    expect(labels.length).toBe(19)
    expect(labels).toContain('CF03')
    expect(labels).toContain('R16')
  })

  it('renders a different total when rSlotCount/cfSlotCount props change', () => {
    const { container } = renderGrid([], 2, 1)
    const labels = Array.from(container.querySelectorAll('[data-testid="reactor-slot-label"]')).map(
      (el) => el.textContent
    )
    expect(labels.length).toBe(3)
    expect(labels).toEqual(['R01', 'R02', 'CF01'])
  })
})

describe('StatusBadge — reactor occupancy 409 (issue #97)', () => {
  it('shows the server message when a status change is rejected as a double-booking', async () => {
    const detail =
      "Reactor R05 is already occupied by ONGOING experiment 'HPHT_222' (started 2026-07-24). Complete or cancel it before starting 'HPHT_MH_072'."
    // The axios response interceptor (frontend/src/api/client.ts) already copies
    // response.data.detail onto error.message by the time onError sees it, so a
    // faithful mock sets .message to the detail itself, not the generic Axios
    // "Request failed with status code 409" text (which never reaches onError
    // in real usage).
    vi.mocked(experimentsApi.patchStatus).mockRejectedValueOnce(
      Object.assign(new Error(detail), {
        response: { status: 409, data: { detail } },
      })
    )

    renderGrid([makeCard({ status: 'QUEUED' })])

    fireEvent.click(screen.getByTitle('Change status'))
    fireEvent.click(screen.getByRole('button', { name: 'ONGOING' }))

    await waitFor(() =>
      expect(
        screen.getByText(/already occupied by ONGOING experiment 'HPHT_222'/)
      ).toBeInTheDocument()
    )
  })

  it('shows an intelligible toast for a real network failure (no response)', async () => {
    // Axios never actually produces an empty .message: a genuine network/timeout
    // failure carries a non-empty default message (e.g. "Network Error"), which
    // the interceptor leaves untouched because there is no response.data.detail
    // to copy. This models that real failure mode, not a synthetic empty string.
    vi.mocked(experimentsApi.patchStatus).mockRejectedValueOnce(
      Object.assign(new Error('Network Error'), { response: undefined })
    )

    renderGrid([makeCard({ status: 'QUEUED' })])

    fireEvent.click(screen.getByTitle('Change status'))
    fireEvent.click(screen.getByRole('button', { name: 'ONGOING' }))

    await waitFor(() => expect(screen.getByText('Update failed')).toBeInTheDocument())
    expect(screen.getByText('Network Error')).toBeInTheDocument()
  })

  it('[defensive] falls back to a generic message if the error ever has no message at all', async () => {
    // Not a real Axios shape — Axios always sets a non-empty default message.
    // This only guards the `|| 'Could not update status'` fallback itself, in
    // case some future rejection path ever supplies a genuinely empty message.
    vi.mocked(experimentsApi.patchStatus).mockRejectedValueOnce(
      Object.assign(new Error(''), { response: undefined })
    )

    renderGrid([makeCard({ status: 'QUEUED' })])

    fireEvent.click(screen.getByTitle('Change status'))
    fireEvent.click(screen.getByRole('button', { name: 'ONGOING' }))

    await waitFor(() =>
      expect(screen.getByText('Could not update status')).toBeInTheDocument()
    )
  })
})

describe('ReactorCard — modification date defaults to the lab day (Mat, 2026-10-05)', () => {
  it('defaults the Modification date input to today in America/New_York, not the browser zone', () => {
    renderGrid([makeCard()])
    fireEvent.click(screen.getByText('HPHT_MH_072'))
    const date = screen.getByLabelText('Modification date') as HTMLInputElement
    const expected = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(new Date())
    expect(date.value).toBe(expected)
  })
})

describe('ReactorCard — reactor modification saves a dated note (issue #122 PR-B)', () => {
  beforeEach(() => {
    vi.mocked(experimentsApi.addNote).mockClear()
  })

  it('posts a modification note with the picked event_date and clears the textarea', async () => {
    renderGrid([makeCard()])
    fireEvent.click(screen.getByText('HPHT_MH_072'))
    const date = screen.getByLabelText('Modification date') as HTMLInputElement
    fireEvent.change(date, { target: { value: '2026-09-20' } })
    const box = screen.getByPlaceholderText(/enter a reactor modification/i) as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: '  Swapped stir shaft  ' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() =>
      expect(experimentsApi.addNote).toHaveBeenCalledWith(
        'HPHT_MH_072', 'Swapped stir shaft', { note_type: 'modification', event_date: '2026-09-20' },
      ),
    )
    await waitFor(() => expect(box.value).toBe(''))
    expect(await screen.findByText(/Modification saved for 2026-09-20/)).toBeInTheDocument()
  })

  it('Save is disabled while the textarea is blank (Review Focus 5)', () => {
    renderGrid([makeCard()])
    fireEvent.click(screen.getByText('HPHT_MH_072'))
    const box = screen.getByPlaceholderText(/enter a reactor modification/i)
    fireEvent.change(box, { target: { value: '   ' } })
    expect(screen.getByRole('button', { name: /^save$/i })).toBeDisabled()
    expect(experimentsApi.addNote).not.toHaveBeenCalled()
  })

  it('renders the latest prior modification from the card payload, not a change-request query', () => {
    renderGrid([makeCard({
      latest_modification: { note_text: 'Replaced septum', event_date: '2026-09-18', created_at: '2026-09-18T10:00:00Z' },
    })])
    fireEvent.click(screen.getByText('HPHT_MH_072'))
    expect(screen.getByText('Replaced septum')).toBeInTheDocument()
    expect(screen.getByText('Sep 18, 2026')).toBeInTheDocument()
  })

  it('an open modal shows the latest modification after the grid refreshes (no stale snapshot)', async () => {
    const first = makeCard({ latest_modification: { note_text: 'Replaced septum', event_date: '2026-09-18', created_at: '2026-09-18T10:00:00Z' } })
    const { rerender } = renderGrid([first])
    fireEvent.click(screen.getByText('HPHT_MH_072'))
    expect(screen.getByText('Replaced septum')).toBeInTheDocument()
    const refreshed = makeCard({ latest_modification: { note_text: 'Topped up catalyst', event_date: '2026-09-20', created_at: '2026-09-20T10:00:00Z' } })
    rerender(tree([refreshed]))
    expect(await screen.findByText('Topped up catalyst')).toBeInTheDocument()
    expect(screen.queryByText('Replaced septum')).toBeNull()
  })
})

describe('ReactorGrid — Parr group (issue #147)', () => {
  function renderWithParr(cards: ReactorCardData[]) {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    return render(
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>
          <ToastProvider>
            <ReactorGrid
              cards={cards}
              rSlotCount={16}
              pSlotCount={6}
              cfSlotCount={3}
              specs={{
                R03: { volume_mL: 100, material: 'Hastelloy', vendor: 'Yushen' },
                P02: { volume_mL: 75, material: 'Hastelloy', vendor: 'Parr' },
              }}
            />
          </ToastProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    )
  }
  const labelsIn = (el: HTMLElement) =>
    Array.from(el.querySelectorAll('[data-testid="reactor-slot-label"]')).map((n) => n.textContent)

  it('renders six Parr slots in their own group between HPHT and Core Flood', () => {
    const { container } = renderWithParr([])
    const groups = Array.from(container.querySelectorAll('section[data-testid^="reactor-group-"]'))
    expect(groups.map((g) => g.getAttribute('data-testid'))).toEqual([
      'reactor-group-R',
      'reactor-group-P',
      'reactor-group-CF',
    ])
    expect(labelsIn(groups[1] as HTMLElement)).toEqual(['P01', 'P02', 'P03', 'P04', 'P05', 'P06'])
    expect(labelsIn(groups[0] as HTMLElement)).toHaveLength(16)
  })

  it('places a P03 card in the Parr group, not on R03', () => {
    const { container } = renderWithParr([
      makeCard({ reactor_number: 3, reactor_label: 'P03', experiment_id: 'HPHT_PARR_1' }),
    ])
    const parr = container.querySelector('[data-testid="reactor-group-P"]') as HTMLElement
    const hpht = container.querySelector('[data-testid="reactor-group-R"]') as HTMLElement
    expect(parr.textContent).toContain('HPHT_PARR_1')
    expect(hpht.textContent).not.toContain('HPHT_PARR_1')
  })

  it('shows empty-slot specs from the payload', () => {
    const { container } = renderWithParr([])
    const parr = container.querySelector('[data-testid="reactor-group-P"]') as HTMLElement
    // Only P02 has a spec in this payload; Hastelloy can only come from it.
    expect(parr.textContent).toContain('Hastelloy')
    expect(parr.textContent).toContain('75')
  })
})

describe('runPagePath — run page link (issues #150, #157)', () => {
  it('links an ONGOING R or P card to its base ID, not its own segment ID', () => {
    expect(runPagePath(makeCard({ experiment_id: 'HPHT_297-2', base_experiment_id: 'HPHT_297' })))
      .toBe('/hpht/HPHT_297')
    expect(runPagePath(makeCard({ reactor_label: 'P03', base_experiment_id: 'HPHT_310' })))
      .toBe('/hpht/HPHT_310')
  })

  it('links CF cards to /core-floods/{base} and non-ONGOING cards to their run', () => {
    expect(runPagePath(makeCard({
      reactor_label: 'CF01', experiment_type: 'Core Flood', experiment_id: 'CF_018-3', base_experiment_id: 'CF_018',
    }))).toBe('/core-floods/CF_018')
    expect(runPagePath(makeCard({ status: 'QUEUED', base_experiment_id: 'HPHT_330' }))).toBe('/hpht/HPHT_330')
    expect(runPagePath(makeCard({ status: 'COMPLETED' }))).toBe('/hpht/HPHT_MH_072')
  })

  it('gives no link without a base ID or for an unknown slot series', () => {
    expect(runPagePath(makeCard({ base_experiment_id: null }))).toBeNull()
    expect(runPagePath(makeCard({ reactor_label: 'X01' }))).toBeNull()
  })
})

describe('reactor detail modal — leads to the run (issue #157)', () => {
  const openModal = async (card: ReactorCardData) => {
    renderGrid([card])
    fireEvent.click(screen.getByText(card.experiment_id!))
    return screen.findByRole('dialog', { name: `${card.reactor_label} ${card.experiment_id}` })
  }
  const primaries = (dialog: HTMLElement) =>
    Array.from(dialog.querySelectorAll('button')).filter((b) => b.className.includes('bg-red-500'))

  it('makes Open run page the only primary action, after Close and Open segment', async () => {
    const dialog = await openModal(makeCard({ base_experiment_id: 'HPHT_MH_072' }))
    const run = within(dialog).getByRole('button', { name: 'Open run page' })
    const segment = within(dialog).getByRole('button', { name: 'Open segment HPHT_MH_072' })
    expect(primaries(dialog)).toEqual([run])
    expect(segment).not.toHaveClass('bg-red-500')
    expect(within(dialog).queryByRole('button', { name: /view detail/i })).toBeNull()

    // Footer order: Close, Open segment, Open run page (primary last).
    const footer = run.parentElement!
    expect(Array.from(footer.querySelectorAll('button')).map((b) => b.textContent)).toEqual([
      'Close', 'Open segment HPHT_MH_072', 'Open run page',
    ])
  })

  it('offers the Core Flood run for a CF card and navigates to it', async () => {
    const card = makeCard({
      reactor_label: 'CF01', reactor_number: 1, experiment_type: 'Core Flood',
      experiment_id: 'CF_018-3', base_experiment_id: 'CF_018',
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <MemoryRouter initialEntries={['/']}>
        <QueryClientProvider client={queryClient}>
          <ToastProvider>
            <Routes>
              <Route path="/" element={<ReactorGrid cards={[card]} rSlotCount={16} cfSlotCount={3} />} />
              <Route path="/core-floods/:baseId" element={<p>core flood run page</p>} />
            </Routes>
          </ToastProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByText('CF_018-3'))
    const dialog = await screen.findByRole('dialog', { name: 'CF01 CF_018-3' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Open run page' }))
    expect(await screen.findByText('core flood run page')).toBeInTheDocument()
  })

  it('makes Open segment primary when the card has no run', async () => {
    const dialog = await openModal(makeCard({ base_experiment_id: null }))
    expect(within(dialog).queryByRole('button', { name: 'Open run page' })).toBeNull()
    expect(primaries(dialog)).toEqual([within(dialog).getByRole('button', { name: 'Open segment HPHT_MH_072' })])
  })

  it('puts the run actions above the modification note, whose Save is never primary', async () => {
    const dialog = await openModal(makeCard())
    const run = within(dialog).getByRole('button', { name: 'Open run page' })
    const heading = within(dialog).getByText('Log a reactor modification note')
    // The footer precedes the note section in document order.
    expect(run.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    const save = within(dialog).getByRole('button', { name: 'Save' })
    expect(save).not.toHaveClass('bg-red-500')
    expect(save).toBeDisabled()
    fireEvent.change(within(dialog).getByPlaceholderText('Enter a reactor modification…'), {
      target: { value: 'Swapped stir shaft' },
    })
    expect(save).toBeEnabled()
    expect(save).not.toHaveClass('bg-red-500')
    expect(primaries(dialog)).toEqual([run])
  })
})

describe('ReactorCard — experiment-first layout (issue #165)', () => {
  const header = (container: HTMLElement, label: string) => {
    const slot = Array.from(container.querySelectorAll('[data-testid="reactor-slot-label"]'))
      .find((el) => el.textContent?.trim() === label)!
    return slot.closest('[data-testid="reactor-card-header"]') as HTMLElement
  }
  const cardOf = (container: HTMLElement, label: string) => header(container, label).parentElement as HTMLElement

  it('puts slot label, experiment ID and status on one header row, ID largest', () => {
    const { container } = renderGrid([makeCard()])
    const h = header(container, 'R05')
    const [slot, id] = Array.from(h.children) as HTMLElement[]
    expect(slot).toHaveTextContent('R05')
    expect(slot).toHaveClass('text-sm', 'text-ink-muted')
    expect(id).toHaveTextContent('HPHT_MH_072')
    expect(id).toHaveClass('text-lg', 'font-bold', 'truncate')
    expect(id).toHaveAttribute('title', 'HPHT_MH_072')
    expect(within(h).getByTitle('Change status')).toBeInTheDocument()
  })

  it('no longer shows the Sample line on the card', () => {
    const { container } = renderGrid([makeCard({ sample_id: 'ROCK-7' })])
    expect(cardOf(container, 'R05')).not.toHaveTextContent('Sample:')
    expect(screen.queryByText('ROCK-7')).toBeNull()
  })

  it('shows the last sampled date as a calendar date', () => {
    const { container } = renderGrid([makeCard({ last_sampled_date: '2026-11-06' })])
    expect(within(cardOf(container, 'R05')).getByTestId('reactor-card-last-sampled'))
      .toHaveTextContent('Last sampled: Nov 6, 2026')
  })

  it('shows run H2 to date in g/t, formatted like the run tables', () => {
    const { container } = renderGrid([makeCard({ cumulative_h2_grams_per_ton: 1.234567 })])
    const metrics = within(cardOf(container, 'R05')).getByTestId('reactor-card-metrics')
    expect(metrics).toHaveTextContent('200 °C')
    expect(metrics).toHaveTextContent('Day 3')
    expect(metrics).toHaveTextContent('H₂ 1.235 g/t')
  })

  it('shows placeholders when values are missing', () => {
    const { container } = renderGrid([makeCard({ temperature_c: null, days_running: null })])
    const card = within(cardOf(container, 'R05'))
    expect(card.getByTestId('reactor-card-last-sampled')).toHaveTextContent('Last sampled: —')
    const metrics = card.getByTestId('reactor-card-metrics')
    expect(metrics).toHaveTextContent('— °C')
    expect(metrics).toHaveTextContent('Day —')
    expect(metrics).toHaveTextContent('H₂ — g/t')
  })

  it('gives empty slots the same rows, with placeholders', () => {
    const { container } = renderGrid([])
    const card = cardOf(container, 'R01')
    expect(card).toHaveTextContent('No experiment assigned')
    expect(card).toHaveTextContent('Empty')
    expect(within(card).getByTestId('reactor-card-last-sampled')).toHaveTextContent('Last sampled: —')
    expect(within(card).getByTestId('reactor-card-metrics')).toHaveTextContent('H₂ — g/t')
  })

  it('lays the groups out R 4 wide, P 3 wide and CF 3 wide', () => {
    const queryClient = new QueryClient()
    const { container } = render(
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>
          <ToastProvider>
            <ReactorGrid cards={[]} rSlotCount={16} pSlotCount={6} cfSlotCount={3} />
          </ToastProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    )
    const grid = (k: string) => container.querySelector(`[data-testid="reactor-grid-${k}"]`)!
    expect(grid('R')).toHaveClass('grid-cols-1', 'sm:grid-cols-2', 'lg:grid-cols-4')
    expect(grid('P')).toHaveClass('grid-cols-1', 'sm:grid-cols-2', 'lg:grid-cols-3')
    expect(grid('CF')).toHaveClass('grid-cols-1', 'sm:grid-cols-3')
  })
})
