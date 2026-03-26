import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'

interface Props {
  /** Called when the user selects an experiment to copy from. */
  onSelect: (experimentId: string) => void
  /** Called when the toggle is cleared — parent should reset form to defaults. */
  onClear: () => void
  /** If set, shows the "copied from" badge instead of the search input. */
  copiedFrom: string | null
}

/** Debounce helper: returns the value after `delay` ms of no changes. */
function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(id)
  }, [value, delay])
  return debounced
}

/**
 * "Copy from existing" toggle for the New Experiment wizard header.
 * Opens an inline search input that queries the experiments list API
 * and populates a dropdown with matching results.
 */
export function CopyFromExisting({ onSelect, onClear, copiedFrom }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const debouncedQuery = useDebounced(query, 300)

  const { data, isFetching } = useQuery({
    queryKey: ['experiments-copy-search', debouncedQuery],
    queryFn: () => experimentsApi.list({ search: debouncedQuery, limit: 10 }),
    enabled: open && debouncedQuery.length >= 1,
    staleTime: 10_000,
  })

  const results = data?.items ?? []

  function handleToggleOpen() {
    setOpen(true)
    setQuery('')
    setDropdownOpen(false)
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  function handleClear() {
    setOpen(false)
    setQuery('')
    setDropdownOpen(false)
    onClear()
  }

  function handleSelect(experimentId: string) {
    setDropdownOpen(false)
    setOpen(false)
    setQuery('')
    onSelect(experimentId)
  }

  // If already copied, show the badge + clear button
  if (copiedFrom) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-ink-muted">Copying from:</span>
        <span className="text-xs font-mono-data text-ink-primary bg-surface-raised border border-surface-border rounded px-2 py-0.5">
          {copiedFrom}
        </span>
        <button
          type="button"
          onClick={handleClear}
          className="text-xs text-ink-muted hover:text-ink-primary underline"
        >
          Clear
        </button>
      </div>
    )
  }

  // Toggle not open — show the "Copy from existing" button
  if (!open) {
    return (
      <button
        type="button"
        onClick={handleToggleOpen}
        className="text-xs text-ink-muted hover:text-ink-primary underline"
      >
        Copy from existing experiment
      </button>
    )
  }

  // Open — show inline search + dropdown
  return (
    <div className="flex items-center gap-2">
      <div className="relative w-64">
        <input
          ref={inputRef}
          type="text"
          className="w-full bg-surface-input border border-surface-border rounded px-2 py-1 text-xs text-ink-primary placeholder-ink-muted focus:outline-none focus:ring-1 focus:ring-brand-red/50"
          placeholder="Search experiment ID…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setDropdownOpen(true)
          }}
          onFocus={() => setDropdownOpen(true)}
          onBlur={() => setTimeout(() => setDropdownOpen(false), 150)}
          autoComplete="off"
        />
        {dropdownOpen && query.length >= 1 && (
          <div className="absolute z-20 left-0 right-0 top-full mt-0.5 bg-surface-raised border border-surface-border rounded shadow-lg max-h-52 overflow-y-auto">
            {isFetching && (
              <p className="px-3 py-2 text-xs text-ink-muted">Searching…</p>
            )}
            {!isFetching && results.length === 0 && (
              <p className="px-3 py-2 text-xs text-ink-muted">No experiments found</p>
            )}
            {results.map((exp) => (
              <button
                key={exp.id}
                type="button"
                onMouseDown={() => handleSelect(exp.experiment_id)}
                className="w-full text-left px-3 py-2 hover:bg-surface-border/30 flex items-center gap-3"
              >
                <span className="text-xs font-mono-data text-ink-primary font-medium">
                  {exp.experiment_id}
                </span>
                {exp.experiment_type && (
                  <span className="text-xs text-ink-muted">{exp.experiment_type}</span>
                )}
                <span
                  className={`ml-auto text-xs ${
                    exp.status === 'ONGOING'
                      ? 'text-green-600'
                      : exp.status === 'COMPLETED'
                        ? 'text-ink-muted'
                        : 'text-red-400'
                  }`}
                >
                  {exp.status}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={handleClear}
        className="text-xs text-ink-muted hover:text-ink-primary"
      >
        ✕
      </button>
    </div>
  )
}
