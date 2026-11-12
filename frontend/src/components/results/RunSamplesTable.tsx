import { Fragment, type ReactNode } from 'react'
import { Badge, Num, Table, TableBody, TableHead, TableRow, Td, Th } from '@/components/ui'
import { SegmentLink } from '@/components/runs/SegmentLink'
import { SampleFlagButtons, SampleFlagDetail, useSampleFlags } from '@/components/runs/SampleFlags'
import { formatPrecise } from '@/utils/numberFormat'
import { labDateOf } from '@/utils/labDate'
import { SampleDetails, hasDetails } from './SampleDetails'
import type { SampleRow } from './sampleRows'

/** Which page the table sits on: one segment (the detail page's Results tab) or a
 *  whole run (the HPHT and Core Flood run pages). */
export type SampleScope = 'segment' | 'run'
/** The experiment kind; a column can be limited to the kinds whose rows carry it. */
export type SampleKind = 'hpht' | 'core-flood' | 'other'

type Group = 'GC' | 'Solution' | 'Core flood'

export interface SampleColumn {
  key: string
  head: ReactNode
  /** Accessible header text where `head` is markup. */
  label?: string
  group?: Group
  scope: SampleScope | 'both'
  kinds?: SampleKind[]
  /** A running total: left off side-sample tables, whose rows are raw values. */
  runTotal?: boolean
  cell: (r: SampleRow) => ReactNode
}

const CELL = 'font-mono-data text-xs'
const GROUP = 'text-center border-l border-surface-border'
// Segment then Date stay put while the table scrolls sideways (Mat, 2026-11-10:
// segment first). Segment has a fixed width (fits CF_020-5_Background2) so Date can
// pin right after it; on the Results tab, with no Segment, Date pins at the left.
const STICKY_SEGMENT = 'sticky left-0 z-10 w-44 min-w-[11rem] max-w-[11rem] truncate'
const STICKY_DATE_AFTER_SEGMENT = 'sticky left-44 z-10'
const STICKY_DATE_FIRST = 'sticky left-0 z-10'
const STICKY_HEAD_BG = 'bg-surface-overlay'
const STICKY_ROW_BG = 'bg-surface-raised group-hover:bg-surface-overlay'

/** Headers are upper-cased by CSS, which turns µ into Greek capital Mu ("MMOL" reads
 *  as millimoles), so the µ prefix is kept lower case. */
const umol = <>H₂ <span className="normal-case">µ</span>mol</>

const num = (v: (r: SampleRow) => number | null) => (r: SampleRow) => <Num value={v(r)} />

/** Every column in display order. The lead columns (no group) come first, then
 *  GC, Solution and Core flood. Issue #163: one spec for all three tables. */
export const SAMPLE_COLUMNS: readonly SampleColumn[] = [
  { key: 'segment', head: 'Segment', scope: 'run', cell: (r) => <SegmentLink id={r.experimentId} /> },
  { key: 'date', head: 'Date', scope: 'both', cell: (r) => (r.date ? labDateOf(r.date) : '—') },
  { key: 'day', head: 'Day', scope: 'both', cell: (r) => formatPrecise(r.day) },
  { key: 'tube', head: 'Tube', scope: 'both', cell: (r) => formatPrecise(r.tube) },
  { key: 'note', head: 'Result note', scope: 'both', cell: () => null }, // rendered with the flags
  { key: 'h2Ppm', head: 'H₂ ppm', group: 'GC', scope: 'both', cell: num((r) => r.h2Ppm) },
  { key: 'h2Umol', head: umol, label: 'H₂ µmol', group: 'GC', scope: 'both', cell: num((r) => r.h2Umol) },
  { key: 'h2Gt', head: 'H₂ g/t', group: 'GC', scope: 'both', cell: num((r) => r.h2Gt) },
  { key: 'cumH2Gt', head: 'Cum. H₂ g/t', group: 'GC', scope: 'run', runTotal: true, cell: num((r) => r.cumH2Gt) },
  { key: 'h2GtPerDay', head: 'g/t/day', group: 'GC', scope: 'run', runTotal: true, cell: num((r) => r.h2GtPerDay) },
  // v_core_flood_samples has no Fe²⁺ yield, so the column is not shown for core floods.
  {
    key: 'fe2H2Pct', head: 'Fe²⁺ H₂ %', group: 'GC', scope: 'both', kinds: ['hpht', 'other'],
    cell: num((r) => r.fe2H2Pct),
  },
  { key: 'ph', head: 'pH', group: 'Solution', scope: 'both', cell: num((r) => r.ph) },
  { key: 'cond', head: 'Cond.', group: 'Solution', scope: 'both', cell: num((r) => r.cond) },
  // The Results tab's rows carry no sampling volume.
  { key: 'liqMl', head: 'Liq mL', group: 'Solution', scope: 'run', cell: num((r) => r.liqMl) },
  {
    key: 'flow', head: 'Flow', group: 'Core flood', scope: 'run', kinds: ['core-flood'],
    cell: (r) => (
      <>
        <Num value={r.flow} precise />
        {r.flow === 0 && <Badge variant="warning" className="ml-2">HOLD</Badge>}
      </>
    ),
  },
  {
    key: 'permFlow', head: 'Perm. flow', group: 'Core flood', scope: 'run', kinds: ['core-flood'],
    cell: (r) => (
      <>
        <Num value={r.permFlow} precise />
        {r.permFlow != null && <Badge variant="info" className="ml-2">PERM</Badge>}
      </>
    ),
  },
  { key: 'inletPsi', head: 'Inlet psi', group: 'Core flood', scope: 'run', kinds: ['core-flood'], cell: num((r) => r.inletPsi) },
  { key: 'outletPsi', head: 'Outlet psi', group: 'Core flood', scope: 'run', kinds: ['core-flood'], cell: num((r) => r.outletPsi) },
]

/** The columns a table shows for its scope, kind and side-sample setting. */
export function columnsFor(scope: SampleScope, kind: SampleKind, variant = false): SampleColumn[] {
  return SAMPLE_COLUMNS.filter((c) =>
    (c.scope === 'both' || c.scope === scope)
    && (c.kinds === undefined || c.kinds.includes(kind))
    && !(variant && c.runTotal),
  )
}

/** Header-group spans in column order: [label or null for the lead columns, span]. */
function groupSpans(columns: SampleColumn[]): [Group | null, number][] {
  const spans: [Group | null, number][] = []
  for (const c of columns) {
    const g = c.group ?? null
    const last = spans[spans.length - 1]
    if (last && last[0] === g) last[1] += 1
    else spans.push([g, 1])
  }
  return spans
}

interface Props<S> {
  /** In display order. */
  rows: SampleRow<S>[]
  scope: SampleScope
  kind: SampleKind
  /** Side samples (blanks, bypasses, variants): raw values, no running totals. */
  variant?: boolean
  /** Row click (or Enter) edits; rows `canEdit` rejects are not clickable. */
  onEdit?: (source: S) => void
  canEdit?: (row: SampleRow<S>) => boolean
  /** ICP element ppm by result id; a row gets an ICP flag only when present. */
  icpByResult: Map<number, Record<string, number>>
  /** Page-specific DETAILS content shown above run dates and notes. */
  detailsExtra?: (row: SampleRow<S>) => ReactNode
  /** Shown in place of rows when there are none; omit to show the header alone. */
  emptyText?: string
}

/** The samples table of the Results tab and both run pages (issue #163): one
 *  column spec, one interaction model (click a row to edit), and the ICP, MOD
 *  and DETAILS flags beside the result note. */
export function RunSamplesTable<S>({
  rows, scope, kind, variant = false, onEdit, canEdit = () => true, icpByResult, detailsExtra, emptyText,
}: Props<S>) {
  const flags = useSampleFlags()
  const columns = columnsFor(scope, kind, variant)
  const spans = groupSpans(columns)
  const hasSegment = columns[0]?.key === 'segment'
  const stickyFor = (key: string) =>
    key === 'segment' ? STICKY_SEGMENT
      : key === 'date' ? (hasSegment ? STICKY_DATE_AFTER_SEGMENT : STICKY_DATE_FIRST)
        : null

  return (
    <Table>
      <TableHead>
        <tr>
          {spans.map(([group, span], i) =>
            group === null
              ? <td key={i} colSpan={span} aria-hidden="true" />
              : <Th key={i} colSpan={span} className={GROUP}>{group}</Th>,
          )}
        </tr>
        <tr>
          {columns.map((c) => {
            const sticky = stickyFor(c.key)
            return (
              <Th key={c.key} aria-label={c.label} className={sticky ? `${sticky} ${STICKY_HEAD_BG}` : ''}>
                {c.head}
              </Th>
            )
          })}
        </tr>
      </TableHead>
      <TableBody>
        {rows.length === 0 && emptyText && (
          <TableRow>
            <Td colSpan={columns.length} className="text-center py-8 text-ink-muted">{emptyText}</Td>
          </TableRow>
        )}
        {rows.map((r) => {
          const icp = icpByResult.get(r.resultId)
          const date = r.date ? labDateOf(r.date) : '—'
          // Unique per row: side samples by experiment, others by tube when known.
          const which = variant
            ? `${r.experimentId} ${date}`
            : r.tube != null ? `${date}, tube ${r.tube}` : date
          const extra = detailsExtra?.(r)
          const showDetails = hasDetails(r, extra != null)
          const editable = onEdit !== undefined && canEdit(r)
          const note = r.notes
            .filter((n) => n.note_type === 'result_note' || n.note_type === 'observation')
            .map((n) => n.note_text)
            .join(' · ')
          return (
            <Fragment key={r.resultId}>
              <TableRow
                className={`group ${editable ? 'cursor-pointer' : ''}`}
                data-testid={`sample-${r.resultId}`}
                tabIndex={editable ? 0 : undefined}
                onClick={editable ? () => onEdit(r.source) : undefined}
                onKeyDown={editable
                  ? (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) onEdit(r.source) }
                  : undefined}
              >
                {columns.map((c) => {
                  const sticky = stickyFor(c.key)
                  if (c.key === 'note') {
                    return (
                      <Td key={c.key} className="text-xs">
                        <span className="inline-flex items-center gap-2">
                          <span className="block max-w-[16rem] truncate" title={note}>{note}</span>
                          <SampleFlagButtons
                            resultId={r.resultId}
                            icpLabel={`Show ICP for ${which}`}
                            modLabel={`Show modification for ${which}`}
                            detailsLabel={`Show details for ${which}`}
                            icp={icp}
                            notes={r.notes}
                            hasDetails={showDetails}
                            flags={flags}
                          />
                        </span>
                      </Td>
                    )
                  }
                  return (
                    <Td
                      key={c.key}
                      className={[
                        CELL,
                        c.key === 'date' ? 'text-ink-muted' : '',
                        sticky ? `${sticky} ${STICKY_ROW_BG}` : '',
                      ].join(' ')}
                      title={c.key === 'segment' ? r.experimentId : undefined}
                    >
                      {c.key === 'day' && scope === 'segment' && r.isPrimary && (
                        <span className="text-ink-muted mr-1" title="Primary result for this timepoint">★</span>
                      )}
                      {c.cell(r)}
                    </Td>
                  )
                })}
              </TableRow>
              <SampleFlagDetail
                resultId={r.resultId}
                colSpan={columns.length}
                icp={icp}
                notes={r.notes}
                details={showDetails ? <SampleDetails row={r} extra={extra} /> : undefined}
                flags={flags}
              />
            </Fragment>
          )
        })}
      </TableBody>
    </Table>
  )
}
