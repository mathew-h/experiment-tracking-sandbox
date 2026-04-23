import { apiClient } from './client'

export type ExperimentStatus = 'ONGOING' | 'COMPLETED' | 'CANCELLED' | 'QUEUED'

export interface ExperimentListItem {
  id: number
  experiment_id: string
  experiment_number: number
  status: ExperimentStatus
  researcher: string | null
  date: string | null
  sample_id: string | null
  created_at: string
  experiment_type: string | null
  reactor_number: number | null
  additives_summary: string | null
  condition_note: string | null
}

export interface ExperimentListResponse {
  items: ExperimentListItem[]
  total: number
  skip: number
  limit: number
}

export interface ExperimentDetail {
  id: number
  experiment_id: string
  experiment_number: number
  status: ExperimentStatus
  researcher: string | null
  date: string | null
  sample_id: string | null
  base_experiment_id: string | null
  parent_experiment_fk: number | null
  created_at: string
  updated_at: string | null
  conditions: Record<string, unknown> | null
  notes: Array<{ id: number; note_text: string; created_at: string; updated_at: string | null }>
  modifications: Array<{
    id: number
    modified_by: string | null
    modification_type: string | null
    modified_table: string | null
    old_values: Record<string, unknown> | null
    new_values: Record<string, unknown> | null
    created_at: string
  }>
}

export interface ResultWithFlags {
  id: number
  experiment_fk: number
  time_post_reaction_days: number | null
  time_post_reaction_bucket_days: number | null
  cumulative_time_post_reaction_days: number | null
  is_primary_timepoint_result: boolean
  description: string
  created_at: string
  has_scalar: boolean
  has_icp: boolean
  has_brine_modification: boolean
  brine_modification_description: string | null
  grams_per_ton_yield: number | null
  h2_grams_per_ton_yield: number | null
  h2_micromoles: number | null
  gross_ammonium_concentration_mM: number | null
  background_ammonium_concentration_mM: number | null
  final_conductivity_mS_cm: number | null
  final_ph: number | null
  scalar_measurement_date: string | null
  ferrous_iron_yield_h2_pct: number | null
  ferrous_iron_yield_nh3_pct: number | null
  xrd_run_date: string | null
}

export interface ExperimentListParams {
  status?: string
  researcher?: string
  search?: string
  sample_id?: string
  experiment_type?: string
  reactor_number?: number
  date_from?: string
  date_to?: string
  skip?: number
  limit?: number
}

export interface CreateExperimentPayload {
  experiment_id: string
  status?: string
  researcher?: string
  date?: string
  sample_id?: string
  experiment_type?: string
  note?: string
}

export interface ChangeRequestEntry {
  id: number
  reactor_label: string
  requested_change: string
  notion_status: string
  carried_forward: boolean
  sync_date: string
  created_at: string
}

export const experimentsApi = {
  list: (params?: ExperimentListParams) =>
    apiClient.get<ExperimentListResponse>('/experiments', { params }).then((r) => r.data),

  get: (experimentId: string) =>
    apiClient.get<ExperimentDetail>(`/experiments/${experimentId}`).then((r) => r.data),

  create: (payload: CreateExperimentPayload) =>
    apiClient.post<ExperimentDetail>('/experiments', payload).then((r) => r.data),

  patch: (
    experimentId: string,
    payload: {
      status?: string
      researcher?: string
      date?: string
      experiment_id?: string
    },
  ) =>
    apiClient
      .patch<ExperimentDetail>(`/experiments/${experimentId}`, payload)
      .then((r) => r.data),

  patchStatus: (experimentId: string, status: ExperimentStatus) =>
    apiClient.patch<ExperimentDetail>(`/experiments/${experimentId}/status`, { status }).then((r) => r.data),

  nextId: (type: string) =>
    apiClient.get<{ next_id: string }>('/experiments/next-id', { params: { type } }).then((r) => r.data),

  checkExists: (experimentId: string) =>
    apiClient
      .get<{ exists: boolean }>(`/experiments/${encodeURIComponent(experimentId)}/exists`)
      .then((r) => r.data),

  getResults: (experimentId: string) =>
    apiClient.get<ResultWithFlags[]>(`/experiments/${experimentId}/results`).then((r) => r.data),

  setBackgroundAmmonium: (experimentId: string, value: number) =>
    apiClient.patch<{ updated: number }>(`/experiments/${experimentId}/background-ammonium`, { value }).then((r) => r.data),

  addNote: (experimentId: string, text: string) =>
    apiClient.post(`/experiments/${experimentId}/notes`, { note_text: text }).then((r) => r.data),

  patchNote: (experimentId: string, noteId: number, text: string) =>
    apiClient.patch<{ id: number; note_text: string; created_at: string; updated_at: string | null }>(`/experiments/${experimentId}/notes/${noteId}`, { note_text: text }),

  deleteNote: (experimentId: string, noteId: number) =>
    apiClient.delete(`/experiments/${experimentId}/notes/${noteId}`),

  getChangeRequests: (experimentId: string) =>
    apiClient.get<ChangeRequestEntry[]>(
      `/experiments/${experimentId}/change-requests`
    ).then((r) => r.data),

  delete: (experimentId: string) =>
    apiClient.delete(`/experiments/${experimentId}`).then((r) => r.data),
}
