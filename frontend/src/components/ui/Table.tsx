import { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from 'react'

interface TableProps extends HTMLAttributes<HTMLTableElement> {
  striped?: boolean
}

/** Styled HTML table wrapper for data-dense lab tables. */
export function Table({ striped: _striped = false, className = '', children, ...props }: TableProps) {
  return (
    <div className="w-full overflow-x-auto rounded-lg border border-surface-border">
      <table
        className={['w-full text-sm border-collapse', className].join(' ')}
        {...props}
      >
        {children}
      </table>
    </div>
  )
}

/** thead wrapper applying sticky header styles. */
export function TableHead({ className = '', children, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead className={['bg-surface-overlay border-b border-surface-border', className].join(' ')} {...props}>
      {children}
    </thead>
  )
}

/** tbody wrapper for Table. */
export function TableBody({ className = '', children, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <tbody className={['divide-y divide-surface-border', className].join(' ')} {...props}>
      {children}
    </tbody>
  )
}

/** Table row with hover highlight and optional border. */
export function TableRow({ className = '', children, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={['bg-surface-raised hover:bg-surface-overlay transition-colors duration-75', className].join(' ')}
      {...props}
    >
      {children}
    </tr>
  )
}

/** Sortable-friendly column header cell with uppercase label styling. */
export function Th({ className = '', children, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={[
        'px-3 py-2.5 text-left text-2xs font-semibold text-ink-muted uppercase tracking-wider',
        'whitespace-nowrap',
        className,
      ].join(' ')}
      {...props}
    >
      {children}
    </th>
  )
}

/** Standard data cell with consistent padding and text color. */
export function Td({ className = '', children, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td
      className={['px-3 py-2.5 text-ink-secondary whitespace-nowrap', className].join(' ')}
      {...props}
    >
      {children}
    </td>
  )
}

// Mono data cell — for numeric values
/** Data cell styled for numeric/monospace values (right-aligned, font-mono-data). */
export function TdValue({ className = '', children, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td
      className={['px-3 py-2.5 font-mono-data text-ink-primary whitespace-nowrap text-right', className].join(' ')}
      {...props}
    >
      {children}
    </td>
  )
}
