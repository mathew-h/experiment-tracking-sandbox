import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import type { HphtConditionsSummary } from '@/api/hpht'
import { chemicalsApi } from '@/api/chemicals'
import { Card, CardHeader } from '@/components/ui'
import { SegmentLink } from '@/components/runs/SegmentLink'
import { fmt } from '@/components/results/sampleFields'
import { formatPrecise } from '@/utils/numberFormat'
import { labDateOf } from '@/utils/labDate'

const HEADING = 'text-xs font-semibold text-ink-secondary uppercase tracking-wider'

function Item({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className="text-sm font-mono-data text-ink-primary">{children}</dd>
    </div>
  )
}

const withUnit = (v: number | null, unit: string) => (v == null ? '—' : `${fmt(v)} ${unit}`)

/** Read-only setup of the run's latest non-variant segment, with its additives.
 *  Edits happen on that segment's Conditions tab. */
export function ConditionsSummaryCard({ conditions }: { conditions: HphtConditionsSummary | null }) {
  const experimentId = conditions?.experiment_id
  // An additives failure leaves the row as "—"; the rest of the card still renders.
  const { data: additives } = useQuery({
    queryKey: ['additives', experimentId],
    queryFn: () => chemicalsApi.listExperimentAdditives(experimentId as string),
    enabled: !!experimentId,
  })

  return (
    <section aria-labelledby="conditions-heading">
      <Card padding="none">
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2 w-full">
            <h2 id="conditions-heading" className={HEADING}>
              Conditions
              {experimentId && (
                <SegmentLink id={experimentId} className="ml-2 normal-case tracking-normal font-normal" />
              )}
            </h2>
            {experimentId && (
              <Link
                // Explicit tab (issue #162), in case the detail page's default ever changes.
                to={`/experiments/${encodeURIComponent(experimentId)}?tab=conditions`}
                className="text-xs text-red-400 hover:text-red-300"
              >
                Edit on Conditions tab
              </Link>
            )}
          </div>
        </CardHeader>
        <div className="p-4">
          {!conditions ? (
            <p className="text-sm text-ink-muted">No conditions recorded for this run.</p>
          ) : (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 xl:grid-cols-5">
              <Item label="Temperature">{withUnit(conditions.temperature_c, '°C')}</Item>
              <Item label="Reaction pressure">{withUnit(conditions.rxn_temp_pressure_psi, 'psi')}</Item>
              <Item label="Rock mass">{withUnit(conditions.rock_mass_g, 'g')}</Item>
              <Item label="Water volume">{withUnit(conditions.water_volume_mL, 'mL')}</Item>
              <Item label="W:R">{fmt(conditions.water_to_rock_ratio)}</Item>
              <Item label="Catalyst">
                {conditions.catalyst
                  ? `${conditions.catalyst}${conditions.catalyst_ppm != null ? ` (${formatPrecise(conditions.catalyst_ppm)} ppm)` : ''}`
                  : '—'}
              </Item>
              <Item label="Feedstock">{conditions.feedstock ?? '—'}</Item>
              <Item label="Sample ID">{conditions.sample_id ?? '—'}</Item>
              <Item label="Start date">{conditions.date ? labDateOf(conditions.date) : '—'}</Item>
              <Item label="Additives">
                {additives && additives.length > 0 ? (
                  <ul className="space-y-0.5">
                    {additives.map((a) => (
                      <li key={a.id}>
                        {a.compound?.name ?? `Compound #${a.compound_id}`} {formatPrecise(a.amount)} {a.unit}
                      </li>
                    ))}
                  </ul>
                ) : (
                  '—'
                )}
              </Item>
            </dl>
          )}
        </div>
      </Card>
    </section>
  )
}
