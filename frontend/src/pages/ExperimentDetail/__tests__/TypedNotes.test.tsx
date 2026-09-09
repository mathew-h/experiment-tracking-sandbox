/** Issue #118 PR3: the Results tab, Notes tab and Add Results modal read and
 *  write the typed notes model. */
import { render, screen, fireEvent, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import type { ExperimentNote, ResultWithFlags } from '@/api/experiments'
import * as experimentsApiModule from '@/api/experiments'
import * as resultsApiModule from '@/api/results'
import { ResultsTab } from '../ResultsTab'
import { NotesTab } from '../NotesTab'
import { AddResultsModal } from '../AddResultsModal'

vi.mock('@/api/experiments', async () => {
  const actual = await vi.importActual<typeof import('@/api/experiments')>('@/api/experiments')
  return {
    ...actual,
    experimentsApi: {
      getResults: vi.fn(),
      getReplicateGroup: vi.fn(() => Promise.resolve({ base_experiment_id: 'X', members: [] })),
      getGroup: vi.fn(() => Promise.reject(new Error('404'))),
      setBackgroundAmmonium: vi.fn(),
      addNote: vi.fn(() => Promise.resolve({})),
      patchNote: vi.fn(() => Promise.resolve({ data: {} })),
      deleteNote: vi.fn(() => Promise.resolve()),
    },
  }
})

vi.mock('@/api/results', () => ({
  resultsApi: {
    getScalar: vi.fn(),
    getIcp: vi.fn(),
    createResult: vi.fn(() => Promise.resolve({ id: 77 })),
    createScalar: vi.fn(() => Promise.resolve({})),
  },
}))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  )
}

function note(partial: Partial<ExperimentNote> & { id: number; note_text: string }): ExperimentNote {
  return {
    note_type: 'observation',
    result_id: null,
    created_by: null,
    needs_review: false,
    created_at: '2026-04-01T00:00:00Z',
    updated_at: null,
    ...partial,
  }
}

const baseResult: ResultWithFlags = {
  id: 1,
  experiment_fk: 10,
  time_post_reaction_days: 7,
  time_post_reaction_bucket_days: 7,
  cumulative_time_post_reaction_days: 7,
  is_primary_timepoint_result: true,
  description: 'legacy',
  created_at: '2026-04-01T00:00:00Z',
  has_scalar: false,
  has_icp: false,
  has_modification_note: false,
  notes: [],
  brine_modification_description: null,
  grams_per_ton_yield: null,
  h2_concentration: null,
  h2_grams_per_ton_yield: null,
  h2_micromoles: null,
  gross_ammonium_concentration_mM: null,
  background_ammonium_concentration_mM: null,
  final_conductivity_mS_cm: null,
  final_ph: null,
  scalar_measurement_date: null,
  ferrous_iron_yield_h2_pct: null,
  ferrous_iron_yield_nh3_pct: null,
  nmr_run_date: null,
  icp_run_date: null,
  gc_run_date: null,
  xrd_run_date: null,
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ResultsTab — typed notes', () => {
  it('shows MOD for a modification note and NOTE for any other note type', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      {
        ...baseResult,
        id: 1,
        has_modification_note: true,
        notes: [
          note({ id: 11, note_text: 'brine swapped', note_type: 'modification', result_id: 1 }),
          note({ id: 12, note_text: 'slightly cloudy', note_type: 'observation', result_id: 1 }),
        ],
      },
      { ...baseResult, id: 2, time_post_reaction_days: 14, notes: [note({ id: 13, note_text: 'only a remark', note_type: 'result_note', result_id: 2 })] },
      { ...baseResult, id: 3, time_post_reaction_days: 21 },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    const rows = await screen.findAllByText(/^T\+/)
    expect(rows).toHaveLength(3)
    expect(screen.getAllByText('MOD')).toHaveLength(1)
    // day 7 (observation) and day 14 (result_note) get NOTE; day 21 gets nothing
    expect(screen.getAllByText('NOTE')).toHaveLength(2)
  })

  it('lists every typed note with its label in the expanded row', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      {
        ...baseResult,
        has_modification_note: true,
        notes: [
          note({ id: 11, note_text: 'brine swapped', note_type: 'modification', result_id: 1 }),
          note({ id: 12, note_text: 'slightly cloudy', note_type: 'observation', result_id: 1, needs_review: true }),
        ],
      },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    fireEvent.click(await screen.findByText('T+7'))
    const panel = await screen.findByTestId('timepoint-notes')
    expect(within(panel).getByText(/brine swapped/)).toBeInTheDocument()
    expect(within(panel).getByText(/slightly cloudy/)).toBeInTheDocument()
    expect(within(panel).getByText(/· Modification/)).toBeInTheDocument()
    expect(within(panel).getByText(/· Observation/)).toBeInTheDocument()
    expect(within(panel).getByText(/needs review/)).toBeInTheDocument()
  })
})

describe('NotesTab — typed notes', () => {
  const notes = [
    note({ id: 1, note_text: 'The description', note_type: 'description' }),
    note({ id: 2, note_text: 'Queued from backfill', result_id: 5, needs_review: true, created_by: 'reclassify_notes_020' }),
    note({ id: 3, note_text: 'A plain observation' }),
  ]

  it('labels each note with its type and flags the review queue', () => {
    wrap(<NotesTab experimentId="HPHT_001" notes={notes} />)
    expect(screen.getByText('Description', { selector: 'span' })).toBeInTheDocument()
    // badges only -- the add-note <select> also has an 'Observation' option
    expect(screen.getAllByText('Observation', { selector: 'span' })).toHaveLength(2)
    expect(screen.getByText('Needs review')).toBeInTheDocument()
    expect(screen.getByText(/Review queue only \(1\)/)).toBeInTheDocument()
  })

  it('the review filter hides resolved notes', async () => {
    const user = userEvent.setup()
    wrap(<NotesTab experimentId="HPHT_001" notes={notes} />)
    await user.click(screen.getByRole('checkbox', { name: /review queue only/i }))
    expect(screen.queryByText('A plain observation')).not.toBeInTheDocument()
    expect(screen.getByText('Queued from backfill')).toBeInTheDocument()
  })

  it('Mark reviewed clears needs_review through PATCH', async () => {
    const user = userEvent.setup()
    wrap(<NotesTab experimentId="HPHT_001" notes={notes} />)
    await user.click(screen.getByRole('button', { name: /mark reviewed/i }))
    expect(experimentsApiModule.experimentsApi.patchNote).toHaveBeenCalledWith('HPHT_001', 2, { needs_review: false })
  })

  it('adding a note sends the chosen type, and a second description is not offered', async () => {
    const user = userEvent.setup()
    wrap(<NotesTab experimentId="HPHT_001" notes={notes} />)
    const select = screen.getByLabelText('Type') as HTMLSelectElement
    const descOption = within(select).getByRole('option', { name: /description/i }) as HTMLOptionElement
    expect(descOption.disabled).toBe(true)
    await user.type(screen.getByPlaceholderText(/add a note/i), 'fresh observation')
    await user.click(screen.getByRole('button', { name: /add note/i }))
    expect(experimentsApiModule.experimentsApi.addNote).toHaveBeenCalledWith(
      'HPHT_001', 'fresh observation', { note_type: 'observation' },
    )
  })
})

describe('AddResultsModal — typed note composer', () => {
  it('has no required Description field and posts each non-blank note scoped to the new result', async () => {
    const user = userEvent.setup()
    wrap(<AddResultsModal open onClose={() => {}} experimentFk={10} experimentId="HPHT_001" idTimepointDays={7} />)
    expect(screen.queryByText(/^Description/)).not.toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Note 1 type'), 'modification')
    await user.type(screen.getByLabelText('Note 1 text'), 'brine replaced with DI')
    await user.click(screen.getByRole('button', { name: /add another note/i }))
    await user.type(screen.getByLabelText('Note 2 text'), 'liquid clear')
    await user.click(screen.getByRole('button', { name: /save results/i }))

    await vi.waitFor(() => expect(resultsApiModule.resultsApi.createResult).toHaveBeenCalled())
    const payload = vi.mocked(resultsApiModule.resultsApi.createResult).mock.calls[0][0]
    expect(payload).not.toHaveProperty('description')
    expect(payload).not.toHaveProperty('brine_modification_description')
    await vi.waitFor(() => expect(experimentsApiModule.experimentsApi.addNote).toHaveBeenCalledTimes(2))
    expect(experimentsApiModule.experimentsApi.addNote).toHaveBeenCalledWith(
      'HPHT_001', 'brine replaced with DI', { note_type: 'modification', result_id: 77 },
    )
    expect(experimentsApiModule.experimentsApi.addNote).toHaveBeenCalledWith(
      'HPHT_001', 'liquid clear', { note_type: 'observation', result_id: 77 },
    )
  })

  it('a blank note row posts nothing', async () => {
    const user = userEvent.setup()
    wrap(<AddResultsModal open onClose={() => {}} experimentFk={10} experimentId="HPHT_001" idTimepointDays={7} />)
    await user.click(screen.getByRole('button', { name: /save results/i }))
    await vi.waitFor(() => expect(resultsApiModule.resultsApi.createScalar).toHaveBeenCalled())
    expect(experimentsApiModule.experimentsApi.addNote).not.toHaveBeenCalled()
  })
})
