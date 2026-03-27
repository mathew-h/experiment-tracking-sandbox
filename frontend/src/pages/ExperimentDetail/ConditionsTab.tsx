import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { conditionsApi, type ConditionsResponse, type ConditionsPayload } from '@/api/conditions'
import { chemicalsApi, type Compound } from '@/api/chemicals'
import { Button, Input, Select, Modal, useToast } from '@/components/ui'
import { CompoundFormModal } from '@/components/CompoundFormModal'

const FEEDSTOCK_OPTIONS = [
  { value: 'Nitrogen', label: 'Nitrogen' },
  { value: 'Nitrate', label: 'Nitrate' },
  { value: 'Blank', label: 'None / Blank' },
]

const ADDITIVE_UNIT_OPTIONS = [
  { value: 'g', label: 'g' }, { value: 'mg', label: 'mg' },
  { value: 'mM', label: 'mM' }, { value: 'ppm', label: 'ppm' },
  { value: '% of Rock', label: '% of Rock' }, { value: 'mL', label: 'mL' },
  { value: 'μL', label: 'μL' }, { value: 'mol', label: 'mol' },
  { value: 'mmol', label: 'mmol' },
]

const EXPERIMENT_TYPE_OPTIONS = [
  { value: 'Serum',      label: 'Serum' },
  { value: 'Autoclave',  label: 'Autoclave' },
  { value: 'HPHT',       label: 'HPHT' },
  { value: 'Core Flood', label: 'Core Flood' },
  { value: 'Other',      label: 'Other' },
]

interface Props {
  conditions: ConditionsResponse | null
  experimentId: string
  experimentFk: number
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
export function ConditionsTab({ conditions, experimentId, experimentFk }: Props) {
  const [editOpen, setEditOpen] = useState(false)
  const [form, setForm] = useState<Partial<ConditionsPayload>>({})

  // Add additive modal state
  const [addAdditiveOpen, setAddAdditiveOpen] = useState(false)
  const [selectedCompound, setSelectedCompound] = useState<{ id: number; name: string } | null>(null)
  const [additiveAmount, setAdditiveAmount] = useState('')
  const [additiveUnit, setAdditiveUnit] = useState('g')
  const [compoundQuery, setCompoundQuery] = useState('')
  const [compoundDropdownOpen, setCompoundDropdownOpen] = useState(false)
  const [createCompoundOpen, setCreateCompoundOpen] = useState(false)
  const [createCompoundName, setCreateCompoundName] = useState('')

  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()

  // Additives — keyed by experiment string ID (not conditions integer ID)
  const { data: additives = [] } = useQuery({
    queryKey: ['additives', experimentId],
    queryFn: () => chemicalsApi.listExperimentAdditives(experimentId),
  })

  // Compound search for picker
  const { data: compoundResults = [] } = useQuery({
    queryKey: ['compounds', compoundQuery],
    queryFn: () => chemicalsApi.listCompounds({ search: compoundQuery, limit: 10 }),
    enabled: compoundQuery.length >= 1 && compoundDropdownOpen,
  })

  const upsertAdditiveMutation = useMutation({
    mutationFn: () => {
      if (!selectedCompound) throw new Error('No compound selected')
      return chemicalsApi.upsertAdditive(experimentId, selectedCompound.id, {
        amount: parseFloat(additiveAmount),
        unit: additiveUnit,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['additives', experimentId] })
      success('Additive saved')
      setAddAdditiveOpen(false)
      setSelectedCompound(null)
      setAdditiveAmount('')
      setAdditiveUnit('g')
      setCompoundQuery('')
    },
    onError: (err: Error) => toastError('Failed to save additive', err.message),
  })

  const deleteAdditiveMutation = useMutation({
    mutationFn: (compoundId: number) => chemicalsApi.deleteAdditive(experimentId, compoundId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['additives', experimentId] })
      success('Additive removed')
    },
    onError: (err: Error) => toastError('Failed to remove additive', err.message),
  })

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!conditions) {
        return conditionsApi.create({
          ...form,
          experiment_fk: experimentFk,
          experiment_id: experimentId,
        })
      }
      return conditionsApi.patch(conditions.id, form)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] })
      queryClient.invalidateQueries({ queryKey: ['conditions', experimentId] })
      success(conditions ? 'Conditions updated' : 'Details added')
      setEditOpen(false)
    },
    onError: (err: Error) =>
      toastError(conditions ? 'Update failed' : 'Failed to add details', err.message),
  })

  const openEdit = () => {
    setForm({
      experiment_type: conditions?.experiment_type ?? undefined,
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

  const closeAddModal = () => {
    setAddAdditiveOpen(false)
    setSelectedCompound(null)
    setAdditiveAmount('')
    setAdditiveUnit('g')
    setCompoundQuery('')
  }

  const set = (k: keyof ConditionsPayload) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((p) => ({ ...p, [k]: e.target.value === '' ? undefined : (isNaN(Number(e.target.value)) ? e.target.value : Number(e.target.value)) }))

  const hasExactCompoundMatch = compoundResults.some(
    (c: Compound) => c.name.toLowerCase() === compoundQuery.toLowerCase()
  )

  return (
    <>
      {!conditions ? (
        <div className="p-8 flex flex-col items-center gap-3 text-center">
          <p className="text-sm text-ink-muted">No conditions recorded for this experiment.</p>
          <Button variant="ghost" size="sm" onClick={openEdit}>+ Add Details</Button>
        </div>
      ) : (
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
              <div key={a.id} className="flex items-baseline gap-4 py-1 border-b border-surface-border/50 group">
                <span className="text-xs text-ink-secondary w-44 shrink-0">{a.compound?.name ?? `Compound #${a.compound_id}`}</span>
                <span className="text-xs font-mono-data text-ink-primary">{a.amount} {a.unit}</span>
                {a.mass_in_grams != null && (
                  <span className="text-xs text-ink-muted">{a.mass_in_grams.toFixed(4)} g</span>
                )}
                <button
                  onClick={() => deleteAdditiveMutation.mutate(a.compound_id)}
                  className="ml-auto text-xs text-ink-muted hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity px-1"
                  type="button"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        </div>
        </>
      )}

      {/* Edit Conditions Modal */}
      <Modal open={editOpen} onClose={() => setEditOpen(false)} title={conditions ? 'Edit Conditions' : 'Add Details'}>
        <div className="space-y-3 p-4">
          <div className="grid grid-cols-2 gap-3">
            <Select
              label="Experiment Type"
              options={EXPERIMENT_TYPE_OPTIONS}
              value={form.experiment_type ?? ''}
              onChange={(e) => setForm((p) => ({ ...p, experiment_type: e.target.value || undefined }))}
              placeholder="Select type…"
            />
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
            <Button variant="primary" loading={saveMutation.isPending} onClick={() => saveMutation.mutate()}>Save</Button>
          </div>
        </div>
      </Modal>

      {/* Add Additive Modal */}
      <Modal open={addAdditiveOpen} onClose={closeAddModal} title="Add Chemical Additive">
        <div className="space-y-3 p-4">
          {/* Compound typeahead */}
          <div className="relative">
            <label className="block text-xs font-medium text-ink-secondary mb-1">Compound</label>
            {selectedCompound ? (
              <div className="flex items-center gap-2">
                <span className="text-sm text-ink-primary font-medium">{selectedCompound.name}</span>
                <button
                  type="button"
                  className="text-xs text-ink-muted hover:text-ink-primary"
                  onClick={() => { setSelectedCompound(null); setCompoundQuery('') }}
                >
                  Change
                </button>
              </div>
            ) : (
              <>
                <input
                  className="w-full bg-surface-input border border-surface-border rounded px-2 py-1.5 text-sm text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50"
                  placeholder="Search compounds…"
                  value={compoundQuery}
                  onChange={(e) => { setCompoundQuery(e.target.value); setCompoundDropdownOpen(true) }}
                  onFocus={() => setCompoundDropdownOpen(true)}
                  onBlur={() => setTimeout(() => setCompoundDropdownOpen(false), 150)}
                  autoComplete="off"
                />
                {compoundDropdownOpen && compoundQuery.length >= 1 && (
                  <div className="absolute z-10 left-0 right-0 top-full mt-0.5 bg-surface-raised border border-surface-border rounded shadow-lg max-h-48 overflow-y-auto">
                    {compoundResults.map((c: Compound) => (
                      <button
                        key={c.id}
                        type="button"
                        className="w-full text-left px-3 py-1.5 text-sm text-ink-primary hover:bg-surface-border/30"
                        onMouseDown={() => {
                          setSelectedCompound({ id: c.id, name: c.name })
                          setCompoundQuery(c.name)
                          setCompoundDropdownOpen(false)
                        }}
                      >
                        {c.name}{c.formula ? ` (${c.formula})` : ''}
                      </button>
                    ))}
                    {!hasExactCompoundMatch && compoundQuery.trim().length >= 2 && (
                      <button
                        type="button"
                        className="w-full text-left px-3 py-1.5 text-sm text-brand-red hover:bg-surface-border/30 border-t border-surface-border/50"
                        onMouseDown={() => {
                          setCreateCompoundName(compoundQuery)
                          setCompoundDropdownOpen(false)
                          setCreateCompoundOpen(true)
                        }}
                      >
                        Create "{compoundQuery.trim()}"
                      </button>
                    )}
                  </div>
                )}
              </>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Amount"
              type="number"
              value={additiveAmount}
              onChange={(e) => setAdditiveAmount(e.target.value)}
            />
            <Select
              label="Unit"
              options={ADDITIVE_UNIT_OPTIONS}
              placeholder="Unit…"
              value={additiveUnit}
              onChange={(e) => setAdditiveUnit(e.target.value)}
            />
          </div>

          <div className="flex gap-2 justify-end pt-2">
            <Button variant="ghost" onClick={closeAddModal}>Cancel</Button>
            <Button
              variant="primary"
              loading={upsertAdditiveMutation.isPending}
              disabled={!selectedCompound || !additiveAmount || !additiveUnit}
              onClick={() => upsertAdditiveMutation.mutate()}
            >
              Save
            </Button>
          </div>
        </div>

        <CompoundFormModal
          open={createCompoundOpen}
          onClose={() => setCreateCompoundOpen(false)}
          onSuccess={(compound) => {
            setSelectedCompound({ id: compound.id, name: compound.name })
            setCompoundQuery(compound.name)
            setCreateCompoundOpen(false)
          }}
          initialName={createCompoundName}
          minimal
        />
      </Modal>
    </>
  )
}
