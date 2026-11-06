import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { coreFloodsApi } from '@/api/coreFloods'
import {
  Table, TableHead, TableBody, TableRow, Th, Td,
  Badge, Input, PageSpinner,
} from '@/components/ui'
import { labDateOf } from '@/utils/labDate'

const SEARCH_DEBOUNCE_MS = 250

const SCOPES = [
  { value: 'active', label: 'Active' },
  { value: 'all', label: 'All' },
] as const

/** Core flood runs, one row per base ID, with an Active/All scope toggle and search. */
export function CoreFloodListPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const scope = searchParams.get('scope') === 'all' ? 'all' : 'active'

  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setQ(search.trim()), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [search])

  const { data, isLoading, error } = useQuery({
    queryKey: ['core-floods', scope, q],
    queryFn: () => coreFloodsApi.list(q ? { scope, q } : { scope }),
  })

  const setScope = (next: 'active' | 'all') => {
    setSearchParams(next === 'all' ? { scope: 'all' } : {}, { replace: true })
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-ink-primary">Core Floods</h1>
        <p className="text-xs text-ink-muted mt-0.5">
          {data ? `${data.length} ${data.length === 1 ? 'run' : 'runs'}` : '…'}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded border border-surface-border p-0.5" role="group" aria-label="Scope">
          {SCOPES.map((s) => (
            <button
              key={s.value}
              type="button"
              aria-pressed={scope === s.value}
              onClick={() => setScope(s.value)}
              className={`px-3 py-1 text-xs rounded ${
                scope === s.value
                  ? 'bg-surface-raised text-ink-primary'
                  : 'text-ink-muted hover:text-ink-secondary'
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
        <div className="w-56">
          <Input
            placeholder="Search runs…"
            aria-label="Search runs"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {isLoading && <PageSpinner />}
      {error && (
        <p className="text-sm text-red-400 py-4">
          Failed to load core floods: {(error as Error).message}
        </p>
      )}

      {data && (
        <div className="overflow-x-auto">
          <Table>
            <TableHead>
              <tr>
                <Th>Run</Th>
                <Th>Description</Th>
                <Th>Rig</Th>
                <Th>Samples</Th>
                <Th>Last sample</Th>
                <Th>Status</Th>
              </tr>
            </TableHead>
            <TableBody>
              {data.length === 0 ? (
                <TableRow>
                  <Td colSpan={6} className="text-center py-8 text-ink-muted">
                    {q || scope === 'all' ? 'No core floods match' : 'No active core floods'}
                  </Td>
                </TableRow>
              ) : (
                data.map((run) => (
                  <TableRow key={run.base_id}>
                    <Td>
                      <Link
                        to={`/core-floods/${encodeURIComponent(run.base_id)}`}
                        className="font-mono-data text-red-400 hover:text-red-300"
                      >
                        {run.base_id}
                      </Link>
                    </Td>
                    <Td className="text-xs max-w-md !whitespace-normal">
                      {run.description ?? <span className="text-ink-muted">—</span>}
                    </Td>
                    <Td className="font-mono-data text-xs">
                      {run.rig ?? <span className="text-ink-muted">—</span>}
                    </Td>
                    <Td className="font-mono-data text-xs">{run.sample_count}</Td>
                    <Td className="font-mono-data text-xs text-ink-muted">
                      {run.last_sample_date ? labDateOf(run.last_sample_date) : '—'}
                    </Td>
                    <Td>
                      {run.ongoing_experiment_ids.length > 0 ? (
                        <Badge variant="ongoing">Ongoing</Badge>
                      ) : (
                        <span className="text-xs text-ink-muted">Completed</span>
                      )}
                    </Td>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
