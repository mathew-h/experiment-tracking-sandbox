import { Fragment, useState } from 'react'
import type { CoreFloodSample } from '@/api/coreFloods'
import { Badge, Table, TableBody, TableHead, TableRow, Td, Th } from '@/components/ui'
import { labDateOf } from '@/utils/labDate'
import { fmt, noteSummary } from './fields'
import { IcpList } from '@/components/icp/IcpList'

interface Props {
  samples: CoreFloodSample[]
  /** Side samples: the same columns, plus the segment ID under the date (blanks, bypasses). */
  variant: boolean
  onEdit: (s: CoreFloodSample) => void
  /** ICP element ppm by result id; a row gets an expander only when present. */
  icpByResult: Map<number, Record<string, number>>
}

const CELL = 'font-mono-data text-xs'
const COLS = 14
const GROUP = 'text-center border-l border-surface-border'
// Expander and Date stay put while the table scrolls sideways; opaque so cells do not show through.
const STICKY_EXPANDER = 'sticky left-0 z-10 w-10 min-w-[2.5rem] max-w-[2.5rem]'
const STICKY_DATE = 'sticky left-10 z-10'
const STICKY_HEAD_BG = 'bg-surface-overlay'
const STICKY_ROW_BG = 'bg-surface-raised group-hover:bg-surface-overlay'

/** Core flood samples, newest first (the server sends oldest first); values go through `fmt`. */
export function SamplesTable({ samples, variant, onEdit, icpByResult }: Props) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const toggle = (id: number) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (!next.delete(id)) next.add(id)
      return next
    })
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
          <Th className={`${STICKY_EXPANDER} ${STICKY_HEAD_BG}`}><span className="sr-only">ICP</span></Th>
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
          const isOpen = icp !== undefined && expanded.has(s.result_id)
          const date = s.sample_date ? labDateOf(s.sample_date) : '—'
          const note = noteSummary(s)
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
                <Td className={`${STICKY_EXPANDER} ${STICKY_ROW_BG}`}>
                  {icp !== undefined && (
                    <button
                      type="button"
                      aria-label={
                        variant
                          ? `Show ICP for ${s.experiment_id} ${date}`
                          : s.sample_tube_number != null
                            ? `Show ICP for ${date}, tube ${s.sample_tube_number}`
                            : `Show ICP for ${date}`
                      }
                      aria-expanded={isOpen}
                      className="text-ink-muted hover:text-ink-primary px-1"
                      onClick={(e) => {
                        e.stopPropagation()
                        toggle(s.result_id)
                      }}
                    >
                      {isOpen ? '▾' : '▸'}
                    </button>
                  )}
                </Td>
                <Td className={`${CELL} text-ink-muted ${STICKY_DATE} ${STICKY_ROW_BG}`}>
                  {date}
                  {variant && <div className="text-ink-secondary">{s.experiment_id}</div>}
                </Td>
                <Td className={CELL}>{fmt(s.cumulative_time_post_reaction_days)}</Td>
                <Td className={CELL}>{fmt(s.sample_tube_number)}</Td>
                <Td className="text-xs">
                  <span className="inline-flex items-center gap-2">
                    <span className="block max-w-[16rem] truncate" title={note.text}>{note.text}</span>
                    {note.hasModification && <Badge variant="info">MOD</Badge>}
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
              {isOpen && (
                <tr className="bg-surface-overlay">
                  <Td colSpan={COLS} className="px-6 py-2">
                    <IcpList elements={icp} />
                  </Td>
                </tr>
              )}
            </Fragment>
          )
        })}
      </TableBody>
    </Table>
  )
}
