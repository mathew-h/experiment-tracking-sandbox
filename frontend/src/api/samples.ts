import { apiClient } from './client'

export interface Sample {
  sample_id: string
  rock_classification: string | null
  state: string | null
  country: string | null
  locality: string | null
  latitude: number | null
  longitude: number | null
  description: string | null
  characterized: boolean
  created_at: string
  updated_at: string
}

export const samplesApi = {
  list: (params?: { skip?: number; limit?: number }) =>
    apiClient.get<Sample[]>('/samples', { params }).then((r) => r.data),

  get: (id: string) =>
    apiClient.get<Sample>(`/samples/${id}`).then((r) => r.data),

  create: (payload: Partial<Sample>) =>
    apiClient.post<Sample>('/samples', payload).then((r) => r.data),

  patch: (id: string, payload: Partial<Sample>) =>
    apiClient.patch<Sample>(`/samples/${id}`, payload).then((r) => r.data),
}
