import { Link } from 'react-router-dom'
import type { CoreFloodSegment } from '@/api/coreFloods'
import { StatusBadge, Table, TableBody, TableHead, TableRow, Td, Th } from '@/components/ui'
import { fmt } from './fields'

interface Props {
  baseId: string
  segments: CoreFloodSegment[]
}

/** The run's segments with read-only cells; segment edits are added per row. */
export function SegmentsTable({ segments }: Props) {
  return (
    <Table>
      <TableHead>
        <tr>
          <Th>Segment</Th>
          <Th>Status</Th>
          <Th>Description</Th>
          <Th>Pore volume (mL)</Th>
        </tr>
      </TableHead>
      <TableBody>
        {segments.map((seg) => (
          <TableRow key={seg.id}>
            <Td>
              <Link
                to={`/experiments/${encodeURIComponent(seg.experiment_id)}`}
                className="font-mono-data text-red-400 hover:text-red-300"
              >
                {seg.experiment_id}
              </Link>
            </Td>
            <Td>{seg.status ? <StatusBadge status={seg.status} /> : '—'}</Td>
            <Td className="text-xs">
              {seg.description ?? <span className="text-ink-muted">—</span>}
            </Td>
            <Td className="font-mono-data text-xs">{fmt(seg.pore_volume_mL)}</Td>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
