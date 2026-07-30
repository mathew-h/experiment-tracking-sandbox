import { apiClient } from './client'

export interface BulkUploadResult {
  created: number
  updated: number
  skipped: number
  errors: string[]
  warnings: string[]
  feedbacks: Record<string, unknown>[]
  message: string
  /** True when the server rolled back instead of committing. */
  dry_run?: boolean
  /** Structured plan — new-experiments only; null elsewhere. */
  plan?: UploadPlan | null
  /** sha256 of the plan; replay it on commit to prove the plan is unchanged. */
  plan_hash?: string | null
}

// ─── Upload plan (issue #100 items 2, 6-9) ───────────────────────────────────
// Mirrors backend/api/schemas/bulk_upload.py. Currently populated only by the
// new-experiments endpoint; every other upload type returns plan: null.

export interface PlanFieldChange {
  field: string
  old: unknown
  new: unknown
}

export interface PlanCreate {
  row: number
  experiment_id: string
  parent_id: string | null
  copied_from: string | null
}

export interface PlanRename {
  row: number
  from_id: string
  to_id: string
}

export interface PlanOverwrite {
  row: number
  experiment_id: string
  fields_changed: PlanFieldChange[]
}

export interface PlanSkip {
  row: number
  experiment_id: string | null
  reason: string
}

export interface PlanConflict {
  row: number
  kind: string
  detail: string
}

export interface UploadPlan {
  creates: PlanCreate[]
  renames: PlanRename[]
  overwrites: PlanOverwrite[]
  skips: PlanSkip[]
  conflicts: PlanConflict[]
  counts: Record<string, number>
}

export interface SampleConflictMatch {
  sample_id: string
  similarity: number
}

export interface SampleConflict {
  incoming_id: string
  normalized: string
  candidate_matches: SampleConflictMatch[]
}

export interface ConflictCheckResult {
  status: 'warnings'
  conflicts: SampleConflict[]
  message: string
}

export function isConflictCheckResult(r: BulkUploadResult | ConflictCheckResult): r is ConflictCheckResult {
  return (r as ConflictCheckResult).status === 'warnings'
}

export interface NextIds {
  HPHT: number
  Serum: number
  CF: number
  Autoclave: number
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
  | 'experiment-deletion'

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
  // Card 1 — Master Results (drag-and-drop upload of the master tracker file)
  uploadMasterResults: (file: File) =>
    post<BulkUploadResult>('/bulk-uploads/master-results', fileForm(file)),

  // Card 2 — ICP-OES Data
  uploadIcpOes: (file: File, overwrite = false) => {
    const fd = fileForm(file)
    fd.append('overwrite', overwrite ? 'true' : 'false')
    return post<BulkUploadResult>('/bulk-uploads/icp-oes', fd)
  },

  // Card 3 — XRD Mineralogy (auto-detects Aeris, ActLabs, or Experiment+Timepoint)
  uploadXrdMineralogy: (file: File, overwrite = false) => {
    const fd = fileForm(file)
    fd.append('overwrite', overwrite ? 'true' : 'false')
    return post<BulkUploadResult>('/bulk-uploads/xrd-mineralogy', fd)
  },

  // Card 4 — Solution Chemistry
  uploadScalarResults: (file: File) =>
    post<BulkUploadResult>('/bulk-uploads/scalar-results', fileForm(file)),

  // Card 5 — New Experiments. Preview-first: the UI always calls this with
  // { dryRun: true } first, then replays the returned plan_hash to commit
  // (issue #100 items 5-6).
  uploadNewExperiments: (
    file: File,
    opts: { dryRun?: boolean; planHash?: string } = {},
  ) => {
    const fd = fileForm(file)
    if (opts.dryRun) fd.append('dry_run', 'true')
    if (opts.planHash) fd.append('plan_hash', opts.planHash)
    return post<BulkUploadResult>('/bulk-uploads/new-experiments', fd)
  },

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
  uploadActlabsRock: (file: File, resolutions?: Record<string, string>) => {
    const fd = fileForm(file)
    if (resolutions) fd.append('resolutions', JSON.stringify(resolutions))
    return post<BulkUploadResult | ConflictCheckResult>('/bulk-uploads/actlabs-rock', fd)
  },

  // Card 11 — Experiment Status Update
  uploadExperimentStatus: (file: File) =>
    post<BulkUploadResult>('/bulk-uploads/experiment-status', fileForm(file)),

  // Card 12 — Bulk experiment deletion (issue #109 Phase 1). Hard, irreversible
  // cascade delete of every experiment_id in the file; the backend refuses this
  // for anyone but the data owner. No dry_run — Phase 1 has no preview step.
  uploadExperimentDeletion: (file: File) =>
    post<BulkUploadResult>('/bulk-uploads/experiment-deletion', fileForm(file)),

  // Card 13 — pXRF Readings
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
