import { apiClient } from './client'

export interface XRDAnalysis {
  id: number
  experiment_id: string
  mineral_phases: Record<string, number> | null
  analysis_date: string | null
}

export interface PXRFReading {
  reading_no: string
  fe: number | null
  mg: number | null
  ni: number | null
  cu: number | null
  si: number | null
  co: number | null
  mo: number | null
  al: number | null
  ca: number | null
  ingested_at: string
}

export interface ExternalAnalysis {
  id: number
  sample_id: string | null
  experiment_id: string | null
  analysis_type: string
  analysis_date: string | null
  laboratory: string | null
}

export const analysisApi = {
  getXRD: (experimentId: string) =>
    apiClient.get<XRDAnalysis[]>(`/analysis/xrd/${experimentId}`).then((r) => r.data),

  listPXRF: (params?: { skip?: number; limit?: number }) =>
    apiClient.get<PXRFReading[]>('/analysis/pxrf', { params }).then((r) => r.data),

  getExternal: (experimentId: string) =>
    apiClient.get<ExternalAnalysis[]>(`/analysis/external/${experimentId}`).then((r) => r.data),
}
