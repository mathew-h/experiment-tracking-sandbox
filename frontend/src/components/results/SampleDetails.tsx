import type { ReactNode } from 'react'
import { NoteBadge } from '@/components/experiments/NoteBadge'
import type { NoteType } from '@/api/experiments'
import type { SampleRow } from './sampleRows'

/** GC renders even when blank if an H₂ reading exists: a field that appears only
 *  when populated cannot show a researcher that it is missing (issue #115). */
export function gcMissing(row: SampleRow): boolean {
  const gc = row.runDates.find((d) => d.label === 'GC')
  return gc !== undefined && gc.value == null && row.h2Ppm != null
}

/** True when the DETAILS flag has something to show for this row. */
export function hasDetails(row: SampleRow, hasExtra = false): boolean {
  return hasExtra || row.notes.length > 0 || gcMissing(row) || row.runDates.some((d) => d.value != null)
}

interface Props {
  row: SampleRow
  /** Page-specific values shown first (the Results tab's DO and Fe(II)). */
  extra?: ReactNode
}

/** The DETAILS section of a sample (issue #163): page extras, instrument run
 *  dates with the missing-GC warning, and every note on the timepoint. */
export function SampleDetails({ row, extra }: Props) {
  const missing = gcMissing(row)
  const dates = row.runDates.filter((d) => d.value != null || (d.label === 'GC' && missing))
  return (
    <div className="space-y-3">
      {extra}
      {dates.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-ink-secondary mb-1">Instrument Run Dates</p>
          <div className="grid grid-cols-4 gap-x-4 gap-y-1">
            {dates.map((d) => (
              <div key={d.label} className="text-xs">
                <span className="text-ink-muted">{d.label}: </span>
                <span className={`font-mono-data ${d.value == null ? 'text-status-warning' : 'text-ink-primary'}`}>
                  {/* Run dates are calendar dates stored at UTC midnight; converting
                      to lab time would show the day before, so take the date part. */}
                  {d.value == null ? 'not recorded' : d.value.slice(0, 10)}
                </span>
              </div>
            ))}
          </div>
          {missing && (
            <p className="text-xs text-ink-muted mt-1">
              An H₂ reading is stored for this timepoint but no GC run date, so it is
              not counted by the Dashboard's GC Measurements card.
            </p>
          )}
        </div>
      )}
      {row.notes.length > 0 && (
        <div data-testid="timepoint-notes">
          <p className="text-xs font-semibold text-ink-secondary mb-1">Notes</p>
          <ul className="space-y-1">
            {row.notes.map((n) => (
              <li key={n.id} className="text-xs flex items-start gap-2">
                <NoteBadge type={n.note_type as NoteType} />
                <span className="text-ink-primary">
                  {n.note_text}
                  {n.created_by && <span className="text-ink-muted"> · {n.created_by}</span>}
                  {n.needs_review && <span className="text-status-error"> · needs review</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
