// frontend/src/pages/SampleDetail/PhotosTab.tsx
import { useState } from 'react'
import { useQueryClient, useMutation } from '@tanstack/react-query'
import { samplesApi, type SampleDetail } from '@/api/samples'

interface Props { sample: SampleDetail }

export function PhotosTab({ sample }: Props) {
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [desc, setDesc] = useState('')

  const uploadMutation = useMutation({
    mutationFn: () => samplesApi.uploadPhoto(sample.sample_id, file!, desc || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sample', sample.sample_id] })
      setFile(null)
      setDesc('')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (photoId: number) => samplesApi.deletePhoto(sample.sample_id, photoId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sample', sample.sample_id] }),
  })

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-surface-border bg-surface-raised p-4 space-y-3">
        <label className="block text-xs font-medium text-ink-secondary">Upload Photo (JPG / PNG, max 20 MB)</label>
        <input type="file" accept="image/jpeg,image/png" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm" />
        {file && (
          <div className="space-y-2">
            <input
              type="text"
              placeholder="Description (optional)"
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary focus:outline-none"
            />
            <button
              onClick={() => uploadMutation.mutate()}
              disabled={uploadMutation.isPending}
              className="text-xs bg-brand-red text-white px-3 py-1.5 rounded hover:bg-brand-red/90 disabled:opacity-50"
            >
              {uploadMutation.isPending ? 'Uploading…' : 'Upload'}
            </button>
          </div>
        )}
      </div>

      {sample.photos.length === 0 ? (
        <p className="text-sm text-ink-muted text-center py-8">No photos yet.</p>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {sample.photos.map((p) => (
            <div key={p.id} className="rounded-lg border border-surface-border bg-surface-raised p-3 space-y-2">
              <div className="h-36 bg-surface-overlay rounded overflow-hidden flex items-center justify-center">
                <span className="text-xs text-ink-muted font-mono-data break-all px-2">{p.file_name}</span>
              </div>
              {p.description && <p className="text-xs text-ink-muted">{p.description}</p>}
              <p className="text-xs text-ink-muted">{new Date(p.created_at).toLocaleDateString()}</p>
              <button
                className="text-xs text-red-400 hover:text-red-300"
                onClick={() => deleteMutation.mutate(p.id)}
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
