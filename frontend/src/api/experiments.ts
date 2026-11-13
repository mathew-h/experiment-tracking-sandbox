import { apiClient } from './client'
import type { ExperimentIcp } from './icp'
import { blobErrorMessage, filenameFromDisposition, saveBlob } from '@/utils/download'

export type ExperimentStatus = 'ONGOING' | 'COMPLETED' | 'CANCELLED' | 'QUEUED'

import type { NoteType } from './noteTypes'
export type { NoteType } from './noteTypes'

export interface ExperimentNote {
  id: number
  /** The owning experiment's ID. Present on every note payload since issue #190. */
  experiment_id?: string
  note_text: string
  note_type: NoteType
  /** Set when the note is about one timepoint (experimental_results.id). */
  result_id: number | null
  /** Calendar-date anchor for a 'modification' not tied to a result (issue #122 PR-B). */
  event_date?: string | null
  /** Firebase email on notes typed in the app; a source tag on uploaded ones. */
  created_by: string | null
  /** True for rows the #118 backfill could not place with certainty. */
  needs_review: boolean
  created_at: string
  updated_at: string | null
}

export interface NoteCreate {
  note_text: string
  note_type?: NoteType
  result_id?: number | null
  event_date?: string | null
}

export interface NotePatch {
  note_text?: string
  note_type?: NoteType
  needs_review?: boolean
  event_date?: string | null
}

export interface ReviewNoteItem extends ExperimentNote {
  experiment_id: string
  experiment_fk: number
  researcher: string | null
  time_post_reaction_days: number | null
}

/** Issue #122 PR-A: one bar of the review-queue text histogram. */
export interface DistinctText {
  text: string
  count: number
}

export interface ReviewQueueResponse {
  items: ReviewNoteItem[]
  total: number
  skip: number
  limit: number
  /** Top 50 distinct note_text values in the current filter, most frequent first. */
  distinct_texts: DistinctText[]
}

export type ReviewOrder = 'experiment' | 'created_at' | 'text'

export interface ReviewQueueParams {
  researcher?: string
  note_type?: NoteType
  /** Case-insensitive substring of note_text; `%`/`_` are literal. */
  q?: string
  /** Case-insensitive substring of experiment_id. */
  experiment_id?: string
  order?: ReviewOrder
  desc?: boolean
  skip?: number
  limit?: number
}

/** Issue #122 PR-A: body of PATCH /experiments/notes/bulk. Atomic on the server. */
export interface NotesBulkPatch {
  ids: number[]
  needs_review?: boolean
  note_type?: NoteType
}

export interface NotesBulkResponse {
  count: number
  ids: number[]
}

export interface ExperimentListItem {
  id: number
  experiment_id: string
  experiment_number: number
  status: ExperimentStatus
  researcher: string | null
  date: string | null
  sample_id: string | null
  created_at: string
  experiment_type: string | null
  reactor_number: number | null
  additives_summary: string | null
  /** The note typed 'description' (issue #118). */
  description: string | null
  /** Issue #168: lab-local YYYY-MM-DD of the latest dated result; null when none.
   *  A flat-mode vial row carries the latest over its vials. Render as is (no slicing).
   *  Always sent by the API; optional so payloads built before #168 stay valid. */
  last_result_date?: string | null
  base_experiment_id: string | null
  parent_experiment_fk: number | null
  replicate_label: string | null
  is_outlier: boolean
  /** Issue #152: a background / blank vial; left out of a mixed group's averages.
   *  Always sent by the API; optional so payloads built before #152 stay valid. */
  is_background?: boolean
  id_timepoint_days: number | null
  /** Issue #98: what the ID column renders — the group stem in grouped mode,
   *  the timepoint-stripped stem in flat mode. `experiment_id` above still
   *  names the real representative row. */
  group_display_id?: string | null
  /** Number of experiment rows this row stands for (1 = an ordinary row). */
  vial_count?: number
  /** Grouped mode only: the group's distinct replicate letters, for the badge. */
  replicate_letters?: string[] | null
  /** Grouped-list mode only: one entry per replicate letter-row of this group. */
  replicates?: ExperimentListItem[] | null
}

export interface ExperimentListResponse {
  items: ExperimentListItem[]
  total: number
  skip: number
  limit: number
}

export interface ExperimentDetail {
  id: number
  experiment_id: string
  experiment_number: number
  status: ExperimentStatus
  researcher: string | null
  date: string | null
  sample_id: string | null
  base_experiment_id: string | null
  parent_experiment_fk: number | null
  replicate_label: string | null
  is_outlier: boolean
  /** Issue #152: a background / blank vial; left out of a mixed group's averages.
   *  Always sent by the API; optional so payloads built before #152 stay valid. */
  is_background?: boolean
  id_timepoint_days: number | null
  created_at: string
  updated_at: string | null
  conditions: Record<string, unknown> | null
  notes: ExperimentNote[]
  modifications: Array<{
    id: number
    modified_by: string | null
    modification_type: string | null
    modified_table: string | null
    old_values: Record<string, unknown> | null
    new_values: Record<string, unknown> | null
    created_at: string
  }>
}

/** Issue #99: what deleting an experiment destroys (counts) and decouples (lists).
 *  `total` sums the counts only — the listed experiments survive. */
export interface DeleteImpact {
  experiment_id: string
  /** The setup row (temperature, pH, rock mass, reactor…) — destroyed with the
   *  experiment, so it is counted in `total`. */
  conditions: number
  results: number
  scalar_results: number
  icp_results: number
  result_files: number
  notes: number
  additives: number
  external_analyses: number
  xrd_phases: number
  total: number
  /** Other experiments that named this one as their ammonium background. */
  background_for: string[]
  /** Sample groups whose H2 background link points at this experiment; links are kept. */
  h2_background_for: string[]
  /** Replicates whose parent pointer is dropped; their group ID is unaffected. */
  replicate_children: string[]
}

export interface ExperimentDeleted {
  experiment_id: string
  deleted: boolean
  impact: DeleteImpact
}

export interface ResultWithFlags {
  id: number
  experiment_fk: number
  time_post_reaction_days: number | null
  time_post_reaction_bucket_days: number | null
  cumulative_time_post_reaction_days: number | null
  is_primary_timepoint_result: boolean
  created_at: string
  has_scalar: boolean
  has_icp: boolean
  /** Issue #118: true when a 'modification' note is scoped to this result. */
  has_modification_note: boolean
  /** Every typed note scoped to this result, in id order. */
  notes: ExperimentNote[]
  grams_per_ton_yield: number | null
  h2_concentration: number | null
  h2_grams_per_ton_yield: number | null
  h2_micromoles: number | null
  gross_ammonium_concentration_mM: number | null
  background_ammonium_concentration_mM: number | null
  final_conductivity_mS_cm: number | null
  final_ph: number | null
  scalar_measurement_date: string | null
  ferrous_iron_yield_h2_pct: number | null
  ferrous_iron_yield_nh3_pct: number | null
  nmr_run_date: string | null
  icp_run_date: string | null
  gc_run_date: string | null
  xrd_run_date: string | null
  /** Issue #146: the sample's tube number, when one was recorded. */
  sample_tube_number?: number | null
}

/** Fields a researcher can hand-enter on a non-core-flood result (issue #146).
 *  Gas pressure is in MPa on the wire; the form converts from psi. */
export interface ResultEntryFields {
  gc_run_date?: string | null
  sample_tube_number?: number | null
  sampling_volume_mL?: number | null
  h2_concentration?: number | null
  gas_sampling_volume_ml?: number | null
  gas_sampling_pressure_MPa?: number | null
  final_ph?: number | null
  final_conductivity_mS_cm?: number | null
  gross_ammonium_concentration_mM?: number | null
  /** Sets the sample's first result note; blank deletes it. */
  result_note?: string | null
  /** Adds a new modification note; never edits an existing one. */
  modification_note?: string | null
}

export interface ResultEntryCreate extends ResultEntryFields {
  measurement_date: string
  time_post_reaction_days?: number
}

export interface ResultEntryUpdate extends ResultEntryFields {
  /** May be omitted but never null. */
  measurement_date?: string
}

export interface ExperimentListParams {
  status?: string
  researcher?: string
  search?: string
  sample_id?: string
  experiment_type?: string
  reactor_number?: number
  /** Start date bounds, inclusive lab-local (America/New_York) YYYY-MM-DD. */
  date_from?: string
  date_to?: string
  /** Issue #168: last result date bounds (latest scalar measurement date, lab-local), inclusive. */
  last_result_from?: string
  last_result_to?: string
  description?: string
  additive?: string
  /** Issue #152: true = backgrounds only, false = samples only. */
  is_background?: boolean
  skip?: number
  limit?: number
  group_replicates?: boolean
}

export interface CreateExperimentPayload {
  experiment_id: string
  status?: string
  researcher?: string
  date?: string
  sample_id?: string
  experiment_type?: string
  note?: string
  is_background?: boolean
}

export interface RollupTimepoint {
  base_experiment_id: string
  time_post_reaction_bucket_days: number | null
  /** Distinct vials (experiments) behind this bucket's statistics. */
  n_vials: number
  /** Distinct replicate letters; 0 for an unlettered group. */
  n_replicate_letters: number
  /** Rows actually averaged — exceeds n_vials when a vial holds several. */
  n_values: number
  mean_gross_ammonium_mM: number | null
  median_gross_ammonium_mM: number | null
  sd_gross_ammonium_mM: number | null
  mean_net_ammonium_mM: number | null
  sd_net_ammonium_mM: number | null
  mean_h2_ppm: number | null
  sd_h2_ppm: number | null
  mean_h2_micromoles: number | null
  sd_h2_micromoles: number | null
  mean_h2_grams_per_ton: number | null
  sd_h2_grams_per_ton: number | null
  mean_fe_yield_h2_pct: number | null
  sd_fe_yield_h2_pct: number | null
  mean_fe_yield_nh3_pct: number | null
  sd_fe_yield_nh3_pct: number | null
  mean_grams_per_ton_yield: number | null
  sd_grams_per_ton_yield: number | null
  mean_final_ph: number | null
  /** Issue #152: every non-outlier member is a background, so these are the background's own stats. */
  is_background_group?: boolean
}

export interface ReplicateGroupMember {
  id: number
  experiment_id: string
  replicate_label: string | null
  status: ExperimentStatus | null
  is_outlier: boolean
  /** Issue #152: a background / blank vial; left out of a mixed group's averages.
   *  Always sent by the API; optional so payloads built before #152 stay valid. */
  is_background?: boolean
}

export interface ReplicateGroup {
  base_experiment_id: string
  parent: ReplicateGroupMember | null
  members: ReplicateGroupMember[]
}

export interface ReplicateGroupMemberDetail extends ReplicateGroupMember {
  id_timepoint_days: number | null
  researcher: string | null
  date: string | null
  result_count: number
  conditions: Record<string, unknown>
}

/** Issue #98: one replicate letter and its timepoint vials. */
export interface ReplicateLetterGroup {
  replicate_label: string
  vials: ReplicateGroupMemberDetail[]
}

export interface ReplicateGroupDetail {
  base_experiment_id: string
  parent: ReplicateGroupMemberDetail | null
  members: ReplicateGroupMemberDetail[]
  member_count: number
  shared_conditions: Record<string, unknown>
  divergent_fields: string[]
  additives_summary: string | null
  additive_names: string | null
  additives_diverge: boolean
  /** Issue #98: `members` grouped by letter. `member_count` stays per-vial. */
  replicates: ReplicateLetterGroup[]
  replicate_count: number
  /** Issue #144: the serum-vial H2 background linked to this group, if any. */
  h2_background: H2BackgroundLink | null
}

export interface H2BackgroundLink {
  mode: 'group' | 'vial'
  background_ref: string
  created_by: string | null
  updated_at: string | null
}

/** One row of GET /experiments/groups/{base_id}/h2-background/rollup. */
export interface H2BackgroundRollup {
  base_experiment_id: string
  time_post_reaction_bucket_days: number | null
  n_values: number
  bkg_time_bucket_days: number | null
  bkg_time_gap_days: number | null
  bkg_n_values: number | null
  bkg_mean_h2_micromoles: number | null
  bkg_sd_h2_micromoles: number | null
  mean_net_h2_micromoles: number | null
  sd_net_h2_micromoles: number | null
  mean_net_h2_grams_per_ton: number | null
  sd_net_h2_grams_per_ton: number | null
  mean_net_fe_yield_h2_pct: number | null
  sd_net_fe_yield_h2_pct: number | null
  below_background: boolean | null
}

/** Mirrors backend ReplicateCreateResponse: created items are ExperimentResponse-shaped
 *  (no conditions/notes/modifications). */
export interface CreatedReplicate {
  id: number
  experiment_id: string
  experiment_number: number
  status: ExperimentStatus | null
  researcher: string | null
  date: string | null
  sample_id: string | null
  base_experiment_id: string | null
  parent_experiment_fk: number | null
  replicate_label: string | null
  is_outlier: boolean
  /** Issue #152: a background / blank vial; left out of a mixed group's averages.
   *  Always sent by the API; optional so payloads built before #152 stay valid. */
  is_background?: boolean
  created_at: string
  updated_at: string | null
}

export interface CreateReplicatesResponse {
  created: CreatedReplicate[]
  skipped: string[]
}

/**
 * Per-request timeout for the Excel exports, overriding the shared client's 30 s
 * (issue #168). Building a workbook of every experiment measured ~3 s on the
 * 2026-11-06 dump, so this leaves wide headroom for the lab PC and data growth
 * while a stuck request still fails.
 */
export const EXPORT_TIMEOUT_MS = 120_000

export const experimentsApi = {
  list: (params?: ExperimentListParams) =>
    apiClient.get<ExperimentListResponse>('/experiments', { params }).then((r) => r.data),

  get: (experimentId: string) =>
    apiClient.get<ExperimentDetail>(`/experiments/${experimentId}`).then((r) => r.data),

  create: (payload: CreateExperimentPayload) =>
    apiClient.post<ExperimentDetail>('/experiments', payload).then((r) => r.data),

  patch: (
    experimentId: string,
    payload: {
      status?: string
      researcher?: string
      date?: string
      experiment_id?: string
      sample_id?: string
      is_outlier?: boolean
      is_background?: boolean
    },
  ) =>
    apiClient
      .patch<ExperimentDetail>(`/experiments/${experimentId}`, payload)
      .then((r) => r.data),

  patchStatus: (experimentId: string, status: ExperimentStatus) =>
    apiClient.patch<ExperimentDetail>(`/experiments/${experimentId}/status`, { status }).then((r) => r.data),

  nextId: (type: string) =>
    apiClient.get<{ next_id: string }>('/experiments/next-id', { params: { type } }).then((r) => r.data),

  checkExists: (experimentId: string) =>
    apiClient
      .get<{ exists: boolean }>(`/experiments/${encodeURIComponent(experimentId)}/exists`)
      .then((r) => r.data),

  getResults: (experimentId: string) =>
    apiClient.get<ResultWithFlags[]>(`/experiments/${experimentId}/results`).then((r) => r.data),

  /** Issue #146: one atomic create of a result, its scalar row and its notes. */
  createResult: (experimentId: string, body: ResultEntryCreate) =>
    apiClient
      .post<ResultWithFlags>(`/experiments/${encodeURIComponent(experimentId)}/results`, body)
      .then((r) => r.data),

  /** Issue #146: changed fields only; a primary result of a non-core-flood experiment. */
  updateResult: (experimentId: string, resultId: number, body: ResultEntryUpdate) =>
    apiClient
      .patch<ResultWithFlags>(
        `/experiments/${encodeURIComponent(experimentId)}/results/${resultId}`,
        body,
      )
      .then((r) => r.data),

  setBackgroundAmmonium: (experimentId: string, value: number) =>
    apiClient.patch<{ updated: number }>(`/experiments/${experimentId}/background-ammonium`, { value }).then((r) => r.data),

  addNote: (experimentId: string, text: string, opts: Omit<NoteCreate, 'note_text'> = {}) =>
    apiClient
      .post<ExperimentNote>(`/experiments/${experimentId}/notes`, { note_text: text, ...opts })
      .then((r) => r.data),

  patchNote: (experimentId: string, noteId: number, patch: NotePatch) =>
    apiClient.patch<ExperimentNote>(`/experiments/${experimentId}/notes/${noteId}`, patch),

  /** Issue #118/#122: notes flagged needs_review, across all experiments, filtered and ordered. */
  getReviewQueue: (params: ReviewQueueParams = {}) =>
    apiClient
      .get<ReviewQueueResponse>('/experiments/notes/review', { params })
      .then((r) => r.data),

  /** Issue #122 PR-A: resolve / retype many notes in one atomic call (cap 500). */
  bulkPatchNotes: (body: NotesBulkPatch) =>
    apiClient.patch<NotesBulkResponse>('/experiments/notes/bulk', body).then((r) => r.data),

  /** Issue #122 PR-A: delete many notes in one atomic call (cap 500). */
  bulkDeleteNotes: (ids: number[]) =>
    apiClient
      .delete<NotesBulkResponse>('/experiments/notes/bulk', { data: { ids } })
      .then((r) => r.data),

  deleteNote: (experimentId: string, noteId: number) =>
    apiClient.delete(`/experiments/${experimentId}/notes/${noteId}`),

  getDeleteImpact: (experimentId: string) =>
    apiClient
      .get<DeleteImpact>(`/experiments/${encodeURIComponent(experimentId)}/delete-impact`)
      .then((r) => r.data),

  delete: (experimentId: string) =>
    apiClient
      .delete<ExperimentDeleted>(`/experiments/${encodeURIComponent(experimentId)}`)
      .then((r) => r.data),

  /** ICP readings over cumulative time for the experiment's whole series (issue #143). */
  getIcp: (experimentId: string) =>
    apiClient
      .get<ExperimentIcp>(`/experiments/${encodeURIComponent(experimentId)}/icp`)
      .then((r) => r.data),

  getRollup: (experimentId: string) =>
    apiClient.get<RollupTimepoint[]>(`/experiments/${experimentId}/rollup`).then((r) => r.data),

  getReplicateGroup: (experimentId: string) =>
    apiClient.get<ReplicateGroup>(`/experiments/${experimentId}/replicate-group`).then((r) => r.data),

  createReplicates: (payload: { base_experiment_id: string; count: number }) =>
    apiClient.post<CreateReplicatesResponse>('/experiments/replicates', payload).then((r) => r.data),

  getGroup: (baseId: string) =>
    apiClient
      .get<ReplicateGroupDetail>(`/experiments/groups/${encodeURIComponent(baseId)}`)
      .then((r) => r.data),

  getGroupRollup: (baseId: string) =>
    apiClient
      .get<RollupTimepoint[]>(`/experiments/groups/${encodeURIComponent(baseId)}/rollup`)
      .then((r) => r.data),

  /** Issue #144: link a background experiment (whole group or one vial) to a group. */
  setGroupH2Background: (
    baseId: string,
    body: { experiment_id: string; mode: 'group' | 'vial' },
  ) =>
    apiClient
      .put<H2BackgroundLink>(
        `/experiments/groups/${encodeURIComponent(baseId)}/h2-background`,
        body,
      )
      .then((r) => r.data),

  clearGroupH2Background: (baseId: string) =>
    apiClient
      .delete(`/experiments/groups/${encodeURIComponent(baseId)}/h2-background`)
      .then(() => undefined),

  getGroupH2BackgroundRollup: (baseId: string) =>
    apiClient
      .get<H2BackgroundRollup[]>(
        `/experiments/groups/${encodeURIComponent(baseId)}/h2-background/rollup`,
      )
      .then((r) => r.data),

  /**
   * Download the Export all workbook for an experiment's whole lineage (issue #141).
   * Fetched as a blob through apiClient so the Firebase token is attached.
   * Resolves to the saved filename; rejects with the server's `detail` text on failure.
   */
  exportAll: async (experimentId: string): Promise<string> => {
    try {
      const response = await apiClient.get<Blob>(
        `/experiments/${encodeURIComponent(experimentId)}/export`,
        { responseType: 'blob', timeout: EXPORT_TIMEOUT_MS },
      )
      const filename = filenameFromDisposition(
        response.headers['content-disposition'],
        `${experimentId}_export.xlsx`,
      )
      saveBlob(response.data, filename)
      return filename
    } catch (err) {
      throw new Error(await blobErrorMessage(err))
    }
  },

  /**
   * Download one workbook for a chosen set of experiments (issue #142).
   * Resolves to the saved filename; rejects with the server's `detail` text on failure.
   */
  exportSelection: async (experimentIds: string[], includeSeries: boolean): Promise<string> => {
    try {
      const response = await apiClient.post<Blob>(
        '/experiments/export',
        { experiment_ids: experimentIds, include_series: includeSeries },
        { responseType: 'blob', timeout: EXPORT_TIMEOUT_MS },
      )
      const filename = filenameFromDisposition(
        response.headers['content-disposition'],
        'data_export.xlsx',
      )
      saveBlob(response.data, filename)
      return filename
    } catch (err) {
      throw new Error(await blobErrorMessage(err))
    }
  },
}
