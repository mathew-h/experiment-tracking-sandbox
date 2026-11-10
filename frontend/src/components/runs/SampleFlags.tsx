import { useState, type MouseEvent, type ReactNode } from 'react'
import { IcpList } from '@/components/icp/IcpList'
import { Td } from '@/components/ui'

/** A per-sample flag that opens its own section under the row (issue #164).
 *  `details` (issue #163) opens run dates, notes and any page-specific extras. */
export type SampleFlag = 'icp' | 'mod' | 'details'

/** The note fields the flags read; RunSampleNote and the Results tab's notes both fit. */
export interface FlagNote {
  id: number
  note_type: string
  note_text: string
  created_by: string | null
}

export interface SampleFlagState {
  isOpen: (resultId: number, flag: SampleFlag) => boolean
  toggle: (resultId: number, flag: SampleFlag) => void
}

/** Which flag sections are open, per sample; any number can be open at once. */
export function useSampleFlags(): SampleFlagState {
  const [open, setOpen] = useState<Set<string>>(() => new Set())
  const key = (id: number, flag: SampleFlag) => `${id}:${flag}`
  return {
    isOpen: (id, flag) => open.has(key(id, flag)),
    toggle: (id, flag) =>
      setOpen((prev) => {
        const next = new Set(prev)
        if (!next.delete(key(id, flag))) next.add(key(id, flag))
        return next
      }),
  }
}

const modificationNotes = (notes: FlagNote[]) => notes.filter((n) => n.note_type === 'modification')

// Badge shape with the Results tab's colours (ICP info, MOD warning), as a button.
const FLAG =
  'inline-flex items-center gap-1 px-2 py-0.5 text-2xs font-medium rounded border uppercase tracking-wider ' +
  'cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-red-500'
const TONE: Record<SampleFlag, string> = {
  icp: 'bg-status-info/10 text-status-info border-status-info/20 hover:bg-status-info/20',
  mod: 'bg-status-warning/10 text-status-warning border-status-warning/20 hover:bg-status-warning/20',
  details: 'bg-surface-overlay text-ink-secondary border-surface-border hover:text-ink-primary',
}

interface FlagButtonsProps {
  resultId: number
  /** Accessible names, unique per row (e.g. "Show ICP for 2026-10-05, tube 7"). */
  icpLabel: string
  modLabel: string
  /** Shown only with `hasDetails`. */
  detailsLabel?: string
  /** The sample's ICP readings, when it has any. */
  icp: Record<string, number> | undefined
  notes: FlagNote[]
  /** True when the row has something for the DETAILS section to show. */
  hasDetails?: boolean
  flags: SampleFlagState
}

/** The ICP, MOD and DETAILS flags of one sample. Each toggles its section in the
 *  detail row and stops the click, so the row's own click (edit) does not fire. */
export function SampleFlagButtons({
  resultId, icpLabel, modLabel, detailsLabel, icp, notes, hasDetails = false, flags,
}: FlagButtonsProps) {
  const hasMod = modificationNotes(notes).length > 0
  const showDetails = hasDetails && detailsLabel !== undefined
  if (icp === undefined && !hasMod && !showDetails) return null
  const button = (flag: SampleFlag, text: string, label: string) => {
    const open = flags.isOpen(resultId, flag)
    return (
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        className={`${FLAG} ${TONE[flag]}`}
        onClick={(e: MouseEvent) => {
          e.stopPropagation()
          flags.toggle(resultId, flag)
        }}
        // Enter on a focused flag must not reach the row's Enter-to-edit handler.
        onKeyDown={(e) => e.stopPropagation()}
      >
        {text}
        <span aria-hidden="true">{open ? '▾' : '▸'}</span>
      </button>
    )
  }
  return (
    <span className="inline-flex items-center gap-1">
      {icp !== undefined && button('icp', 'ICP', icpLabel)}
      {hasMod && button('mod', 'MOD', modLabel)}
      {showDetails && button('details', 'DETAILS', detailsLabel)}
    </span>
  )
}

interface FlagDetailProps {
  resultId: number
  colSpan: number
  icp: Record<string, number> | undefined
  notes: FlagNote[]
  /** The DETAILS section's content; rendered only while that flag is open. */
  details?: ReactNode
  flags: SampleFlagState
}

/** The row under a sample holding whichever flag sections are open; nothing when none is. */
export function SampleFlagDetail({ resultId, colSpan, icp, notes, details, flags }: FlagDetailProps) {
  const showIcp = icp !== undefined && flags.isOpen(resultId, 'icp')
  const mods = modificationNotes(notes)
  const showMod = mods.length > 0 && flags.isOpen(resultId, 'mod')
  const showDetails = details != null && flags.isOpen(resultId, 'details')
  if (!showIcp && !showMod && !showDetails) return null
  return (
    <tr className="bg-surface-overlay">
      <Td colSpan={colSpan} className="px-6 py-2 space-y-2 whitespace-normal">
        {showIcp && icp && (
          <section role="region" aria-label="ICP readings">
            <IcpList elements={icp} />
          </section>
        )}
        {showMod && (
          <section role="region" aria-label="Modification notes" className="text-xs">
            <p className="text-2xs uppercase tracking-wider text-status-warning mb-1">Modification</p>
            <ul className="space-y-1">
              {mods.map((n) => (
                <li key={n.id} className="text-ink-secondary">
                  {n.note_text}
                  {n.created_by && <span className="text-ink-muted"> · {n.created_by}</span>}
                </li>
              ))}
            </ul>
          </section>
        )}
        {showDetails && (
          <section role="region" aria-label="Sample details" className="text-xs">
            {details}
          </section>
        )}
      </Td>
    </tr>
  )
}
