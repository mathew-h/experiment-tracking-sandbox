import { Fragment } from 'react'
import type { HphtSample } from '@/api/hpht'
import { Table, TableBody, TableHead, TableRow, Td, Th } from '@/components/ui'
import { SegmentLink } from '@/components/runs/SegmentLink'
import { SampleFlagButtons, SampleFlagDetail, useSampleFlags } from '@/components/runs/SampleFlags'
import { fmt } from '@/components/results/sampleFields'
import { noteSummary } from '@/pages/CoreFloods/fields'
import { labDateOf } from '@/utils/labDate'

interface Props {
  samples: HphtSample[]
  /** Side samples (variants): raw values only, so the running-total columns are dropped. */
  variant: boolean
  onEdit: (s: HphtSample) => void
  /** ICP element ppm by result id; a row gets an ICP flag only when present. */
  icpByResult: Map<number, Record<string, number>>
}

const CELL = 'font-mono-data text-xs'
const GROUP = 'text-center border-l border-surface-border'
// Date stays put while the table scrolls sideways; opaque so cells do not show through.
// The ICP expander column it once shared the edge with is gone (issue #164).
const STICKY_DATE = 'sticky left-0 z-10'
const STICKY_HEAD_BG = 'bg-surface-overlay'
const STICKY_ROW_BG = 'bg-surface-raised group-hover:bg-surface-overlay'

type Column = { head: string; value: (s: HphtSample) => number | null; runTotal?: boolean }

const GC_COLUMNS: readonly Column[] = [
  { head: 'H₂ ppm', value: (s) => s.h2_concentration },
  { head: 'H₂ µmol', value: (s) => s.h2_micromoles },
  { head: 'H₂ g/t', value: (s) => s.h2_grams_per_ton_yield },
  { head: 'Cum. H₂ g/t', value: (s) => s.cumulative_h2_grams_per_ton, runTotal: true },
  { head: 'g/t/day', value: (s) => s.h2_grams_per_ton_per_day, runTotal: true },
  { head: 'Fe²⁺ H₂ %', value: (s) => s.ferrous_iron_yield_h2_pct },
]
const SOLUTION_COLUMNS: readonly Column[] = [
  { head: 'pH', value: (s) => s.final_ph },
  { head: 'Cond.', value: (s) => s.final_conductivity_mS_cm },
]
const LEAD_COLUMNS = 5 // Date, Day, Segment, Tube, Result Note/Sample Description

/** Headers are upper-cased by CSS, which turns µ into Greek capital Mu ("MMOL" reads
 *  as millimoles), so the µ prefix is kept lower case. */
function headLabel(head: string) {
  const [before, after] = head.split('µ')
  if (after === undefined) return head
  return <>{before}<span className="normal-case">µ</span>{after}</>
}

/** HPHT run samples, newest first (the server sends oldest first). Clicking a row edits it. */
export function HphtSamplesTable({ samples, variant, onEdit, icpByResult }: Props) {
  // Issue #164: the ICP and MOD flags open their own sections under the row.
  const flags = useSampleFlags()
  const gc = GC_COLUMNS.filter((c) => !variant || !c.runTotal)
  const colCount = LEAD_COLUMNS + gc.length + SOLUTION_COLUMNS.length
  const rows = [...samples].reverse()

  return (
    <Table>
      <TableHead>
        <tr>
          <td colSpan={LEAD_COLUMNS} aria-hidden="true" />
          <Th colSpan={gc.length} className={GROUP}>GC</Th>
          <Th colSpan={SOLUTION_COLUMNS.length} className={GROUP}>Solution</Th>
        </tr>
        <tr>
          <Th className={`${STICKY_DATE} ${STICKY_HEAD_BG}`}>Date</Th>
          <Th>Day</Th>
          <Th>Segment</Th>
          <Th>Tube</Th>
          <Th>Result Note/Sample Description</Th>
          {[...gc, ...SOLUTION_COLUMNS].map((c) => <Th key={c.head}>{headLabel(c.head)}</Th>)}
        </tr>
      </TableHead>
      <TableBody>
        {rows.length === 0 && (
          <TableRow>
            <Td colSpan={colCount} className="text-center py-8 text-ink-muted">No samples yet</Td>
          </TableRow>
        )}
        {rows.map((s) => {
          const icp = icpByResult.get(s.result_id)
          const date = s.sample_date ? labDateOf(s.sample_date) : '—'
          const note = noteSummary(s)
          return (
            <Fragment key={s.result_id}>
              <TableRow
                className="group cursor-pointer"
                tabIndex={0}
                data-testid={`sample-${s.result_id}`}
                onClick={() => onEdit(s)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && e.target === e.currentTarget) onEdit(s)
                }}
              >
                <Td className={`${CELL} text-ink-muted ${STICKY_DATE} ${STICKY_ROW_BG}`}>{date}</Td>
                <Td className={CELL}>{fmt(s.cumulative_time_post_reaction_days)}</Td>
                <Td className={CELL}>
                  {/* Issue #158: stops propagation, so the row's edit click does not fire. */}
                  <SegmentLink id={s.experiment_id} />
                </Td>
                <Td className={CELL}>{fmt(s.sample_tube_number)}</Td>
                <Td className="text-xs">
                  <span className="inline-flex items-center gap-2">
                    <span className="block max-w-[16rem] truncate" title={note.text}>{note.text}</span>
                    <SampleFlagButtons
                      resultId={s.result_id}
                      icpLabel={`Show ICP for ${s.experiment_id} ${date}`}
                      modLabel={`Show modification for ${s.experiment_id} ${date}`}
                      icp={icp}
                      notes={s.notes}
                      flags={flags}
                    />
                  </span>
                </Td>
                {[...gc, ...SOLUTION_COLUMNS].map((c) => (
                  <Td key={c.head} className={CELL}>{fmt(c.value(s))}</Td>
                ))}
              </TableRow>
              <SampleFlagDetail resultId={s.result_id} colSpan={colCount} icp={icp} notes={s.notes} flags={flags} />
            </Fragment>
          )
        })}
      </TableBody>
    </Table>
  )
}
