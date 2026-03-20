import { apiClient } from './client'

export interface BulkUploadResult {
  created: number
  updated: number
  skipped: number
  errors: string[]
  warnings: string[]
  feedbacks: Record<string, unknown>[]
  message: string
}

export interface NextIds {
  HPHT: number
  Serum: number
  CF: number
}

// Template types that have a downloadable template
export type TemplateType =
  | 'new-experiments'
  | 'scalar-results'
  | 'xrd-mineralogy'
  | 'timepoint-modifications'
  | 'rock-inventory'
  | 'chemical-inventory'
  | 'elemental-composition'
  | 'experiment-status'

function fileForm(file: File): FormData {
  const fd = new FormData()
  fd.append('file', file)
  return fd
}

function post<T>(path: string, body?: FormData | null): Promise<T> {
  return apiClient
    .post<T>(path, body ?? undefined, body ? { headers: { 'Content-Type': 'multipart/form-data' } } : undefined)
    .then((r) => r.data)
}

export const bulkUploadsApi = {
  // Card 1 — Master Results Sync
  triggerMasterSync: () =>
    post<BulkUploadResult>('/bulk-uploads/master-results'),

  uploadMasterResults: (file: File) =>
    post<BulkUploadResult>('/bulk-uploads/master-results', fileForm(file)),

  // Card 2 — ICP-OES Data
  uploadIcpOes: (file: File) =>
    post<BulkUploadResult>('/bulk-uploads/icp-oes', fileForm(file)),

  // Card 3 — XRD Mineralogy (auto-detects Aeris vs ActLabs)
  uploadXrdMineralogy: (file: File) =>
    post<BulkUploadResult>('/bulk-uploads/xrd-mineralogy', fileForm(file)),

  // Card 4 — Solution Chemistry
  uploadScalarResults: (file: File) =>
    post<BulkUploadResult>('/bulk-uploads/scalar-results', fileForm(file)),

  // Card 5 — New Experiments
  uploadNewExperiments: (file: File) =>
    post<BulkUploadResult>('/bulk-uploads/new-experiments', fileForm(file)),

  // Card 6 — Timepoint Modifications
  uploadTimepointModifications: (file: File) =>
    post<BulkUploadResult>('/bulk-uploads/timepoint-modifications', fileForm(file)),

  // Card 7 — Rock Inventory
  uploadRockInventory: (file: File) =>
    post<BulkUploadResult>('/bulk-uploads/rock-inventory', fileForm(file)),

  // Card 8 — Chemical Inventory
  uploadChemicalInventory: (file: File) =>
    post<BulkUploadResult>('/bulk-uploads/chemical-inventory', fileForm(file)),

  // Card 9 — Sample Chemical Composition
  uploadElementalComposition: (file: File, defaultUnit?: string) => {
    const fd = fileForm(file)
    if (defaultUnit) fd.append('default_unit', defaultUnit)
    return post<BulkUploadResult>('/bulk-uploads/elemental-composition', fd)
  },

  // Card 10 — ActLabs Rock Analysis
  uploadActlabsRock: (file: File) =>
    post<BulkUploadResult>('/bulk-uploads/actlabs-rock', fileForm(file)),

  // Card 11 — Experiment Status Update
  uploadExperimentStatus: (file: File) =>
    post<BulkUploadResult>('/bulk-uploads/experiment-status', fileForm(file)),

  // Card 12 — pXRF Readings
  uploadPXRF: (file: File) =>
    post<BulkUploadResult>('/bulk-uploads/pxrf', fileForm(file)),

  // Next-ID chips (New Experiments card)
  getNextIds: (): Promise<NextIds> =>
    apiClient.get<NextIds>('/experiments/next-ids').then((r) => r.data),

  // Template downloads
  downloadTemplate: async (type: TemplateType, mode?: string): Promise<void> => {
    const params = mode ? `?mode=${encodeURIComponent(mode)}` : ''
    const response = await apiClient.get(`/bulk-uploads/templates/${type}${params}`, {
      responseType: 'blob',
    })
    const url = URL.createObjectURL(response.data as Blob)
    const a = document.createElement('a')
    a.href = url
    const suffix = mode ? `-${mode}` : ''
    a.download = `${type}${suffix}-template.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  },
}
