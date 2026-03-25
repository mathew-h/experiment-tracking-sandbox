/**
 * IMPORTANT — experiment_id vs experiment_fk
 *
 * experiment_id  — the human-readable string label, e.g. "HPHT_001".
 *                  Used in URLs (/experiments/:id) and display only.
 *
 * experiment_fk  — experiments.id, the integer primary key stored in the DB.
 *                  This is the value that must appear in ALL write payloads.
 *
 * Correct pattern for result writes:
 *   const { data: experiment } = useQuery(['experiment', id], () => experimentsApi.get(id))
 *   createResult({ experiment_fk: experiment.id, ... })   // ← integer PK
 *
 * Never do:
 *   createResult({ experiment_fk: id as any, ... })       // ← URL string — FK violation
 */
import { apiClient } from './client'

export interface ExperimentResult {
  id: number
  experiment_fk: number
  time_post_reaction_days: number | null
  time_post_reaction_bucket_days: number | null
  cumulative_time_post_reaction_days: number | null
  is_primary_timepoint_result: boolean
  description: string
  created_at: string
}

/** Payload for POST /api/results. experiment_fk must be experiments.id (integer PK). */
export interface ResultCreate {
  /** experiments.id integer PK — resolve via experimentsApi.get(), never pass the URL string param */
  experiment_fk: number
  description: string
  time_post_reaction_days?: number | null
  time_post_reaction_bucket_days?: number | null
  cumulative_time_post_reaction_days?: number | null
  is_primary_timepoint_result?: boolean
}

export interface ScalarResult {
  id: number
  result_id: number
  final_ph: number | null
  final_conductivity_mS_cm: number | null
  final_dissolved_oxygen_mg_L: number | null
  gross_ammonium_concentration_mM: number | null
  background_ammonium_concentration_mM: number | null
  grams_per_ton_yield: number | null
  ferrous_iron_yield: number | null
  h2_concentration: number | null
  h2_micromoles: number | null
  h2_grams_per_ton_yield: number | null
  measurement_date: string | null
}

export interface ICPResult {
  id: number
  result_id: number
  dilution_factor: number | null
  instrument_used: string | null
  fe: number | null
  si: number | null
  mg: number | null
  ca: number | null
  ni: number | null
  cu: number | null
  mo: number | null
  zn: number | null
  mn: number | null
  cr: number | null
  co: number | null
  al: number | null
}

/** Payload for POST /api/results/scalar. result_id must be ExperimentResult.id. */
export interface ScalarCreate {
  result_id: number
  final_ph?: number | null
  final_conductivity_mS_cm?: number | null
  final_dissolved_oxygen_mg_L?: number | null
  final_nitrate_concentration_mM?: number | null
  final_alkalinity_mg_L?: number | null
  gross_ammonium_concentration_mM?: number | null
  background_ammonium_concentration_mM?: number | null
  ferrous_iron_yield?: number | null
  sampling_volume_mL?: number | null
  h2_concentration?: number | null
  gas_sampling_volume_ml?: number | null
  gas_sampling_pressure_MPa?: number | null
  background_experiment_fk?: number | null
  co2_partial_pressure_MPa?: number | null
}

export const resultsApi = {
  list: (experimentId: string | number) =>
    apiClient.get<ExperimentResult[]>(`/results/${experimentId}`).then((r) => r.data),

  /** experiment_fk in payload must be experiments.id (integer PK), not the string experiment_id */
  createResult: (payload: ResultCreate) =>
    apiClient.post<ExperimentResult>('/results', payload).then((r) => r.data),

  createScalar: (payload: ScalarCreate) =>
    apiClient.post<ScalarResult>('/results/scalar', payload).then((r) => r.data),

  listScalar: (params?: { result_id?: number }) =>
    apiClient.get<ScalarResult[]>('/results/scalar/', { params }).then((r) => r.data),

  patchScalar: (id: number, payload: Partial<ScalarResult>) =>
    apiClient.patch<ScalarResult>(`/results/scalar/${id}`, payload).then((r) => r.data),

  getIcp: (resultId: number) =>
    apiClient.get<ICPResult>(`/results/icp/${resultId}`).then((r) => r.data),
}
