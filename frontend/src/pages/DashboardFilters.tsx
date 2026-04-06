import { useId } from 'react'

export interface DashboardFilterState {
  statuses: string[]   // empty = all
  types: string[]      // empty = all
  dateFrom: string     // ISO date string '' = unset
  dateTo: string
}

const STATUS_OPTIONS = ['ONGOING', 'COMPLETED', 'CANCELLED', 'QUEUED']
const TYPE_OPTIONS = ['HPHT', 'Serum', 'Core Flood', 'Autoclave', 'Other']

function Chip({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'px-2.5 py-1 rounded text-xs font-medium border transition-colors',
        active
          ? 'bg-brand-red text-white border-brand-red'
          : 'text-ink-muted border-surface-border hover:border-ink-muted hover:text-ink-secondary',
      ].join(' ')}
    >
      {label}
    </button>
  )
}

/** Filter bar for the dashboard — researcher, status, and date-range selectors. */
export function DashboardFilters({
  filters,
  onChange,
}: {
  filters: DashboardFilterState
  onChange: (f: DashboardFilterState) => void
}) {
  const fromId = useId()
  const toId = useId()

  function toggleStatus(s: string) {
    const next = filters.statuses.includes(s)
      ? filters.statuses.filter((x) => x !== s)
      : [...filters.statuses, s]
    onChange({ ...filters, statuses: next })
  }

  function toggleType(t: string) {
    const next = filters.types.includes(t)
      ? filters.types.filter((x) => x !== t)
      : [...filters.types, t]
    onChange({ ...filters, types: next })
  }

  const hasFilters =
    filters.statuses.length > 0 || filters.types.length > 0 || filters.dateFrom || filters.dateTo

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      {/* Status chips */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-2xs text-ink-muted uppercase tracking-wider mr-0.5">Status</span>
        {STATUS_OPTIONS.map((s) => (
          <Chip
            key={s}
            label={s.charAt(0) + s.slice(1).toLowerCase()}
            active={filters.statuses.includes(s)}
            onClick={() => toggleStatus(s)}
          />
        ))}
      </div>

      {/* Type chips */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-2xs text-ink-muted uppercase tracking-wider mr-0.5">Type</span>
        {TYPE_OPTIONS.map((t) => (
          <Chip key={t} label={t} active={filters.types.includes(t)} onClick={() => toggleType(t)} />
        ))}
      </div>

      {/* Date range */}
      <div className="flex items-center gap-1.5">
        <label htmlFor={fromId} className="text-2xs text-ink-muted uppercase tracking-wider">
          From
        </label>
        <input
          id={fromId}
          type="date"
          value={filters.dateFrom}
          onChange={(e) => onChange({ ...filters, dateFrom: e.target.value })}
          className="text-xs bg-surface-overlay border border-surface-border rounded px-2 py-0.5 text-ink-secondary focus:outline-none focus:border-ink-muted"
        />
        <label htmlFor={toId} className="text-2xs text-ink-muted uppercase tracking-wider">
          To
        </label>
        <input
          id={toId}
          type="date"
          value={filters.dateTo}
          onChange={(e) => onChange({ ...filters, dateTo: e.target.value })}
          className="text-xs bg-surface-overlay border border-surface-border rounded px-2 py-0.5 text-ink-secondary focus:outline-none focus:border-ink-muted"
        />
      </div>

      {hasFilters && (
        <button
          type="button"
          onClick={() => onChange({ statuses: [], types: [], dateFrom: '', dateTo: '' })}
          className="text-2xs text-ink-muted hover:text-ink-primary underline"
        >
          Clear
        </button>
      )}
    </div>
  )
}
