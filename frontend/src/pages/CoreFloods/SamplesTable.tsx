import { Fragment } from 'react'
import type { CoreFloodSample } from '@/api/coreFloods'
import { Badge, Table, TableBody, TableHead, TableRow, Td, Th } from '@/components/ui'
import { SegmentLink } from '@/components/runs/SegmentLink'
import { labDateOf } from '@/utils/labDate'
import { fmt, noteSummary } from './fields'
import { SampleFlagButtons, SampleFlagDetail, useSampleFlags } from '@/components/runs/SampleFlags'

interface Props {
  samples: CoreFloodSample[]
  /** Side samples (blanks, bypasses): the same columns. */
  variant: boolean
  onEdit: (s: CoreFloodSample) => void
  /** ICP element ppm by result id; a row gets an ICP flag only when present. */
  icpByResult: Map<number, Record<string, number>>
}

const CELL = 'font-mono-data text-xs'
const COLS = 14
const GROUP = 'text-center border-l border-surface-border'
// Segment then Date stay put while the table scrolls sideways (Mat, 2026-11-10: the
// segment comes first); opaque so cells do not show through. Segment has a fixed
// width (fits CF_020-5_Background2) so Date can pin right after it.
const STICKY_SEGMENT = 'sticky left-0 z-10 w-44 min-w-[11rem] max-w-[11rem] truncate'
const STICKY_DATE = 'sticky left-44 z-10'
const STICKY_HEAD_BG = 'bg-surface-overlay'
const STICKY_ROW_BG = 'bg-surface-raised group-hover:bg-surface-overlay'

/** Core flood samples, newest first (the server sends oldest first); values go through `fmt`. */
export function SamplesTable({ samples, variant, onEdit, icpByResult }: Props) {
  // Issue #164: the ICP and MOD flags open their own sections under the row.
  const flags = useSampleFlags()
  const rows = [...samples].reverse()

  return (
    <Table>
      <TableHead>
        <tr>
          <td colSpan={5} aria-hidden="true" />
          <Th colSpan={2} className={GROUP}>GC</Th>
          <Th colSpan={3} className={GROUP}>Solution</Th>
          <Th colSpan={4} className={GROUP}>Core flood</Th>
        </tr>
        <tr>
          <Th className={`${STICKY_SEGMENT} ${STICKY_HEAD_BG}`}>Segment</Th>
          <Th className={`${STICKY_DATE} ${STICKY_HEAD_BG}`}>Date</Th>
          <Th>Day</Th>
          <Th>Tube</Th>
          <Th>Result note</Th>
          <Th>H₂ ppm</Th>
          <Th>H₂ g/t</Th>
          <Th>pH</Th>
          <Th>Cond.</Th>
          <Th>Liq mL</Th>
          <Th>Flow</Th>
          <Th>Perm. flow</Th>
          <Th>Inlet psi</Th>
          <Th>Outlet psi</Th>
        </tr>
      </TableHead>
      <TableBody>
        {rows.map((s) => {
          const icp = icpByResult.get(s.result_id)
          const date = s.sample_date ? labDateOf(s.sample_date) : '—'
          const note = noteSummary(s)
          // Unique per row: side samples by experiment, main samples by tube when known.
          const which = variant
            ? `${s.experiment_id} ${date}`
            : s.sample_tube_number != null
              ? `${date}, tube ${s.sample_tube_number}`
              : date
          return (
            <Fragment key={s.result_id}>
              <TableRow
                className="group cursor-pointer"
                tabIndex={0}
                onClick={() => onEdit(s)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && e.target === e.currentTarget) onEdit(s)
                }}
              >
                <Td className={`${CELL} ${STICKY_SEGMENT} ${STICKY_ROW_BG}`} title={s.experiment_id}>
                  {/* Which segment the sample came from. The link stops propagation,
                      so the row's edit click does not fire. */}
                  <SegmentLink id={s.experiment_id} />
                </Td>
                <Td className={`${CELL} text-ink-muted ${STICKY_DATE} ${STICKY_ROW_BG}`}>
                  {date}
                </Td>
                <Td className={CELL}>{fmt(s.cumulative_time_post_reaction_days)}</Td>
                <Td className={CELL}>{fmt(s.sample_tube_number)}</Td>
                <Td className="text-xs">
                  <span className="inline-flex items-center gap-2">
                    <span className="block max-w-[16rem] truncate" title={note.text}>{note.text}</span>
                    <SampleFlagButtons
                      resultId={s.result_id}
                      icpLabel={`Show ICP for ${which}`}
                      modLabel={`Show modification for ${which}`}
                      icp={icp}
                      notes={s.notes}
                      flags={flags}
                    />
                  </span>
                </Td>
                <Td className={CELL}>{fmt(s.h2_concentration)}</Td>
                <Td className={CELL}>{fmt(s.h2_grams_per_ton_yield)}</Td>
                <Td className={CELL}>{fmt(s.final_ph)}</Td>
                <Td className={CELL}>{fmt(s.final_conductivity_mS_cm)}</Td>
                <Td className={CELL}>{fmt(s.sampling_volume_mL)}</Td>
                <Td className={CELL}>
                  {fmt(s.flow_rate_mL_min)}
                  {s.flow_rate_mL_min === 0 && (
                    <Badge variant="warning" className="ml-2">HOLD</Badge>
                  )}
                </Td>
                <Td className={CELL}>
                  {fmt(s.permeability_flow_rate_mL_min)}
                  {s.permeability_flow_rate_mL_min != null && (
                    <Badge variant="info" className="ml-2">PERM</Badge>
                  )}
                </Td>
                <Td className={CELL}>{fmt(s.inlet_pressure_psi)}</Td>
                <Td className={CELL}>{fmt(s.outlet_pressure_psi)}</Td>
              </TableRow>
              <SampleFlagDetail resultId={s.result_id} colSpan={COLS} icp={icp} notes={s.notes} flags={flags} />
            </Fragment>
          )
        })}
      </TableBody>
    </Table>
  )
}
