import { useNavigate } from 'react-router-dom'
import type { GanttEntry } from '@/api/dashboard'

const STATUS_BAR: Record<string, string> = {
  ONGOING: 'bg-status-ongoing',
  COMPLETED: 'bg-status-completed',
  CANCELLED: 'bg-surface-border opacity-60',
}

export function ExperimentTimeline({ entries }: { entries: GanttEntry[] }) {
  const navigate = useNavigate()

  if (entries.length === 0) {
    return (
      <p className="text-sm text-ink-muted text-center py-8">
        No experiments to display — try clearing filters
      </p>
    )
  }

  const maxDays = Math.max(...entries.map((e) => e.days_running ?? 1), 1)

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[400px] space-y-0.5">
        {entries.map((entry) => {
          const pct = Math.max(((entry.days_running ?? 1) / maxDays) * 100, 1)
          const barColor = STATUS_BAR[entry.status] ?? 'bg-surface-overlay'

          return (
            <div
              key={entry.experiment_db_id}
              className="flex items-center gap-2 py-0.5 group cursor-pointer"
              onClick={() => navigate(`/experiments/${entry.experiment_id}`)}
              title={`${entry.experiment_id}${entry.experiment_type ? ` · ${entry.experiment_type}` : ''} · Day ${entry.days_running ?? 0}`}
            >
              {/* Label */}
              <span className="text-xs font-mono-data text-ink-secondary w-32 shrink-0 truncate group-hover:text-ink-primary transition-colors">
                {entry.experiment_id}
              </span>

              {/* Bar track */}
              <div className="flex-1 h-3.5 bg-surface-overlay rounded overflow-hidden">
                <div
                  className={`h-full rounded transition-all duration-300 ${barColor}`}
                  style={{ width: `${pct}%` }}
                />
              </div>

              {/* Day count */}
              <span className="text-xs font-mono-data text-ink-muted w-10 text-right shrink-0">
                {entry.days_running ?? 0}d
              </span>
            </div>
          )
        })}

        {/* X-axis */}
        <div className="flex items-center gap-2 mt-3 pt-2 border-t border-surface-border">
          <span className="text-2xs text-ink-muted w-32 shrink-0">Experiment</span>
          <div className="flex-1 flex justify-between">
            <span className="text-2xs text-ink-muted">0d</span>
            <span className="text-2xs text-ink-muted">{Math.round(maxDays / 2)}d</span>
            <span className="text-2xs text-ink-muted">{maxDays}d</span>
          </div>
          <span className="w-10" />
        </div>
      </div>
    </div>
  )
}
