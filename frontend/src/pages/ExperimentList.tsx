import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { experimentsApi } from '@/api/experiments'
import {
  Table, TableHead, TableBody, TableRow, Th, Td,
  Button, Input, Select, PageSpinner,
} from '@/components/ui'

const STATUS_OPTIONS = [
  { value: 'ONGOING', label: 'Ongoing' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'CANCELLED', label: 'Cancelled' },
]
const TYPE_OPTIONS = [
  { value: 'Serum', label: 'Serum' },
  { value: 'HPHT', label: 'HPHT' },
  { value: 'Autoclave', label: 'Autoclave' },
  { value: 'Core Flood', label: 'Core Flood' },
]
const PAGE_SIZES = [25, 50, 100]

export function ExperimentListPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [statusFilter, setStatusFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [sampleFilter, setSampleFilter] = useState('')
  const [reactorFilter, setReactorFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [skip, setSkip] = useState(0)
  const [limit, setLimit] = useState(25)

  const queryKey = ['experiments', statusFilter, typeFilter, sampleFilter, reactorFilter, dateFrom, dateTo, skip, limit]
  const { data, isLoading, error } = useQuery({
    queryKey,
    queryFn: () => experimentsApi.list({
      status: statusFilter || undefined,
      experiment_type: typeFilter || undefined,
      sample_id: sampleFilter || undefined,
      reactor_number: reactorFilter ? parseInt(reactorFilter) : undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      skip,
      limit,
    }),
  })

  const statusMutation = useMutation({
    mutationFn: ({ experimentId, status }: { experimentId: string; status: string }) =>
      experimentsApi.patchStatus(experimentId, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['experiments'] }),
  })

  const resetPage = () => setSkip(0)
  const totalPages = data ? Math.ceil(data.total / limit) : 0
  const currentPage = Math.floor(skip / limit) + 1
  const hasActiveFilters = !!(statusFilter || typeFilter || sampleFilter || reactorFilter || dateFrom || dateTo)

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-ink-primary">Experiments</h1>
          <p className="text-xs text-ink-muted mt-0.5">
            {data ? `${data.total} total` : '…'}
          </p>
        </div>
        <Button
          variant="primary"
          size="sm"
          onClick={() => navigate('/experiments/new')}
          leftIcon={
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path d="M6 1v10M1 6h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          }
        >
          New Experiment
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-2">
        <div className="w-40">
          <Select
            label=""
            options={STATUS_OPTIONS}
            placeholder="All statuses"
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); resetPage() }}
          />
        </div>
        <div className="w-40">
          <Select
            label=""
            options={TYPE_OPTIONS}
            placeholder="All types"
            value={typeFilter}
            onChange={(e) => { setTypeFilter(e.target.value); resetPage() }}
          />
        </div>
        <div className="w-36">
          <Input
            placeholder="Sample ID…"
            value={sampleFilter}
            onChange={(e) => { setSampleFilter(e.target.value); resetPage() }}
          />
        </div>
        <div className="w-24">
          <Input
            placeholder="Reactor #"
            value={reactorFilter}
            onChange={(e) => { setReactorFilter(e.target.value); resetPage() }}
          />
        </div>
        <div className="w-36">
          <Input
            type="date"
            placeholder="From"
            value={dateFrom}
            onChange={(e) => { setDateFrom(e.target.value); resetPage() }}
          />
        </div>
        <div className="w-36">
          <Input
            type="date"
            placeholder="To"
            value={dateTo}
            onChange={(e) => { setDateTo(e.target.value); resetPage() }}
          />
        </div>
        {hasActiveFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setStatusFilter(''); setTypeFilter(''); setSampleFilter('')
              setReactorFilter(''); setDateFrom(''); setDateTo(''); resetPage()
            }}
          >
            Clear
          </Button>
        )}
      </div>

      {isLoading && <PageSpinner />}
      {error && <p className="text-sm text-red-400 py-4">Failed to load experiments</p>}

      {data && (
        <>
          <Table>
            <TableHead>
              <tr>
                <Th>#</Th>
                <Th>Experiment ID</Th>
                <Th>Description</Th>
                <Th>Sample</Th>
                <Th>Reactor</Th>
                <Th>Status</Th>
                <Th>Date</Th>
                <Th>Additives</Th>
              </tr>
            </TableHead>
            <TableBody>
              {data.items.length === 0 ? (
                <TableRow>
                  <Td colSpan={8} className="text-center py-8 text-ink-muted">No experiments found</Td>
                </TableRow>
              ) : (
                data.items.map((exp) => (
                  <TableRow
                    key={exp.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/experiments/${exp.experiment_id}`)}
                  >
                    <Td className="font-mono-data text-ink-muted">{exp.experiment_number}</Td>
                    <Td>
                      <span className="font-mono-data text-red-400 hover:text-red-300">
                        {exp.experiment_id}
                      </span>
                    </Td>
                    <Td className="text-xs text-ink-secondary max-w-48 truncate">
                      {exp.condition_note ?? <span className="text-ink-muted">—</span>}
                    </Td>
                    <Td className="font-mono-data text-xs">
                      {exp.sample_id ?? <span className="text-ink-muted">—</span>}
                    </Td>
                    <Td className="font-mono-data text-xs">
                      {exp.reactor_number ?? <span className="text-ink-muted">—</span>}
                    </Td>
                    <Td onClick={(e) => e.stopPropagation()}>
                      <select
                        className="bg-surface-card border border-surface-border rounded px-1.5 py-0.5 text-xs text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50"
                        value={exp.status ?? ''}
                        onChange={(e) =>
                          statusMutation.mutate({ experimentId: exp.experiment_id, status: e.target.value })
                        }
                      >
                        {STATUS_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    </Td>
                    <Td className="font-mono-data text-xs text-ink-muted">{exp.date ? exp.date.slice(0, 10) : '—'}</Td>
                    <Td className="text-xs text-ink-secondary max-w-48 truncate">
                      {exp.additives_summary ?? <span className="text-ink-muted">—</span>}
                    </Td>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>

          {/* Pagination */}
          <div className="flex items-center justify-between text-xs text-ink-muted pt-1">
            <div className="flex items-center gap-2">
              <span>Rows per page:</span>
              {PAGE_SIZES.map((size) => (
                <button
                  key={size}
                  onClick={() => { setLimit(size); resetPage() }}
                  className={`px-2 py-0.5 rounded ${limit === size ? 'bg-surface-raised text-ink-primary' : 'hover:text-ink-secondary'}`}
                >
                  {size}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-3">
              <span>Page {currentPage} of {totalPages || 1}</span>
              <Button
                variant="ghost"
                size="xs"
                disabled={skip === 0}
                onClick={() => setSkip(Math.max(0, skip - limit))}
              >
                ←
              </Button>
              <Button
                variant="ghost"
                size="xs"
                disabled={skip + limit >= data.total}
                onClick={() => setSkip(skip + limit)}
              >
                →
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
