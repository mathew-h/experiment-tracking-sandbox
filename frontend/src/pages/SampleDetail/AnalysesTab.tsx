// frontend/src/pages/SampleDetail/AnalysesTab.tsx
import { useState } from 'react'
import { useQueryClient, useMutation } from '@tanstack/react-query'
import { samplesApi, type SampleDetail, type ExternalAnalysisCreate, type ExternalAnalysis } from '@/api/samples'

const PXRF_ELEMENT_LABELS: Record<string, string> = {
  fe: 'Fe', mg: 'Mg', si: 'Si', ca: 'Ca', al: 'Al',
  ni: 'Ni', cu: 'Cu', co: 'Co', mo: 'Mo', k: 'K', au: 'Au', zn: 'Zn',
}

function PXRFDataTable({ a }: { a: ExternalAnalysis }) {
  if (!a.pxrf_data) return null
  const d = a.pxrf_data
  const elements = Object.entries(PXRF_ELEMENT_LABELS).filter(
    ([key]) => d[key as keyof typeof d] != null
  )
  if (elements.length === 0) return null
  return (
    <div className="mt-2 ml-2 border-l border-surface-border/50 pl-3">
      <p className="text-xs text-ink-muted mb-1">
        Average of {d.reading_count} reading{d.reading_count !== 1 ? 's' : ''} (ppm)
      </p>
      <div className="grid grid-cols-4 gap-x-4 gap-y-1 text-xs">
        {elements.map(([key, label]) => (
          <div key={key} className="flex justify-between gap-2">
            <span className="text-ink-muted font-mono-data">{label}</span>
            <span className="text-ink-secondary font-mono-data">
              {(d[key as keyof typeof d] as number).toFixed(1)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function XRDPhaseTable({ a }: { a: ExternalAnalysis }) {
  if (!a.xrd_data || Object.keys(a.xrd_data.mineral_phases).length === 0) return null
  const phases = Object.entries(a.xrd_data.mineral_phases).sort(([, a], [, b]) => b - a)
  return (
    <div className="mt-2 ml-2 border-l border-surface-border/50 pl-3">
      <p className="text-xs text-ink-muted mb-1">Mineral phases (wt%)</p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        {phases.map(([mineral, amount]) => (
          <div key={mineral} className="flex justify-between gap-2">
            <span className="text-ink-secondary capitalize">{mineral}</span>
            <span className="text-ink-muted font-mono-data">{amount.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

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
          <div className="space-y-2">
            {items.map((a) => (
              <div key={a.id} className="border-b border-surface-border/50 pb-2">
                <div className="flex items-start justify-between text-sm">
                  <div className="flex gap-4 text-ink-muted">
                    <span className="font-mono-data">
                      {a.pxrf_reading_no ?? a.magnetic_susceptibility ?? a.description ?? '—'}
                    </span>
                    <span>{a.analysis_date ? new Date(a.analysis_date).toLocaleDateString() : '—'}</span>
                    <span>{a.laboratory ?? '—'}</span>
                  </div>
                  <button
                    className="text-xs text-red-400 hover:text-red-300 shrink-0"
                    onClick={() => deleteMutation.mutate(a.id)}
                  >
                    Delete
                  </button>
                </div>
                <PXRFDataTable a={a} />
                <XRDPhaseTable a={a} />
              </div>
            ))}
          </div>
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
