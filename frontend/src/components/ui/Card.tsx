import { HTMLAttributes } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'raised' | 'flat'
  padding?: 'none' | 'sm' | 'md' | 'lg'
}

interface CardSectionProps extends HTMLAttributes<HTMLDivElement> {
  label?: string
}

const paddingClasses = {
  none: '',
  sm:   'p-3',
  md:   'p-4',
  lg:   'p-5',
}

const variantClasses = {
  default: 'bg-surface-raised border border-surface-border shadow-panel',
  raised:  'bg-surface-overlay border border-surface-border shadow-panel-lg',
  flat:    'bg-transparent border border-surface-border',
}

export function Card({ variant = 'default', padding = 'md', className = '', children, ...props }: CardProps) {
  return (
    <div className={[variantClasses[variant], paddingClasses[padding], 'rounded-lg', className].join(' ')} {...props}>
      {children}
    </div>
  )
}

export function CardHeader({ label, className = '', children, ...props }: CardSectionProps) {
  return (
    <div className={['flex items-center justify-between px-4 py-3 border-b border-surface-border', className].join(' ')} {...props}>
      {label && <span className="text-xs font-semibold text-ink-secondary uppercase tracking-wider">{label}</span>}
      {children}
    </div>
  )
}

export function CardBody({ className = '', children, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={['p-4', className].join(' ')} {...props}>
      {children}
    </div>
  )
}

// Metric card — for dashboard stats
interface MetricCardProps {
  label: string
  value: string | number
  unit?: string
  trend?: 'up' | 'down' | 'neutral'
  sub?: string
  className?: string
}

export function MetricCard({ label, value, unit, sub, className = '' }: MetricCardProps) {
  return (
    <Card className={className}>
      <p className="text-xs font-medium text-ink-muted uppercase tracking-wider mb-2">{label}</p>
      <div className="flex items-baseline gap-1.5">
        <span className="text-2xl font-bold text-ink-primary font-mono-data leading-none">{value}</span>
        {unit && <span className="text-xs text-ink-muted">{unit}</span>}
      </div>
      {sub && <p className="text-xs text-ink-muted mt-1.5">{sub}</p>}
    </Card>
  )
}
