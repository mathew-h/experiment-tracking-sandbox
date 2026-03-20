import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card } from '@/components/ui'
import type { ReactorCardData } from '@/api/dashboard'

// Fixed reactor layout: R01-R16 and CF01-CF02
const R_SLOTS = Array.from({ length: 16 }, (_, i) => `R${String(i + 1).padStart(2, '0')}`)
const CF_SLOTS = ['CF01', 'CF02']

function statusColors(status: string | null) {
  switch (status) {
    case 'ONGOING':
      return 'text-status-ongoing bg-status-ongoing/10 border-status-ongoing/20'
    case 'COMPLETED':
      return 'text-status-completed bg-status-completed/10 border-status-completed/20'
    case 'CANCELLED':
      return 'text-status-cancelled bg-status-cancelled/10 border-status-cancelled/20'
    default:
      return 'text-ink-muted bg-surface-overlay border-surface-border'
  }
}

function ReactorCard({
  label,
  card,
  onClick,
}: {
  label: string
  card: ReactorCardData | null
  onClick: (card: ReactorCardData) => void
}) {
  const occupied = card !== null

  return (
    <Card
      className={[
        'transition-colors duration-150 select-none min-h-[100px]',
        occupied ? 'hover:border-ink-muted cursor-pointer' : 'opacity-40',
      ].join(' ')}
      onClick={() => occupied && onClick(card!)}
    >
      <div className="flex items-start justify-between mb-2">
        <div>
          <p className="text-2xs text-ink-muted uppercase tracking-wider font-medium mb-0.5">
            Reactor
          </p>
          <p className="text-xl font-bold text-ink-primary font-mono-data leading-none">{label}</p>
        </div>
        <span
          className={[
            'inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-2xs font-semibold uppercase tracking-wider border',
            occupied ? statusColors(card!.status) : 'text-ink-muted bg-surface-overlay border-surface-border',
          ].join(' ')}
        >
          <span
            className={[
              'w-1.5 h-1.5 rounded-full',
              occupied && card!.status === 'ONGOING' ? 'bg-status-ongoing animate-pulse-slow' : 'bg-surface-border',
            ].join(' ')}
          />
          {occupied ? (card!.status ?? 'Active') : 'Empty'}
        </span>
      </div>

      {occupied ? (
        <div className="space-y-1">
          <p className="text-sm font-medium text-ink-primary font-mono-data leading-tight">
            {card!.experiment_id}
          </p>
          {card!.sample_id && (
            <p className="text-xs text-ink-secondary">
              <span className="text-ink-muted">Sample:</span>{' '}
              <span className="font-mono-data">{card!.sample_id}</span>
            </p>
          )}
          {card!.description && (
            <p className="text-xs text-ink-muted line-clamp-2 leading-snug italic">
              {card!.description}
            </p>
          )}
          {card!.experiment_type && (
            <p className="text-xs text-ink-muted">{card!.experiment_type}</p>
          )}
          <div className="flex items-center gap-3 pt-0.5">
            {card!.temperature_c != null && (
              <span className="text-xs text-ink-muted">
                <span className="font-mono-data text-ink-secondary">{card!.temperature_c}</span> °C
              </span>
            )}
            {card!.days_running != null && (
              <span className="text-xs text-ink-muted">
                Day{' '}
                <span className="font-mono-data text-ink-secondary">{card!.days_running}</span>
              </span>
            )}
          </div>
        </div>
      ) : (
        <p className="text-xs text-ink-muted mt-1">No active experiment</p>
      )}
    </Card>
  )
}

function ReactorDetailModal({
  card,
  onClose,
}: {
  card: ReactorCardData
  onClose: () => void
}) {
  const navigate = useNavigate()

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="bg-surface-overlay border border-surface-border rounded-lg p-6 w-full max-w-md shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <div>
            <p className="text-2xs text-ink-muted uppercase tracking-wider mb-1">
              {card.reactor_label}
            </p>
            <h2 className="text-lg font-bold text-ink-primary font-mono-data">
              {card.experiment_id}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-ink-muted hover:text-ink-primary text-xl leading-none mt-0.5"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <dl className="space-y-2 text-sm">
          {card.sample_id && (
            <div className="flex gap-2">
              <dt className="text-ink-muted w-28 shrink-0">Sample ID</dt>
              <dd className="text-ink-primary font-mono-data">{card.sample_id}</dd>
            </div>
          )}
          {card.researcher && (
            <div className="flex gap-2">
              <dt className="text-ink-muted w-28 shrink-0">Researcher</dt>
              <dd className="text-ink-secondary">{card.researcher}</dd>
            </div>
          )}
          {card.experiment_type && (
            <div className="flex gap-2">
              <dt className="text-ink-muted w-28 shrink-0">Type</dt>
              <dd className="text-ink-secondary">{card.experiment_type}</dd>
            </div>
          )}
          {card.temperature_c != null && (
            <div className="flex gap-2">
              <dt className="text-ink-muted w-28 shrink-0">Temperature</dt>
              <dd className="font-mono-data text-ink-secondary">{card.temperature_c} °C</dd>
            </div>
          )}
          {card.days_running != null && (
            <div className="flex gap-2">
              <dt className="text-ink-muted w-28 shrink-0">Elapsed</dt>
              <dd className="font-mono-data text-ink-secondary">Day {card.days_running}</dd>
            </div>
          )}
          {card.started_at && (
            <div className="flex gap-2">
              <dt className="text-ink-muted w-28 shrink-0">Started</dt>
              <dd className="font-mono-data text-ink-secondary">
                {card.started_at.slice(0, 10)}
              </dd>
            </div>
          )}
          {card.description && (
            <div className="pt-2 border-t border-surface-border">
              <p className="text-ink-muted text-2xs uppercase tracking-wider mb-1.5">
                Description
              </p>
              <p className="text-ink-secondary leading-relaxed text-sm">{card.description}</p>
            </div>
          )}
        </dl>

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-ink-muted hover:text-ink-primary border border-surface-border rounded transition-colors"
          >
            Close
          </button>
          <button
            onClick={() => navigate(`/experiments/${card.experiment_id}`)}
            className="px-3 py-1.5 text-sm bg-brand-red text-white rounded hover:opacity-90 transition-opacity"
          >
            View Detail →
          </button>
        </div>
      </div>
    </div>
  )
}

export function ReactorGrid({ cards }: { cards: ReactorCardData[] }) {
  const [selected, setSelected] = useState<ReactorCardData | null>(null)

  // Build lookup: reactor_label → card data
  const byLabel: Record<string, ReactorCardData> = {}
  for (const c of cards) {
    byLabel[c.reactor_label] = c
  }

  return (
    <>
      {/* Standard reactors R01–R16 */}
      <div>
        <p className="text-2xs text-ink-muted uppercase tracking-wider font-medium mb-2">
          Standard Reactors (R01–R16)
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
          {R_SLOTS.map((label) => (
            <ReactorCard
              key={label}
              label={label}
              card={byLabel[label] ?? null}
              onClick={setSelected}
            />
          ))}
        </div>
      </div>

      {/* Core flood CF01–CF02 */}
      <div className="mt-4">
        <p className="text-2xs text-ink-muted uppercase tracking-wider font-medium mb-2">
          Core Flood (CF01–CF02)
        </p>
        <div className="grid grid-cols-2 gap-2 max-w-xs">
          {CF_SLOTS.map((label) => (
            <ReactorCard
              key={label}
              label={label}
              card={byLabel[label] ?? null}
              onClick={setSelected}
            />
          ))}
        </div>
      </div>

      {selected && (
        <ReactorDetailModal card={selected} onClose={() => setSelected(null)} />
      )}
    </>
  )
}
