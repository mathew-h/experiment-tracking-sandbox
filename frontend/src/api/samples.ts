// frontend/src/api/samples.ts
import { apiClient } from './client'

// ── Core types ──────────────────────────────────────────────────────────

export interface Sample {
  sample_id: string
  rock_classification: string | null
  state: string | null
  country: string | null
  locality: string | null
  latitude: number | null
  longitude: number | null
  description: string | null
  characterized: boolean
  created_at: string
}

export interface SampleListItem {
  sample_id: string
  rock_classification: string | null
  locality: string | null
  state: string | null
  country: string | null
  characterized: boolean
  experiment_count: number
  has_pxrf: boolean
  has_xrd: boolean
  has_elemental: boolean
  created_at: string
}

export interface SampleListResponse {
  items: SampleListItem[]
  total: number
  skip: number
  limit: number
}

export interface SampleGeoItem {
  sample_id: string
  latitude: number
  longitude: number
  rock_classification: string | null
  characterized: boolean
}

export interface SamplePhoto {
  id: number
  sample_id: string
  file_name: string | null
  file_path: string
  file_type: string | null
  description: string | null
  created_at: string
}

export interface ExternalAnalysis {
  id: number
  sample_id: string | null
  analysis_type: string | null
  analysis_date: string | null
  laboratory: string | null
  analyst: string | null
  pxrf_reading_no: string | null
  description: string | null
  magnetic_susceptibility: string | null
  created_at: string
  analysis_files: AnalysisFile[]
}

export interface AnalysisFile {
  id: number
  external_analysis_id: number
  file_name: string | null
  file_path: string
  file_type: string | null
  created_at: string
}

export interface ActivityEntry {
  id: number
  modification_type: string
  modified_table: string
  modified_by: string
  old_values: Record<string, unknown>
  new_values: Record<string, unknown>
  created_at: string
}

export interface ElementalAnalysisItem {
  analyte_symbol: string
  unit: string
  analyte_composition: number | null
}

export interface LinkedExperiment {
  experiment_id: string
  experiment_type: string | null
  status: string | null
  date: string | null
}

export interface SampleDetail extends Sample {
  photos: SamplePhoto[]
  analyses: ExternalAnalysis[]
  elemental_results: ElementalAnalysisItem[]
  experiments: LinkedExperiment[]
}

export interface ExternalAnalysisCreate {
  analysis_type: string
  analysis_date?: string | null
  laboratory?: string | null
  analyst?: string | null
  pxrf_reading_no?: string | null
  description?: string | null
  magnetic_susceptibility?: string | null
}

export interface AnalysisWithWarnings {
  analysis: ExternalAnalysis
  warnings: string[]
}

// ── List filter params ──────────────────────────────────────────────────

export interface SampleListParams {
  skip?: number
  limit?: number
  country?: string
  rock_classification?: string
  locality?: string
  characterized?: boolean
  search?: string
  has_pxrf?: boolean
  has_xrd?: boolean
  has_elemental?: boolean
}

// ── API client ──────────────────────────────────────────────────────────

export const samplesApi = {
  list: (params?: SampleListParams) =>
    apiClient.get<SampleListResponse>('/samples', { params }).then((r) => r.data),

  listGeo: () =>
    apiClient.get<SampleGeoItem[]>('/samples/geo').then((r) => r.data),

  get: (id: string) =>
    apiClient.get<SampleDetail>(`/samples/${id}`).then((r) => r.data),

  create: (payload: Partial<Sample>) =>
    apiClient.post<Sample>('/samples', payload).then((r) => r.data),

  patch: (id: string, payload: Partial<Sample>) =>
    apiClient.patch<Sample>(`/samples/${id}`, payload).then((r) => r.data),

  delete: (id: string) =>
    apiClient.delete(`/samples/${id}`),

  uploadPhoto: (id: string, file: File, description?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (description) form.append('description', description)
    return apiClient.post<SamplePhoto>(`/samples/${id}/photos`, form).then((r) => r.data)
  },

  deletePhoto: (sampleId: string, photoId: number) =>
    apiClient.delete(`/samples/${sampleId}/photos/${photoId}`),

  listAnalyses: (id: string) =>
    apiClient.get<ExternalAnalysis[]>(`/samples/${id}/analyses`).then((r) => r.data),

  createAnalysis: (id: string, payload: ExternalAnalysisCreate) =>
    apiClient.post<AnalysisWithWarnings>(`/samples/${id}/analyses`, payload).then((r) => r.data),

  deleteAnalysis: (sampleId: string, analysisId: number) =>
    apiClient.delete(`/samples/${sampleId}/analyses/${analysisId}`),

  listActivity: (sampleId: string) =>
    apiClient.get<ActivityEntry[]>(`/samples/${sampleId}/activity`).then((r) => r.data),
}
