// frontend/src/pages/SampleDetail/AnalysesTab.tsx
import { useState } from 'react'
import { useQueryClient, useMutation } from '@tanstack/react-query'
import { samplesApi, type SampleDetail, type ExternalAnalysisCreate } from '@/api/samples'

interface Props { sample: SampleDetail }

const ANALYSIS_TYPES = ['pXRF', 'XRD', 'Elemental', 'Titration', 'Magnetic Susceptibility', 'Other']

export function AnalysesTab({ sample }: Props) {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<ExternalAnalysisCreate>({ analysis_type: 'pXRF' })
  const [warnings, setWarnings] = useState<string[]>([])

  const createMutation = useMutation({
    mutationFn: () => samplesApi.createAnalysis(sample.sample_id, form),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['sample', sample.sample_id] })
      setWarnings(data.warnings)
      if (data.warnings.length === 0) setShowForm(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => samplesApi.deleteAnalysis(sample.sample_id, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sample', sample.sample_id] }),
  })

  const groups = sample.analyses.reduce<Record<string, typeof sample.analyses>>((acc, a) => {
    const t = a.analysis_type ?? 'Other'
    ;(acc[t] ??= []).push(a)
    return acc
  }, {})

  return (
    <div className="space-y-4">
      {Object.entries(groups).map(([type, items]) => (
        <div key={type} className="rounded-lg border border-surface-border bg-surface-raised p-4">
          <h3 className="text-sm font-medium text-ink-primary mb-3">{type}</h3>
          <table className="w-full text-sm">
            <tbody>
              {items.map((a) => (
                <tr key={a.id} className="border-b border-surface-border/50">
                  <td className="py-2 pr-4 text-ink-muted font-mono-data">
                    {a.pxrf_reading_no ?? a.magnetic_susceptibility ?? a.description ?? '—'}
                  </td>
                  <td className="py-2 pr-4 text-ink-muted">
                    {a.analysis_date ? new Date(a.analysis_date).toLocaleDateString() : '—'}
                  </td>
                  <td className="py-2 pr-4 text-ink-muted">{a.laboratory ?? '—'}</td>
                  <td className="py-2">
                    <button className="text-xs text-red-400 hover:text-red-300" onClick={() => deleteMutation.mutate(a.id)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {sample.analyses.length === 0 && !showForm && (
        <p className="text-sm text-ink-muted text-center py-8">No analyses recorded.</p>
      )}

      {!showForm ? (
        <button onClick={() => setShowForm(true)} className="text-xs text-ink-muted hover:text-ink-primary border border-dashed border-surface-border rounded px-4 py-2 w-full">
          + Add Analysis
        </button>
      ) : (
        <div className="rounded-lg border border-surface-border bg-surface-raised p-4 space-y-3">
          <div>
            <label className="block text-xs font-medium text-ink-secondary mb-1">Type</label>
            <select
              value={form.analysis_type}
              onChange={(e) => setForm((f) => ({ ...f, analysis_type: e.target.value }))}
              className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary focus:outline-none"
            >
              {ANALYSIS_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          {form.analysis_type === 'pXRF' && (
            <div>
              <label className="block text-xs font-medium text-ink-secondary mb-1">Reading Numbers (comma-separated)</label>
              <input
                value={form.pxrf_reading_no ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, pxrf_reading_no: e.target.value }))}
                className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary focus:outline-none"
              />
            </div>
          )}
          {form.analysis_type === 'Magnetic Susceptibility' && (
            <div>
              <label className="block text-xs font-medium text-ink-secondary mb-1">Value (×10⁻³)</label>
              <input
                value={form.magnetic_susceptibility ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, magnetic_susceptibility: e.target.value }))}
                className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary focus:outline-none"
              />
            </div>
          )}
          <div>
            <label className="block text-xs font-medium text-ink-secondary mb-1">Description</label>
            <input
              value={form.description ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary focus:outline-none"
            />
          </div>
          {warnings.length > 0 && (
            <div className="text-xs text-yellow-300 space-y-1 bg-yellow-500/10 rounded p-2">
              {warnings.map((w, i) => <p key={i}>{w}</p>)}
            </div>
          )}
          <div className="flex gap-2">
            <button onClick={() => setShowForm(false)} className="text-xs text-ink-muted hover:text-ink-primary px-3 py-1">Cancel</button>
            <button
              onClick={() => createMutation.mutate()}
              disabled={createMutation.isPending}
              className="text-xs bg-brand-red text-white px-3 py-1 rounded hover:bg-brand-red/90 disabled:opacity-50"
            >
              {createMutation.isPending ? 'Saving…' : 'Add'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
