import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { experimentsApi, type ResultWithFlags } from '@/api/experiments'
import { resultsApi } from '@/api/results'
import { Badge, Button, PageSpinner } from '@/components/ui'
import { AddResultsModal } from './AddResultsModal'
import { GroupedResultsView } from './GroupedResultsView'

const DEFAULT_BACKGROUND_NH4 = 0.2

function fmt(n: number | null | undefined, decimals = 2) {
  return n != null ? n.toFixed(decimals) : '—'
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return iso.slice(0, 10)
}

function fmtPct(n: number | null | undefined, decimals = 1) {
  return n != null ? `${n.toFixed(decimals)}%` : '—'
}

const GRID = 'grid-cols-[1.5rem_5rem_6rem_5rem_5rem_4.5rem_5rem_5rem_4.5rem_4rem_6rem_9rem_1.5rem]'

function ExpandedRow({ result }: { result: ResultWithFlags }) {
  const { data: scalar, isLoading: loadingScalar } = useQuery({
    queryKey: ['scalar', result.id],
    queryFn: () => resultsApi.getScalar(result.id),
    enabled: result.has_scalar,
  })

  const { data: icp } = useQuery({
    queryKey: ['icp', result.id],
    queryFn: () => resultsApi.getIcp(result.id),
    enabled: result.has_icp,
  })

  if (loadingScalar) return <div className="py-3 pl-6"><PageSpinner /></div>

  return (
    <div className="bg-surface-raised border-t border-surface-border px-6 py-3 space-y-3">
      {scalar && (
        <div>
          <p className="text-xs font-semibold text-ink-secondary mb-1">Scalar Results</p>
          <div className="grid grid-cols-3 gap-x-6 gap-y-1">
            {[
              ['Final pH', scalar.final_ph, ''],
              ['Conductivity', scalar.final_conductivity_mS_cm, 'mS/cm'],
              ['Gross NH₄', scalar.gross_ammonium_concentration_mM, 'mM'],
              ['Net NH₄ Yield', scalar.grams_per_ton_yield, 'g/t'],
              ['H₂ (ppm)', scalar.h2_concentration, 'ppm'],
              ['H₂ (µmol)', scalar.h2_micromoles, 'µmol'],
              ['H₂ Yield', scalar.h2_grams_per_ton_yield, 'g/t'],
              ['DO', scalar.final_dissolved_oxygen_mg_L, 'mg/L'],
              ['Fe(II)', scalar.ferrous_iron_yield, ''],
            ].map(([label, val, unit]) => val != null ? (
              <div key={String(label)} className="text-xs">
                <span className="text-ink-muted">{label}: </span>
                <span className="font-mono-data text-ink-primary">{fmt(val as number, 1)}{unit ? ` ${unit}` : ''}</span>
              </div>
            ) : null)}
          </div>
        </div>
      )}
      {result.has_brine_modification && (
        <div>
          <p className="text-xs font-semibold text-ink-secondary mb-1">
            Sampling Modification
            <Badge variant="warning" dot className="ml-2">MOD</Badge>
          </p>
          {result.brine_modification_description && (
            <p className="text-xs text-ink-primary">{result.brine_modification_description}</p>
          )}
        </div>
      )}
      {icp && (
        <div>
          <p className="text-xs font-semibold text-ink-secondary mb-1">ICP-OES</p>
          <div className="grid grid-cols-4 gap-x-4 gap-y-1">
            {['fe','si','mg','ca','ni','cu','mo','zn','mn','cr','co','al','s'].map((el) => {
              const val = (icp as unknown as Record<string, unknown>)[el]
              return val != null ? (
                <div key={el} className="text-xs">
                  <span className="text-ink-muted uppercase">{el}: </span>
                  <span className="font-mono-data text-ink-primary">{String(val)}</span>
                </div>
              ) : null
            })}
          </div>
          {icp.dilution_factor && (
            <p className="text-xs text-ink-muted mt-1">Dilution: {icp.dilution_factor}× · {icp.instrument_used ?? ''}</p>
          )}
        </div>
      )}
    </div>
  )
}

interface Props {
  experimentId: string
  experimentFk: number
}

/** Results tab: timepoint result cards with scalar chemistry and ICP data. */
export function ResultsTab({ experimentId, experimentFk }: Props) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [bgInput, setBgInput] = useState(false)
  const [bgValue, setBgValue] = useState(String(DEFAULT_BACKGROUND_NH4))
  const [showAddModal, setShowAddModal] = useState(false)
  const [mode, setMode] = useState<'individual' | 'grouped'>('individual')
  const queryClient = useQueryClient()

  const { data: replicateGroup } = useQuery({
    queryKey: ['replicate-group', experimentId],
    queryFn: () => experimentsApi.getReplicateGroup(experimentId),
  })
  const hasGroup = (replicateGroup?.members.length ?? 0) > 0

  const { data: results, isLoading } = useQuery({
    queryKey: ['experiment-results', experimentId],
    queryFn: () => experimentsApi.getResults(experimentId),
  })

  // Derive the current background NH4 from the first result with a scalar value,
  // falling back to the default. This reflects what is actually stored in the DB
  // and stays correct after page reloads and after "Apply to all" refetches.
  const storedBgValue = results?.find((r) => r.background_ammonium_concentration_mM != null)
    ?.background_ammonium_concentration_mM ?? DEFAULT_BACKGROUND_NH4

  const bgMutation = useMutation({
    mutationFn: (value: number) => experimentsApi.setBackgroundAmmonium(experimentId, value),
    onSuccess: () => {
      setBgInput(false)
      queryClient.invalidateQueries({ queryKey: ['experiment-results', experimentId] })
      queryClient.invalidateQueries({ queryKey: ['scalar'] })
    },
  })

  const toggle = (id: number) => setExpanded((s) => {
    const n = new Set(s)
    n.has(id) ? n.delete(id) : n.add(id)
    return n
  })

  if (isLoading) return <PageSpinner />

  return (
    <div>
      {/* Action bar */}
      <div className="flex items-center justify-between gap-2 px-4 py-2 border-b border-surface-border">
        <div className="flex items-center gap-2">
          {bgInput ? (
            <>
              <label className="text-xs text-ink-secondary">Background NH₄ (mM)</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={bgValue}
                onChange={(e) => setBgValue(e.target.value)}
                className="w-20 text-xs px-2 py-1 border border-surface-border rounded bg-surface-raised text-ink-primary font-mono-data"
                autoFocus
              />
              <button
                onClick={() => {
                  const parsed = parseFloat(bgValue)
                  if (!isNaN(parsed) && parsed >= 0) bgMutation.mutate(parsed)
                }}
                disabled={bgMutation.isPending}
                className="text-xs px-2 py-1 bg-navy-700 text-white rounded hover:bg-navy-600 disabled:opacity-50"
              >
                {bgMutation.isPending ? 'Applying…' : 'Apply to all'}
              </button>
              <button
                onClick={() => setBgInput(false)}
                className="text-xs px-2 py-1 text-ink-muted hover:text-ink-primary"
              >
                Cancel
              </button>
              {bgMutation.isError && (
                <span className="text-xs text-red-500">Failed — try again</span>
              )}
            </>
          ) : (
            <button
              onClick={() => { setBgValue(String(storedBgValue)); setBgInput(true) }}
              className="text-xs text-ink-secondary hover:text-ink-primary underline-offset-2 hover:underline"
            >
              Background NH₄: {storedBgValue} mM
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          {hasGroup && (
            <div className="flex items-center rounded border border-surface-border overflow-hidden text-xs">
              <button
                className={`px-2.5 py-1 ${mode === 'individual' ? 'bg-surface-raised text-ink-primary' : 'text-ink-secondary hover:text-ink-primary'}`}
                onClick={() => setMode('individual')}
              >
                Individual
              </button>
              <button
                className={`px-2.5 py-1 ${mode === 'grouped' ? 'bg-surface-raised text-ink-primary' : 'text-ink-secondary hover:text-ink-primary'}`}
                onClick={() => setMode('grouped')}
              >
                Grouped (n={replicateGroup!.members.length})
              </button>
            </div>
          )}
          <Button variant="primary" size="sm" onClick={() => setShowAddModal(true)}>
            + Add Results
          </Button>
        </div>
      </div>

      {mode === 'grouped' && hasGroup ? (
        <div className="p-4">
          <GroupedResultsView experimentId={experimentId} />
        </div>
      ) : (
        <>
          {/* Empty state */}
          {!results?.length && (
            <p className="text-sm text-ink-muted p-4 text-center">No results recorded</p>
          )}

          {results && results.length > 0 && (
            <>
              {/* Header row */}
              <div className={`grid ${GRID} gap-2 px-4 py-2 border-b border-surface-border text-xs text-ink-muted`}>
                <span></span>
                <span>Time (d)</span>
                <span>Sample Date</span>
                <span>Gross NH₄ (mM)</span>
                <span>NH₄ (g/t)</span>
                <span>Fe²⁺ NH₃ (%)</span>
                <span>H₂ (µmol)</span>
                <span>H₂ (g/t)</span>
                <span>Fe²⁺ H₂ (%)</span>
                <span>pH</span>
                <span>Cond. (mS/cm)</span>
                <span>ICP / XRD / MOD</span>
                <span></span>
              </div>
              {results.map((r) => (
                <div key={r.id}>
                  <div
                    className={`grid ${GRID} gap-2 px-4 py-2 border-b border-surface-border/50 hover:bg-surface-raised cursor-pointer items-center`}
                    onClick={() => toggle(r.id)}
                  >
                    <span className="text-xs text-ink-muted">{r.is_primary_timepoint_result ? '★' : ''}</span>
                    <span className="font-mono-data text-sm text-ink-primary">T+{r.time_post_reaction_days ?? '?'}</span>
                    <span className="font-mono-data text-xs text-ink-secondary">{fmtDate(r.scalar_measurement_date)}</span>
                    <span className="font-mono-data text-xs text-ink-secondary">{fmt(r.gross_ammonium_concentration_mM)}</span>
                    <span className="font-mono-data text-xs text-ink-secondary">{fmt(r.grams_per_ton_yield)}</span>
                    <span className="font-mono-data text-xs text-ink-secondary">{fmtPct(r.ferrous_iron_yield_nh3_pct)}</span>
                    <span className="font-mono-data text-xs text-ink-secondary">{fmt(r.h2_micromoles)}</span>
                    <span className="font-mono-data text-xs text-ink-secondary">{fmt(r.h2_grams_per_ton_yield)}</span>
                    <span className="font-mono-data text-xs text-ink-secondary">{fmtPct(r.ferrous_iron_yield_h2_pct)}</span>
                    <span className="font-mono-data text-xs text-ink-secondary">{fmt(r.final_ph, 1)}</span>
                    <span className="font-mono-data text-xs text-ink-secondary">{fmt(r.final_conductivity_mS_cm)}</span>
                    <span className="flex items-center gap-1">
                      {r.has_icp && <Badge variant="info" dot>ICP</Badge>}
                      {r.xrd_run_date && <Badge variant="info" dot>XRD</Badge>}
                      {r.has_brine_modification && <Badge variant="warning" dot>MOD</Badge>}
                    </span>
                    <span className="text-ink-muted text-xs">{expanded.has(r.id) ? '▲' : '▼'}</span>
                  </div>
                  {expanded.has(r.id) && <ExpandedRow result={r} />}
                </div>
              ))}
            </>
          )}
        </>
      )}

      <AddResultsModal
        open={showAddModal}
        onClose={() => setShowAddModal(false)}
        experimentFk={experimentFk}
        experimentId={experimentId}
      />
    </div>
  )
}
