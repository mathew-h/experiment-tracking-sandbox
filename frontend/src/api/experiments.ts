import { apiClient } from './client'

export interface Experiment {
  id: number
  experiment_id: string
  experiment_number: number
  status: 'ONGOING' | 'COMPLETED' | 'CANCELLED'
  researcher: string | null
  date: string | null
  sample_id: string | null
  base_experiment_id: string | null
  parent_experiment_fk: number | null
  created_at: string
  updated_at: string
}

export interface ExperimentDetail extends Experiment {
  conditions: Record<string, unknown> | null
  results: unknown[]
  notes: unknown[]
}

export interface ExperimentListParams {
  status?: string
  researcher?: string
  sample_id?: string
  skip?: number
  limit?: number
}

export interface CreateExperimentPayload {
  experiment_id: string
  status?: string
  researcher?: string
  date?: string
  sample_id?: string
  base_experiment_id?: string
  parent_experiment_fk?: number
}

export interface PatchExperimentPayload {
  status?: string
  researcher?: string
  date?: string
}

export const experimentsApi = {
  list: (params?: ExperimentListParams) =>
    apiClient.get<Experiment[]>('/experiments', { params }).then((r) => r.data),

  get: (id: string | number) =>
    apiClient.get<ExperimentDetail>(`/experiments/${id}`).then((r) => r.data),

  create: (payload: CreateExperimentPayload) =>
    apiClient.post<ExperimentDetail>('/experiments', payload).then((r) => r.data),

  patch: (id: string | number, payload: PatchExperimentPayload) =>
    apiClient.patch<ExperimentDetail>(`/experiments/${id}`, payload).then((r) => r.data),

  delete: (id: string | number) =>
    apiClient.delete(`/experiments/${id}`).then((r) => r.data),

  addNote: (id: string | number, text: string) =>
    apiClient.post(`/experiments/${id}/notes`, { note_text: text }).then((r) => r.data),
}
