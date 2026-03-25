import { apiClient } from './client'

export interface Compound {
  id: number
  name: string
  formula: string | null
  cas_number: string | null
  molecular_weight_g_mol: number | null
  density_g_cm3: number | null
  melting_point_c: number | null
  boiling_point_c: number | null
  solubility: string | null
  hazard_class: string | null
  preferred_unit: string | null
  supplier: string | null
  catalog_number: string | null
  notes: string | null
  elemental_fraction: number | null
  catalyst_formula: string | null
}

export interface ChemicalAdditive {
  id: number
  compound_id: number
  amount: number
  unit: string
  addition_order: number | null
  mass_in_grams: number | null
  moles_added: number | null
  catalyst_ppm: number | null
  compound: Compound | null
}

export interface AdditivePayload {
  compound_id: number
  amount: number
  unit: string
  addition_order?: number
}

export interface AdditiveUpsertPayload {
  amount: number
  unit: string
  addition_order?: number
  addition_method?: string
}

export type CompoundCreatePayload = Omit<Compound, 'id'>
export type CompoundUpdatePayload = Partial<Omit<Compound, 'id'>>

export const chemicalsApi = {
  listCompounds: (params?: { search?: string; skip?: number; limit?: number }) =>
    apiClient.get<Compound[]>('/chemicals/compounds', { params }).then((r) => r.data),

  getCompound: (id: number) =>
    apiClient.get<Compound>(`/chemicals/compounds/${id}`).then((r) => r.data),

  createCompound: (payload: CompoundCreatePayload) =>
    apiClient.post<Compound>('/chemicals/compounds', payload).then((r) => r.data),

  updateCompound: (id: number, payload: CompoundUpdatePayload) =>
    apiClient.patch<Compound>(`/chemicals/compounds/${id}`, payload).then((r) => r.data),

  /** Legacy: list by conditions integer ID. Used internally during wizard submission. */
  listAdditives: (conditionsId: number) =>
    apiClient.get<ChemicalAdditive[]>(`/chemicals/additives/${conditionsId}`).then((r) => r.data),

  /** Legacy: create additive by conditions integer ID. Used during wizard submission. */
  addAdditive: (conditionsId: number, payload: AdditivePayload) =>
    apiClient.post<ChemicalAdditive>(`/chemicals/additives/${conditionsId}`, payload).then((r) => r.data),

  /** List additives by experiment string ID. */
  listExperimentAdditives: (experimentId: string) =>
    apiClient.get<ChemicalAdditive[]>(`/experiments/${experimentId}/additives`).then((r) => r.data),

  /** Upsert an additive by experiment string ID + compound ID. */
  upsertAdditive: (experimentId: string, compoundId: number, payload: AdditiveUpsertPayload) =>
    apiClient
      .put<ChemicalAdditive>(`/experiments/${experimentId}/additives/${compoundId}`, payload)
      .then((r) => r.data),

  /** Delete an additive by experiment string ID + compound ID. */
  deleteAdditive: (experimentId: string, compoundId: number) =>
    apiClient.delete(`/experiments/${experimentId}/additives/${compoundId}`),
}
