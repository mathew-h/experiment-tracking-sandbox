import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { samplesApi, SampleListParams } from '@/api/samples'
import {
  Table, TableHead, TableBody, TableRow, Th, Td,
  Input, Button, Modal, Badge, PageSpinner, useToast,
} from '@/components/ui'
import { NewSampleModal } from './SampleDetail/NewSampleModal'

export function SamplesPage() {
  const navigate = useNavigate()
  const { error: toastError } = useToast()
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const [country, setCountry] = useState('')
  const [hasPxrf, setHasPxrf] = useState(false)
  const [hasXrd, setHasXrd] = useState(false)
  const [hasElemental, setHasElemental] = useState(false)
  const [skip, setSkip] = useState(0)
  const [limit] = useState(50)
  const [showNewModal, setShowNewModal] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  const params: SampleListParams = {
    skip,
    limit,
    ...(search && { search }),
    ...(country && { country }),
    ...(hasPxrf && { has_pxrf: true }),
    ...(hasXrd && { has_xrd: true }),
    ...(hasElemental && { has_elemental: true }),
  }

  const { data, isLoading } = useQuery({
    queryKey: ['samples', params],
    queryFn: () => samplesApi.list(params),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => samplesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['samples'] })
      setDeleteTarget(null)
    },
    onError: (err: unknown) => {
      const msg = (err as { message?: string }).message ?? 'Delete failed'
      toastError('Delete failed', msg)
      setDeleteTarget(null)
    },
  })

  const totalPages = data ? Math.ceil(data.total / limit) : 0
  const currentPage = Math.floor(skip / limit) + 1

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-ink-primary">Samples</h1>
          <p className="text-xs text-ink-muted mt-0.5">
            {data ? `${data.total} samples` : 'Geological sample inventory'}
          </p>
        </div>
        <Button variant="primary" onClick={() => setShowNewModal(true)}>+ New Sample</Button>
      </div>

      {/* Filters toolbar */}
      <div className="flex flex-wrap gap-2 items-center">
        <Input
          placeholder="Search by ID or description…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setSkip(0) }}
          className="w-64"
        />
        <Input
          placeholder="Country"
          value={country}
          onChange={(e) => { setCountry(e.target.value); setSkip(0) }}
          className="w-36"
        />
        {(['pXRF', 'XRD', 'Elemental'] as const).map((label) => {
          const active =
            label === 'pXRF' ? hasPxrf : label === 'XRD' ? hasXrd : hasElemental
          const setter =
            label === 'pXRF' ? setHasPxrf : label === 'XRD' ? setHasXrd : setHasElemental
          return (
            <button
              key={label}
              onClick={() => { setter(!active); setSkip(0) }}
              className={`px-3 py-1 rounded text-xs font-medium border transition-colors ${
                active
                  ? 'bg-brand-red/10 border-brand-red text-brand-red'
                  : 'border-surface-border text-ink-muted hover:border-ink-muted'
              }`}
            >
              {label}
            </button>
          )
        })}
      </div>

      {isLoading && <PageSpinner />}

      {/* Table */}
      {data && (
        <>
          <Table>
            <TableHead>
              <tr>
                <Th>Sample ID</Th>
                <Th>Classification</Th>
                <Th>Description</Th>
                <Th>Location</Th>
                <Th>Characterized</Th>
                <Th>Analyses</Th>
                <Th>Experiments</Th>
                <Th></Th>
              </tr>
            </TableHead>
            <TableBody>
              {data.items.length === 0 ? (
                <TableRow>
                  <Td colSpan={8} className="text-center py-8 text-ink-muted">No samples found</Td>
                </TableRow>
              ) : (
                data.items.map((s) => (
                  <TableRow
                    key={s.sample_id}
                    onClick={() => navigate(`/samples/${s.sample_id}`)}
                    className="cursor-pointer"
                  >
                    <Td className="font-mono-data text-ink-primary">{s.sample_id}</Td>
                    <Td>{s.rock_classification ?? <span className="text-ink-muted">—</span>}</Td>
                    <Td className="max-w-xs">
                      {s.description
                        ? <span className="block truncate text-ink-secondary" title={s.description}>{s.description}</span>
                        : <span className="text-ink-muted">—</span>}
                    </Td>
                    <Td className="text-ink-muted">
                      {[s.locality, s.state, s.country].filter(Boolean).join(', ') || '—'}
                    </Td>
                    <Td>
                      <Badge variant={s.characterized ? 'success' : 'default'}>
                        {s.characterized ? 'Yes' : 'No'}
                      </Badge>
                    </Td>
                    <Td>
                      <div className="flex gap-1">
                        {s.has_pxrf && <Badge variant="default">pXRF</Badge>}
                        {s.has_xrd && <Badge variant="default">XRD</Badge>}
                        {s.has_elemental && <Badge variant="default">Elem</Badge>}
                      </div>
                    </Td>
                    <Td className="tabular-nums">{s.experiment_count}</Td>
                    <Td onClick={(e) => e.stopPropagation()}>
                      <button
                        className="text-xs text-red-400 hover:text-red-300"
                        onClick={() => setDeleteTarget(s.sample_id)}
                      >
                        Delete
                      </button>
                    </Td>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between text-sm text-ink-muted">
              <span>Page {currentPage} of {totalPages}</span>
              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  disabled={skip === 0}
                  onClick={() => setSkip(skip - limit)}
                >
                  ← Prev
                </Button>
                <Button
                  variant="ghost"
                  disabled={currentPage >= totalPages}
                  onClick={() => setSkip(skip + limit)}
                >
                  Next →
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      {/* New Sample Modal — full implementation in Task 12 */}
      {showNewModal && (
        <NewSampleModal
          onClose={() => setShowNewModal(false)}
          onCreated={(id) => {
            queryClient.invalidateQueries({ queryKey: ['samples'] })
            setShowNewModal(false)
            navigate(`/samples/${id}`)
          }}
        />
      )}

      {/* Delete confirmation modal */}
      <Modal
        open={deleteTarget !== null}
        title="Delete Sample"
        onClose={() => setDeleteTarget(null)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button
              variant="danger"
              onClick={() => { if (deleteTarget) deleteMutation.mutate(deleteTarget) }}
              disabled={deleteMutation.isPending}
            >
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-ink-secondary">
          Delete <span className="font-mono-data">{deleteTarget}</span>? This cannot be undone.
        </p>
      </Modal>
    </div>
  )
}
