import React, { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, useToast } from '@/components/ui'
import type { ReactorCardData } from '@/api/dashboard'
import { experimentsApi, type ExperimentStatus } from '@/api/experiments'

function todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

const STATUS_OPTIONS = ['ONGOING', 'COMPLETED', 'CANCELLED', 'QUEUED'] as const
type _ExperimentStatus = typeof STATUS_OPTIONS[number]

// Static hardware specs — used for both occupied and empty slots.
// Source: lab hardware inventory (issue #2).
const REACTOR_SPECS: Record<string, { volume_mL: number; material: string; vendor: string }> = {
  R01: { volume_mL: 100, material: 'Hastelloy', vendor: 'Yushen' },
  R02: { volume_mL: 100, material: 'Hastelloy', vendor: 'Yushen' },
  R03: { volume_mL: 100, material: 'Hastelloy', vendor: 'Yushen' },
  R04: { volume_mL: 500, material: 'Titanium',  vendor: 'Yushen' },
  R05: { volume_mL: 500, material: 'Titanium',  vendor: 'Yushen' },
  R06: { volume_mL: 500, material: 'Titanium',  vendor: 'Yushen' },
  R07: { volume_mL: 300, material: 'Titanium',  vendor: 'Tan' },
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
      return 'text-status-ongoing bg-status-ongoing/10'
    case 'COMPLETED':
      return 'text-status-completed bg-status-completed/10'
    case 'CANCELLED':
      return 'text-status-cancelled bg-status-cancelled/10'
    case 'QUEUED':
      return 'text-status-queued bg-status-queued/10'
    default:
      return 'text-ink-muted bg-surface-overlay'
  }
}

function isCoreFlood(label: string): boolean {
  return label.startsWith('CF')
}

function StatusBadge({
  card,
}: {
  card: ReactorCardData
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()
  const { error: toastError } = useToast()

  const { mutate, isPending } = useMutation({
    mutationFn: (newStatus: ExperimentStatus) =>
      experimentsApi.patchStatus(card.experiment_id!, newStatus),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    // Without this a 409 from the occupancy check (issue #97) is swallowed: the
    // dropdown snaps back and the user is told nothing. The server's detail
    // names the occupying experiment and its start date, so show it verbatim
    // in the body — matching the title/body convention used by the other
    // handlers in this file (e.g. ReactorDetailModal's dateMutation/crMutation).
    onError: (err: Error) => {
      toastError('Update failed', err.message || 'Could not update status')
    },
  })

  // Close dropdown on outside click
  useEffect(() => {
    if (!open) return
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [open])

  return (
    <div ref={ref} className="relative" onClick={(e) => e.stopPropagation()}>
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={isPending}
        className={[
          'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-medium uppercase tracking-wide transition-opacity',
          statusColors(card.status),
          isPending ? 'opacity-50' : 'hover:opacity-80 cursor-pointer',
        ].join(' ')}
        title="Change status"
      >
        <span
          className={[
            'w-1.5 h-1.5 rounded-full',
            card.status === 'ONGOING'
              ? 'bg-status-ongoing animate-pulse-slow'
              : card.status === 'QUEUED'
                ? 'bg-status-queued'
                : 'bg-surface-border',
          ].join(' ')}
        />
        {card.status ?? 'Active'}
        <span className="ml-0.5 opacity-60">▾</span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 z-20 bg-surface-overlay border border-surface-border rounded shadow-lg min-w-[110px]">
          {STATUS_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => {
                setOpen(false)
                if (s !== card.status) mutate(s)
              }}
              className={[
                'w-full text-left px-3 py-1.5 text-2xs font-semibold uppercase tracking-wider transition-colors',
                s === card.status
                  ? 'text-ink-muted cursor-default'
                  : 'text-ink-secondary hover:bg-surface-border/30 cursor-pointer',
              ].join(' ')}
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  )
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
  const isCF = isCoreFlood(label)
  // HPHT-only hardware spec (volume/material/vendor) — never shown on Core Flood cards.
  const showSpecsBadge = !isCF

  return (
    <Card
      padding="none"
      className={[
        'transition-colors duration-150 select-none min-h-[100px] p-4 px-5 border-l-2',
        isCF ? 'border-l-status-info/70' : 'border-l-transparent',
        occupied ? 'hover:border-ink-muted cursor-pointer' : 'opacity-35 border-dashed',
      ].join(' ')}
      onClick={() => occupied && onClick(card!)}
    >
      <div className="flex items-start justify-between mb-1">
        <p className="text-xl font-bold text-ink-primary font-mono-data leading-none">{label}</p>
        {occupied ? (
          <StatusBadge card={card!} />
        ) : (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-medium uppercase tracking-wide text-ink-muted bg-surface-overlay">
            <span className="w-1.5 h-1.5 rounded-full bg-surface-border" />
            Empty
          </span>
        )}
      </div>

      {occupied ? (
        <div className="space-y-1.5">
          <p className="text-base font-semibold text-ink-primary font-mono-data leading-snug">
            {card!.experiment_id}
          </p>
          {card!.sample_id && (
            <p className="text-xs text-ink-secondary leading-snug">
              <span className="text-ink-muted">Sample:</span>{' '}
              <span className="font-mono-data">{card!.sample_id}</span>
            </p>
          )}
          {card!.description && (
            <p
              className="text-xs text-ink-secondary line-clamp-2 leading-snug italic"
              title={card!.description}
            >
              {card!.description}
            </p>
          )}
          {card!.todays_modification && (
            <p
              className="text-xs text-ink-secondary line-clamp-2 leading-snug"
              title={card!.todays_modification}
            >
              <span className="text-ink-muted">Modified today:</span>{' '}
              {card!.todays_modification}
            </p>
          )}
          <div className="flex items-center gap-3 pt-0.5">
            {card!.temperature_c != null && (
              <span className="text-xs text-ink-muted">
                <span className="font-mono-data text-ink-secondary">{card!.temperature_c}</span> °C
              </span>
            )}
            {card!.days_running != null && (
              <span className="inline-flex items-center gap-1 rounded bg-surface-overlay px-1.5 py-0.5 text-xs font-semibold text-ink-primary">
                Day <span className="font-mono-data">{card!.days_running}</span>
              </span>
            )}
          </div>
          {showSpecsBadge && (
            <ReactorSpecsBadge
              volume_mL={card!.volume_mL ?? REACTOR_SPECS[label]?.volume_mL ?? null}
              material={card!.material ?? REACTOR_SPECS[label]?.material ?? null}
              vendor={card!.vendor ?? REACTOR_SPECS[label]?.vendor ?? null}
            />
          )}
        </div>
      ) : (
        <div className="space-y-1.5">
          <p className="text-xs text-ink-muted mt-1">No experiment assigned</p>
          {showSpecsBadge && (
            <ReactorSpecsBadge
              volume_mL={REACTOR_SPECS[label]?.volume_mL ?? null}
              material={REACTOR_SPECS[label]?.material ?? null}
              vendor={REACTOR_SPECS[label]?.vendor ?? null}
            />
          )}
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
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()
  const [editingDate, setEditingDate] = useState(false)
  const [dateDraft, setDateDraft] = useState('')
  const [crDate, setCrDate] = useState(todayISO)
  const [crText, setCrText] = useState('')
  const [crLoadedForDate, setCrLoadedForDate] = useState<string | null>(null)
  const isQueued = card.status === 'QUEUED'

  const { data: recentCR } = useQuery({
    queryKey: ['reactorModificationRecent', card.experiment_id, crDate],
    queryFn: () => experimentsApi.getRecentChangeRequests(card.experiment_id as string, crDate),
    enabled: !!card.experiment_id,
  })

  // Pre-populate the modification text field with whatever entry exists for the
  // selected date, whenever the selected date changes and its data has arrived.
  useEffect(() => {
    if (recentCR && crLoadedForDate !== crDate) {
      setCrText(recentCR.selected?.requested_change ?? '')
      setCrLoadedForDate(crDate)
    }
  }, [recentCR, crDate, crLoadedForDate])

  const dateMutation = useMutation({
    mutationFn: (newDate: string) =>
      experimentsApi.patch(card.experiment_id as string, { date: newDate }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
      success('Start date updated')
      setEditingDate(false)
    },
    onError: () => {
      toastError('Update failed', 'Could not save start date')
      setEditingDate(false)
    },
  })

  const crMutation = useMutation({
    mutationFn: (text: string) =>
      experimentsApi.createChangeRequest(card.experiment_id as string, {
        reactor_label: card.reactor_label,
        requested_change: text,
        sync_date: crDate,
      }),
    onSuccess: (saved) => {
      setCrText(saved.requested_change)
      queryClient.invalidateQueries({ queryKey: ['reactorModificationRecent', card.experiment_id] })
      queryClient.invalidateQueries({ queryKey: ['changeRequests', card.experiment_id] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      success('Reactor modification saved')
    },
    onError: () => {
      toastError('Save failed', 'Could not save reactor modification')
    },
  })

  function startDateEdit() {
    setDateDraft(card.started_at?.slice(0, 10) ?? '')
    setEditingDate(true)
  }

  function confirmDate() {
    if (!card.experiment_id) return
    const trimmed = dateDraft.trim()
    if (trimmed) dateMutation.mutate(`${trimmed}T00:00:00`)
    else setEditingDate(false)
  }

  function formatDateShort(iso: string): string {
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="bg-surface-overlay border border-surface-border rounded-lg p-6 w-full max-w-md shadow-xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
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

        {/* EXPERIMENT section */}
        <div className="mb-4">
          <p className="text-ink-muted text-2xs uppercase tracking-wider mb-2">Experiment</p>
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
            {!isQueued && card.days_running != null && (
              <div className="flex gap-2">
                <dt className="text-ink-muted w-28 shrink-0">Elapsed</dt>
                <dd className="font-mono-data text-ink-secondary">
                  Day {card.days_running}
                  {card.started_at
                    ? ` (started ${formatDateShort(card.started_at)})`
                    : ''}
                </dd>
              </div>
            )}
            {!isQueued && (
              <div className="flex gap-2 items-center">
                <dt className="text-ink-muted w-28 shrink-0">Started</dt>
                <dd className="font-mono-data text-ink-secondary flex items-center gap-1">
                  {editingDate ? (
                    <>
                      <input
                        type="date"
                        value={dateDraft}
                        onChange={(e) => setDateDraft(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') confirmDate()
                          if (e.key === 'Escape') setEditingDate(false)
                        }}
                        className="font-mono-data border border-surface-border rounded px-1 bg-surface-raised text-ink-primary text-sm"
                        autoFocus
                      />
                      <button
                        onClick={confirmDate}
                        disabled={dateMutation.isPending}
                        className="text-status-success hover:opacity-80 text-sm"
                        title="Save date"
                        aria-label="Save date"
                      >
                        ✓
                      </button>
                      <button
                        onClick={() => setEditingDate(false)}
                        className="text-ink-muted hover:text-ink-secondary text-sm"
                        title="Cancel"
                        aria-label="Cancel date edit"
                      >
                        ✗
                      </button>
                    </>
                  ) : (
                    <>
                      <span>{card.started_at ? card.started_at.slice(0, 10) : '—'}</span>
                      <button
                        onClick={startDateEdit}
                        className="text-ink-muted hover:text-ink-secondary transition-colors text-sm leading-none cursor-pointer"
                        title="Edit start date"
                        aria-label="Edit start date"
                      >
                        ✎
                      </button>
                    </>
                  )}
                </dd>
              </div>
            )}
            {card.description && (
              <div className="pt-1">
                <p className="text-ink-secondary leading-relaxed text-sm">{card.description}</p>
              </div>
            )}
          </dl>
        </div>

        {/* HARDWARE section */}
        {(card.volume_mL != null || card.material || card.vendor) && (
          <div className="pt-3 border-t border-surface-border mb-4">
            <p className="text-ink-muted text-2xs uppercase tracking-wider mb-2">Hardware</p>
            <dl className="space-y-1.5 text-sm">
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
            </dl>
          </div>
        )}

        {/* REACTOR MODIFICATION section */}
        {card.experiment_id && (
          <div className="pt-3 border-t border-surface-border">
            <p className="text-ink-muted text-2xs uppercase tracking-wider mb-3">Reactor Modification</p>

            {/* Most recent prior entry for this experiment — read only */}
            {recentCR?.previous && (
              <div className="mb-3 p-2.5 bg-surface-raised rounded border border-surface-border">
                <p className="text-2xs text-ink-muted mb-1">
                  {formatDateShort(recentCR.previous.sync_date)}
                </p>
                <p className="text-xs text-ink-secondary leading-relaxed">
                  {recentCR.previous.requested_change}
                </p>
              </div>
            )}

            {/* Editable date + text for the selected entry */}
            <div className="flex items-center justify-between mb-1.5">
              <p className="text-xs text-ink-muted">Reactor Modification for</p>
              <input
                type="date"
                value={crDate}
                onChange={(e) => setCrDate(e.target.value)}
                className="font-mono-data text-xs border border-surface-border rounded px-1.5 py-0.5 bg-surface-raised text-ink-primary"
                aria-label="Modification date"
              />
            </div>
            <textarea
              value={crText}
              onChange={(e) => setCrText(e.target.value)}
              rows={3}
              placeholder="Enter a reactor modification…"
              className="w-full text-sm bg-surface-raised border border-surface-border rounded px-2.5 py-2 text-ink-primary placeholder:text-ink-muted resize-none focus:outline-none focus:border-ink-muted transition-colors"
            />
            <button
              onClick={() => crMutation.mutate(crText.trim())}
              disabled={!crText.trim() || crMutation.isPending}
              className="mt-2 px-3 py-1.5 text-sm bg-brand-red text-white rounded hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {crMutation.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        )}

        {/* Footer */}
        <div className="mt-5 flex justify-end gap-2 pt-3 border-t border-surface-border">
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

/** Grid of reactor status cards showing current occupant, temperature, and elapsed time. */
export function ReactorGrid({
  cards,
  rSlotCount,
  cfSlotCount,
}: {
  cards: ReactorCardData[]
  rSlotCount: number
  cfSlotCount: number
}) {
  const [selected, setSelected] = useState<ReactorCardData | null>(null)

  // Build lookup: reactor_label → card data
  const byLabel: Record<string, ReactorCardData> = {}
  for (const c of cards) {
    byLabel[c.reactor_label] = c
  }

  const pad = (i: number) => String(i).padStart(2, '0')
  const R_SLOTS = Array.from({ length: rSlotCount }, (_, i) => `R${pad(i + 1)}`)
  const CF_SLOTS = Array.from({ length: cfSlotCount }, (_, i) => `CF${pad(i + 1)}`)

  // Single unified grid: R01-R16 then CF01-CF03, in slot order — the 19-slot
  // total no longer divides evenly into a 6-column grid, so this uses 5
  // columns to keep R and CF rows breaking more naturally.
  const ALL_SLOTS = [...R_SLOTS, ...CF_SLOTS]

  return (
    <>
      {/* Section title lives in the enclosing Dashboard CardHeader ("Reactor Status") */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
        {ALL_SLOTS.map((label) => (
          <ReactorCard
            key={label}
            label={label}
            card={byLabel[label] ?? null}
            onClick={setSelected}
          />
        ))}
      </div>

      {selected && (
        <ReactorDetailModal
          key={selected.experiment_id ?? selected.reactor_label}
          card={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  )
}
