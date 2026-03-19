export type ExperimentType = 'Serum' | 'HPHT' | 'Autoclave' | 'Core Flood'

export type ConditionField =
  | 'particle_size' | 'initial_ph' | 'rock_mass_g' | 'water_volume_mL'
  | 'temperature_c' | 'reactor_number' | 'feedstock' | 'stir_speed_rpm'
  | 'initial_conductivity_mS_cm' | 'room_temp_pressure_psi' | 'rxn_temp_pressure_psi'
  | 'co2_partial_pressure_MPa' | 'core_height_cm' | 'core_width_cm'
  | 'confining_pressure' | 'pore_pressure'

export const FIELD_VISIBILITY: Record<ExperimentType, Set<ConditionField>> = {
  Serum: new Set([
    'particle_size', 'initial_ph', 'rock_mass_g', 'water_volume_mL',
    'temperature_c', 'feedstock', 'stir_speed_rpm', 'initial_conductivity_mS_cm',
  ]),
  HPHT: new Set([
    'particle_size', 'initial_ph', 'rock_mass_g', 'water_volume_mL',
    'temperature_c', 'reactor_number', 'feedstock', 'stir_speed_rpm',
    'initial_conductivity_mS_cm', 'room_temp_pressure_psi', 'rxn_temp_pressure_psi',
    'co2_partial_pressure_MPa',
  ]),
  Autoclave: new Set([
    'particle_size', 'initial_ph', 'rock_mass_g', 'water_volume_mL',
    'temperature_c', 'feedstock', 'initial_conductivity_mS_cm',
  ]),
  'Core Flood': new Set([
    'particle_size', 'initial_ph', 'rock_mass_g', 'water_volume_mL',
    'temperature_c', 'reactor_number', 'feedstock', 'initial_conductivity_mS_cm',
    'room_temp_pressure_psi', 'rxn_temp_pressure_psi',
    'core_height_cm', 'core_width_cm', 'confining_pressure', 'pore_pressure',
  ]),
}

export function isVisible(field: ConditionField, type: ExperimentType | ''): boolean {
  if (!type) return false
  return FIELD_VISIBILITY[type]?.has(field) ?? false
}
