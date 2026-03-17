import { useQuery } from '@tanstack/react-query'
import { analysisApi } from '@/api/analysis'
import { Table, TableHead, TableBody, TableRow, Th, Td, TdValue, Card, CardHeader, CardBody, PageSpinner } from '@/components/ui'

export function AnalysisPage() {
  const { data: pxrfReadings, isLoading, error } = useQuery({
    queryKey: ['pxrf'],
    queryFn: () => analysisApi.listPXRF({ limit: 100 }),
  })

  const elements = ['fe', 'mg', 'ni', 'cu', 'si', 'co', 'mo', 'al', 'ca'] as const

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-ink-primary">Analysis</h1>
        <p className="text-xs text-ink-muted mt-0.5">XRD, pXRF, and external analytical data</p>
      </div>

      <Card padding="none">
        <CardHeader label="pXRF Readings">
          <span className="text-2xs text-ink-muted">
            {pxrfReadings ? `${pxrfReadings.length} readings` : ''}
          </span>
        </CardHeader>
        <CardBody>
          {isLoading && <PageSpinner />}
          {error && <p className="text-sm text-red-400">Failed to load pXRF data</p>}
          {pxrfReadings && (
            <Table>
              <TableHead>
                <tr>
                  <Th>Reading No.</Th>
                  {elements.map((el) => <Th key={el} className="text-right">{el.toUpperCase()}</Th>)}
                  <Th>Ingested</Th>
                </tr>
              </TableHead>
              <TableBody>
                {pxrfReadings.length === 0 ? (
                  <TableRow>
                    <Td colSpan={elements.length + 2} className="text-center py-8 text-ink-muted">No readings</Td>
                  </TableRow>
                ) : (
                  pxrfReadings.map((r) => (
                    <TableRow key={r.reading_no}>
                      <Td className="font-mono-data text-ink-primary">{r.reading_no}</Td>
                      {elements.map((el) => (
                        <TdValue key={el}>
                          {r[el] != null ? r[el]!.toFixed(1) : <span className="text-ink-muted">—</span>}
                        </TdValue>
                      ))}
                      <Td className="font-mono-data text-ink-muted">
                        {new Date(r.ingested_at).toLocaleDateString()}
                      </Td>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </CardBody>
      </Card>

      <Card padding="none">
        <CardHeader label="XRD Analysis" />
        <CardBody>
          <p className="text-sm text-ink-muted text-center py-6">
            Select an experiment from the Experiments page to view XRD phase data.
          </p>
        </CardBody>
      </Card>
    </div>
  )
}
