import { Fragment, useState, type ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { experimentsApi, type ExperimentListItem, type ExperimentStatus } from '@/api/experiments'
import {
  Table, TableHead, TableBody, TableRow, Th, Td,
  Button, Input, Select, PageSpinner,
} from '@/components/ui'

const STATUS_OPTIONS = [
  { value: 'QUEUED', label: 'Queued' },
  { value: 'ONGOING', label: 'Ongoing' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'CANCELLED', label: 'Cancelled' },
]

const STATUS_TEXT_CLASS: Record<string, string> = {
  ONGOING:   'text-status-ongoing',
  COMPLETED: 'text-status-completed',
  CANCELLED: 'text-status-cancelled',
  QUEUED:    'text-status-queued',
}
const TYPE_OPTIONS = [
  { value: 'Serum', label: 'Serum' },
  { value: 'HPHT', label: 'HPHT' },
  { value: 'Autoclave', label: 'Autoclave' },
  { value: 'Core Flood', label: 'Core Flood' },
]
const PAGE_SIZES = [25, 50, 100]

/** Paginated, filterable experiment list with status badges and quick-nav links. */
export function ExperimentListPage() {
  const navigate = useNavigate()

  const [statusFilter, setStatusFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [experimentIdFilter, setExperimentIdFilter] = useState('')
  const [sampleFilter, setSampleFilter] = useState('')
  const [reactorFilter, setReactorFilter] = useState('')
  const [descriptionFilter, setDescriptionFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [skip, setSkip] = useState(0)
  const [limit, setLimit] = useState(25)
  const [groupReplicates, setGroupReplicates] = useState(true)
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set())

  const queryKey = ['experiments', statusFilter, typeFilter, experimentIdFilter, sampleFilter, reactorFilter, descriptionFilter, dateFrom, dateTo, skip, limit, groupReplicates]
  const { data, isLoading, error } = useQuery({
    queryKey,
    queryFn: () => experimentsApi.list({
      status: statusFilter || undefined,
      experiment_type: typeFilter || undefined,
      search: experimentIdFilter || undefined,
      sample_id: sampleFilter || undefined,
      reactor_number: reactorFilter ? parseInt(reactorFilter) : undefined,
      description: descriptionFilter || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      skip,
      limit,
      group_replicates: groupReplicates || undefined,
    }),
  })

  const resetPage = () => setSkip(0)
  const totalPages = data ? Math.ceil(data.total / limit) : 0
  const currentPage = Math.floor(skip / limit) + 1
  const hasActiveFilters = !!(statusFilter || typeFilter || experimentIdFilter || sampleFilter || reactorFilter || descriptionFilter || dateFrom || dateTo)

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
            aria-label="Status filter"
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
        <div className="w-44">
          <Input
            placeholder="Experiment ID…"
            value={experimentIdFilter}
            onChange={(e) => { setExperimentIdFilter(e.target.value); resetPage() }}
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
        <div className="w-44">
          <Input
            placeholder="Description…"
            value={descriptionFilter}
            onChange={(e) => { setDescriptionFilter(e.target.value); resetPage() }}
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
        <label className="flex items-center gap-1.5 text-xs text-ink-secondary pb-2 cursor-pointer select-none">
          <input
            type="checkbox"
            aria-label="Group replicates"
            checked={groupReplicates}
            onChange={(e) => { setGroupReplicates(e.target.checked); resetPage() }}
            className="accent-brand-red"
          />
          Group replicates
        </label>
        {hasActiveFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setStatusFilter(''); setTypeFilter(''); setExperimentIdFilter('')
              setSampleFilter(''); setReactorFilter(''); setDescriptionFilter('')
              setDateFrom(''); setDateTo(''); resetPage()
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
                data.items.map((exp) => {
                  const hasReplicates = !!exp.replicates?.length
                  const expanded = expandedGroups.has(exp.id)
                  return (
                    <Fragment key={exp.id}>
                      <ExperimentRow
                        exp={exp}
                        groupBadge={
                          hasReplicates ? (
                            <button
                              aria-label="Expand replicates"
                              onClick={(e) => {
                                e.stopPropagation()
                                setExpandedGroups((prev) => {
                                  const next = new Set(prev)
                                  if (next.has(exp.id)) next.delete(exp.id)
                                  else next.add(exp.id)
                                  return next
                                })
                              }}
                              className="ml-2 inline-flex items-center gap-1 rounded bg-surface-raised px-1.5 py-0.5 text-2xs text-ink-secondary hover:text-ink-primary"
                            >
                              <span className={`transition-transform ${expanded ? 'rotate-90' : ''}`}>▸</span>
                              {exp.replicates!.length} replicates: {exp.replicates!.map((r) => r.replicate_label).join(', ')}
                            </button>
                          ) : null
                        }
                      />
                      {hasReplicates && expanded &&
                        exp.replicates!.map((rep) => <ExperimentRow key={rep.id} exp={rep} child />)}
                    </Fragment>
                  )
                })
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

/** A single experiment row; shared by group-parent and expanded-child rendering. */
function ExperimentRow({ exp, child, groupBadge }: { exp: ExperimentListItem; child?: boolean; groupBadge?: ReactNode }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const statusMutation = useMutation({
    mutationFn: ({ experimentId, status }: { experimentId: string; status: ExperimentStatus }) =>
      experimentsApi.patchStatus(experimentId, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['experiments'] }),
  })

  return (
    <TableRow
      className="cursor-pointer"
      onClick={() => navigate(`/experiments/${exp.experiment_id}`)}
    >
      <Td className={`font-mono-data text-ink-muted ${child ? 'pl-6' : ''}`}>{exp.experiment_number}</Td>
      <Td>
        <span className={`font-mono-data text-red-400 hover:text-red-300 ${child ? 'pl-6 inline-flex items-center gap-1' : ''}`}>
          {child && <span className="text-ink-muted">↳ {exp.replicate_label}</span>}
          {exp.experiment_id}
        </span>
        {exp.id_timepoint_days != null && (
          <span className="ml-1 rounded bg-surface-raised px-1.5 py-0.5 text-2xs text-ink-secondary">
            day {exp.id_timepoint_days}
          </span>
        )}
        {groupBadge}
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
        <div className="relative inline-block">
          <select
            className={[
              'appearance-none bg-surface-overlay border border-surface-border rounded',
              'pl-2 pr-6 py-0.5 text-xs font-medium focus:outline-none focus:ring-1 focus:ring-brand-red/50',
              STATUS_TEXT_CLASS[exp.status ?? ''] ?? 'text-ink-secondary',
            ].join(' ')}
            value={exp.status ?? ''}
            onMouseDown={(e) => e.stopPropagation()}
            onPointerDown={(e) => e.stopPropagation()}
            onChange={(e) =>
              statusMutation.mutate({ experimentId: exp.experiment_id, status: e.target.value as ExperimentStatus })
            }
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <span className="pointer-events-none absolute inset-y-0 right-1.5 flex items-center text-ink-muted text-2xs">▾</span>
        </div>
      </Td>
      <Td className="font-mono-data text-xs text-ink-muted">{exp.date ? exp.date.slice(0, 10) : '—'}</Td>
      <Td className="text-xs text-ink-secondary max-w-48 truncate">
        {exp.additives_summary ?? <span className="text-ink-muted">—</span>}
      </Td>
    </TableRow>
  )
}
