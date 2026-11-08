import { useMemo } from 'react'
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { HphtSample } from '@/api/hpht'
import { chartColors } from '@/assets/brand'
import { markerLabels, type ChartMarker } from '@/components/icp/icpSeries'
import { fmt } from '@/components/results/sampleFields'
import { chartMarkers, chartPoints, hasH2, type HphtPoint } from './hphtSeries'

interface ChartSpec {
  key: keyof Omit<HphtPoint, 'day'>
  title: string
  unit: string
  color: string
  /** Rate points stand alone per interval: dots only, no connecting line. */
  dotsOnly?: boolean
}

// Series tokens in fixed order (#140 palette); chartColors.mean is the brand red, kept off these.
const CHARTS: readonly ChartSpec[] = [
  { key: 'cumH2', title: 'Cumulative H₂', unit: 'g/t', color: chartColors.series[0] },
  { key: 'rate', title: 'H₂ rate per interval', unit: 'g/t/day', color: chartColors.series[1], dotsOnly: true },
  { key: 'cumFe', title: 'Cumulative Fe²⁺ → H₂ yield', unit: '%', color: chartColors.series[2] },
]

const TICK = { fill: chartColors.label, fontSize: 11 }

function RunChart({
  spec, points, markers,
}: { spec: ChartSpec; points: HphtPoint[]; markers: ChartMarker[] }) {
  const labels = useMemo(() => markerLabels(markers, points.map((p) => p.day)), [markers, points])
  return (
    <figure className="space-y-2" aria-label={spec.title}>
      <figcaption className="text-xs text-ink-secondary">
        {spec.title} <span className="text-ink-muted">({spec.unit})</span>
      </figcaption>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 16, right: 16, bottom: 16, left: 0 }}>
            <CartesianGrid stroke={chartColors.grid} strokeDasharray="3 3" />
            <XAxis
              dataKey="day"
              type="number"
              domain={['auto', 'auto']}
              stroke={chartColors.axis}
              tick={TICK}
              label={{ value: 'Cumulative day', position: 'insideBottom', offset: -8, ...TICK }}
            />
            <YAxis stroke={chartColors.axis} tick={TICK} width={48} />
            <Tooltip
              contentStyle={{ background: chartColors.tooltipBg, border: 'none' }}
              labelFormatter={(d) => `Day ${d}`}
              formatter={(v) => [`${fmt(typeof v === 'number' ? v : null)} ${spec.unit}`, spec.title]}
            />
            {markers.map((m, i) => (
              <ReferenceLine
                key={m.experimentId}
                x={m.day}
                stroke={chartColors.axis}
                strokeDasharray="4 4"
                label={{ value: m.experimentId, ...labels[i], fill: chartColors.label, fontSize: 10 }}
              />
            ))}
            <Line
              // Straight segments: a curve would invent H₂ between samples.
              type="linear"
              dataKey={spec.key}
              name={spec.title}
              stroke={spec.color}
              strokeWidth={spec.dotsOnly ? 0 : 2}
              dot={{ r: spec.dotsOnly ? 3 : 2, fill: spec.color, stroke: spec.color }}
              connectNulls={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  )
}

/** The run's cumulative H₂, H₂ rate and Fe²⁺ yield against cumulative day. Variants are excluded. */
export function HphtCharts({ samples }: { samples: HphtSample[] }) {
  const points = useMemo(() => chartPoints(samples), [samples])
  const markers = useMemo(() => chartMarkers(samples), [samples])
  if (!hasH2(samples)) {
    return <p className="text-sm text-ink-muted py-6 text-center">No H₂ measurements on this run yet.</p>
  }
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
      {CHARTS.map((spec) => (
        <RunChart key={spec.key} spec={spec} points={points} markers={markers} />
      ))}
    </div>
  )
}
