import { useNavigate } from 'react-router-dom'
import type { ActivityEntry } from '@/api/dashboard'

const ACTION_LABEL: Record<string, string> = {
  create: 'Created',
  update: 'Updated',
  delete: 'Deleted',
}

const ACTION_COLOR: Record<string, string> = {
  create: 'text-status-ongoing',
  update: 'text-amber-400',
  delete: 'text-status-cancelled',
}

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 30) return `${days}d ago`
  return new Date(iso).toISOString().slice(0, 10)
}

/** Scrollable feed of recent experiment modifications with timestamp and actor. */
export function ActivityFeed({ entries }: { entries: ActivityEntry[] }) {
  const navigate = useNavigate()

  if (entries.length === 0) {
    return (
      <p className="text-sm text-ink-muted text-center py-8">No recent activity</p>
    )
  }

  return (
    <ul className="divide-y divide-surface-border">
      {entries.map((entry) => (
        <li key={entry.id} className="flex items-start gap-3 py-2.5">
          <span
            className={`text-xs font-semibold uppercase tracking-wider w-16 shrink-0 mt-0.5 ${ACTION_COLOR[entry.modification_type] ?? 'text-ink-muted'}`}
          >
            {ACTION_LABEL[entry.modification_type] ?? entry.modification_type}
          </span>

          <div className="flex-1 min-w-0">
            <p className="text-xs text-ink-secondary leading-snug">
              <span className="font-medium text-ink-primary">{entry.modified_table}</span>
              {entry.experiment_id && (
                <>
                  {' — '}
                  <button
                    onClick={() => navigate(`/experiments/${entry.experiment_id}`)}
                    className="text-brand-red hover:underline font-mono-data"
                  >
                    {entry.experiment_id}
                  </button>
                </>
              )}
            </p>
            {entry.modified_by && (
              <p className="text-2xs text-ink-muted mt-0.5">{entry.modified_by}</p>
            )}
          </div>

          <span className="text-2xs text-ink-muted shrink-0 mt-0.5 whitespace-nowrap">
            {timeAgo(entry.created_at)}
          </span>
        </li>
      ))}
    </ul>
  )
}
