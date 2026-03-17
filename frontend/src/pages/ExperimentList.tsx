import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { experimentsApi } from '@/api/experiments'
import {
  Table, TableHead, TableBody, TableRow, Th, Td,
  StatusBadge, Button, Input, Select, PageSpinner,
} from '@/components/ui'

export function ExperimentListPage() {
  const navigate = useNavigate()
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')

  const { data: experiments, isLoading, error } = useQuery({
    queryKey: ['experiments', statusFilter],
    queryFn: () => experimentsApi.list({ status: statusFilter || undefined, limit: 200 }),
  })

  const filtered = experiments?.filter((e) =>
    !search || e.experiment_id.toLowerCase().includes(search.toLowerCase()) ||
    (e.researcher ?? '').toLowerCase().includes(search.toLowerCase())
  ) ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-ink-primary">Experiments</h1>
          <p className="text-xs text-ink-muted mt-0.5">
            {experiments ? `${filtered.length} of ${experiments.length}` : '…'} experiments
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={() => navigate('/experiments/new')} leftIcon={
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M6 1v10M1 6h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
        }>
          New Experiment
        </Button>
      </div>

      {/* Filters */}
      <div className="flex items-end gap-3">
        <div className="w-60">
          <Input
            placeholder="Search ID or researcher…"
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
        <div className="w-40">
          <Select
            options={[
              { value: 'ONGOING',   label: 'Ongoing' },
              { value: 'COMPLETED', label: 'Completed' },
              { value: 'CANCELLED', label: 'Cancelled' },
            ]}
            placeholder="All statuses"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          />
        </div>
      </div>

      {isLoading && <PageSpinner />}
      {error && <p className="text-sm text-red-400 py-4">Failed to load experiments</p>}

      {experiments && (
        <Table>
          <TableHead>
            <tr>
              <Th>#</Th>
              <Th>Experiment ID</Th>
              <Th>Status</Th>
              <Th>Researcher</Th>
              <Th>Sample</Th>
              <Th>Date</Th>
            </tr>
          </TableHead>
          <TableBody>
            {filtered.length === 0 ? (
              <TableRow>
                <Td colSpan={6} className="text-center py-8 text-ink-muted">No experiments found</Td>
              </TableRow>
            ) : (
              filtered.map((exp) => (
                <TableRow key={exp.id}>
                  <Td className="font-mono-data text-ink-muted">{exp.experiment_number}</Td>
                  <Td>
                    <Link
                      to={`/experiments/${exp.id}`}
                      className="font-mono-data text-red-400 hover:text-red-300 hover:underline"
                    >
                      {exp.experiment_id}
                    </Link>
                  </Td>
                  <Td><StatusBadge status={exp.status} /></Td>
                  <Td>{exp.researcher ?? <span className="text-ink-muted">—</span>}</Td>
                  <Td className="font-mono-data">{exp.sample_id ?? <span className="text-ink-muted">—</span>}</Td>
                  <Td className="font-mono-data text-ink-muted">{exp.date ?? '—'}</Td>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
