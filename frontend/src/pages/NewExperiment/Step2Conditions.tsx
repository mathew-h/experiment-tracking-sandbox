import { Input, Select, Button } from '@/components/ui'
import { isVisible } from './fieldVisibility'
import type { ExperimentType } from './fieldVisibility'
import { parseVialSize, VIAL_SIZE_MAX_ML } from './vialSize'
import { slotOptionsFor } from '@/utils/reactorSlots'

const FEEDSTOCK_OPTIONS = [
  { value: 'Nitrogen', label: 'Nitrogen' },
  { value: 'Nitrate', label: 'Nitrate' },
  { value: 'Blank', label: 'None / Blank' },
]

export interface Step2Data {
  temperature_c: string
  initial_ph: string
  rock_mass_g: string
  water_volume_mL: string
  serum_vial_size_mL: string
  particle_size: string
  feedstock: string
  /** Picked slot label ('R03', 'P03', 'CF01'); split into reactor_number +
   *  reactor_series on submit (issue #147). */
  reactor_slot: string
  stir_speed_rpm: string
  initial_conductivity_mS_cm: string
  room_temp_pressure_psi: string
  rxn_temp_pressure_psi: string
  co2_partial_pressure_MPa: string
  core_height_cm: string
  core_width_cm: string
  pore_volume_mL: string
  confining_pressure: string
  pore_pressure: string
}

interface Props {
  data: Step2Data
  experimentType: ExperimentType | ''
  onChange: (patch: Partial<Step2Data>) => void
  onBack: () => void
  onNext: () => void
}

function field(
  label: string,
  key: keyof Step2Data,
  type: ExperimentType | '',
  data: Step2Data,
  onChange: (p: Partial<Step2Data>) => void,
  unit?: string,
  inputType = 'number',
) {
  if (!isVisible(key as never, type)) return null
  return (
    <Input
      key={key}
      label={unit ? `${label} (${unit})` : label}
      type={inputType}
      value={data[key]}
      onChange={(e) => onChange({ [key]: e.target.value } as Partial<Step2Data>)}
    />
  )
}

/** Step 2 of new experiment wizard: reactor conditions, pressure, and fluid parameters. */
export function Step2Conditions({ data, experimentType, onChange, onBack, onNext }: Props) {
  const rockMass = parseFloat(data.rock_mass_g)
  const waterVol = parseFloat(data.water_volume_mL)
  const wtr = (!isNaN(rockMass) && !isNaN(waterVol) && rockMass > 0)
    ? (waterVol / rockMass).toFixed(2)
    : null
  // The field() helper can't carry step/min/error, so this input is rendered directly.
  const vialVisible = isVisible('serum_vial_size_mL', experimentType)
  const vialError = vialVisible ? parseVialSize(data.serum_vial_size_mL).error : undefined

  // Core Flood only. The wizard creates the experiment before its conditions, so a
  // 422 on the conditions POST would strand an experiment with no conditions row.
  const poreVisible = isVisible('pore_volume_mL', experimentType)
  const poreBlank = data.pore_volume_mL.trim() === ''
  const poreError = poreVisible && !poreBlank && !(Number(data.pore_volume_mL) > 0)
    ? 'Must be greater than 0'
    : undefined

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        {field('Temperature', 'temperature_c', experimentType, data, onChange, '°C')}
        {field('Initial pH', 'initial_ph', experimentType, data, onChange)}
        {field('Rock Mass', 'rock_mass_g', experimentType, data, onChange, 'g')}
        {field('Water Volume', 'water_volume_mL', experimentType, data, onChange, 'mL')}
        {vialVisible && (
          <Input
            label="Serum Vial Size (mL)"
            type="number"
            step={1}
            min={1}
            max={VIAL_SIZE_MAX_ML}
            value={data.serum_vial_size_mL}
            error={vialError}
            onChange={(e) => onChange({ serum_vial_size_mL: e.target.value })}
          />
        )}
        {wtr && (
          <div className="col-span-2 flex items-center gap-2 p-2 bg-surface-raised rounded text-xs text-ink-secondary">
            <span className="text-ink-muted">Water : Rock Ratio</span>
            <span className="font-mono-data text-ink-primary ml-auto">{wtr}</span>
          </div>
        )}
        {field('Particle Size', 'particle_size', experimentType, data, onChange, undefined, 'text')}
        {isVisible('feedstock', experimentType) && (
          <Select
            label="Feedstock"
            options={FEEDSTOCK_OPTIONS}
            placeholder="Select…"
            value={data.feedstock}
            onChange={(e) => onChange({ feedstock: e.target.value })}
          />
        )}
        {isVisible('reactor_number', experimentType) && (
          <Select
            label="Reactor"
            options={slotOptionsFor(experimentType)}
            placeholder="Select…"
            value={data.reactor_slot}
            onChange={(e) => onChange({ reactor_slot: e.target.value })}
          />
        )}
        {field('Stir Speed', 'stir_speed_rpm', experimentType, data, onChange, 'RPM')}
        {field('Initial Conductivity', 'initial_conductivity_mS_cm', experimentType, data, onChange, 'mS/cm')}
        {field('Room Temp Pressure', 'room_temp_pressure_psi', experimentType, data, onChange, 'psi')}
        {field('Rxn Temp Pressure', 'rxn_temp_pressure_psi', experimentType, data, onChange, 'psi')}
        {field('CO₂ Partial Pressure', 'co2_partial_pressure_MPa', experimentType, data, onChange, 'MPa')}
        {field('Core Height', 'core_height_cm', experimentType, data, onChange, 'cm')}
        {field('Core Width', 'core_width_cm', experimentType, data, onChange, 'cm')}
        {poreVisible && (
          <Input
            label="Pore Volume (mL)"
            type="number"
            min={0}
            value={data.pore_volume_mL}
            error={poreError}
            onChange={(e) => onChange({ pore_volume_mL: e.target.value })}
          />
        )}
        {field('Confining Pressure', 'confining_pressure', experimentType, data, onChange)}
        {field('Pore Pressure', 'pore_pressure', experimentType, data, onChange)}
      </div>
      <div className="flex justify-between pt-2">
        <Button variant="ghost" onClick={onBack}>← Back</Button>
        <Button variant="primary" onClick={onNext} disabled={!!vialError || !!poreError}>Next: Additives →</Button>
      </div>
    </div>
  )
}
