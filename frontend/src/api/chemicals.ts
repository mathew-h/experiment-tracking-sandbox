import { apiClient } from './client'

export interface Compound {
  id: number
  name: string
  formula: string | null
  cas_number: string | null
  molecular_weight_g_mol: number | null
  preferred_unit: string | null
  supplier: string | null
}

export interface ChemicalAdditive {
  id: number
  compound_id: number
  compound_name: string
  amount: number | null
  unit: string | null
  addition_order: number | null
}

export const chemicalsApi = {
  listCompounds: (params?: { search?: string; skip?: number; limit?: number }) =>
    apiClient.get<Compound[]>('/chemicals/compounds', { params }).then((r) => r.data),

  getCompound: (id: number) =>
    apiClient.get<Compound>(`/chemicals/compounds/${id}`).then((r) => r.data),

  createCompound: (payload: Partial<Compound>) =>
    apiClient.post<Compound>('/chemicals/compounds', payload).then((r) => r.data),

  listAdditives: (conditionsId: number) =>
    apiClient.get<ChemicalAdditive[]>(`/chemicals/additives/${conditionsId}`).then((r) => r.data),

  addAdditive: (conditionsId: number, payload: Partial<ChemicalAdditive>) =>
    apiClient.post<ChemicalAdditive>(`/chemicals/additives/${conditionsId}`, payload).then((r) => r.data),
}
