// frontend/src/pages/SampleDetail/OverviewTab.tsx
import { useState } from 'react'
import { useQueryClient, useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { samplesApi, type SampleDetail } from '@/api/samples'

interface Props { sample: SampleDetail }

export function OverviewTab({ sample }: Props) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({
    rock_classification: sample.rock_classification ?? '',
    locality: sample.locality ?? '',
    state: sample.state ?? '',
    country: sample.country ?? '',
    latitude: sample.latitude?.toString() ?? '',
    longitude: sample.longitude?.toString() ?? '',
    description: sample.description ?? '',
  })

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  const saveMutation = useMutation({
    mutationFn: () => samplesApi.patch(sample.sample_id, {
      ...(form.rock_classification !== (sample.rock_classification ?? '') && { rock_classification: form.rock_classification || undefined }),
      ...(form.locality !== (sample.locality ?? '') && { locality: form.locality || undefined }),
      ...(form.state !== (sample.state ?? '') && { state: form.state || undefined }),
      ...(form.country !== (sample.country ?? '') && { country: form.country || undefined }),
      ...(form.latitude && { latitude: parseFloat(form.latitude) }),
      ...(form.longitude && { longitude: parseFloat(form.longitude) }),
      ...(form.description !== (sample.description ?? '') && { description: form.description || undefined }),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sample', sample.sample_id] })
      setEditing(false)
    },
  })

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-surface-border bg-surface-raised p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-ink-primary">Sample Details</span>
          {!editing && (
            <button onClick={() => setEditing(true)} className="text-xs text-ink-muted hover:text-ink-primary">
              Edit
            </button>
          )}
        </div>
        {!editing ? (
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            {[
              ['Rock Classification', sample.rock_classification],
              ['Locality', sample.locality],
              ['State', sample.state],
              ['Country', sample.country],
              ['Latitude', sample.latitude?.toString()],
              ['Longitude', sample.longitude?.toString()],
            ].map(([label, val]) => (
              <div key={String(label)}>
                <dt className="text-xs text-ink-muted">{label}</dt>
                <dd className="text-ink-primary font-mono-data">{val ?? '—'}</dd>
              </div>
            ))}
            <div className="col-span-2">
              <dt className="text-xs text-ink-muted">Description</dt>
              <dd className="text-ink-secondary">{sample.description ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-ink-muted">Characterized</dt>
              <dd className={`text-xs font-medium ${sample.characterized ? 'text-green-400' : 'text-ink-muted'}`}>
                {sample.characterized ? 'Yes' : 'No'}
              </dd>
            </div>
          </dl>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              {(['rock_classification', 'locality', 'state', 'country'] as const).map((k) => (
                <div key={k}>
                  <label className="block text-xs font-medium text-ink-secondary mb-1 capitalize">{k.replace('_', ' ')}</label>
                  <input
                    value={form[k]}
                    onChange={set(k)}
                    className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50"
                  />
                </div>
              ))}
              {(['latitude', 'longitude'] as const).map((k) => (
                <div key={k}>
                  <label className="block text-xs font-medium text-ink-secondary mb-1 capitalize">{k}</label>
                  <input
                    type="number"
                    value={form[k]}
                    onChange={set(k)}
                    className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50"
                  />
                </div>
              ))}
            </div>
            <div>
              <label className="block text-xs font-medium text-ink-secondary mb-1">Description</label>
              <textarea
                rows={3}
                value={form.description}
                onChange={set('description')}
                className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary resize-none focus:outline-none focus:ring-1 focus:ring-brand-red/50"
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setEditing(false)} className="text-xs text-ink-muted hover:text-ink-primary px-3 py-1">Cancel</button>
              <button
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending}
                className="text-xs bg-brand-red text-white px-3 py-1 rounded hover:bg-brand-red/90 disabled:opacity-50"
              >
                {saveMutation.isPending ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        )}
      </div>

      {sample.elemental_results.length > 0 && (
        <div className="rounded-lg border border-surface-border bg-surface-raised p-4">
          <h3 className="text-sm font-medium text-ink-primary mb-3">Elemental Composition</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-ink-muted border-b border-surface-border">
                <th className="pb-2 pr-4">Analyte</th>
                <th className="pb-2 pr-4">Value</th>
                <th className="pb-2">Unit</th>
              </tr>
            </thead>
            <tbody>
              {sample.elemental_results.map((r) => (
                <tr key={r.analyte_symbol} className="border-b border-surface-border/50">
                  <td className="py-2 pr-4 font-mono-data text-ink-primary">{r.analyte_symbol}</td>
                  <td className="py-2 pr-4 font-mono-data text-ink-secondary">
                    {r.analyte_composition != null ? r.analyte_composition.toFixed(4) : '—'}
                  </td>
                  <td className="py-2 text-ink-muted">{r.unit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {sample.experiments.length > 0 && (
        <div className="rounded-lg border border-surface-border bg-surface-raised p-4">
          <h3 className="text-sm font-medium text-ink-primary mb-3">Linked Experiments</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-ink-muted border-b border-surface-border">
                <th className="pb-2 pr-4">Experiment ID</th>
                <th className="pb-2 pr-4">Type</th>
                <th className="pb-2 pr-4">Status</th>
                <th className="pb-2">Date</th>
              </tr>
            </thead>
            <tbody>
              {sample.experiments.map((e) => (
                <tr
                  key={e.experiment_id}
                  onClick={() => navigate(`/experiments/${e.experiment_id}`)}
                  className="cursor-pointer hover:bg-surface-overlay/50 border-b border-surface-border/50"
                >
                  <td className="py-2 pr-4 font-mono-data text-ink-primary">{e.experiment_id}</td>
                  <td className="py-2 pr-4 text-ink-muted">{e.experiment_type ?? '—'}</td>
                  <td className="py-2 pr-4 text-ink-muted">{e.status ?? '—'}</td>
                  <td className="py-2 text-ink-muted">{e.date ? new Date(e.date).toLocaleDateString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
