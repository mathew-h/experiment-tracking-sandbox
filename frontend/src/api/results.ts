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

export interface ScalarResult {
  id: number
  result_id: number
  final_ph: number | null
  final_conductivity_mS_cm: number | null
  gross_ammonium_concentration_mM: number | null
  background_ammonium_concentration_mM: number | null
  grams_per_ton_yield: number | null
  ferrous_iron_yield: number | null
  h2_concentration: number | null
  h2_micromoles: number | null
  h2_grams_per_ton_yield: number | null
  measurement_date: string | null
}

export const resultsApi = {
  list: (experimentId: string | number) =>
    apiClient.get<ExperimentResult[]>(`/results/${experimentId}`).then((r) => r.data),

  createResult: (payload: Partial<ExperimentResult>) =>
    apiClient.post<ExperimentResult>('/results', payload).then((r) => r.data),

  listScalar: (params?: { result_id?: number }) =>
    apiClient.get<ScalarResult[]>('/results/scalar/', { params }).then((r) => r.data),

  patchScalar: (id: number, payload: Partial<ScalarResult>) =>
    apiClient.patch<ScalarResult>(`/results/scalar/${id}`, payload).then((r) => r.data),
}
