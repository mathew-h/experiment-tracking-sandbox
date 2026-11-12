import React, { useState, useRef, useEffect, useId } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Num, useToast } from '@/components/ui'
import type { ReactorCardData, ReactorSpec } from '@/api/dashboard'
import { experimentsApi, type ExperimentStatus } from '@/api/experiments'
import { labTodayISO } from '@/utils/labDate'
import { runPathFor } from '@/utils/experimentId'

const STATUS_OPTIONS = ['ONGOING', 'COMPLETED', 'CANCELLED', 'QUEUED'] as const
type _ExperimentStatus = typeof STATUS_OPTIONS[number]

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

/** Date-only strings (YYYY-MM-DD) are calendar dates, not instants: parse them
 *  as LOCAL midnight so the rendered day never shifts west of UTC. Full ISO
 *  datetimes (started_at, created_at) still go through Date normally. */
export function formatDateShort(iso: string): string {
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  const d = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function isCoreFlood(label: string): boolean {
  return label.startsWith('CF')
}

/** Run type a slot series holds: CF rigs run core floods, R and P (#147) vessels run HPHT. */
function runTypeForLabel(label: string): 'HPHT' | 'Core Flood' | null {
  if (isCoreFlood(label)) return 'Core Flood'
  if (/^[RP]\d/.test(label)) return 'HPHT'
  return null
}

/** Run page of a card's experiment, whatever its status (issues #150, #157);
 *  null when the card has no base ID or the slot series has no run page. */
export function runPagePath(card: ReactorCardData): string | null {
  const type = runTypeForLabel(card.reactor_label)
  return type && card.base_experiment_id ? runPathFor(type, card.base_experiment_id) : null
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

const PLACEHOLDER = '—'

/** One reactor slot (issue #165). Every card, occupied or empty, has the same
 *  rows in the same order, so cards in a grid row line up: header (slot label,
 *  experiment ID, status), description (two lines reserved), "Modified today"
 *  when there is one, last sampled date, metrics (temperature, day, run H2 to
 *  date), and hardware specs for R and P vessels. Missing values show "—". */
function ReactorCard({
  label,
  card,
  spec,
  onClick,
}: {
  label: string
  card: ReactorCardData | null
  /** Hardware spec from the dashboard payload; undefined for CF rigs. */
  spec: ReactorSpec | undefined
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
        'h-full flex flex-col gap-1.5 transition-colors duration-150 select-none p-4 px-5 border-l-2',
        isCF ? 'border-l-status-info/70' : 'border-l-transparent',
        occupied ? 'hover:border-ink-muted cursor-pointer' : 'opacity-35 border-dashed',
      ].join(' ')}
      onClick={() => occupied && onClick(card!)}
    >
      <div className="flex items-center gap-2 min-w-0" data-testid="reactor-card-header">
        <span className="shrink-0 text-sm font-medium font-mono-data text-ink-muted" data-testid="reactor-slot-label">
          {label}
        </span>
        {occupied ? (
          <span
            className="min-w-0 flex-1 truncate text-lg font-bold leading-tight text-ink-primary font-mono-data"
            title={card!.experiment_id ?? undefined}
          >
            {card!.experiment_id}
          </span>
        ) : (
          <span className="min-w-0 flex-1 truncate text-xs text-ink-muted">No experiment assigned</span>
        )}
        <span className="ml-auto shrink-0">
          {occupied ? (
            <StatusBadge card={card!} />
          ) : (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-medium uppercase tracking-wide text-ink-muted bg-surface-overlay">
              <span className="w-1.5 h-1.5 rounded-full bg-surface-border" />
              Empty
            </span>
          )}
        </span>
      </div>

      {/* Two lines reserved whether or not there is a description. */}
      <p
        className="min-h-[2lh] text-xs text-ink-secondary line-clamp-2 leading-snug italic"
        title={card?.description ?? undefined}
      >
        {card?.description ?? ''}
      </p>

      {card?.todays_modification && (
        <p
          className="text-xs text-ink-secondary line-clamp-2 leading-snug"
          title={card.todays_modification}
        >
          <span className="text-ink-muted">Modified today:</span>{' '}
          {card.todays_modification}
        </p>
      )}

      <p className="text-xs text-ink-muted" data-testid="reactor-card-last-sampled">
        Last sampled:{' '}
        <span className="font-mono-data text-ink-secondary">
          {card?.last_sampled_date ? formatDateShort(card.last_sampled_date) : PLACEHOLDER}
        </span>
      </p>

      <div className="mt-auto flex items-center gap-3" data-testid="reactor-card-metrics">
        <span className="text-xs text-ink-muted">
          <span className="font-mono-data text-ink-secondary">
            {card?.temperature_c != null ? card.temperature_c : PLACEHOLDER}
          </span>{' '}
          °C
        </span>
        <span className="inline-flex items-center gap-1 rounded bg-surface-overlay px-1.5 py-0.5 text-xs font-semibold text-ink-primary">
          Day <span className="font-mono-data">{card?.days_running ?? PLACEHOLDER}</span>
        </span>
        <span className="text-xs text-ink-muted" title="Run H₂ to date, all segments">
          H₂{' '}
          <span className="font-mono-data text-ink-secondary">
            <Num value={card?.cumulative_h2_grams_per_ton} />
          </span>{' '}
          g/t
        </span>
      </div>

      {showSpecsBadge && (
        <ReactorSpecsBadge
          volume_mL={card?.volume_mL ?? spec?.volume_mL ?? null}
          material={card?.material ?? spec?.material ?? null}
          vendor={card?.vendor ?? spec?.vendor ?? null}
        />
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
  const [crDate, setCrDate] = useState(() => labTodayISO())
  const [crText, setCrText] = useState('')
  const isQueued = card.status === 'QUEUED'
  const titleId = useId()

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

  // Issue #122 PR-B (decision 9): each save is a NEW dated 'modification' note.
  // Corrections happen in the experiment's Notes tab; there is no per-date upsert.
  const crMutation = useMutation({
    mutationFn: (text: string) =>
      experimentsApi.addNote(card.experiment_id as string, text, {
        note_type: 'modification',
        event_date: crDate,
      }),
    onSuccess: () => {
      setCrText('')
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['experiment', card.experiment_id] })
      success(`Modification saved for ${crDate}`)
    },
    onError: (err: Error) => {
      toastError('Save failed', err.message || 'Could not save reactor modification')
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

  const runPath = runPagePath(card)

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${titleId}-slot ${titleId}-id`}
        className="bg-surface-overlay border border-surface-border rounded-lg p-6 w-full max-w-md shadow-xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div>
            <p id={`${titleId}-slot`} className="text-2xs text-ink-muted uppercase tracking-wider mb-1">
              {card.reactor_label}
            </p>
            <h2 id={`${titleId}-id`} className="text-lg font-bold text-ink-primary font-mono-data">
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

        {/* Navigation (issue #157): the run is the primary destination, and sits
            above the modification note so the note reads as a side task. */}
        <div className="flex justify-end gap-2 pt-3 pb-4 border-t border-surface-border">
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
          <Button
            variant={runPath ? 'secondary' : 'primary'}
            size="sm"
            onClick={() => navigate(`/experiments/${encodeURIComponent(card.experiment_id ?? '')}`)}
          >
            Open segment {card.experiment_id}
          </Button>
          {runPath && (
            <Button variant="primary" size="sm" onClick={() => navigate(runPath)}>
              Open run page
            </Button>
          )}
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

            {/* Most recent modification on this experiment — read only (from the card payload) */}
            {card.latest_modification && (
              <div className="mb-3 p-2.5 bg-surface-raised rounded border border-surface-border">
                <p className="text-2xs text-ink-muted mb-1">
                  {formatDateShort(card.latest_modification.event_date ?? card.latest_modification.created_at)}
                </p>
                <p className="text-xs text-ink-secondary leading-relaxed">
                  {card.latest_modification.note_text}
                </p>
              </div>
            )}

            {/* Editable date + text for the selected entry */}
            <div className="flex items-center justify-between mb-1.5">
              <h3 className="text-xs font-medium text-ink-secondary">Log a reactor modification note</h3>
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
            <Button
              variant="secondary"
              size="sm"
              className="mt-2"
              onClick={() => crMutation.mutate(crText.trim())}
              disabled={!crText.trim() || crMutation.isPending}
            >
              {crMutation.isPending ? 'Saving…' : 'Save'}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

/** Grid of reactor status cards showing current occupant, temperature, and elapsed time. */
export function ReactorGrid({
  cards,
  rSlotCount,
  pSlotCount = 0,
  cfSlotCount,
  specs = {},
}: {
  cards: ReactorCardData[]
  rSlotCount: number
  /** Parr vessels P01-P06 (issue #147); 0 renders no Parr group. */
  pSlotCount?: number
  cfSlotCount: number
  /** Hardware spec per slot label, from the dashboard payload. */
  specs?: Record<string, ReactorSpec>
}) {
  const [selected, setSelected] = useState<ReactorCardData | null>(null)

  // Build lookup: reactor_label → card data
  const byLabel: Record<string, ReactorCardData> = {}
  for (const c of cards) {
    byLabel[c.reactor_label] = c
  }

  const pad = (i: number) => String(i).padStart(2, '0')
  const slots = (prefix: string, count: number) =>
    Array.from({ length: count }, (_, i) => `${prefix}${pad(i + 1)}`)

  // One labelled group per vessel series (issue #147): the Yushen/Tan HPHT
  // vessels, the Parr HPHT vessels, then the Core Flood rigs. A group with no
  // slots is not rendered.
  const groups = [
    // Columns per group (issue #165): R 4x4, P 3x2, CF 3x1 at full width.
    { key: 'R', title: 'HPHT', slots: slots('R', rSlotCount),
      cols: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4' },
    { key: 'P', title: 'Parr', slots: slots('P', pSlotCount),
      cols: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3' },
    { key: 'CF', title: 'Core Flood', slots: slots('CF', cfSlotCount),
      cols: 'grid-cols-1 sm:grid-cols-3' },
  ].filter((g) => g.slots.length > 0)

  return (
    <>
      {/* Section title lives in the enclosing Dashboard CardHeader ("Reactor Status") */}
      <div className="space-y-4">
        {groups.map((g) => (
          <section key={g.key} aria-label={`${g.title} reactors`} data-testid={`reactor-group-${g.key}`}>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">
              {g.title}
              <span className="ml-2 font-mono-data normal-case tracking-normal">
                {g.slots[0]}–{g.slots[g.slots.length - 1]}
              </span>
            </h3>
            <div className={`grid ${g.cols} gap-2`} data-testid={`reactor-grid-${g.key}`}>
              {g.slots.map((label) => (
                <ReactorCard
                  key={label}
                  label={label}
                  card={byLabel[label] ?? null}
                  spec={specs[label]}
                  onClick={setSelected}
                />
              ))}
            </div>
          </section>
        ))}
      </div>

      {selected && (
        <ReactorDetailModal
          key={selected.experiment_id ?? selected.reactor_label}
          // Render from the live card so a save (which invalidates ['dashboard'])
          // updates the open modal's "latest" block; fall back to the click-time
          // snapshot if the slot's occupant changed under us (the key resets state).
          card={
            byLabel[selected.reactor_label]?.experiment_id === selected.experiment_id
              ? byLabel[selected.reactor_label]
              : selected
          }
          onClose={() => setSelected(null)}
        />
      )}
    </>
  )
}
