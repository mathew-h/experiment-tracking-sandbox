import { useState } from 'react'
import { Modal, Input, Button, FileUpload } from '@/components/ui'
import { samplesApi } from '@/api/samples'

interface Props {
  onClose: () => void
  onCreated: (sampleId: string) => void
}

interface FormData {
  sample_id: string
  rock_classification: string
  locality: string
  state: string
  country: string
  latitude: string
  longitude: string
  description: string
  pxrf_reading_no: string
  magnetic_susceptibility: string
}

const EMPTY: FormData = {
  sample_id: '',
  rock_classification: '',
  locality: '',
  state: '',
  country: '',
  latitude: '',
  longitude: '',
  description: '',
  pxrf_reading_no: '',
  magnetic_susceptibility: '',
}

export function NewSampleModal({ onClose, onCreated }: Props) {
  const [form, setForm] = useState<FormData>(EMPTY)
  const [photo, setPhoto] = useState<File | null>(null)
  const [photoDesc, setPhotoDesc] = useState('')
  const [step, setStep] = useState<'idle' | 'creating' | 'uploading' | 'done'>('idle')
  const [warnings, setWarnings] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  const set =
    (k: keyof FormData) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm((f) => ({ ...f, [k]: e.target.value }))

  const handleSubmit = async () => {
    if (!form.sample_id.trim()) return
    setStep('creating')
    setWarnings([])
    setError(null)
    try {
      const sample = await samplesApi.create({
        sample_id: form.sample_id.trim(),
        ...(form.rock_classification && { rock_classification: form.rock_classification }),
        ...(form.locality && { locality: form.locality }),
        ...(form.state && { state: form.state }),
        ...(form.country && { country: form.country }),
        ...(form.latitude && { latitude: parseFloat(form.latitude) }),
        ...(form.longitude && { longitude: parseFloat(form.longitude) }),
        ...(form.description && { description: form.description }),
      })

      setStep('uploading')

      if (photo) {
        await samplesApi.uploadPhoto(sample.sample_id, photo, photoDesc || undefined)
      }

      const w: string[] = []
      if (form.pxrf_reading_no) {
        const result = await samplesApi.createAnalysis(sample.sample_id, {
          analysis_type: 'pXRF',
          pxrf_reading_no: form.pxrf_reading_no,
        })
        w.push(...result.warnings)
      }
      if (form.magnetic_susceptibility) {
        await samplesApi.createAnalysis(sample.sample_id, {
          analysis_type: 'Magnetic Susceptibility',
          magnetic_susceptibility: form.magnetic_susceptibility,
        })
      }

      setWarnings(w)
      setStep('done')
      onCreated(sample.sample_id)
    } catch (err) {
      const msg = (err as { message?: string }).message ?? 'Failed to create sample'
      setError(msg)
      setStep('idle')
    }
  }

  const busy = step === 'creating' || step === 'uploading'
  const buttonLabel =
    step === 'creating' ? 'Creating…' : step === 'uploading' ? 'Uploading…' : 'Create Sample'

  return (
    <Modal
      open
      onClose={busy ? () => {} : onClose}
      title="New Sample"
      description="Create a sample record with optional photo and initial analyses."
      size="xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            loading={busy}
            disabled={busy || !form.sample_id.trim()}
          >
            {buttonLabel}
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-6">
        {/* Left column — core sample fields */}
        <div className="flex flex-col gap-4">
          <p className="text-xs font-semibold text-ink-muted uppercase tracking-wider">
            Sample Details
          </p>

          <Input
            label="Sample ID *"
            value={form.sample_id}
            onChange={set('sample_id')}
            placeholder="e.g. DUN-001"
            disabled={busy}
          />

          <Input
            label="Rock Classification"
            value={form.rock_classification}
            onChange={set('rock_classification')}
            placeholder="e.g. Dunite"
            disabled={busy}
          />

          <Input
            label="Locality"
            value={form.locality}
            onChange={set('locality')}
            placeholder="e.g. Oman ophiolite"
            disabled={busy}
          />

          <div className="grid grid-cols-2 gap-3">
            <Input
              label="State / Province"
              value={form.state}
              onChange={set('state')}
              placeholder="e.g. Muscat"
              disabled={busy}
            />
            <Input
              label="Country"
              value={form.country}
              onChange={set('country')}
              placeholder="e.g. Oman"
              disabled={busy}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Latitude"
              type="number"
              value={form.latitude}
              onChange={set('latitude')}
              placeholder="e.g. 22.5"
              disabled={busy}
            />
            <Input
              label="Longitude"
              type="number"
              value={form.longitude}
              onChange={set('longitude')}
              placeholder="e.g. 57.3"
              disabled={busy}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-ink-secondary uppercase tracking-wider">
              Description
            </label>
            <textarea
              value={form.description}
              onChange={set('description')}
              placeholder="Additional notes about this sample…"
              disabled={busy}
              rows={3}
              className={[
                'w-full bg-surface-raised border border-surface-border rounded text-sm text-ink-primary',
                'placeholder-ink-muted px-3 py-2 resize-none',
                'transition-colors duration-100',
                'focus:outline-none focus:border-red-500 focus:ring-1 focus:ring-red-500/30',
                'hover:border-ink-muted',
                'disabled:opacity-40 disabled:cursor-not-allowed',
              ].join(' ')}
            />
          </div>
        </div>

        {/* Right column — optional analyses + photo */}
        <div className="flex flex-col gap-4">
          <p className="text-xs font-semibold text-ink-muted uppercase tracking-wider">
            Optional Analyses &amp; Photo
          </p>

          <Input
            label="pXRF Reading No."
            value={form.pxrf_reading_no}
            onChange={set('pxrf_reading_no')}
            placeholder="e.g. R-0042"
            hint="Links this sample to an existing pXRF reading."
            disabled={busy}
          />

          <Input
            label="Magnetic Susceptibility"
            value={form.magnetic_susceptibility}
            onChange={set('magnetic_susceptibility')}
            placeholder="e.g. 3.2 × 10⁻³ SI"
            disabled={busy}
          />

          <FileUpload
            label="Sample Photo (optional)"
            accept="image/jpeg,image/png,image/webp"
            hint="JPEG, PNG or WebP — one photo uploaded on creation."
            disabled={busy}
            onFiles={(files) => setPhoto(files[0] ?? null)}
          />

          {photo && (
            <div className="flex items-center justify-between rounded bg-surface-raised border border-surface-border px-3 py-2">
              <span className="text-xs text-ink-secondary truncate max-w-[160px]">{photo.name}</span>
              <button
                onClick={() => setPhoto(null)}
                disabled={busy}
                className="text-ink-muted hover:text-ink-primary transition-colors text-xs ml-2 shrink-0"
              >
                Remove
              </button>
            </div>
          )}

          {photo && (
            <Input
              label="Photo Description"
              value={photoDesc}
              onChange={(e) => setPhotoDesc(e.target.value)}
              placeholder="Optional caption…"
              disabled={busy}
            />
          )}

          {/* Warnings from pXRF linking */}
          {warnings.length > 0 && (
            <div className="rounded bg-amber-500/10 border border-amber-500/30 px-3 py-2 flex flex-col gap-1">
              <p className="text-xs font-semibold text-amber-400 uppercase tracking-wider">
                Warnings
              </p>
              {warnings.map((w, i) => (
                <p key={i} className="text-xs text-amber-300">
                  {w}
                </p>
              ))}
            </div>
          )}

          {/* Error message */}
          {error && (
            <div className="rounded bg-red-500/10 border border-red-500/30 px-3 py-2">
              <p className="text-xs text-red-400">{error}</p>
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}
