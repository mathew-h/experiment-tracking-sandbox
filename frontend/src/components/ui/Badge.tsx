type BadgeVariant = 'default' | 'success' | 'warning' | 'error' | 'info' | 'ongoing' | 'completed' | 'cancelled'

interface BadgeProps {
  children: React.ReactNode
  variant?: BadgeVariant
  dot?: boolean
  className?: string
}

const variantClasses: Record<BadgeVariant, string> = {
  default:   'bg-surface-overlay text-ink-secondary border-surface-border',
  success:   'bg-status-success/10 text-status-success border-status-success/20',
  warning:   'bg-status-warning/10 text-status-warning border-status-warning/20',
  error:     'bg-status-error/10 text-status-error border-status-error/20',
  info:      'bg-status-info/10 text-status-info border-status-info/20',
  ongoing:   'bg-status-ongoing/10 text-status-ongoing border-status-ongoing/20',
  completed: 'bg-status-completed/10 text-status-completed border-status-completed/20',
  cancelled: 'bg-status-cancelled/10 text-status-cancelled border-status-cancelled/20',
}

const dotClasses: Record<BadgeVariant, string> = {
  default:   'bg-ink-muted',
  success:   'bg-status-success',
  warning:   'bg-status-warning',
  error:     'bg-status-error',
  info:      'bg-status-info',
  ongoing:   'bg-status-ongoing',
  completed: 'bg-status-completed',
  cancelled: 'bg-status-cancelled',
}

/** Pill-shaped label with semantic color variants and optional status dot. */
export function Badge({ children, variant = 'default', dot = false, className = '' }: BadgeProps) {
  return (
    <span className={[
      'inline-flex items-center gap-1.5 px-2 py-0.5 text-2xs font-medium rounded border uppercase tracking-wider',
      variantClasses[variant],
      className,
    ].join(' ')}>
      {dot && <span className={['w-1.5 h-1.5 rounded-full shrink-0', dotClasses[variant]].join(' ')} />}
      {children}
    </span>
  )
}

/** Convenience badge that maps an experiment status string to the correct variant. */
export function StatusBadge({ status }: { status: string }) {
  const variant = (status.toLowerCase() as BadgeVariant)
  const validVariants: BadgeVariant[] = ['ongoing', 'completed', 'cancelled']
  return (
    <Badge variant={validVariants.includes(variant) ? variant : 'default'} dot>
      {status}
    </Badge>
  )
}
