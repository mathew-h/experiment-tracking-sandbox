import { apiClient } from './client'

export interface ReactorStatus {
  reactor_number: number
  experiment_id: string | null
  experiment_fk: number | null
  status: string | null
  researcher: string | null
  days_running: number | null
  temperature_c: number | null
  experiment_type: string | null
}

export interface TimelineEntry {
  result_id: number
  time_post_reaction_days: number
  cumulative_time_post_reaction_days: number
  description: string
  created_at: string
}

export const dashboardApi = {
  reactorStatus: () =>
    apiClient.get<ReactorStatus[]>('/dashboard/reactor-status').then((r) => r.data),

  timeline: (experimentId: string) =>
    apiClient.get<TimelineEntry[]>(`/dashboard/timeline/${experimentId}`).then((r) => r.data),
}
