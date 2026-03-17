interface SpinnerProps {
  size?: 'xs' | 'sm' | 'md' | 'lg'
  className?: string
  label?: string
}

const sizeClasses = {
  xs: 'w-3 h-3 border',
  sm: 'w-4 h-4 border-2',
  md: 'w-6 h-6 border-2',
  lg: 'w-8 h-8 border-2',
}

export function Spinner({ size = 'md', className = '', label }: SpinnerProps) {
  return (
    <span
      role="status"
      aria-label={label ?? 'Loading'}
      className={['inline-flex items-center gap-2', className].join(' ')}
    >
      <span className={[
        'animate-spin rounded-full border-surface-border border-t-red-500',
        sizeClasses[size],
      ].join(' ')} />
      {label && <span className="text-xs text-ink-muted">{label}</span>}
    </span>
  )
}

export function PageSpinner() {
  return (
    <div className="flex items-center justify-center w-full h-64">
      <Spinner size="lg" label="Loading…" />
    </div>
  )
}
