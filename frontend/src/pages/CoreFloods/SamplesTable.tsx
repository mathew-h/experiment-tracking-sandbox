import type { CoreFloodSample } from '@/api/coreFloods'
import { Badge, Table, TableBody, TableHead, TableRow, Td, Th } from '@/components/ui'
import { labDateOf } from '@/utils/labDate'
import { fmt } from './fields'

interface Props {
  samples: CoreFloodSample[]
  /** Variant (side) samples carry no cumulative columns. */
  variant: boolean
  onEdit: (s: CoreFloodSample) => void
}

const CELL = 'font-mono-data text-xs'

/** Core flood samples in server order; every value is the server's, shown through `fmt`. */
export function SamplesTable({ samples, variant, onEdit }: Props) {
  return (
    <Table>
      <TableHead>
        <tr>
          <Th>Sample date</Th>
          <Th>Cum. day</Th>
          <Th>Segment</Th>
          <Th>Tube #</Th>
          <Th>Flow (mL/min)</Th>
          <Th>Liquid vol (mL)</Th>
          <Th>H₂ (ppm)</Th>
          <Th>H₂ (µmol)</Th>
          <Th>H₂ (g/t)</Th>
          {!variant && <Th>Cum. H₂ (g/t)</Th>}
          {!variant && <Th>g/t/day</Th>}
          {!variant && <Th>Pore volumes</Th>}
          <Th>pH</Th>
          <Th>Cond. (mS/cm)</Th>
        </tr>
      </TableHead>
      <TableBody>
        {samples.map((s) => (
          <TableRow
            key={s.result_id}
            className="cursor-pointer"
            tabIndex={0}
            onClick={() => onEdit(s)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onEdit(s)
            }}
          >
            <Td className={`${CELL} text-ink-muted`}>
              {s.sample_date ? labDateOf(s.sample_date) : '—'}
            </Td>
            <Td className={CELL}>{fmt(s.cumulative_time_post_reaction_days)}</Td>
            <Td className={CELL}>{s.experiment_id}</Td>
            <Td className={CELL}>{fmt(s.sample_tube_number)}</Td>
            <Td className={CELL}>
              {fmt(s.flow_rate_mL_min)}
              {s.flow_rate_mL_min === 0 && (
                <Badge variant="warning" className="ml-2">HOLD</Badge>
              )}
            </Td>
            <Td className={CELL}>{fmt(s.sampling_volume_mL)}</Td>
            <Td className={CELL}>{fmt(s.h2_concentration)}</Td>
            <Td className={CELL}>{fmt(s.h2_micromoles)}</Td>
            <Td className={CELL}>{fmt(s.h2_grams_per_ton_yield)}</Td>
            {!variant && <Td className={CELL}>{fmt(s.cumulative_h2_grams_per_ton)}</Td>}
            {!variant && <Td className={CELL}>{fmt(s.h2_grams_per_ton_per_day)}</Td>}
            {!variant && <Td className={CELL}>{fmt(s.cumulative_pore_volumes)}</Td>}
            <Td className={CELL}>{fmt(s.final_ph)}</Td>
            <Td className={CELL}>{fmt(s.final_conductivity_mS_cm)}</Td>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
