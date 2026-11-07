import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import type { ExperimentListItem, H2BackgroundLink } from '@/api/experiments'
import { Button, Input, Modal } from '@/components/ui'
import { splitTimepointToken } from '@/utils/experimentId'

type Mode = 'group' | 'vial'

const MIN_SEARCH_CHARS = 2

interface H2BackgroundRowProps {
  baseId: string
  link: H2BackgroundLink | null
}

function errorDetail(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

/** The picked result's group key: its base experiment ID, else its timepoint-stripped stem. */
function groupKeyOf(item: ExperimentListItem): string {
  return item.base_experiment_id ?? splitTimepointToken(item.experiment_id).stem
}

/** Serum-vial H2 background control for a replicate group (issue #144). */
export function H2BackgroundRow({ baseId, link }: H2BackgroundRowProps) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [picked, setPicked] = useState<ExperimentListItem | null>(null)
  const [mode, setMode] = useState<Mode>('group')
  const [serverError, setServerError] = useState<string | null>(null)

  const { data: rollup } = useQuery({
    queryKey: ['group-h2-bkg-rollup', baseId],
    queryFn: () => experimentsApi.getGroupH2BackgroundRollup(baseId),
    enabled: link !== null,
  })

  const searchEnabled = open && search.trim().length >= MIN_SEARCH_CHARS
  const { data: results } = useQuery({
    queryKey: ['h2-bkg-search', search.trim()],
    queryFn: () => experimentsApi.list({ search: search.trim(), experiment_type: 'Serum' }),
    enabled: searchEnabled,
  })

  const invalidate = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ['replicate-group-detail', baseId] }),
      queryClient.invalidateQueries({ queryKey: ['group-rollup', baseId] }),
      queryClient.invalidateQueries({ queryKey: ['group-h2-bkg-rollup', baseId] }),
    ])

  const closeModal = () => {
    setOpen(false)
    setSearch('')
    setPicked(null)
    setMode('group')
    setServerError(null)
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      experimentsApi.setGroupH2Background(baseId, {
        experiment_id: picked!.experiment_id,
        mode,
      }),
    onSuccess: async () => {
      await invalidate()
      closeModal()
    },
    onError: (err: unknown) => setServerError(errorDetail(err, 'Could not set the H₂ background')),
  })

  const clearMutation = useMutation({
    mutationFn: () => experimentsApi.clearGroupH2Background(baseId),
    onSuccess: () => invalidate(),
  })

  const items = searchEnabled ? (results?.items ?? []) : []
  const groupKey = picked ? groupKeyOf(picked) : ''
  const sameGroupCount = picked ? items.filter((i) => groupKeyOf(i) === groupKey).length : 0
  const groupLabel =
    sameGroupCount > 0
      ? `Whole group (${groupKey}, ${sameGroupCount} ${sameGroupCount === 1 ? 'vial' : 'vials'})`
      : `Whole group (${groupKey})`
  const stem = picked ? splitTimepointToken(picked.experiment_id).stem : ''

  const noData =
    link !== null && rollup !== undefined && !rollup.some((r) => r.bkg_n_values != null)

  return (
    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
      <span className="text-ink-muted">H₂ background:</span>
      <span className="font-mono-data text-ink-primary">
        {link
          ? `${link.background_ref} · ${link.mode === 'group' ? 'whole group' : 'single vial'}`
          : 'None'}
      </span>
      {link ? (
        <>
          <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
            Change
          </Button>
          <Button
            size="sm"
            variant="ghost"
            loading={clearMutation.isPending}
            onClick={() => clearMutation.mutate()}
          >
            Clear
          </Button>
        </>
      ) : (
        <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
          Set
        </Button>
      )}
      {noData && <span className="text-status-warning">background has no H₂ data</span>}

      <Modal
        open={open}
        onClose={closeModal}
        title="Set H₂ background"
        description="Pick a Serum experiment to subtract from this group's H₂."
        footer={
          <>
            <Button variant="secondary" onClick={closeModal}>
              Cancel
            </Button>
            <Button
              loading={saveMutation.isPending}
              disabled={!picked}
              onClick={() => {
                setServerError(null)
                saveMutation.mutate()
              }}
            >
              Save
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input
            aria-label="Search experiments"
            placeholder="Search Serum experiments"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPicked(null)
              setServerError(null)
            }}
          />
          {searchEnabled && items.length === 0 && (
            <p className="text-xs text-ink-muted">No matching Serum experiments.</p>
          )}
          {!picked && items.length > 0 && (
            <ul className="max-h-48 overflow-y-auto divide-y divide-surface-border border border-surface-border rounded">
              {items.map((item) => (
                <li key={item.experiment_id}>
                  <button
                    type="button"
                    onClick={() => setPicked(item)}
                    className="w-full text-left px-3 py-1.5 text-sm font-mono-data text-ink-primary hover:bg-surface-raised"
                  >
                    {item.experiment_id}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {picked && (
            <fieldset className="space-y-2">
              <legend className="text-xs text-ink-muted mb-1">
                Background: <span className="font-mono-data">{picked.experiment_id}</span>
              </legend>
              <label className="flex items-center gap-2 text-sm text-ink-primary">
                <input
                  type="radio"
                  name="h2-bkg-mode"
                  checked={mode === 'group'}
                  onChange={() => setMode('group')}
                />
                {groupLabel}
              </label>
              <label className="flex items-center gap-2 text-sm text-ink-primary">
                <input
                  type="radio"
                  name="h2-bkg-mode"
                  checked={mode === 'vial'}
                  onChange={() => setMode('vial')}
                />
                {`This vial only (${stem} and its -t vials)`}
              </label>
            </fieldset>
          )}
          {serverError && <p className="text-xs text-red-400">{serverError}</p>}
        </div>
      </Modal>
    </div>
  )
}
