import type { ExperimentListItem } from '@/api/experiments'
import { Table, TableHead, TableBody, TableRow, Th, Td, StatusBadge } from '@/components/ui'
import { labDateOf } from '@/utils/labDate'

const COLUMN_COUNT = 8

interface ExportResultsTableProps {
  rows: ExperimentListItem[]
  selected: ReadonlySet<string>
  onToggle: (row: ExperimentListItem) => void
  onToggleAll: () => void
}

/** Selection key: a collapsed vial row is identified by its stem, not the representative vial. */
export const rowKey = (row: ExperimentListItem) => row.group_display_id ?? row.experiment_id

/** Checkbox table of experiments matching the export filters. */
export function ExportResultsTable({ rows, selected, onToggle, onToggleAll }: ExportResultsTableProps) {
  const allSelected = rows.length > 0 && rows.every((r) => selected.has(rowKey(r)))

  return (
    <Table>
      <TableHead>
        <tr>
          <Th className="w-8">
            <input
              type="checkbox"
              aria-label="Select all shown"
              checked={allSelected}
              onChange={onToggleAll}
              className="accent-brand-red"
            />
          </Th>
          <Th>ID</Th>
          <Th>Type</Th>
          <Th>Status</Th>
          <Th>Start date</Th>
          <Th>Last result</Th>
          <Th>Description</Th>
          <Th>Additives</Th>
        </tr>
      </TableHead>
      <TableBody>
        {rows.length === 0 ? (
          <TableRow>
            <Td colSpan={COLUMN_COUNT} className="text-center py-8 text-ink-muted">No experiments found</Td>
          </TableRow>
        ) : (
          rows.map((row) => {
            const label = row.group_display_id ?? row.experiment_id
            const vials = row.vial_count ?? 1
            const isSelected = selected.has(rowKey(row))
            return (
              <TableRow key={row.experiment_id} className={isSelected ? 'bg-red-500/5' : ''}>
                <Td>
                  <input
                    type="checkbox"
                    aria-label={`Select ${label}`}
                    checked={isSelected}
                    onChange={() => onToggle(row)}
                    className="accent-brand-red"
                  />
                </Td>
                <Td className="font-mono-data">
                  {vials > 1 ? `${label} · ${vials} vials` : label}
                </Td>
                <Td className="text-xs text-ink-secondary">
                  {row.experiment_type ?? <span className="text-ink-muted">—</span>}
                </Td>
                <Td>
                  {row.status ? <StatusBadge status={row.status} /> : <span className="text-ink-muted">—</span>}
                </Td>
                {/* Lab-local, matching the server's Started from/to filter. */}
                <Td className="font-mono-data text-xs text-ink-muted">
                  {row.date ? labDateOf(row.date) : '—'}
                </Td>
                {/* Already a lab-local calendar date from the server: no slicing. */}
                <Td className="font-mono-data text-xs text-ink-muted">
                  {row.last_result_date ?? '—'}
                </Td>
                <Td className="text-xs text-ink-secondary max-w-48 truncate">
                  {row.description ?? <span className="text-ink-muted">—</span>}
                </Td>
                <Td className="text-xs text-ink-secondary max-w-48 truncate">
                  {row.additives_summary ?? <span className="text-ink-muted">—</span>}
                </Td>
              </TableRow>
            )
          })
        )}
      </TableBody>
    </Table>
  )
}
