import { useState } from 'react'
import type { UploadPlan } from '@/api/bulkUploads'

/** Rows shown per section before the "Show N more" toggle. Looser than the 5 used
 *  in BulkUploadRow because the plan renders in a modal with room to scroll. */
const TRUNCATE_AT = 10

type SectionKey = 'conflicts' | 'renames' | 'overwrites' | 'creates' | 'skips'

interface SectionMeta {
  key: SectionKey
  singular: string
  plural: string
  /** Brand status tokens only — never raw hex (frontend/CLAUDE.md). */
  box: string
  heading: string
  defaultOpen: boolean
}

// Fixed order. Conflicts first and expanded, everything else collapsed (issue #100 item 7).
const SECTIONS: SectionMeta[] = [
  { key: 'conflicts', singular: 'conflict', plural: 'conflicts',
    box: 'bg-status-error/5 border-status-error/25', heading: 'text-status-error', defaultOpen: true },
  { key: 'renames', singular: 'rename', plural: 'renames',
    box: 'bg-status-info/5 border-status-info/25', heading: 'text-status-info', defaultOpen: false },
  { key: 'overwrites', singular: 'overwrite', plural: 'overwrites',
    box: 'bg-status-warning/5 border-status-warning/25', heading: 'text-status-warning', defaultOpen: false },
  { key: 'creates', singular: 'create', plural: 'creates',
    box: 'bg-status-success/5 border-status-success/25', heading: 'text-status-success', defaultOpen: false },
  { key: 'skips', singular: 'skip', plural: 'skips',
    box: 'bg-surface-raised border-surface-border', heading: 'text-ink-muted', defaultOpen: false },
]

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width={14} height={14} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
      className={`text-ink-muted transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}

/** Renders a plan value for display. `null`/`undefined`/`''` all read as (empty) so a
 *  field being cleared is visible rather than looking like a rendering bug. */
function fmtValue(v: unknown): string {
  if (v === null || v === undefined || v === '') return '(empty)'
  return String(v)
}

function Line({ children }: { children: React.ReactNode }) {
  return <div className="text-2xs font-mono-data text-ink-secondary leading-relaxed">{children}</div>
}

function RowNo({ row }: { row: number }) {
  return <span className="text-ink-muted">Row {row}</span>
}

function sectionRows(plan: UploadPlan, key: SectionKey): React.ReactNode[] {
  switch (key) {
    case 'conflicts':
      return plan.conflicts.map((c, i) => (
        <Line key={i}>
          <RowNo row={c.row} /> <span className="text-status-error">[{c.kind}]</span> {c.detail}
        </Line>
      ))
    case 'renames':
      return plan.renames.map((r, i) => (
        <Line key={i}>
          <RowNo row={r.row} /> {r.from_id} <span className="text-status-info">→</span>{' '}
          <span className="font-semibold text-ink-primary">{r.to_id}</span>
        </Line>
      ))
    case 'overwrites':
      return plan.overwrites.map((o, i) => (
        <div key={i} className="space-y-0.5">
          <Line>
            <RowNo row={o.row} />{' '}
            <span className="font-semibold text-ink-primary">{o.experiment_id}</span>
          </Line>
          {o.fields_changed.length === 0 ? (
            <Line><span className="pl-4 text-ink-muted">no field changes</span></Line>
          ) : (
            o.fields_changed.map((f, j) => (
              <Line key={j}>
                <span className="pl-4 text-ink-muted">{f.field}:</span>{' '}
                <span className="line-through text-ink-muted">{fmtValue(f.old)}</span>{' '}
                <span className="text-status-warning">→</span>{' '}
                <span className="font-semibold text-ink-primary">{fmtValue(f.new)}</span>
              </Line>
            ))
          )}
        </div>
      ))
    case 'creates':
      return plan.creates.map((c, i) => (
        <Line key={i}>
          <RowNo row={c.row} />{' '}
          <span className="font-semibold text-ink-primary">{c.experiment_id}</span>
          {c.parent_id && <span className="text-ink-muted"> · parent {c.parent_id}</span>}
          {c.copied_from && <span className="text-ink-muted"> · copied from {c.copied_from}</span>}
        </Line>
      ))
    case 'skips':
      return plan.skips.map((s, i) => (
        <Line key={i}>
          <RowNo row={s.row} /> {s.experiment_id ?? '(no ID)'} — {s.reason}
        </Line>
      ))
  }
}

function PlanSection({ meta, rows }: { meta: SectionMeta; rows: React.ReactNode[] }) {
  const [open, setOpen] = useState(meta.defaultOpen)
  const [showAll, setShowAll] = useState(false)
  const count = rows.length
  const visible = showAll ? rows : rows.slice(0, TRUNCATE_AT)
  const hidden = count - visible.length

  return (
    <div className={`rounded border ${meta.box}`}>
      <button
        className="w-full flex items-center justify-between px-3 py-2 text-left"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className={`text-xs font-medium ${meta.heading}`}>
          {count} {count === 1 ? meta.singular : meta.plural}
        </span>
        <Chevron open={open} />
      </button>
      {open && (
        <div className="px-3 pb-2 space-y-1">
          {visible}
          {hidden > 0 && (
            <button
              className="text-2xs text-ink-muted underline hover:text-ink-secondary"
              onClick={() => setShowAll(true)}
            >
              Show {hidden} more
            </button>
          )}
          {showAll && count > TRUNCATE_AT && (
            <button
              className="text-2xs text-ink-muted underline hover:text-ink-secondary"
              onClick={() => setShowAll(false)}
            >
              Show less
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export interface UploadPlanPanelProps {
  plan: UploadPlan
}

/** Renders an UploadPlan as grouped, colour-coded sections with counts in the headers
 *  (issue #100 items 7-8). Presentational only — knows nothing about committing. */
export function UploadPlanPanel({ plan }: UploadPlanPanelProps) {
  const sections = SECTIONS
    .map((meta) => ({ meta, rows: sectionRows(plan, meta.key) }))
    .filter((s) => s.rows.length > 0)

  if (sections.length === 0) {
    return <p className="text-xs text-ink-muted">This file would make no changes.</p>
  }

  return (
    <div className="space-y-2">
      {sections.map(({ meta, rows }) => (
        <PlanSection key={meta.key} meta={meta} rows={rows} />
      ))}
    </div>
  )
}
