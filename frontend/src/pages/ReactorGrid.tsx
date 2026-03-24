import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card } from '@/components/ui'
import type { ReactorCardData } from '@/api/dashboard'

// Fixed reactor layout: R01-R16 and CF01-CF02
const R_SLOTS = Array.from({ length: 16 }, (_, i) => `R${String(i + 1).padStart(2, '0')}`)
const CF_SLOTS = ['CF01', 'CF02']

// Static hardware specs — used for both occupied and empty slots.
// Source: lab hardware inventory (issue #2).
const REACTOR_SPECS: Record<string, { volume_mL: number; material: string; vendor: string }> = {
  R01: { volume_mL: 100, material: 'Hastelloy', vendor: 'Yushen' },
  R02: { volume_mL: 100, material: 'Hastelloy', vendor: 'Yushen' },
  R03: { volume_mL: 100, material: 'Hastelloy', vendor: 'Yushen' },
  R04: { volume_mL: 300, material: 'Titanium',  vendor: 'Tan' },
  R05: { volume_mL: 500, material: 'Titanium',  vendor: 'Yushen' },
  R06: { volume_mL: 500, material: 'Titanium',  vendor: 'Yushen' },
  R07: { volume_mL: 500, material: 'Titanium',  vendor: 'Yushen' },
  R08: { volume_mL: 100, material: 'Titanium',  vendor: 'Tan' },
  R09: { volume_mL: 100, material: 'Titanium',  vendor: 'Tan' },
  R10: { volume_mL: 100, material: 'Titanium',  vendor: 'Yushen' },
  R11: { volume_mL: 100, material: 'Titanium',  vendor: 'Yushen' },
  R12: { volume_mL: 100, material: 'Titanium',  vendor: 'Yushen' },
  R13: { volume_mL: 100, material: 'Titanium',  vendor: 'Yushen' },
  R14: { volume_mL: 100, material: 'Titanium',  vendor: 'Yushen' },
  R15: { volume_mL: 100, material: 'Titanium',  vendor: 'Yushen' },
  R16: { volume_mL: 100, material: 'Titanium',  vendor: 'Yushen' },
}

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

function ReactorSpecsBadge({
  volume_mL,
  material,
  vendor,
}: {
  volume_mL: number | null
  material: string | null
  vendor: string | null
}) {
  if (!volume_mL && !material && !vendor) return null
  return (
    <div className="flex flex-wrap gap-x-2 gap-y-0.5 pt-1 border-t border-surface-border mt-1">
      {volume_mL != null && (
        <span className="text-2xs text-ink-muted">
          <span className="font-mono-data text-ink-secondary">{volume_mL}</span> mL
        </span>
      )}
      {material && (
        <span className="text-2xs text-ink-muted">{material}</span>
      )}
      {vendor && (
        <span className="text-2xs text-ink-muted">{vendor}</span>
      )}
    </div>
  )
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
          <ReactorSpecsBadge
            volume_mL={card!.volume_mL ?? REACTOR_SPECS[label]?.volume_mL ?? null}
            material={card!.material ?? REACTOR_SPECS[label]?.material ?? null}
            vendor={card!.vendor ?? REACTOR_SPECS[label]?.vendor ?? null}
          />
        </div>
      ) : (
        <div className="space-y-1">
          <p className="text-xs text-ink-muted mt-1">No active experiment</p>
          <ReactorSpecsBadge
            volume_mL={REACTOR_SPECS[label]?.volume_mL ?? null}
            material={REACTOR_SPECS[label]?.material ?? null}
            vendor={REACTOR_SPECS[label]?.vendor ?? null}
          />
        </div>
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
          {(card.volume_mL != null || card.material || card.vendor) && (
            <div className="pt-2 border-t border-surface-border">
              <p className="text-ink-muted text-2xs uppercase tracking-wider mb-1.5">
                Hardware
              </p>
              <div className="space-y-1.5">
                {card.volume_mL != null && (
                  <div className="flex gap-2">
                    <dt className="text-ink-muted w-28 shrink-0">Volume</dt>
                    <dd className="font-mono-data text-ink-secondary">{card.volume_mL} mL</dd>
                  </div>
                )}
                {card.material && (
                  <div className="flex gap-2">
                    <dt className="text-ink-muted w-28 shrink-0">Material</dt>
                    <dd className="text-ink-secondary">{card.material}</dd>
                  </div>
                )}
                {card.vendor && (
                  <div className="flex gap-2">
                    <dt className="text-ink-muted w-28 shrink-0">Vendor</dt>
                    <dd className="text-ink-secondary">{card.vendor}</dd>
                  </div>
                )}
              </div>
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
