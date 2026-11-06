import { useMemo, useState } from 'react'
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { CoreFloodIcpRow, CoreFloodSample } from '@/api/coreFloods'
import { chartColors } from '@/assets/brand'
import { chartPoints, defaultSelection, elementsPresent, lineProps, lineStyles, segmentStarts } from './icpSeries'
import { fmt } from './fields'

const cap = (e: string) => e.charAt(0).toUpperCase() + e.slice(1)

const chip = (on: boolean) =>
  `rounded-full border px-2.5 py-0.5 text-xs font-mono-data ${
    on
      ? 'border-red-400 text-ink-primary bg-surface-raised'
      : 'border-surface-border text-ink-muted hover:text-ink-secondary'
  }`

/** Element ppm vs cumulative day, one line per selected element. */
export function IcpChart({ rows, samples }: { rows: CoreFloodIcpRow[]; samples: CoreFloodSample[] }) {
  const present = useMemo(() => elementsPresent(rows), [rows])
  const [selected, setSelected] = useState<string[] | null>(null)
  const [log, setLog] = useState(false)
  const active = selected ?? defaultSelection(present)
  // ICP_ELEMENTS order; styles are assigned by position in this selected list.
  const ordered = present.filter((e) => active.includes(e))
  const points = useMemo(() => chartPoints(rows, ordered, log), [rows, ordered, log])
  const styles = useMemo(() => lineStyles(ordered), [ordered])
  const starts = useMemo(() => segmentStarts(samples), [samples])

  const toggle = (el: string) =>
    setSelected(active.includes(el) ? active.filter((e) => e !== el) : [...active, el])
  const allOn = present.length > 0 && present.every((e) => active.includes(e))
  const toggleAll = () => setSelected(allOn ? null : present)

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" aria-pressed={allOn} onClick={toggleAll} className={chip(allOn)}>
          All
        </button>
        {present.map((el) => (
          <button
            key={el}
            type="button"
            aria-pressed={active.includes(el)}
            onClick={() => toggle(el)}
            className={chip(active.includes(el))}
          >
            {cap(el)}
          </button>
        ))}
        <button
          type="button"
          aria-pressed={log}
          onClick={() => setLog((v) => !v)}
          className={`${chip(log)} ml-auto`}
        >
          Log scale
        </button>
      </div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 16, right: 16, bottom: 16, left: 8 }}>
            <CartesianGrid stroke={chartColors.grid} strokeDasharray="3 3" />
            <XAxis
              dataKey="day"
              type="number"
              domain={['auto', 'auto']}
              stroke={chartColors.axis}
              tick={{ fill: chartColors.label, fontSize: 11 }}
              label={{ value: 'Cumulative day', position: 'insideBottom', offset: -8, fill: chartColors.label, fontSize: 11 }}
            />
            <YAxis
              scale={log ? 'log' : 'linear'}
              domain={['auto', 'auto']}
              allowDataOverflow
              stroke={chartColors.axis}
              tick={{ fill: chartColors.label, fontSize: 11 }}
              label={{ value: 'ppm', angle: -90, position: 'insideLeft', fill: chartColors.label, fontSize: 11 }}
            />
            <Tooltip
              contentStyle={{ background: chartColors.tooltipBg, border: 'none' }}
              labelFormatter={(d) => `Day ${d}`}
              formatter={(v) => fmt(typeof v === 'number' ? v : null)}
            />
            <Legend verticalAlign="top" wrapperStyle={{ paddingBottom: 8 }} />
            {starts.map((s, i) => (
              <ReferenceLine
                key={s.experimentId}
                x={s.day}
                stroke={chartColors.axis}
                strokeDasharray="4 4"
                label={{ value: s.experimentId, position: i % 2 === 0 ? 'insideTopRight' : 'insideTopLeft', fill: chartColors.label, fontSize: 10 }}
              />
            ))}
            {ordered.map((el) => (
              <Line
                key={el}
                type="monotone"
                dataKey={el}
                name={cap(el)}
                stroke={styles[el].color}
                strokeDasharray={styles[el].dash}
                dot={{ r: 2 }}
                {...lineProps(log)}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
