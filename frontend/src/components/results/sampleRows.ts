/** One row shape for every samples table (issue #163). Each page keeps its own
 *  endpoint (v_hpht_samples, v_core_flood_samples, GET /experiments/{id}/results)
 *  and adapts its rows here, so RunSamplesTable never needs to know the source. */
import type { CoreFloodSample } from '@/api/coreFloods'
import type { ResultWithFlags } from '@/api/experiments'
import type { HphtSample } from '@/api/hpht'
import type { RunSampleNote } from '@/api/runs'

/** A timepoint note as the table shows it. `needs_review` only comes from the Results tab. */
export type SampleNote = Omit<RunSampleNote, 'note_type'> & {
  note_type: RunSampleNote['note_type'] | string
  needs_review?: boolean
}

/** An instrument run date (provenance, not a measurement). */
export interface RunDate {
  label: 'NMR' | 'ICP' | 'GC' | 'XRD'
  value: string | null
}

export interface SampleRow<S = unknown> {
  resultId: number
  experimentId: string
  isVariant: boolean
  /** The primary result for its timepoint. Run-page rows are always primary. */
  isPrimary: boolean
  /** Sample date, ISO; shown as the lab calendar date. */
  date: string | null
  /** Run pages: cumulative day since the run started. Results tab: the segment's own day. */
  day: number | null
  tube: number | null
  h2Ppm: number | null
  h2Umol: number | null
  h2Gt: number | null
  cumH2Gt: number | null
  h2GtPerDay: number | null
  fe2H2Pct: number | null
  ph: number | null
  cond: number | null
  liqMl: number | null
  flow: number | null
  permFlow: number | null
  inletPsi: number | null
  outletPsi: number | null
  notes: SampleNote[]
  /** Only the dates this row's source carries; run-page rows carry GC alone. */
  runDates: RunDate[]
  /** The page's own row, handed back to its edit callback. */
  source: S
}

const NO_CORE_FLOOD = { flow: null, permFlow: null, inletPsi: null, outletPsi: null } as const

export function fromHpht(s: HphtSample): SampleRow<HphtSample> {
  return {
    resultId: s.result_id,
    experimentId: s.experiment_id,
    isVariant: s.is_variant,
    isPrimary: true,
    date: s.sample_date,
    day: s.cumulative_time_post_reaction_days,
    tube: s.sample_tube_number,
    h2Ppm: s.h2_concentration,
    h2Umol: s.h2_micromoles,
    h2Gt: s.h2_grams_per_ton_yield,
    cumH2Gt: s.cumulative_h2_grams_per_ton,
    h2GtPerDay: s.h2_grams_per_ton_per_day,
    fe2H2Pct: s.ferrous_iron_yield_h2_pct,
    ph: s.final_ph,
    cond: s.final_conductivity_mS_cm,
    liqMl: s.sampling_volume_mL,
    ...NO_CORE_FLOOD,
    notes: s.notes,
    runDates: [{ label: 'GC', value: s.gc_run_date }],
    source: s,
  }
}

export function fromCoreFlood(s: CoreFloodSample): SampleRow<CoreFloodSample> {
  return {
    resultId: s.result_id,
    experimentId: s.experiment_id,
    isVariant: s.is_variant,
    isPrimary: true,
    date: s.sample_date,
    day: s.cumulative_time_post_reaction_days,
    tube: s.sample_tube_number,
    h2Ppm: s.h2_concentration,
    h2Umol: s.h2_micromoles,
    h2Gt: s.h2_grams_per_ton_yield,
    cumH2Gt: s.cumulative_h2_grams_per_ton,
    h2GtPerDay: s.h2_grams_per_ton_per_day,
    // v_core_flood_samples has no Fe²⁺ yield; the column is not shown for core floods.
    fe2H2Pct: null,
    ph: s.final_ph,
    cond: s.final_conductivity_mS_cm,
    liqMl: s.sampling_volume_mL,
    flow: s.flow_rate_mL_min,
    permFlow: s.permeability_flow_rate_mL_min,
    inletPsi: s.inlet_pressure_psi,
    outletPsi: s.outlet_pressure_psi,
    notes: s.notes,
    runDates: [{ label: 'GC', value: s.gc_run_date }],
    source: s,
  }
}

export function fromResult(r: ResultWithFlags, experimentId: string): SampleRow<ResultWithFlags> {
  return {
    resultId: r.id,
    experimentId,
    isVariant: false,
    isPrimary: r.is_primary_timepoint_result,
    date: r.scalar_measurement_date,
    day: r.time_post_reaction_days,
    tube: r.sample_tube_number ?? null,
    h2Ppm: r.h2_concentration,
    h2Umol: r.h2_micromoles,
    h2Gt: r.h2_grams_per_ton_yield,
    cumH2Gt: null,
    h2GtPerDay: null,
    fe2H2Pct: r.ferrous_iron_yield_h2_pct,
    ph: r.final_ph,
    cond: r.final_conductivity_mS_cm,
    liqMl: null,
    ...NO_CORE_FLOOD,
    notes: r.notes.map((n) => ({
      id: n.id,
      note_type: n.note_type,
      note_text: n.note_text,
      created_by: n.created_by,
      needs_review: n.needs_review,
    })),
    runDates: [
      { label: 'NMR', value: r.nmr_run_date },
      { label: 'ICP', value: r.icp_run_date },
      { label: 'GC', value: r.gc_run_date },
      { label: 'XRD', value: r.xrd_run_date },
    ],
    source: r,
  }
}
