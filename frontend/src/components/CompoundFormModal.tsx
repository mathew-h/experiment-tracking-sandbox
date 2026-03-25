import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { chemicalsApi, type Compound, type CompoundCreatePayload } from '@/api/chemicals'
import { Modal, Input, Button, useToast } from '@/components/ui'

interface Props {
  open: boolean
  onClose: () => void
  /** Called with the created/updated compound on success. */
  onSuccess: (compound: Compound) => void
  /** If provided, modal is in edit mode. */
  initial?: Compound
  /** Pre-fills the name field (for create-from-picker flow). */
  initialName?: string
  /** Minimal mode: only shows name field, no advanced fields. */
  minimal?: boolean
}

const EMPTY_FORM: Record<string, string> = {
  name: '', formula: '', cas_number: '', molecular_weight_g_mol: '',
  density_g_cm3: '', melting_point_c: '', boiling_point_c: '',
  solubility: '', hazard_class: '', supplier: '', catalog_number: '', notes: '',
}

function toNum(s: string): number | null {
  const n = parseFloat(s)
  return isNaN(n) ? null : n
}

/** Reusable modal for creating or editing a Compound. Supports minimal mode for inline picker create. */
export function CompoundFormModal({ open, onClose, onSuccess, initial, initialName, minimal }: Props) {
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()
  const isEdit = Boolean(initial)

  const [form, setForm] = useState<Record<string, string>>(EMPTY_FORM)

  useEffect(() => {
    if (!open) return
    if (initial) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: reset form when modal opens with initial data
      setForm({
        name: initial.name,
        formula: initial.formula ?? '',
        cas_number: initial.cas_number ?? '',
        molecular_weight_g_mol: initial.molecular_weight_g_mol?.toString() ?? '',
        density_g_cm3: initial.density_g_cm3?.toString() ?? '',
        melting_point_c: initial.melting_point_c?.toString() ?? '',
        boiling_point_c: initial.boiling_point_c?.toString() ?? '',
        solubility: initial.solubility ?? '',
        hazard_class: initial.hazard_class ?? '',
        supplier: initial.supplier ?? '',
        catalog_number: initial.catalog_number ?? '',
        notes: initial.notes ?? '',
      })
    } else {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: reset form when modal opens in create mode
      setForm({ ...EMPTY_FORM, name: initialName ?? '' })
    }
  }, [open, initial, initialName])

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((p) => ({ ...p, [k]: e.target.value }))

  const createMutation = useMutation({
    mutationFn: () => {
      const payload: CompoundCreatePayload = {
        name: form.name.trim(),
        formula: form.formula?.trim() || null,
        cas_number: form.cas_number?.trim() || null,
        molecular_weight_g_mol: form.molecular_weight_g_mol ? toNum(form.molecular_weight_g_mol) : null,
        density_g_cm3: form.density_g_cm3 ? toNum(form.density_g_cm3) : null,
        melting_point_c: form.melting_point_c ? toNum(form.melting_point_c) : null,
        boiling_point_c: form.boiling_point_c ? toNum(form.boiling_point_c) : null,
        solubility: form.solubility?.trim() || null,
        hazard_class: form.hazard_class?.trim() || null,
        supplier: form.supplier?.trim() || null,
        catalog_number: form.catalog_number?.trim() || null,
        notes: form.notes?.trim() || null,
        preferred_unit: null,
        elemental_fraction: null,
        catalyst_formula: null,
      }
      return chemicalsApi.createCompound(payload)
    },
    onSuccess: (compound) => {
      queryClient.invalidateQueries({ queryKey: ['compounds'] })
      success(`Compound "${compound.name}" created`)
      onSuccess(compound)
      onClose()
    },
    onError: (err: Error) => {
      const msg = err.message?.includes('409') ? 'A compound with this name or CAS number already exists' : err.message
      toastError('Failed to create compound', msg)
    },
  })

  const updateMutation = useMutation({
    mutationFn: () => {
      const payload = {
        name: form.name.trim() || undefined,
        formula: form.formula?.trim() || undefined,
        cas_number: form.cas_number?.trim() || undefined,
        molecular_weight_g_mol: form.molecular_weight_g_mol ? toNum(form.molecular_weight_g_mol) ?? undefined : undefined,
        density_g_cm3: form.density_g_cm3 ? toNum(form.density_g_cm3) ?? undefined : undefined,
        melting_point_c: form.melting_point_c ? toNum(form.melting_point_c) ?? undefined : undefined,
        boiling_point_c: form.boiling_point_c ? toNum(form.boiling_point_c) ?? undefined : undefined,
        solubility: form.solubility?.trim() || undefined,
        hazard_class: form.hazard_class?.trim() || undefined,
        supplier: form.supplier?.trim() || undefined,
        catalog_number: form.catalog_number?.trim() || undefined,
        notes: form.notes?.trim() || undefined,
      }
      return chemicalsApi.updateCompound(initial!.id, payload)
    },
    onSuccess: (compound) => {
      queryClient.invalidateQueries({ queryKey: ['compounds'] })
      success(`Compound "${compound.name}" updated`)
      onSuccess(compound)
      onClose()
    },
    onError: (err: Error) => {
      const msg = err.message?.includes('409') ? 'A compound with this name or CAS number already exists' : err.message
      toastError('Failed to update compound', msg)
    },
  })

  const isPending = createMutation.isPending || updateMutation.isPending
  const canSubmit = form.name?.trim().length >= 2

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isEdit ? `Edit: ${initial?.name}` : 'Add Compound'}
    >
      <div className="space-y-3 p-4">
        <Input
          label="Name *"
          value={form.name ?? ''}
          onChange={set('name')}
          placeholder="e.g. Magnesium Hydroxide"
        />

        {!minimal && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Input label="Formula" value={form.formula ?? ''} onChange={set('formula')} placeholder="e.g. Mg(OH)₂" />
              <Input
                label="CAS Number"
                value={form.cas_number ?? ''}
                onChange={set('cas_number')}
                placeholder="e.g. 1309-42-8"
              />
              <Input label="MW (g/mol)" type="number" value={form.molecular_weight_g_mol ?? ''} onChange={set('molecular_weight_g_mol')} />
              <Input label="Density (g/cm³)" type="number" value={form.density_g_cm3 ?? ''} onChange={set('density_g_cm3')} />
              <Input label="Melting Point (°C)" type="number" value={form.melting_point_c ?? ''} onChange={set('melting_point_c')} />
              <Input label="Boiling Point (°C)" type="number" value={form.boiling_point_c ?? ''} onChange={set('boiling_point_c')} />
              <Input label="Solubility" value={form.solubility ?? ''} onChange={set('solubility')} />
              <Input label="Hazard Class" value={form.hazard_class ?? ''} onChange={set('hazard_class')} />
              <Input label="Supplier" value={form.supplier ?? ''} onChange={set('supplier')} />
              <Input label="Catalog #" value={form.catalog_number ?? ''} onChange={set('catalog_number')} />
            </div>
            <div>
              <label className="block text-xs font-medium text-ink-secondary mb-1">Notes</label>
              <textarea
                className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-1 focus:ring-brand-red/50 resize-none"
                rows={2}
                value={form.notes ?? ''}
                onChange={set('notes')}
              />
            </div>
          </>
        )}

        <div className="flex gap-2 justify-end pt-1">
          <Button variant="ghost" onClick={onClose} disabled={isPending}>Cancel</Button>
          <Button
            variant="primary"
            loading={isPending}
            disabled={!canSubmit}
            onClick={() => isEdit ? updateMutation.mutate() : createMutation.mutate()}
          >
            {isEdit ? 'Save Changes' : 'Create Compound'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
