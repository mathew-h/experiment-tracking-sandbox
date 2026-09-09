import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Modal, Button } from '@/components/ui'
import { resultsApi, type ResultCreate, type ScalarCreate } from '@/api/results'
import { experimentsApi } from '@/api/experiments'
import { NOTE_TYPE_LABELS, type NoteType } from '@/api/noteTypes'

const PSI_TO_MPA = 0.00689476

function todayIso(): string {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d.toISOString().slice(0, 10)
}

function parseOptFloat(s: string): number | null {
  if (s.trim() === '') return null
  const n = parseFloat(s)
  return isNaN(n) ? null : n
}

interface Props {
  open: boolean
  onClose: () => void
  experimentFk: number
  experimentId: string
  /** Day parsed from a -t<days> token on the experiment ID (issue #81). When set,
   *  the time field is defaulted and locked to this value for every result. */
  idTimepointDays?: number | null
}

/** Note types that make sense on a timepoint (issue #118). 'description' is
 *  experiment-level and lives on the Notes tab. */
const RESULT_NOTE_TYPES: NoteType[] = ['observation', 'modification', 'result_note']

interface NoteDraft {
  note_type: NoteType
  text: string
}

interface FormState {
  measurement_date: string
  time_post_reaction_days: string
  gross_ammonium_concentration_mM: string
  h2_concentration: string
  gas_sampling_pressure_psi: string
  gas_sampling_volume_ml: string
  final_ph: string
  final_conductivity_mS_cm: string
  notes: NoteDraft[]
}

function buildInitial(idTimepointDays?: number | null): FormState {
  return {
    measurement_date: todayIso(),
    time_post_reaction_days: idTimepointDays != null ? String(idTimepointDays) : '',
    gross_ammonium_concentration_mM: '',
    h2_concentration: '',
    gas_sampling_pressure_psi: '',
    gas_sampling_volume_ml: '',
    final_ph: '',
    final_conductivity_mS_cm: '',
    notes: [{ note_type: 'observation', text: '' }],
  }
}

function validate(f: FormState, idTimepointDays?: number | null): string | null {
  if (
    idTimepointDays != null &&
    f.time_post_reaction_days.trim() !== '' &&
    Math.abs(parseFloat(f.time_post_reaction_days) - idTimepointDays) > 0.0001
  ) {
    return `Time is locked to day ${idTimepointDays} by the experiment ID token; remove the -t token from the ID to log a different day.`
  }
  if (!f.measurement_date) return 'Measurement date is required.'
  if (f.time_post_reaction_days.trim() === '') return 'Time post reaction is required.'
  if (isNaN(parseFloat(f.time_post_reaction_days))) return 'Time post reaction must be a number.'
  for (const key of ['h2_concentration', 'gas_sampling_pressure_psi', 'gas_sampling_volume_ml'] as const) {
    const v = f[key].trim()
    if (v !== '') {
      const n = parseFloat(v)
      if (isNaN(n) || n < 0) return `${key.replace(/_/g, ' ')} must be ≥ 0.`
    }
  }
  return null
}

/** Result entry modal: POST /api/results, POST /api/results/scalar, then one
 *  POST /experiments/{id}/notes per non-blank typed note (issue #118). Nothing
 *  textual is required. */
export function AddResultsModal({ open, onClose, experimentFk, experimentId, idTimepointDays }: Props) {
  const [form, setForm] = useState<FormState>(() => buildInitial(idTimepointDays))
  const [serverError, setServerError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  // Re-sync the locked time field when the modal (re)opens or the ID timepoint
  // becomes known/changes — the modal instance can stay mounted while its
  // `experiment` data (and therefore idTimepointDays) loads or changes.
  useEffect(() => {
    if (open) {
      setForm((f) => ({
        ...f,
        time_post_reaction_days: idTimepointDays != null ? String(idTimepointDays) : f.time_post_reaction_days,
      }))
    }
  }, [open, idTimepointDays])

  function set(field: Exclude<keyof FormState, 'notes'>, value: string) {
    setForm((f) => ({ ...f, [field]: value }))
  }

  function setNote(index: number, patch: Partial<NoteDraft>) {
    setForm((f) => ({
      ...f,
      notes: f.notes.map((n, i) => (i === index ? { ...n, ...patch } : n)),
    }))
  }

  function addNoteRow() {
    setForm((f) => ({ ...f, notes: [...f.notes, { note_type: 'observation', text: '' }] }))
  }

  function removeNoteRow(index: number) {
    setForm((f) => ({
      ...f,
      notes: f.notes.length === 1 ? [{ note_type: 'observation', text: '' }] : f.notes.filter((_, i) => i !== index),
    }))
  }

  const mutation = useMutation({
    mutationFn: async (f: FormState) => {
      const resultPayload: ResultCreate = {
        experiment_fk: experimentFk,
        time_post_reaction_days: parseFloat(f.time_post_reaction_days),
        measurement_date: f.measurement_date || null,
      }
      const result = await resultsApi.createResult(resultPayload)

      const gasPressureMPa = f.gas_sampling_pressure_psi.trim()
        ? parseFloat(f.gas_sampling_pressure_psi) * PSI_TO_MPA
        : null

      const scalarPayload: ScalarCreate = {
        result_id: result.id,
        measurement_date: f.measurement_date || null,
        gross_ammonium_concentration_mM: parseOptFloat(f.gross_ammonium_concentration_mM),
        h2_concentration: parseOptFloat(f.h2_concentration),
        gas_sampling_pressure_MPa: gasPressureMPa,
        gas_sampling_volume_ml: parseOptFloat(f.gas_sampling_volume_ml),
        final_ph: parseOptFloat(f.final_ph),
        final_conductivity_mS_cm: parseOptFloat(f.final_conductivity_mS_cm),
      }
      await resultsApi.createScalar(scalarPayload)

      for (const n of f.notes) {
        const text = n.text.trim()
        if (!text) continue
        await experimentsApi.addNote(experimentId, text, { note_type: n.note_type, result_id: result.id })
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiment-results', experimentId] })
      queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] })
      setForm(buildInitial(idTimepointDays))
      setServerError(null)
      onClose()
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setServerError(detail ?? 'Failed to save results. Please try again.')
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const err = validate(form, idTimepointDays)
    if (err) { setServerError(err); return }
    setServerError(null)
    mutation.mutate(form)
  }

  function handleClose() {
    if (mutation.isPending) return
    setForm(buildInitial(idTimepointDays))
    setServerError(null)
    onClose()
  }

  const inputCls = 'w-full text-xs px-2 py-1.5 border border-surface-border rounded bg-surface-raised text-ink-primary font-mono-data focus:outline-none focus:ring-1 focus:ring-red-500'
  const labelCls = 'block text-xs text-ink-secondary mb-1'

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Add Results"
      description="Create a new timepoint result for this experiment."
      size="lg"
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={handleClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleSubmit}
            loading={mutation.isPending}
            disabled={mutation.isPending}
          >
            Save Results
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Row 1: date + time */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>Measurement date <span className="text-red-400">*</span></label>
            <input
              type="date"
              value={form.measurement_date}
              onChange={(e) => set('measurement_date', e.target.value)}
              className={inputCls}
              required
            />
          </div>
          <div>
            <label htmlFor="time_post_reaction_days" className={labelCls}>
              Time post reaction (days) <span className="text-red-400">*</span>
            </label>
            <input
              id="time_post_reaction_days"
              type="number"
              step="any"
              min="0"
              placeholder="e.g. 7"
              value={form.time_post_reaction_days}
              onChange={(e) => set('time_post_reaction_days', e.target.value)}
              className={inputCls}
              disabled={idTimepointDays != null}
              required
            />
            {idTimepointDays != null && (
              <p className="text-xs text-ink-muted">
                Locked to day {idTimepointDays} from the experiment ID (-t{idTimepointDays}).
              </p>
            )}
          </div>
        </div>

        {/* Row 2: NH4 + H2 */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>NH₄ concentration (mM)</label>
            <input
              type="number"
              step="any"
              min="0"
              placeholder="optional"
              value={form.gross_ammonium_concentration_mM}
              onChange={(e) => set('gross_ammonium_concentration_mM', e.target.value)}
              className={inputCls}
            />
          </div>
          <div>
            <label className={labelCls}>H₂ concentration (ppm)</label>
            <input
              type="number"
              step="any"
              min="0"
              placeholder="optional"
              value={form.h2_concentration}
              onChange={(e) => set('h2_concentration', e.target.value)}
              className={inputCls}
            />
          </div>
        </div>

        {/* Row 3: gas pressure + gas volume */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>
              Gas sampling pressure (PSI)
              <span className="ml-1 text-ink-muted text-[10px]">stored as MPa</span>
            </label>
            <input
              type="number"
              step="any"
              min="0"
              placeholder="optional"
              value={form.gas_sampling_pressure_psi}
              onChange={(e) => set('gas_sampling_pressure_psi', e.target.value)}
              className={inputCls}
            />
          </div>
          <div>
            <label className={labelCls}>Gas sampling volume (mL)</label>
            <input
              type="number"
              step="any"
              min="0"
              placeholder="optional"
              value={form.gas_sampling_volume_ml}
              onChange={(e) => set('gas_sampling_volume_ml', e.target.value)}
              className={inputCls}
            />
          </div>
        </div>

        {/* Row 4: pH + conductivity */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>pH</label>
            <input
              type="number"
              step="any"
              min="0"
              max="14"
              placeholder="optional"
              value={form.final_ph}
              onChange={(e) => set('final_ph', e.target.value)}
              className={inputCls}
            />
          </div>
          <div>
            <label className={labelCls}>Conductivity (mS/cm)</label>
            <input
              type="number"
              step="any"
              min="0"
              placeholder="optional"
              value={form.final_conductivity_mS_cm}
              onChange={(e) => set('final_conductivity_mS_cm', e.target.value)}
              className={inputCls}
            />
          </div>
        </div>

        {/* Notes (issue #118): typed, optional, as many as needed */}
        <div>
          <p className={labelCls}>Notes <span className="text-ink-muted text-[10px]">optional</span></p>
          <div className="space-y-2">
            {form.notes.map((n, i) => (
              <div key={i} className="flex items-start gap-2" data-testid="note-row">
                <select
                  aria-label={`Note ${i + 1} type`}
                  value={n.note_type}
                  onChange={(e) => setNote(i, { note_type: e.target.value as NoteType })}
                  className="text-xs px-2 py-1.5 border border-surface-border rounded bg-surface-raised text-ink-primary focus:outline-none focus:ring-1 focus:ring-red-500 shrink-0"
                >
                  {RESULT_NOTE_TYPES.map((t) => (
                    <option key={t} value={t}>{NOTE_TYPE_LABELS[t]}</option>
                  ))}
                </select>
                <textarea
                  aria-label={`Note ${i + 1} text`}
                  rows={2}
                  placeholder={
                    n.note_type === 'modification'
                      ? 'what was done to the vial — e.g. brine replaced with DI water'
                      : 'e.g. liquid slightly cloudy'
                  }
                  value={n.text}
                  onChange={(e) => setNote(i, { text: e.target.value })}
                  className="w-full text-xs px-2 py-1.5 border border-surface-border rounded bg-surface-raised text-ink-primary focus:outline-none focus:ring-1 focus:ring-red-500 resize-none"
                />
                <button
                  type="button"
                  aria-label={`Remove note ${i + 1}`}
                  onClick={() => removeNoteRow(i)}
                  className="p-1 text-ink-muted hover:text-red-400"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
          {/* type="button": inside the form, the default submit type would save the result on click */}
          <Button type="button" variant="ghost" size="xs" className="mt-1" onClick={addNoteRow}>
            + Add another note
          </Button>
        </div>

        {serverError && (
          <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded px-3 py-2">
            {serverError}
          </p>
        )}
      </form>
    </Modal>
  )
}
