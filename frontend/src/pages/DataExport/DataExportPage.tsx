import { useEffect, useState } from 'react'
import { useMutation, useQuery, keepPreviousData } from '@tanstack/react-query'
import { experimentsApi, type ExperimentListItem } from '@/api/experiments'
import { Button, PageSpinner, useToast } from '@/components/ui'
import { EMPTY_FILTERS, ExportFilters, type ExportFilterValues } from './ExportFilters'
import { ExportResultsTable, rowKey } from './ExportResultsTable'

const SEARCH_DEBOUNCE_MS = 300
const LIST_LIMIT = 500

/** Filter experiments, tick any number, and download one Excel workbook for all of them. */
export function DataExportPage() {
  const { success, error } = useToast()

  const [filters, setFilters] = useState<ExportFilterValues>(EMPTY_FILTERS)
  const [debouncedFilters, setDebouncedFilters] = useState<ExportFilterValues>(EMPTY_FILTERS)
  useEffect(() => {
    const t = setTimeout(() => setDebouncedFilters(filters), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [filters])

  // Keyed by the row's display id (a collapsed vial row's stem, so a changed
  // representative vial is still the same row) and independent of the filters, so a selection survives
  // narrowing or changing the filter bar.
  const [selected, setSelected] = useState<Map<string, ExperimentListItem>>(new Map())
  const [includeSeries, setIncludeSeries] = useState(true)

  const { data, isLoading, error: loadError } = useQuery({
    queryKey: ['data-export', debouncedFilters],
    queryFn: () => experimentsApi.list({
      status: debouncedFilters.status || undefined,
      experiment_type: debouncedFilters.experimentType || undefined,
      search: debouncedFilters.search.trim() || undefined,
      sample_id: debouncedFilters.sampleId.trim() || undefined,
      reactor_number: debouncedFilters.reactor ? parseInt(debouncedFilters.reactor, 10) : undefined,
      description: debouncedFilters.description.trim() || undefined,
      additive: debouncedFilters.additive.trim() || undefined,
      researcher: debouncedFilters.researcher.trim() || undefined,
      date_from: debouncedFilters.dateFrom || undefined,
      date_to: debouncedFilters.dateTo || undefined,
      last_result_from: debouncedFilters.lastResultFrom || undefined,
      last_result_to: debouncedFilters.lastResultTo || undefined,
      limit: LIST_LIMIT,
      group_replicates: false,
    }),
    placeholderData: keepPreviousData,
  })

  const mutation = useMutation({
    mutationFn: () => experimentsApi.exportSelection(
      [...selected.values()].map((r) => r.experiment_id),
      includeSeries,
    ),
    onSuccess: (filename) => success('Export downloaded', filename),
    onError: (err: Error) => error('Export failed', err.message),
  })

  const rows = data?.items ?? []

  const toggle = (row: ExperimentListItem) =>
    setSelected((prev) => {
      const next = new Map(prev)
      const key = rowKey(row)
      if (next.has(key)) next.delete(key)
      else next.set(key, row)
      return next
    })

  const toggleAll = () =>
    setSelected((prev) => {
      const next = new Map(prev)
      if (rows.length > 0 && rows.every((r) => next.has(rowKey(r)))) {
        rows.forEach((r) => next.delete(rowKey(r)))
      } else {
        rows.forEach((r) => next.set(rowKey(r), r))
      }
      return next
    })

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-ink-primary">Data Export</h1>
        <p className="text-xs text-ink-muted mt-0.5">
          Filter experiments, tick the ones you want, and download one Excel workbook.
        </p>
      </div>

      <ExportFilters value={filters} onChange={setFilters} />

      <div className="flex flex-wrap items-center gap-4 rounded border border-surface-border bg-surface-raised px-3 py-2">
        <span className="text-sm text-ink-primary">{selected.size} selected</span>
        <Button
          variant="ghost"
          size="sm"
          disabled={selected.size === 0}
          onClick={() => setSelected(new Map())}
        >
          Clear selection
        </Button>
        <label className="flex items-center gap-1.5 text-xs text-ink-secondary cursor-pointer select-none">
          <input
            type="checkbox"
            aria-label="Include whole series"
            checked={includeSeries}
            onChange={(e) => setIncludeSeries(e.target.checked)}
            className="accent-brand-red"
          />
          Include whole series
        </label>
        <div className="ml-auto">
          <Button
            variant="primary"
            size="sm"
            loading={mutation.isPending}
            disabled={selected.size === 0}
            onClick={() => mutation.mutate()}
          >
            Export
          </Button>
        </div>
      </div>

      {isLoading && <PageSpinner />}
      {loadError && <p className="text-sm text-red-400 py-4">Failed to load experiments</p>}

      {data && (
        <>
          {data.total > data.items.length && (
            <p className="text-xs text-status-error">
              {`Showing ${data.items.length} of ${data.total}. Narrow your filters to see the rest.`}
            </p>
          )}
          <ExportResultsTable
            rows={rows}
            selected={new Set(selected.keys())}
            onToggle={toggle}
            onToggleAll={toggleAll}
          />
        </>
      )}
    </div>
  )
}
