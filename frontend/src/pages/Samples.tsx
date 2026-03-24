import { useQuery } from '@tanstack/react-query'
import { samplesApi } from '@/api/samples'
import { Table, TableHead, TableBody, TableRow, Th, Td, Badge, PageSpinner } from '@/components/ui'

/** Sample inventory page — stub for M9 implementation. */
export function SamplesPage() {
  const { data: samples, isLoading, error } = useQuery({
    queryKey: ['samples'],
    queryFn: () => samplesApi.list({ limit: 500 }),
  })

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-ink-primary">Samples</h1>
        <p className="text-xs text-ink-muted mt-0.5">
          {samples ? `${samples.length} samples` : 'Geological sample inventory'}
        </p>
      </div>

      {isLoading && <PageSpinner />}
      {error && <p className="text-sm text-red-400">Failed to load samples</p>}

      {samples && (
        <Table>
          <TableHead>
            <tr>
              <Th>Sample ID</Th>
              <Th>Classification</Th>
              <Th>Location</Th>
              <Th>Characterized</Th>
            </tr>
          </TableHead>
          <TableBody>
            {samples.length === 0 ? (
              <TableRow>
                <Td colSpan={4} className="text-center py-8 text-ink-muted">No samples found</Td>
              </TableRow>
            ) : (
              samples.map((s) => (
                <TableRow key={s.sample_id}>
                  <Td className="font-mono-data text-ink-primary">{s.sample_id}</Td>
                  <Td>{s.rock_classification ?? <span className="text-ink-muted">—</span>}</Td>
                  <Td className="text-ink-muted">
                    {[s.locality, s.state, s.country].filter(Boolean).join(', ') || '—'}
                  </Td>
                  <Td>
                    <Badge variant={s.characterized ? 'success' : 'default'}>
                      {s.characterized ? 'Yes' : 'No'}
                    </Badge>
                  </Td>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
