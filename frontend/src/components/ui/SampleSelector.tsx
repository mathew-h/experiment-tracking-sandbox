import { useEffect, useId, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { samplesApi } from '@/api/samples'
import { Badge } from './Badge'

interface Props {
  value: string
  onChange: (sampleId: string) => void
  onCreateNew?: () => void
}

export function SampleSelector({ value, onChange, onCreateNew }: Props) {
  const inputId = useId()
  const [query, setQuery] = useState(value)
  const [debouncedQuery, setDebouncedQuery] = useState(value)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Debounce: wait 300 ms after the user stops typing before querying the server
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), 300)
    return () => clearTimeout(t)
  }, [query])

  const { data: samples } = useQuery({
    queryKey: ['samples-selector', debouncedQuery],
    queryFn: () => samplesApi.list({ search: debouncedQuery || undefined, limit: 30 }),
    enabled: open,
  })

  const options = samples?.items ?? []

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  useEffect(() => { setQuery(value) }, [value])

  const handleSelect = (sampleId: string) => {
    onChange(sampleId)
    setQuery(sampleId)
    setOpen(false)
  }

  const handleClear = () => {
    onChange('')
    setQuery('')
  }

  return (
    <div ref={ref} className="relative">
      <label htmlFor={inputId} className="block text-xs font-medium text-ink-secondary mb-1">
        Sample
      </label>
      {value ? (
        // Show chip when a value is selected
        <div className="flex items-center gap-2 px-3 py-2 bg-surface-input border border-surface-border rounded text-sm">
          <span className="font-mono-data text-ink-primary">{value}</span>
          <button
            onClick={handleClear}
            className="ml-auto text-ink-muted hover:text-ink-primary text-xs"
            aria-label="Clear selection"
          >
            ✕
          </button>
        </div>
      ) : (
        <input
          id={inputId}
          type="text"
          autoComplete="off"
          placeholder="Search by sample ID or locality…"
          value={query}
          onFocus={() => setOpen(true)}
          onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
          className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary placeholder-ink-muted focus:outline-none focus:ring-1 focus:ring-brand-red/50"
        />
      )}

      {open && !value && (
        <ul className="absolute z-20 mt-1 w-full max-h-56 overflow-y-auto bg-surface-raised border border-surface-border rounded shadow-lg">
          {options.map((s) => (
            <li
              key={s.sample_id}
              onMouseDown={() => handleSelect(s.sample_id)}
              className="px-3 py-2 text-sm text-ink-primary hover:bg-surface-overlay cursor-pointer flex items-center justify-between"
            >
              <span>
                <span className="font-mono-data">{s.sample_id}</span>
                {s.rock_classification && (
                  <span className="text-ink-muted ml-2">{s.rock_classification}</span>
                )}
              </span>
              <Badge variant={s.characterized ? 'success' : 'default'} className="text-xs">
                {s.characterized ? 'Char.' : 'Unch.'}
              </Badge>
            </li>
          ))}
          {onCreateNew && (
            <li
              onMouseDown={onCreateNew}
              className="px-3 py-2 text-sm text-brand-red hover:bg-surface-overlay cursor-pointer border-t border-surface-border"
            >
              + Create new sample…
            </li>
          )}
          {options.length === 0 && !onCreateNew && (
            <li className="px-3 py-2 text-sm text-ink-muted">No matches</li>
          )}
        </ul>
      )}
    </div>
  )
}
