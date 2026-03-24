import { apiClient } from './client'

// Legacy types kept for backwards compat (existing /reactor-status endpoint)
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

// M7 full dashboard types
export interface DashboardSummary {
  active_experiments: number
  reactors_in_use: number
  completed_this_month: number
  pending_results: number
}

export interface ReactorCardData {
  reactor_number: number
  reactor_label: string
  experiment_id: string | null
  experiment_db_id: number | null
  status: string | null
  experiment_type: string | null
  sample_id: string | null
  description: string | null
  researcher: string | null
  started_at: string | null
  days_running: number | null
  temperature_c: number | null
  volume_mL: number | null
  material: string | null
  vendor: string | null
}

export interface GanttEntry {
  experiment_id: string
  experiment_db_id: number
  status: string
  experiment_type: string | null
  sample_id: string | null
  researcher: string | null
  started_at: string | null
  ended_at: string | null
  days_running: number | null
}

export interface ActivityEntry {
  id: number
  experiment_id: string | null
  modified_by: string | null
  modification_type: string
  modified_table: string
  created_at: string
}

export interface DashboardData {
  summary: DashboardSummary
  reactors: ReactorCardData[]
  timeline: GanttEntry[]
  recent_activity: ActivityEntry[]
}

export interface TimelineEntry {
  result_id: number
  time_post_reaction_days: number
  cumulative_time_post_reaction_days: number
  description: string
  created_at: string
}

export const dashboardApi = {
  // M7: single full dashboard call
  full: (): Promise<DashboardData> =>
    apiClient.get<DashboardData>('/dashboard/').then((r) => r.data),

  // Legacy: kept for compatibility
  reactorStatus: (): Promise<ReactorStatus[]> =>
    apiClient.get<ReactorStatus[]>('/dashboard/reactor-status').then((r) => r.data),

  timeline: (experimentId: string): Promise<TimelineEntry[]> =>
    apiClient.get<TimelineEntry[]>(`/dashboard/timeline/${experimentId}`).then((r) => r.data),
}
