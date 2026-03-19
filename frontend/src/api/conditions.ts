import { apiClient } from './client'

export interface ConditionsPayload {
  experiment_fk: number
  experiment_id: string
  experiment_type?: string
  temperature_c?: number
  initial_ph?: number
  rock_mass_g?: number
  water_volume_mL?: number
  particle_size?: string
  feedstock?: string
  reactor_number?: number
  stir_speed_rpm?: number
  initial_conductivity_mS_cm?: number
  room_temp_pressure_psi?: number
  rxn_temp_pressure_psi?: number
  co2_partial_pressure_MPa?: number
  core_height_cm?: number
  core_width_cm?: number
  confining_pressure?: number
  pore_pressure?: number
}

export interface ConditionsResponse extends ConditionsPayload {
  id: number
  water_to_rock_ratio?: number | null
  created_at: string
}

export const conditionsApi = {
  create: (payload: ConditionsPayload) =>
    apiClient.post<ConditionsResponse>('/conditions', payload).then((r) => r.data),

  getByExperiment: (experimentId: string) =>
    apiClient.get<ConditionsResponse>(`/conditions/by-experiment/${experimentId}`).then((r) => r.data),

  patch: (conditionsId: number, payload: Partial<ConditionsPayload>) =>
    apiClient.patch<ConditionsResponse>(`/conditions/${conditionsId}`, payload).then((r) => r.data),
}
