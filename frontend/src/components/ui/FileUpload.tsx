import { useRef, DragEvent, ChangeEvent, useState } from 'react'

interface FileUploadProps {
  accept?: string
  multiple?: boolean
  onFiles: (files: File[]) => void
  label?: string
  hint?: string
  error?: string
  disabled?: boolean
  className?: string
}

/** Drag-and-drop / click-to-browse file input with accept filter and validation hint. */
export function FileUpload({ accept, multiple, onFiles, label, hint, error, disabled, className = '' }: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    if (disabled) return
    const files = Array.from(e.dataTransfer.files)
    if (files.length) onFiles(files)
  }

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    if (files.length) onFiles(files)
    e.target.value = ''
  }

  return (
    <div className={['flex flex-col gap-1.5', className].join(' ')}>
      {label && (
        <span className="text-xs font-medium text-ink-secondary uppercase tracking-wider">{label}</span>
      )}
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => e.key === 'Enter' && !disabled && inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={[
          'flex flex-col items-center justify-center gap-2 p-6 rounded-lg border-2 border-dashed',
          'transition-colors duration-150 cursor-pointer text-center',
          dragging
            ? 'border-red-500 bg-red-500/5'
            : error
            ? 'border-red-500/60 bg-red-500/5'
            : 'border-surface-border hover:border-ink-muted hover:bg-surface-raised',
          disabled && 'opacity-40 cursor-not-allowed pointer-events-none',
        ].join(' ')}
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className={dragging ? 'text-red-500' : 'text-ink-muted'}>
          <path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1M12 3v13M8 7l4-4 4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        <div>
          <p className="text-sm text-ink-secondary">
            <span className="text-red-400 font-medium">Click to upload</span> or drag & drop
          </p>
          {accept && <p className="text-xs text-ink-muted mt-0.5">{accept.split(',').join(', ')}</p>}
        </div>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={handleChange}
        className="hidden"
        disabled={disabled}
      />
      {error && <p className="text-xs text-red-400">{error}</p>}
      {hint && !error && <p className="text-xs text-ink-muted">{hint}</p>}
    </div>
  )
}
