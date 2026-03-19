import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { chemicalsApi } from '@/api/chemicals'
import { Input, Select, Button } from '@/components/ui'

const AMOUNT_UNITS = ['g', 'mg', 'mL', 'mM', 'ppm', '% of Rock', 'wt%', 'mol', 'mmol']
  .map((u) => ({ value: u, label: u }))

export interface AdditiveRow {
  compound_id: number | null
  compound_name: string
  amount: string
  unit: string
}

interface Props {
  rows: AdditiveRow[]
  onChange: (rows: AdditiveRow[]) => void
  onBack: () => void
  onNext: () => void
}

export function Step3Additives({ rows, onChange, onBack, onNext }: Props) {
  const [compoundSearch, setCompoundSearch] = useState('')

  const { data: compounds } = useQuery({
    queryKey: ['compounds', compoundSearch],
    queryFn: () => chemicalsApi.listCompounds({ search: compoundSearch, limit: 50 }),
    enabled: compoundSearch.length >= 1,
  })

  const addRow = () => onChange([...rows, { compound_id: null, compound_name: '', amount: '', unit: 'g' }])
  const removeRow = (i: number) => onChange(rows.filter((_, idx) => idx !== i))
  const patchRow = (i: number, patch: Partial<AdditiveRow>) =>
    onChange(rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))

  return (
    <div className="space-y-3">
      <p className="text-xs text-ink-muted">Add chemical additives. Leave empty if none.</p>

      <div className="w-72">
        <Input
          placeholder="Search compounds…"
          value={compoundSearch}
          onChange={(e) => setCompoundSearch(e.target.value)}
        />
      </div>

      {rows.map((row, i) => (
        <div key={i} className="flex items-end gap-2 p-3 bg-surface-raised rounded">
          <div className="flex-1">
            <label className="block text-xs font-medium text-ink-secondary mb-1">Chemical</label>
            <select
              className="w-full bg-surface-input border border-surface-border rounded px-2 py-1.5 text-sm text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50"
              value={row.compound_id ?? ''}
              onChange={(e) => {
                const opt = compounds?.find((c) => c.id === parseInt(e.target.value))
                patchRow(i, { compound_id: opt?.id ?? null, compound_name: opt?.name ?? '' })
              }}
            >
              <option value="">Select compound…</option>
              {compounds?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div className="w-28">
            <Input
              label="Amount"
              type="number"
              value={row.amount}
              onChange={(e) => patchRow(i, { amount: e.target.value })}
            />
          </div>
          <div className="w-28">
            <Select
              label="Unit"
              options={AMOUNT_UNITS}
              value={row.unit}
              onChange={(e) => patchRow(i, { unit: e.target.value })}
            />
          </div>
          <button
            onClick={() => removeRow(i)}
            className="mb-0.5 text-ink-muted hover:text-red-400 text-lg leading-none px-1"
          >
            ×
          </button>
        </div>
      ))}

      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={addRow}>+ Add additive</Button>
        {rows.length === 0 && <span className="text-xs text-ink-muted">No additives (valid)</span>}
      </div>

      <div className="flex justify-between pt-2">
        <Button variant="ghost" onClick={onBack}>← Back</Button>
        <Button variant="primary" onClick={onNext}>Next: Review →</Button>
      </div>
    </div>
  )
}
