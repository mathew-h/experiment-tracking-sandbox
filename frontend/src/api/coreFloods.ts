import { apiClient } from './client'
import type { IcpRow } from './icp'
import type { RunSampleNote, RunSegment } from './runs'

export type CoreFloodWarningCode =
  | 'multiple_roots'
  | 'multiple_ongoing'
  | 'missing_pore_volume'
  | 'missing_description'
  | 'sample_missing_flow_rate'

export interface CoreFloodWarning {
  code: CoreFloodWarningCode
  experiment_ids: string[]
}

/** Shared with the HPHT run endpoints (issue #149). */
export type CoreFloodSegment = RunSegment
export type CoreFloodSampleNote = RunSampleNote

/** One v_core_flood_samples row; names are the view's column names. */
export interface CoreFloodSample {
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
  flow_rate_mL_min: number | null
  nitrogen_flow_rate_mL_min: number | null
  inlet_pressure_psi: number | null
  outlet_pressure_psi: number | null
  sampling_volume_mL: number | null
  h2_concentration: number | null
  gas_sampling_volume_ml: number | null
  gas_sampling_pressure_MPa: number | null
  h2_micromoles: number | null
  h2_mass_ug: number | null
  h2_grams_per_ton_yield: number | null
  final_ph: number | null
  final_conductivity_mS_cm: number | null
  pore_volume_mL: number | null
  interval_days: number | null
  cumulative_liquid_volume_mL: number | null
  cumulative_pore_volumes: number | null
  cumulative_h2_grams_per_ton: number | null
  h2_grams_per_ton_per_day: number | null
  is_hold_interval: boolean | null
  permeability_flow_rate_mL_min: number | null
  /** Ordered by id. */
  notes: CoreFloodSampleNote[]
}

export interface CoreFloodRun {
  base_id: string
  segments: CoreFloodSegment[]
  samples: CoreFloodSample[]
  warnings: CoreFloodWarning[]
}

export interface CoreFloodRunListItem {
  base_id: string
  segment_count: number
  ongoing_experiment_ids: string[]
  rig: string | null
  sample_count: number
  first_sample_date: string | null
  last_sample_date: string | null
  latest_cumulative_h2_grams_per_ton: number | null
  warning_count: number
  description: string | null
}

/** Shared with the Experiment Detail ICP chart (issue #143). */
export type CoreFloodIcpRow = IcpRow

/** Body of POST /core-floods/{experiment_id}/samples. Dates are YYYY-MM-DD. */
export interface CoreFloodSampleCreate {
  measurement_date: string
  flow_rate_mL_min: number
  time_post_reaction_days?: number
  gc_run_date?: number | string | null
  sample_tube_number?: number | string | null
  sampling_volume_mL?: number | string | null
  h2_concentration?: number | string | null
  gas_sampling_volume_ml?: number | string | null
  gas_sampling_pressure_MPa?: number | string | null
  final_ph?: number | string | null
  final_conductivity_mS_cm?: number | string | null
  nitrogen_flow_rate_mL_min?: number | string | null
  inlet_pressure_psi?: number | string | null
  outlet_pressure_psi?: number | string | null
  permeability_flow_rate_mL_min?: number | string | null
  /** On PATCH, null or blank deletes the first result note; omitted leaves notes alone. */
  result_note?: string | null
}

/** Body of PATCH /core-floods/samples/{result_id}; the day is not editable. */
export type CoreFloodSampleUpdate = Partial<Omit<CoreFloodSampleCreate, 'time_post_reaction_days'>>

export const coreFloodsApi = {
  list: (params: { scope: 'active' | 'all'; q?: string }) =>
    apiClient.get<CoreFloodRunListItem[]>('/core-floods', { params }).then((r) => r.data),

  get: (baseId: string) =>
    apiClient
      .get<CoreFloodRun>(`/core-floods/${encodeURIComponent(baseId)}`)
      .then((r) => r.data),

  icp: (baseId: string) =>
    apiClient
      .get<CoreFloodIcpRow[]>(`/core-floods/${encodeURIComponent(baseId)}/icp`)
      .then((r) => r.data),

  createSample: (experimentId: string, body: CoreFloodSampleCreate) =>
    apiClient
      .post<CoreFloodSample>(`/core-floods/${encodeURIComponent(experimentId)}/samples`, body)
      .then((r) => r.data),

  updateSample: (resultId: number, body: CoreFloodSampleUpdate) =>
    apiClient
      .patch<CoreFloodSample>(`/core-floods/samples/${resultId}`, body)
      .then((r) => r.data),
}
