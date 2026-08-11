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
  { key: 'h2_ppm', label: 'H₂ (ppm)', mean: 'mean_h2_ppm', sd: 'sd_h2_ppm',
    individual: (r) => r.h2_concentration },
  { key: 'h2_umol', label: 'H₂ (µmol)', mean: 'mean_h2_micromoles', sd: 'sd_h2_micromoles',
    individual: (r) => r.h2_micromoles },
  { key: 'h2_gpt', label: 'H₂ (g/t)', mean: 'mean_h2_grams_per_ton', sd: 'sd_h2_grams_per_ton',
    individual: (r) => r.h2_grams_per_ton_yield },
  { key: 'fe_h2', label: 'Fe²⁺ → H₂ (%)', mean: 'mean_fe_yield_h2_pct', sd: 'sd_fe_yield_h2_pct',
    individual: (r) => r.ferrous_iron_yield_h2_pct },
  { key: 'ph', label: 'pH', mean: 'mean_final_ph', sd: null, individual: (r) => r.final_ph },
]

const fmt = (v: number | null | undefined, digits = 2) =>
  v == null ? '—' : v.toFixed(digits)

/** `mean ± sd`, or the mean alone when the bucket held one vial. A NULL sd used
 *  to be coerced to 0 and rendered as "± 0.0", which claims a measured spread of
 *  zero where none was computed at all (issue #101). */
const fmtMeanSd = (
  mean: number | null | undefined, sd: number | null | undefined, digits = 2,
) => (mean == null ? '—' : sd == null ? fmt(mean, digits) : `${fmt(mean, digits)} ± ${fmt(sd, digits)}`)

interface GroupedResultsViewProps {
  baseExperimentId: string
}

/** Base-level grouped results: mean ± std per timepoint from the rollup view,
 *  with individual replicate series overlay and drill-in links. */
export function GroupedResultsView({ baseExperimentId }: GroupedResultsViewProps) {
  const [metricKey, setMetricKey] = useState('h2_ppm')
  const [showIndividual, setShowIndividual] = useState(true)
  const metric = METRICS.find((m) => m.key === metricKey)!

  // NEW query keys — these hit the /experiments/groups/{base_id}[/rollup] endpoints,
  // which return a differently-shaped response than the existing
  // ['replicate-group', ...] / ['rollup', ...] keys used by the wrapper endpoints
  // elsewhere on the detail page. Do not reuse those keys here.
  const { data: group, isError: groupFailed } = useQuery({
    queryKey: ['replicate-group-detail', baseExperimentId],
    queryFn: () => experimentsApi.getGroup(baseExperimentId),
  })
  const { data: rollup, isLoading, isError: rollupFailed } = useQuery({
    queryKey: ['group-rollup', baseExperimentId],
    queryFn: () => experimentsApi.getGroupRollup(baseExperimentId),
  })

  // Issue #98: one series per REPLICATE LETTER, not per vial. A letter
  // sacrificed across timepoints is several rows whose single result each form
  // one time course. Outlier vials contribute no points, matching
  // v_results_scalar_rollup's exclusion so the overlay and the mean agree (D11).
  // When EVERY vial of a letter is flagged is_outlier, the series has no points
  // at all -- label it '(outlier)' so an empty legend entry reads as a
  // deliberate exclusion rather than missing data. A letter with a mix of
  // flagged and clean vials still has real points and stays unlabeled.
  const seriesLetters = useMemo(() => {
    const letters = [
      ...(group?.parent ? [{ key: 'parent', baseLabel: 'replicate 0', vials: [group.parent] }] : []),
      ...(group?.replicates ?? []).map((r) => ({
        key: r.replicate_label,
        baseLabel: `replicate ${r.replicate_label}`,
        vials: r.vials,
      })),
    ]
    return letters.slice(0, chartColors.series.length).map((letter) => {
      const allOutliers = letter.vials.length > 0 && letter.vials.every((v) => v.is_outlier)
      return { ...letter, label: `${letter.baseLabel}${allOutliers ? ' (outlier)' : ''}` }
    })
  }, [group])

  // One fetch per vial (results are stored per experiment row), flattened into
  // its letter's series below.
  const allVials = useMemo(
    () => seriesLetters.flatMap((l) => l.vials.map((v) => ({ letterKey: l.key, vial: v }))),
    [seriesLetters],
  )

  // Issue #101: members carrying NO replicate letter are vials of the stem
  // itself (SERUM_pH_002-t1/-t3/-t7 is one experiment sampled three times).
  // They deliberately form no individual series -- with one vial per bucket the
  // series would be the mean line redrawn on top of itself -- but they must
  // still be reachable, so they join the drill-in links.
  const letterlessVials = useMemo(
    () => (group?.members ?? []).filter((m) => m.replicate_label === null),
    [group],
  )
  const drillInVials = useMemo(
    () => [...allVials.map(({ vial }) => vial), ...letterlessVials],
    [allVials, letterlessVials],
  )

  // Whether the selected metric has any cross-vial spread to report. A bucket
  // holding one vial has a NULL sd, and `fmt(sd ?? 0)` used to render that as
  // "10.0 ± 0.0" -- a fabricated zero standard deviation on a single reading.
  const metricHasSpread = useMemo(
    () => metric.sd != null && (rollup ?? []).some((r) => r[metric.sd!] != null),
    [rollup, metric],
  )

  const vialResults = useQueries({
    queries: allVials.map(({ vial }) => ({
      queryKey: ['experiment-results', vial.experiment_id],
      queryFn: () => experimentsApi.getResults(vial.experiment_id),
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
        seriesLetters.forEach((letter) => {
          let value: number | null = null
          allVials.forEach(({ letterKey, vial }, i) => {
            if (letterKey !== letter.key || vial.is_outlier) return
            const match = (vialResults[i]?.data ?? []).find(
              (res) => res.time_post_reaction_bucket_days === r.time_post_reaction_bucket_days
            )
            if (match) {
              const v = metric.individual(match)
              if (v != null) value = v
            }
          })
          row[letter.key] = value
        })
        return row
      })
  }, [rollup, metric, seriesLetters, allVials, vialResults])

  if (isLoading) return <Spinner />
  // A failed fetch is not an empty result. Both queries used to fall through to
  // the empty-state copy below, so a 404 from /groups/{base_id} read as "this
  // group has no data" -- which is what disguised issue #101 as a data problem.
  if (rollupFailed || groupFailed) {
    return (
      <p className="text-sm text-red-400 py-4">
        Could not load grouped results. Try reloading; if it persists the group may no
        longer exist.
      </p>
    )
  }
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
        <div className="ml-auto flex flex-wrap items-center gap-2 text-xs text-ink-secondary pb-2">
          {drillInVials.map((vial) => (
            <Link
              key={vial.id}
              to={`/experiments/${vial.experiment_id}`}
              className={`font-mono-data ${vial.is_outlier ? 'text-ink-muted line-through hover:text-ink-secondary' : 'text-red-400 hover:text-red-300'}`}
            >
              {vial.experiment_id}
              {vial.is_outlier ? ' (outlier)' : ''}
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
              seriesLetters.map((letter, i) => (
                <Line
                  key={letter.key} dataKey={letter.key} name={letter.label}
                  stroke={chartColors.series[i]} strokeWidth={1.5}
                  dot={{ r: 4, fill: chartColors.series[i] }} connectNulls
                />
              ))}
            <Line
              dataKey="mean"
              name={metricHasSpread ? `mean ± sd (${metric.label})` : metric.label}
              stroke={chartColors.mean} strokeWidth={2}
              dot={{ r: 5, fill: chartColors.mean }} connectNulls
            >
              {metricHasSpread && (
                <ErrorBar dataKey="sd" stroke={chartColors.mean} strokeWidth={1.5} width={6} />
              )}
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
            <Th>H₂ (ppm)</Th>
            <Th>H₂ (µmol)</Th>
            <Th>H₂ (g/t)</Th>
            <Th>Fe²⁺ → H₂ (%)</Th>
            <Th>pH</Th>
          </tr>
        </TableHead>
        <TableBody>
          {rollup.map((r) => (
            <TableRow key={`${r.base_experiment_id}-${r.time_post_reaction_bucket_days}`}>
              <Td className="font-mono-data">{fmt(r.time_post_reaction_bucket_days, 1)}</Td>
              <Td className="font-mono-data text-ink-muted">n = {r.n_vials}</Td>
              <Td className="font-mono-data">
                {fmtMeanSd(r.mean_h2_ppm, r.sd_h2_ppm, 1)}
              </Td>
              <Td className="font-mono-data">
                {fmtMeanSd(r.mean_h2_micromoles, r.sd_h2_micromoles, 1)}
              </Td>
              <Td className="font-mono-data">
                {fmtMeanSd(r.mean_h2_grams_per_ton, r.sd_h2_grams_per_ton, 1)}
              </Td>
              <Td className="font-mono-data">
                {fmtMeanSd(r.mean_fe_yield_h2_pct, r.sd_fe_yield_h2_pct)}
              </Td>
              <Td className="font-mono-data">{fmt(r.mean_final_ph)}</Td>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
