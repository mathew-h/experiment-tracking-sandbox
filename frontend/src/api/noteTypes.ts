/** Issue #118: every experiment note declares what it is for.
 *
 *  Kept in its own module (no API client import) so components can use the
 *  labels while tests mock `@/api/experiments` wholesale. */
export type NoteType = 'description' | 'modification' | 'observation' | 'result_note'

export const NOTE_TYPE_LABELS: Record<NoteType, string> = {
  /** The experiment's summary. At most one per experiment, never on a timepoint. */
  description: 'Description',
  /** What was done to the vial at a timepoint (the MOD badge). */
  modification: 'Modification',
  /** Free text, on a timepoint or not. */
  observation: 'Observation',
  /** A remark about one measurement. */
  result_note: 'Result note',
}
