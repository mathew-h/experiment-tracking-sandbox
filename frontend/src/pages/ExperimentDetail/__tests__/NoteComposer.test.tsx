/** Issue #122 PR-C: the Notes composer writes every note type with an anchor
 *  that ck_note_scope accepts, and refuses the rest before any request. */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import type { ResultWithFlags } from '@/api/experiments'
import * as experimentsApiModule from '@/api/experiments'
import { labTodayISO } from '@/utils/labDate'
import { NoteComposer, anchorProblem, composerPayload } from '../NoteComposer'

vi.mock('@/api/experiments', async () => {
  const actual = await vi.importActual<typeof import('@/api/experiments')>('@/api/experiments')
  return { ...actual, experimentsApi: { addNote: vi.fn(() => Promise.resolve({})) } }
})

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return { ...render(<QueryClientProvider client={qc}><ToastProvider>{ui}</ToastProvider></QueryClientProvider>), qc }
}

const result = (id: number, days: number | null): ResultWithFlags => ({
  id, experiment_fk: 10, time_post_reaction_days: days, time_post_reaction_bucket_days: days,
  cumulative_time_post_reaction_days: days, is_primary_timepoint_result: true, description: 'legacy',
  created_at: '2026-04-01T00:00:00Z', has_scalar: false, has_icp: false, has_modification_note: false,
  notes: [], brine_modification_description: null, grams_per_ton_yield: null, h2_concentration: null,
  h2_grams_per_ton_yield: null, h2_micromoles: null, gross_ammonium_concentration_mM: null,
  background_ammonium_concentration_mM: null, final_conductivity_mS_cm: null, final_ph: null,
  scalar_measurement_date: null, ferrous_iron_yield_h2_pct: null, ferrous_iron_yield_nh3_pct: null,
  nmr_run_date: null, icp_run_date: null, gc_run_date: null, xrd_run_date: null,
})
const RESULTS = [result(5, 7), result(6, 14)]
const addNote = () => vi.mocked(experimentsApiModule.experimentsApi.addNote)

beforeEach(() => { vi.clearAllMocks() })

describe('anchorProblem / composerPayload (pure)', () => {
  it('mirrors ck_note_scope', () => {
    expect(anchorProblem('description', null, null)).toBeNull()
    expect(anchorProblem('description', 5, null)).toMatch(/description/i)
    expect(anchorProblem('result_note', null, null)).toMatch(/timepoint/i)
    expect(anchorProblem('result_note', 5, null)).toBeNull()
    expect(anchorProblem('modification', null, null)).toMatch(/timepoint or a date/i)
    expect(anchorProblem('modification', 5, null)).toBeNull()
    expect(anchorProblem('modification', null, '2026-10-05')).toBeNull()
    expect(anchorProblem('observation', null, null)).toBeNull()
    expect(anchorProblem('observation', 5, null)).toBeNull()
    expect(anchorProblem('observation', null, '2026-10-05')).toMatch(/modification/i)
  })

  it('sends only the anchor keys that apply', () => {
    expect(composerPayload('observation', null, null)).toEqual({ note_type: 'observation' })
    expect(composerPayload('observation', 5, null)).toEqual({ note_type: 'observation', result_id: 5 })
    expect(composerPayload('modification', null, '2026-10-05')).toEqual({ note_type: 'modification', event_date: '2026-10-05' })
    // A result-anchored modification never also sends the date (Gap call 5).
    expect(composerPayload('modification', 5, '2026-10-05')).toEqual({ note_type: 'modification', result_id: 5 })
    expect(composerPayload('description', null, null)).toEqual({ note_type: 'description' })
  })
})

describe('NoteComposer', () => {
  it('a result note cannot be sent until a timepoint is chosen, then posts result_id', async () => {
    const user = userEvent.setup()
    wrap(<NoteComposer experimentId="HPHT_001" hasDescription={false} results={RESULTS} />)
    await user.type(screen.getByPlaceholderText(/add a note/i), 'pH probe drifted')
    await user.selectOptions(screen.getByLabelText('Type'), 'result_note')
    const add = screen.getByRole('button', { name: /add note/i })
    expect(add).toBeDisabled()
    expect(screen.getByText(/needs a timepoint/i)).toBeInTheDocument()
    const tp = screen.getByLabelText('At timepoint') as HTMLSelectElement
    expect(within(tp).getAllByRole('option').map((o) => o.textContent)).toEqual(['Choose…', 'T+7', 'T+14'])
    await user.selectOptions(tp, '6')
    expect(add).toBeEnabled()
    await user.click(add)
    expect(addNote()).toHaveBeenCalledWith('HPHT_001', 'pH probe drifted', { note_type: 'result_note', result_id: 6 })
  })

  it('a modification with no timepoint defaults its date to the lab’s today and posts event_date', async () => {
    const user = userEvent.setup()
    wrap(<NoteComposer experimentId="HPHT_001" hasDescription={false} results={RESULTS} />)
    await user.type(screen.getByPlaceholderText(/add a note/i), 'swapped stir bar')
    await user.selectOptions(screen.getByLabelText('Type'), 'modification')
    const date = screen.getByLabelText('On date') as HTMLInputElement
    expect(date.value).toBe(labTodayISO())
    expect(date).toBeEnabled()
    await user.click(screen.getByRole('button', { name: /add note/i }))
    expect(addNote()).toHaveBeenCalledWith('HPHT_001', 'swapped stir bar', { note_type: 'modification', event_date: labTodayISO() })
  })

  it('choosing a timepoint for a modification clears and disables the date; the payload carries result_id only', async () => {
    const user = userEvent.setup()
    wrap(<NoteComposer experimentId="HPHT_001" hasDescription={false} results={RESULTS} />)
    await user.type(screen.getByPlaceholderText(/add a note/i), 'brine replaced')
    await user.selectOptions(screen.getByLabelText('Type'), 'modification')
    await user.selectOptions(screen.getByLabelText('At timepoint'), '5')
    const date = screen.getByLabelText('On date') as HTMLInputElement
    expect(date.value).toBe('')
    expect(date).toBeDisabled()
    await user.click(screen.getByRole('button', { name: /add note/i }))
    expect(addNote()).toHaveBeenCalledWith('HPHT_001', 'brine replaced', { note_type: 'modification', result_id: 5 })
  })

  it('switching from Modification back to Observation drops the date so no event_date is sent (Review Focus 2)', async () => {
    const user = userEvent.setup()
    wrap(<NoteComposer experimentId="HPHT_001" hasDescription={false} results={RESULTS} />)
    await user.type(screen.getByPlaceholderText(/add a note/i), 'cloudy')
    await user.selectOptions(screen.getByLabelText('Type'), 'modification')
    expect((screen.getByLabelText('On date') as HTMLInputElement).value).toBe(labTodayISO())
    await user.selectOptions(screen.getByLabelText('Type'), 'observation')
    expect(screen.queryByLabelText('On date')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /add note/i }))
    expect(addNote()).toHaveBeenCalledWith('HPHT_001', 'cloudy', { note_type: 'observation' })
  })

  it('Description hides both anchor controls and posts no anchor; it is disabled once one exists', async () => {
    const user = userEvent.setup()
    const { unmount } = wrap(<NoteComposer experimentId="HPHT_001" hasDescription={false} results={RESULTS} />)
    await user.type(screen.getByPlaceholderText(/add a note/i), 'Pyrite + Cu, 90 °C')
    await user.selectOptions(screen.getByLabelText('Type'), 'description')
    expect(screen.queryByLabelText('At timepoint')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('On date')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /add note/i }))
    expect(addNote()).toHaveBeenCalledWith('HPHT_001', 'Pyrite + Cu, 90 °C', { note_type: 'description' })
    unmount()
    wrap(<NoteComposer experimentId="HPHT_001" hasDescription results={RESULTS} />)
    const opt = within(screen.getByLabelText('Type')).getByRole('option', { name: /description/i }) as HTMLOptionElement
    expect(opt.disabled).toBe(true)
  })

  it('shows the server’s detail verbatim inline and in a toast when the POST is rejected', async () => {
    const user = userEvent.setup()
    addNote().mockRejectedValueOnce(new Error("Experiment 'HPHT_001' already has a description note."))
    wrap(<NoteComposer experimentId="HPHT_001" hasDescription={false} results={RESULTS} />)
    await user.type(screen.getByPlaceholderText(/add a note/i), 'dup')
    await user.selectOptions(screen.getByLabelText('Type'), 'description')
    await user.click(screen.getByRole('button', { name: /add note/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent("Experiment 'HPHT_001' already has a description note.")
    // The draft survives so the researcher can fix and resend.
    expect((screen.getByPlaceholderText(/add a note/i) as HTMLTextAreaElement).value).toBe('dup')
  })

  it('a successful add refreshes the experiment, its results, the experiments list and the dashboard', async () => {
    const user = userEvent.setup()
    const { qc } = wrap(<NoteComposer experimentId="HPHT_001" hasDescription={false} results={RESULTS} />)
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    await user.type(screen.getByPlaceholderText(/add a note/i), 'x')
    await user.click(screen.getByRole('button', { name: /add note/i }))
    await vi.waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['experiment', 'HPHT_001'] }))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['experiments'] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['dashboard'] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['experiment-results', 'HPHT_001'] })
    expect((screen.getByPlaceholderText(/add a note/i) as HTMLTextAreaElement).value).toBe('')
    expect((screen.getByLabelText('Type') as HTMLSelectElement).value).toBe('observation')
    expect((screen.getByLabelText('At timepoint') as HTMLSelectElement).value).toBe('')
  })
})
