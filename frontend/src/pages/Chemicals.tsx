import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { chemicalsApi } from '@/api/chemicals'
import { Table, TableHead, TableBody, TableRow, Th, Td, TdValue, Input, PageSpinner } from '@/components/ui'

/** Chemical inventory page: searchable compound table and additive management. */
export function ChemicalsPage() {
  const [search, setSearch] = useState('')

  const { data: compounds, isLoading, error } = useQuery({
    queryKey: ['compounds', search],
    queryFn: () => chemicalsApi.listCompounds({ search: search || undefined, limit: 200 }),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-ink-primary">Chemicals</h1>
          <p className="text-xs text-ink-muted mt-0.5">
            {compounds ? `${compounds.length} compounds` : 'Chemical compound inventory'}
          </p>
        </div>
      </div>

      <div className="w-64">
        <Input
          placeholder="Search compounds…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          leftIcon={
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <circle cx="5" cy="5" r="4" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M10.5 10.5L8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          }
        />
      </div>

      {isLoading && <PageSpinner />}
      {error && <p className="text-sm text-red-400">Failed to load compounds</p>}

      {compounds && (
        <Table>
          <TableHead>
            <tr>
              <Th>Name</Th>
              <Th>Formula</Th>
              <Th>CAS</Th>
              <Th className="text-right">MW (g/mol)</Th>
              <Th>Preferred Unit</Th>
              <Th>Supplier</Th>
            </tr>
          </TableHead>
          <TableBody>
            {compounds.length === 0 ? (
              <TableRow>
                <Td colSpan={6} className="text-center py-8 text-ink-muted">No compounds found</Td>
              </TableRow>
            ) : (
              compounds.map((c) => (
                <TableRow key={c.id}>
                  <Td className="font-medium text-ink-primary">{c.name}</Td>
                  <Td className="font-mono-data">{c.formula ?? '—'}</Td>
                  <Td className="font-mono-data text-ink-muted">{c.cas_number ?? '—'}</Td>
                  <TdValue>{c.molecular_weight_g_mol?.toFixed(2) ?? '—'}</TdValue>
                  <Td className="font-mono-data text-ink-muted">{c.preferred_unit ?? '—'}</Td>
                  <Td className="text-ink-muted">{c.supplier ?? '—'}</Td>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
