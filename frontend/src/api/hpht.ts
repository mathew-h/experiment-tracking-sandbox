import { apiClient } from './client'
import type { IcpRow } from './icp'
import type { RunSampleNote, RunSegment } from './runs'

/** Read-only client for the HPHT run endpoints (issue #149). Samples are
 *  written through experimentsApi.createResult / updateResult (#146). */

export type HphtWarningCode =
  | 'multiple_roots'
  | 'multiple_ongoing'
  | 'missing_description'
  | 'base_mismatch'

export interface HphtWarning {
  code: HphtWarningCode
  experiment_ids: string[]
}

/** Setup of the run's latest non-variant segment. `catalyst` / `catalyst_ppm`
 *  are legacy columns, usually empty; catalysts come from the additives. */
export interface HphtConditionsSummary {
  experiment_id: string
  conditions_id: number
  date: string | null
  sample_id: string | null
  temperature_c: number | null
  rxn_temp_pressure_psi: number | null
  rock_mass_g: number | null
  water_volume_mL: number | null
  water_to_rock_ratio: number | null
  catalyst: string | null
  catalyst_ppm: number | null
  feedstock: string | null
}

/** One v_hpht_samples row; names are the view's column names. Derived columns
 *  are NULL on variant rows. */
export interface HphtSample {
  result_id: number
  experiment_id: string
  experiment_fk: number
  run_base_id: string | null
  is_variant: boolean
  time_post_reaction_days: number | null
  cumulative_time_post_reaction_days: number | null
  sample_date: string | null
  gc_run_date: string | null
  sample_tube_number: number | null
  sampling_volume_mL: number | null
  h2_concentration: number | null
  gas_sampling_volume_ml: number | null
  gas_sampling_pressure_MPa: number | null
  h2_micromoles: number | null
  h2_mass_ug: number | null
  h2_grams_per_ton_yield: number | null
  ferrous_iron_yield_h2_pct: number | null
  final_ph: number | null
  final_conductivity_mS_cm: number | null
  reactor_slot: string | null
  interval_days: number | null
  cumulative_h2_grams_per_ton: number | null
  h2_grams_per_ton_per_day: number | null
  cumulative_h2_micromoles: number | null
  cumulative_ferrous_iron_yield_h2_pct: number | null
  /** Ordered by id. */
  notes: RunSampleNote[]
}

export interface HphtRun {
  base_id: string
  segments: RunSegment[]
  conditions: HphtConditionsSummary | null
  /** Oldest first (cumulative day, then result id). */
  samples: HphtSample[]
  warnings: HphtWarning[]
}

export interface HphtRunListItem {
  base_id: string
  description: string | null
  segment_count: number
  ongoing_experiment_ids: string[]
  reactor_slot: string | null
  sample_count: number
  last_sample_date: string | null
  latest_cumulative_h2_grams_per_ton: number | null
  warning_count: number
}

export const hphtApi = {
  list: (params: { scope: 'active' | 'all'; q?: string }) =>
    apiClient.get<HphtRunListItem[]>('/hpht', { params }).then((r) => r.data),

  get: (baseId: string) =>
    apiClient.get<HphtRun>(`/hpht/${encodeURIComponent(baseId)}`).then((r) => r.data),

  icp: (baseId: string) =>
    apiClient.get<IcpRow[]>(`/hpht/${encodeURIComponent(baseId)}/icp`).then((r) => r.data),
}
