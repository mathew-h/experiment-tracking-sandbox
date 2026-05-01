import { useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui'
import type { SampleConflict } from '@/api/bulkUploads'

export type ConflictResolution =
  | { action: 'link'; existingSampleId: string }
  | { action: 'create' }

export interface SampleConflictModalProps {
  open: boolean
  conflicts: SampleConflict[]
  onConfirm: (resolutions: Record<string, string>) => void
  onCancel: () => void
}

/** Blocking modal shown when the ActLabs upload finds near-duplicate sample IDs.
 *  The user must resolve every conflict before the upload can proceed.
 */
export function SampleConflictModal({ open, conflicts, onConfirm, onCancel }: SampleConflictModalProps) {
  const [choices, setChoices] = useState<Record<string, string>>({})

  const setChoice = (incomingId: string, value: string) =>
    setChoices((prev) => ({ ...prev, [incomingId]: value }))

  const allResolved = conflicts.every((c) => choices[c.incoming_id] !== undefined)

  const handleConfirm = () => {
    onConfirm(choices)
    setChoices({})
  }

  const handleCancel = () => {
    setChoices({})
    onCancel()
  }

  return (
    <Modal
      open={open}
      onClose={handleCancel}
      title="Sample ID Conflicts Detected"
      description="The following incoming sample IDs closely match existing samples. Choose how to handle each one before the upload can proceed."
      size="lg"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={handleCancel}>Cancel Upload</Button>
          <Button variant="primary" onClick={handleConfirm} disabled={!allResolved}>
            Confirm &amp; Upload
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {conflicts.map((conflict) => (
          <div
            key={conflict.incoming_id}
            className="rounded border border-surface-border p-3 space-y-2"
          >
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-ink-primary">Incoming:</span>
              <code className="text-sm font-mono bg-surface-secondary px-1 rounded text-amber-400">
                {conflict.incoming_id}
              </code>
            </div>

            <p className="text-xs text-ink-muted">Close matches in database:</p>
            <div className="space-y-1 pl-2">
              {conflict.candidate_matches.map((m) => (
                <label
                  key={m.sample_id}
                  className="flex items-center gap-2 cursor-pointer text-sm text-ink-primary"
                >
                  <input
                    type="radio"
                    name={`conflict-${conflict.incoming_id}`}
                    value={`link:${m.sample_id}`}
                    checked={choices[conflict.incoming_id] === `link:${m.sample_id}`}
                    onChange={() => setChoice(conflict.incoming_id, `link:${m.sample_id}`)}
                    className="accent-brand-primary"
                  />
                  <span>
                    Link to <code className="font-mono text-xs bg-surface-secondary px-1 rounded">{m.sample_id}</code>
                  </span>
                  <span className="text-xs text-ink-muted ml-auto">
                    {Math.round(m.similarity * 100)}% match
                  </span>
                </label>
              ))}
            </div>

            <label className="flex items-center gap-2 cursor-pointer text-sm text-ink-primary pl-2">
              <input
                type="radio"
                name={`conflict-${conflict.incoming_id}`}
                value="create"
                checked={choices[conflict.incoming_id] === 'create'}
                onChange={() => setChoice(conflict.incoming_id, 'create')}
                className="accent-brand-primary"
              />
              <span>Create as new sample</span>
            </label>
          </div>
        ))}
      </div>
    </Modal>
  )
}
