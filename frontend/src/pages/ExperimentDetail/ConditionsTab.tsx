import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { conditionsApi, type ConditionsResponse, type ConditionsPayload } from '@/api/conditions'
import { chemicalsApi, type AdditivePayload } from '@/api/chemicals'
import { Button, Input, Select, Modal, useToast } from '@/components/ui'

const FEEDSTOCK_OPTIONS = [
  { value: 'Nitrogen', label: 'Nitrogen' },
  { value: 'Nitrate', label: 'Nitrate' },
  { value: 'Blank', label: 'None / Blank' },
]

interface Props {
  conditions: ConditionsResponse | null
  experimentId: string
}

function Row({ label, value, unit }: { label: string; value: unknown; unit?: string }) {
  if (value == null || value === '') return null
  return (
    <div className="flex items-baseline gap-4 py-1 border-b border-surface-border/50">
      <span className="text-xs text-ink-secondary w-44 shrink-0">{label}</span>
      <span className="text-xs font-mono-data text-ink-primary">
        {String(value)}{unit ? ` ${unit}` : ''}
      </span>
    </div>
  )
}

/** Conditions tab: editable experimental setup parameters and chemical additives. */
export function ConditionsTab({ conditions, experimentId }: Props) {
  const [editOpen, setEditOpen] = useState(false)
  const [form, setForm] = useState<Partial<ConditionsPayload>>({})
  const [addAdditiveOpen, setAddAdditiveOpen] = useState(false)
  const [additiveForm, setAdditiveForm] = useState<Partial<AdditivePayload>>({})
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()

  const { data: additives = [] } = useQuery({
    queryKey: ['additives', conditions?.id],
    queryFn: () => chemicalsApi.listAdditives(conditions!.id),
    enabled: Boolean(conditions?.id),
  })

  const { data: compounds = [] } = useQuery({
    queryKey: ['compounds'],
    queryFn: () => chemicalsApi.listCompounds(),
    enabled: addAdditiveOpen,
  })

  const addAdditiveMutation = useMutation({
    mutationFn: () => chemicalsApi.addAdditive(conditions!.id, additiveForm as AdditivePayload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['additives', conditions!.id] })
      success('Additive added')
      setAddAdditiveOpen(false)
      setAdditiveForm({})
    },
    onError: (err: Error) => toastError('Failed to add additive', err.message),
  })

  const patchMutation = useMutation({
    mutationFn: () => conditionsApi.patch(conditions!.id, form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] })
      queryClient.invalidateQueries({ queryKey: ['conditions', experimentId] })
      success('Conditions updated')
      setEditOpen(false)
    },
    onError: (err: Error) => toastError('Update failed', err.message),
  })

  const openEdit = () => {
    setForm({
      temperature_c: conditions?.temperature_c ?? undefined,
      initial_ph: conditions?.initial_ph ?? undefined,
      rock_mass_g: conditions?.rock_mass_g ?? undefined,
      water_volume_mL: conditions?.water_volume_mL ?? undefined,
      feedstock: conditions?.feedstock ?? undefined,
      stir_speed_rpm: conditions?.stir_speed_rpm ?? undefined,
      reactor_number: conditions?.reactor_number ?? undefined,
      initial_conductivity_mS_cm: conditions?.initial_conductivity_mS_cm ?? undefined,
      room_temp_pressure_psi: conditions?.room_temp_pressure_psi ?? undefined,
      rxn_temp_pressure_psi: conditions?.rxn_temp_pressure_psi ?? undefined,
      co2_partial_pressure_MPa: conditions?.co2_partial_pressure_MPa ?? undefined,
      confining_pressure: conditions?.confining_pressure ?? undefined,
      pore_pressure: conditions?.pore_pressure ?? undefined,
      core_height_cm: conditions?.core_height_cm ?? undefined,
      core_width_cm: conditions?.core_width_cm ?? undefined,
    })
    setEditOpen(true)
  }

  if (!conditions) return <p className="text-sm text-ink-muted p-4">No conditions recorded for this experiment.</p>

  const set = (k: keyof ConditionsPayload) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((p) => ({ ...p, [k]: e.target.value === '' ? undefined : (isNaN(Number(e.target.value)) ? e.target.value : Number(e.target.value)) }))

  return (
    <>
      <div className="p-4 space-y-1">
        <div className="flex justify-end mb-2">
          <Button variant="ghost" size="xs" onClick={openEdit}>Edit</Button>
        </div>
        <Row label="Type" value={conditions.experiment_type} />
        <Row label="Temperature" value={conditions.temperature_c} unit="°C" />
        <Row label="Initial pH" value={conditions.initial_ph} />
        <Row label="Rock Mass" value={conditions.rock_mass_g} unit="g" />
        <Row label="Water Volume" value={conditions.water_volume_mL} unit="mL" />
        {conditions.water_to_rock_ratio != null && (
          <div className="flex items-baseline gap-4 py-1 border-b border-surface-border/50">
            <span className="text-xs text-ink-secondary font-semibold w-44 shrink-0">Water : Rock Ratio</span>
            <span className="text-xs font-mono-data text-brand-red font-semibold">{conditions.water_to_rock_ratio.toFixed(2)}</span>
          </div>
        )}
        <Row label="Particle Size" value={conditions.particle_size} />
        <Row label="Feedstock" value={conditions.feedstock} />
        <Row label="Reactor" value={conditions.reactor_number} />
        <Row label="Stir Speed" value={conditions.stir_speed_rpm} unit="RPM" />
        <Row label="Initial Conductivity" value={conditions.initial_conductivity_mS_cm} unit="mS/cm" />
        <Row label="Room Temp Pressure" value={conditions.room_temp_pressure_psi} unit="psi" />
        <Row label="Rxn Temp Pressure" value={conditions.rxn_temp_pressure_psi} unit="psi" />
        <Row label="CO₂ Partial Pressure" value={conditions.co2_partial_pressure_MPa} unit="MPa" />
        <Row label="Core Height" value={conditions.core_height_cm} unit="cm" />
        <Row label="Core Width" value={conditions.core_width_cm} unit="cm" />
        <Row label="Confining Pressure" value={conditions.confining_pressure} />
        <Row label="Pore Pressure" value={conditions.pore_pressure} />
      </div>

      {/* Chemical Additives */}
      <div className="px-4 pb-4 border-t border-surface-border mt-2 pt-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-ink-secondary uppercase tracking-wider">Chemical Additives</span>
          <Button variant="ghost" size="xs" onClick={() => setAddAdditiveOpen(true)}>+ Add</Button>
        </div>
        {additives.length === 0 ? (
          <p className="text-xs text-ink-muted">No additives recorded.</p>
        ) : (
          <div className="space-y-1">
            {additives.map((a) => (
              <div key={a.id} className="flex items-baseline gap-4 py-1 border-b border-surface-border/50">
                <span className="text-xs text-ink-secondary w-44 shrink-0">{a.compound?.name ?? `Compound #${a.compound_id}`}</span>
                <span className="text-xs font-mono-data text-ink-primary">{a.amount} {a.unit}</span>
                {a.mass_in_grams != null && (
                  <span className="text-xs text-ink-muted">{a.mass_in_grams.toFixed(4)} g</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <Modal open={editOpen} onClose={() => setEditOpen(false)} title="Edit Conditions">
        <div className="space-y-3 p-4">
          <div className="grid grid-cols-2 gap-3">
            <Input label="Particle Size" type="text" value={form.particle_size ?? ''} onChange={(e) => setForm((p) => ({ ...p, particle_size: e.target.value || undefined }))} />
            <Input label="Temperature (°C)" type="number" value={form.temperature_c ?? ''} onChange={set('temperature_c')} />
            <Input label="Initial pH" type="number" value={form.initial_ph ?? ''} onChange={set('initial_ph')} />
            <Input label="Rock Mass (g)" type="number" value={form.rock_mass_g ?? ''} onChange={set('rock_mass_g')} />
            <Input label="Water Volume (mL)" type="number" value={form.water_volume_mL ?? ''} onChange={set('water_volume_mL')} />
            <Select label="Feedstock" options={FEEDSTOCK_OPTIONS} value={form.feedstock ?? ''} onChange={set('feedstock')} placeholder="Select…" />
            <Input label="Stir Speed (RPM)" type="number" value={form.stir_speed_rpm ?? ''} onChange={set('stir_speed_rpm')} />
            <Input label="Reactor #" type="number" value={form.reactor_number ?? ''} onChange={set('reactor_number')} />
            <Input label="Initial Conductivity" type="number" value={form.initial_conductivity_mS_cm ?? ''} onChange={set('initial_conductivity_mS_cm')} />
            <Input label="Room Temp Pressure (psi)" type="number" value={form.room_temp_pressure_psi ?? ''} onChange={set('room_temp_pressure_psi')} />
            <Input label="Rxn Temp Pressure (psi)" type="number" value={form.rxn_temp_pressure_psi ?? ''} onChange={set('rxn_temp_pressure_psi')} />
            <Input label="CO₂ Partial Pressure (MPa)" type="number" value={form.co2_partial_pressure_MPa ?? ''} onChange={set('co2_partial_pressure_MPa')} />
            <Input label="Confining Pressure" type="number" value={form.confining_pressure ?? ''} onChange={set('confining_pressure')} />
            <Input label="Pore Pressure" type="number" value={form.pore_pressure ?? ''} onChange={set('pore_pressure')} />
            <Input label="Core Height (cm)" type="number" value={form.core_height_cm ?? ''} onChange={set('core_height_cm')} />
            <Input label="Core Width (cm)" type="number" value={form.core_width_cm ?? ''} onChange={set('core_width_cm')} />
          </div>
          <div className="flex gap-2 justify-end pt-2">
            <Button variant="ghost" onClick={() => setEditOpen(false)}>Cancel</Button>
            <Button variant="primary" loading={patchMutation.isPending} onClick={() => patchMutation.mutate()}>Save</Button>
          </div>
        </div>
      </Modal>

      <Modal open={addAdditiveOpen} onClose={() => { setAddAdditiveOpen(false); setAdditiveForm({}) }} title="Add Chemical Additive">
        <div className="space-y-3 p-4">
          <Select
            label="Compound"
            options={compounds.map((c) => ({ value: String(c.id), label: c.formula ? `${c.name} (${c.formula})` : c.name }))}
            placeholder="Select compound…"
            value={additiveForm.compound_id != null ? String(additiveForm.compound_id) : ''}
            onChange={(e) => setAdditiveForm((p) => ({ ...p, compound_id: Number(e.target.value) || undefined }))}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Amount"
              type="number"
              value={additiveForm.amount ?? ''}
              onChange={(e) => setAdditiveForm((p) => ({ ...p, amount: e.target.value === '' ? undefined : Number(e.target.value) }))}
            />
            <Select
              label="Unit"
              options={[
                { value: 'g', label: 'g' },
                { value: 'mg', label: 'mg' },
                { value: 'mM', label: 'mM' },
                { value: 'ppm', label: 'ppm' },
                { value: '% of Rock', label: '% of Rock' },
                { value: 'mL', label: 'mL' },
                { value: 'μL', label: 'μL' },
                { value: 'mol', label: 'mol' },
                { value: 'mmol', label: 'mmol' },
              ]}
              placeholder="Unit…"
              value={additiveForm.unit ?? ''}
              onChange={(e) => setAdditiveForm((p) => ({ ...p, unit: e.target.value || undefined }))}
            />
          </div>
          <div className="flex gap-2 justify-end pt-2">
            <Button variant="ghost" onClick={() => { setAddAdditiveOpen(false); setAdditiveForm({}) }}>Cancel</Button>
            <Button
              variant="primary"
              loading={addAdditiveMutation.isPending}
              disabled={!additiveForm.compound_id || !additiveForm.amount || !additiveForm.unit}
              onClick={() => addAdditiveMutation.mutate()}
            >
              Add
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
