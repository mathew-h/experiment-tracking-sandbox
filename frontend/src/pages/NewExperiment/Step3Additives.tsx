import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { chemicalsApi, type Compound } from '@/api/chemicals'
import { Input, Select, Button } from '@/components/ui'
import { CompoundFormModal } from '@/components/CompoundFormModal'

const AMOUNT_UNITS = ['g', 'mg', 'mL', 'μL', 'mM', 'M', 'ppm', 'mmol', 'mol', '% of Rock', 'wt%']
  .map((u) => ({ value: u, label: u }))

/** UUID v4 generator that works in non-secure (HTTP) contexts. */
export function generateId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

export interface AdditiveRow {
  id: string
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

interface RowEditorProps {
  row: AdditiveRow
  onPatch: (patch: Partial<AdditiveRow>) => void
  onRemove: () => void
}

/** Per-row compound typeahead with inline create option. */
function RowEditor({ row, onPatch, onRemove }: RowEditorProps) {
  const queryClient = useQueryClient()
  const [query, setQuery] = useState(row.compound_name)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [createInitialName, setCreateInitialName] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const { data: results = [] } = useQuery({
    queryKey: ['compounds', query],
    queryFn: () => chemicalsApi.listCompounds({ search: query, limit: 10 }),
    enabled: query.length >= 1 && dropdownOpen,
  })

  const hasExactMatch = results.some((c) => c.name.toLowerCase() === query.toLowerCase())

  const selectCompound = (compound: Compound) => {
    setQuery(compound.name)
    setDropdownOpen(false)
    onPatch({ compound_id: compound.id, compound_name: compound.name })
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(e.target.value)
    setDropdownOpen(true)
    if (!e.target.value) {
      onPatch({ compound_id: null, compound_name: '' })
    }
  }

  const openCreate = () => {
    setCreateInitialName(query)
    setDropdownOpen(false)
    setCreateOpen(true)
  }

  const handleCreated = (compound: Compound) => {
    queryClient.invalidateQueries({ queryKey: ['compounds'] })
    selectCompound(compound)
    setCreateOpen(false)
  }

  return (
    <div className="flex items-end gap-2 p-3 bg-surface-raised rounded">
      <div className="flex-1 relative">
        <label className="block text-xs font-medium text-ink-secondary mb-1">Chemical</label>
        <input
          ref={inputRef}
          className="w-full bg-surface-input border border-surface-border rounded px-2 py-1.5 text-sm text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50"
          placeholder="Search compounds…"
          value={query}
          onChange={handleInputChange}
          onFocus={() => setDropdownOpen(true)}
          onBlur={() => setTimeout(() => setDropdownOpen(false), 150)}
          autoComplete="off"
        />
        {dropdownOpen && (query.length >= 1) && (
          <div className="absolute z-10 left-0 right-0 top-full mt-0.5 bg-surface-raised border border-surface-border rounded shadow-lg max-h-48 overflow-y-auto">
            {results.map((c) => (
              <button
                key={c.id}
                type="button"
                className="w-full text-left px-3 py-1.5 text-sm text-ink-primary hover:bg-surface-border/30 flex items-center gap-2"
                onMouseDown={() => selectCompound(c)}
              >
                <span>{c.name}</span>
                {c.formula && <span className="text-xs text-ink-muted font-mono-data">{c.formula}</span>}
              </button>
            ))}
            {!hasExactMatch && query.trim().length >= 2 && (
              <button
                type="button"
                className="w-full text-left px-3 py-1.5 text-sm text-brand-red hover:bg-surface-border/30 border-t border-surface-border/50"
                onMouseDown={openCreate}
              >
                Create "{query.trim()}"
              </button>
            )}
            {results.length === 0 && query.trim().length < 2 && (
              <p className="px-3 py-2 text-xs text-ink-muted">Type to search…</p>
            )}
          </div>
        )}
      </div>

      <div className="w-28">
        <Input
          label="Amount"
          type="number"
          value={row.amount}
          onChange={(e) => onPatch({ amount: e.target.value })}
        />
      </div>
      <div className="w-28">
        <Select
          label="Unit"
          options={AMOUNT_UNITS}
          value={row.unit}
          onChange={(e) => onPatch({ unit: e.target.value })}
        />
      </div>
      <button
        onClick={onRemove}
        className="mb-0.5 text-ink-muted hover:text-red-400 text-lg leading-none px-1"
        type="button"
      >
        ×
      </button>

      <CompoundFormModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSuccess={handleCreated}
        initialName={createInitialName}
        minimal
      />
    </div>
  )
}

/** Step 3 of new experiment wizard: chemical additives table with compound typeahead picker. */
export function Step3Additives({ rows, onChange, onBack, onNext }: Props) {
  const addRow = () => onChange([...rows, { id: generateId(), compound_id: null, compound_name: '', amount: '', unit: 'g' }])

  const removeRow = (i: number) => onChange(rows.filter((_, idx) => idx !== i))

  const patchRow = (i: number, patch: Partial<AdditiveRow>) => {
    const updated = rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r))
    // Upsert semantics: if the patched compound_id already exists in another row, remove the duplicate
    if (patch.compound_id != null) {
      const newCompoundId = patch.compound_id
      const deduped = updated.filter((r, idx) => idx === i || r.compound_id !== newCompoundId)
      onChange(deduped)
    } else {
      onChange(updated)
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-ink-muted">Add chemical additives. Leave empty if none.</p>

      {rows.map((row, i) => (
        <RowEditor
          key={row.id}
          row={row}
          onPatch={(patch) => patchRow(i, patch)}
          onRemove={() => removeRow(i)}
        />
      ))}

      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={addRow} type="button">+ Add additive</Button>
        {rows.length === 0 && <span className="text-xs text-ink-muted">No additives (valid)</span>}
      </div>

      <div className="flex justify-between pt-2">
        <Button variant="ghost" onClick={onBack} type="button">← Back</Button>
        <Button variant="primary" onClick={onNext} type="button">Next: Review →</Button>
      </div>
    </div>
  )
}
