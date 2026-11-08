/** Types shared by the Core Flood and HPHT run endpoints (backend `schemas/runs.py`). */

/** One experiment of a run: a sequential segment (X_001, X_001-2) or a `_Text` variant. */
export interface RunSegment {
  id: number
  experiment_id: string
  status: string | null
  date: string | null
  parent_experiment_id: string | null
  is_variant: boolean
  description: string | null
  conditions_id: number | null
  pore_volume_mL: number | null
  rock_mass_g: number | null
  reactor_slot: string | null
}

export interface RunSampleNote {
  id: number
  note_type: 'observation' | 'result_note' | 'modification'
  note_text: string
  created_by: string | null
}
