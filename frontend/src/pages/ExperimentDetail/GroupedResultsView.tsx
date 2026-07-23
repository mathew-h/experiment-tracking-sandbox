import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueries } from '@tanstack/react-query'
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ErrorBar, ResponsiveContainer,
} from 'recharts'
import { experimentsApi } from '@/api/experiments'
import type { ResultWithFlags, RollupTimepoint } from '@/api/experiments'
import { chartColors } from '@/assets/brand'
import { Table, TableHead, TableBody, TableRow, Th, Td, Select, Spinner } from '@/components/ui'

interface MetricDef {
  key: string
  label: string
  mean: keyof RollupTimepoint
  sd: keyof RollupTimepoint | null
  individual: (r: ResultWithFlags) => number | null
}

const METRICS: MetricDef[] = [
  { key: 'gross_nh4', label: 'Gross NH₄ (mM)', mean: 'mean_gross_ammonium_mM', sd: 'sd_gross_ammonium_mM',
    individual: (r) => r.gross_ammonium_concentration_mM },
  { key: 'net_nh4', label: 'Net NH₄ (mM)', mean: 'mean_net_ammonium_mM', sd: 'sd_net_ammonium_mM',
    individual: (r) =>
      r.gross_ammonium_concentration_mM != null && r.background_ammonium_concentration_mM != null
        ? Math.max(0, r.gross_ammonium_concentration_mM - r.background_ammonium_concentration_mM)
        : null },
  { key: 'nh4_gpt', label: 'NH₄ (g/t)', mean: 'mean_grams_per_ton_yield', sd: 'sd_grams_per_ton_yield',
    individual: (r) => r.grams_per_ton_yield },
  { key: 'h2_umol', label: 'H₂ (µmol)', mean: 'mean_h2_micromoles', sd: 'sd_h2_micromoles',
    individual: (r) => r.h2_micromoles },
  { key: 'h2_gpt', label: 'H₂ (g/t)', mean: 'mean_h2_grams_per_ton', sd: 'sd_h2_grams_per_ton',
    individual: (r) => r.h2_grams_per_ton_yield },
  { key: 'fe_h2', label: 'Fe²⁺ → H₂ (%)', mean: 'mean_fe_yield_h2_pct', sd: 'sd_fe_yield_h2_pct',
    individual: (r) => r.ferrous_iron_yield_h2_pct },
  { key: 'fe_nh3', label: 'Fe²⁺ → NH₃ (%)', mean: 'mean_fe_yield_nh3_pct', sd: 'sd_fe_yield_nh3_pct',
    individual: (r) => r.ferrous_iron_yield_nh3_pct },
  { key: 'ph', label: 'pH', mean: 'mean_final_ph', sd: null, individual: (r) => r.final_ph },
]

const fmt = (v: number | null | undefined, digits = 2) =>
  v == null ? '—' : v.toFixed(digits)

interface GroupedResultsViewProps {
  experimentId: string
}

/** Base-level grouped results: mean ± std per timepoint from the rollup view,
 *  with individual replicate series overlay and drill-in links. */
export function GroupedResultsView({ experimentId }: GroupedResultsViewProps) {
  const [metricKey, setMetricKey] = useState('gross_nh4')
  const [showIndividual, setShowIndividual] = useState(true)
  const metric = METRICS.find((m) => m.key === metricKey)!

  const { data: group } = useQuery({
    queryKey: ['replicate-group', experimentId],
    queryFn: () => experimentsApi.getReplicateGroup(experimentId),
  })
  const { data: rollup, isLoading } = useQuery({
    queryKey: ['rollup', experimentId],
    queryFn: () => experimentsApi.getRollup(experimentId),
  })

  // Series entities in fixed order: parent (replicate 0) first, then a, b, c…
  // Only the first chartColors.series.length entities are overlaid (never cycle hues).
  const seriesEntities = useMemo(() => {
    const entities = [
      ...(group?.parent ? [group.parent] : []),
      ...(group?.members ?? []),
    ]
    return entities.slice(0, chartColors.series.length)
  }, [group])

  const memberResults = useQueries({
    queries: seriesEntities.map((m) => ({
      queryKey: ['experiment-results', m.experiment_id],
      queryFn: () => experimentsApi.getResults(m.experiment_id),
      enabled: showIndividual,
    })),
  })

  const chartData = useMemo(() => {
    if (!rollup) return []
    return rollup
      .filter((r) => r.time_post_reaction_bucket_days != null)
      .map((r) => {
        const row: Record<string, number | null> = {
          bucket: r.time_post_reaction_bucket_days,
          mean: r[metric.mean] as number | null,
          sd: metric.sd ? ((r[metric.sd] as number | null) ?? 0) : 0,
        }
        seriesEntities.forEach((m, i) => {
          const results = memberResults[i]?.data ?? []
          const match = results.find(
            (res) => res.time_post_reaction_bucket_days === r.time_post_reaction_bucket_days
          )
          row[m.experiment_id] = match ? metric.individual(match) : null
        })
        return row
      })
  }, [rollup, metric, seriesEntities, memberResults])

  if (isLoading) return <Spinner />
  if (!rollup?.length) {
    return <p className="text-sm text-ink-muted py-4">No primary results to aggregate yet.</p>
  }

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-48">
          <Select
            label="Metric"
            aria-label="Metric"
            value={metricKey}
            onChange={(e) => setMetricKey(e.target.value)}
            options={METRICS.map((m) => ({ value: m.key, label: m.label }))}
          />
        </div>
        <label className="flex items-center gap-1.5 text-xs text-ink-secondary pb-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={showIndividual}
            onChange={(e) => setShowIndividual(e.target.checked)}
            className="accent-brand-red"
          />
          Show individual replicates
        </label>
        <div className="ml-auto flex items-center gap-2 text-xs text-ink-secondary pb-2">
          {seriesEntities.map((m) => (
            <Link
              key={m.id}
              to={`/experiments/${m.experiment_id}`}
              className={`font-mono-data ${m.is_outlier ? 'text-ink-muted line-through hover:text-ink-secondary' : 'text-red-400 hover:text-red-300'}`}
            >
              {m.experiment_id}
              {m.is_outlier ? ' (outlier)' : ''}
            </Link>
          ))}
        </div>
      </div>

      {/* Chart — single y-axis; mean emphasized, members thin; legend always on */}
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid stroke={chartColors.grid} strokeDasharray="3 3" />
            <XAxis
              dataKey="bucket" type="number" domain={['dataMin', 'dataMax']}
              stroke={chartColors.axis} tick={{ fill: chartColors.label, fontSize: 11 }}
              label={{ value: 'Time post-reaction (days)', position: 'insideBottom', offset: -4, fill: chartColors.label, fontSize: 11 }}
            />
            <YAxis
              stroke={chartColors.axis} tick={{ fill: chartColors.label, fontSize: 11 }}
              width={56}
            />
            <Tooltip
              contentStyle={{ backgroundColor: chartColors.tooltipBg, border: `1px solid ${chartColors.grid}`, fontSize: 12 }}
              labelFormatter={(v) => `Day ${v}`}
            />
            <Legend wrapperStyle={{ fontSize: 11, color: chartColors.label }} />
            {showIndividual &&
              seriesEntities.map((m, i) => (
                <Line
                  key={m.id} dataKey={m.experiment_id}
                  name={`${m.replicate_label ? `replicate ${m.replicate_label}` : 'replicate 0'}${m.is_outlier ? ' (outlier)' : ''}`}
                  stroke={chartColors.series[i]} strokeWidth={1.5}
                  dot={{ r: 4, fill: chartColors.series[i] }} connectNulls
                />
              ))}
            <Line
              dataKey="mean" name={`mean ± sd (${metric.label})`}
              stroke={chartColors.mean} strokeWidth={2}
              dot={{ r: 5, fill: chartColors.mean }} connectNulls
            >
              <ErrorBar dataKey="sd" stroke={chartColors.mean} strokeWidth={1.5} width={6} />
            </Line>
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Accessible table view of the rollup */}
      <Table>
        <TableHead>
          <tr>
            <Th>Time (d)</Th>
            <Th>n</Th>
            <Th>Gross NH₄ (mM)</Th>
            <Th>Net NH₄ (mM)</Th>
            <Th>NH₄ (g/t)</Th>
            <Th>H₂ (µmol)</Th>
            <Th>Fe²⁺ → NH₃ (%)</Th>
            <Th>pH</Th>
          </tr>
        </TableHead>
        <TableBody>
          {rollup.map((r) => (
            <TableRow key={`${r.base_experiment_id}-${r.time_post_reaction_bucket_days}`}>
              <Td className="font-mono-data">{fmt(r.time_post_reaction_bucket_days, 1)}</Td>
              <Td className="font-mono-data text-ink-muted">n = {r.n_replicates}</Td>
              <Td className="font-mono-data">
                {r.mean_gross_ammonium_mM == null
                  ? '—'
                  : `${fmt(r.mean_gross_ammonium_mM)} ± ${fmt(r.sd_gross_ammonium_mM ?? 0)}`}
              </Td>
              <Td className="font-mono-data">
                {r.mean_net_ammonium_mM == null
                  ? '—'
                  : `${fmt(r.mean_net_ammonium_mM)} ± ${fmt(r.sd_net_ammonium_mM ?? 0)}`}
              </Td>
              <Td className="font-mono-data">
                {r.mean_grams_per_ton_yield == null
                  ? '—'
                  : `${fmt(r.mean_grams_per_ton_yield, 1)} ± ${fmt(r.sd_grams_per_ton_yield ?? 0, 1)}`}
              </Td>
              <Td className="font-mono-data">
                {r.mean_h2_micromoles == null
                  ? '—'
                  : `${fmt(r.mean_h2_micromoles, 1)} ± ${fmt(r.sd_h2_micromoles ?? 0, 1)}`}
              </Td>
              <Td className="font-mono-data">
                {r.mean_fe_yield_nh3_pct == null
                  ? '—'
                  : `${fmt(r.mean_fe_yield_nh3_pct)} ± ${fmt(r.sd_fe_yield_nh3_pct ?? 0)}`}
              </Td>
              <Td className="font-mono-data">{fmt(r.mean_final_ph)}</Td>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
