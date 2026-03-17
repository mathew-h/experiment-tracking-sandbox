import { forwardRef, ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'outline'
type Size = 'xs' | 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  leftIcon?: React.ReactNode
  rightIcon?: React.ReactNode
}

const variantClasses: Record<Variant, string> = {
  primary:   'bg-red-500 hover:bg-red-600 text-white shadow-glow-red/30 hover:shadow-glow-red border border-red-600',
  secondary: 'bg-surface-raised hover:bg-surface-overlay text-ink-primary border border-surface-border hover:border-ink-muted',
  ghost:     'bg-transparent hover:bg-surface-raised text-ink-secondary hover:text-ink-primary border border-transparent',
  danger:    'bg-red-600 hover:bg-red-500 text-white border border-red-500',
  outline:   'bg-transparent border border-red-500 text-red-500 hover:bg-red-500/10',
}

const sizeClasses: Record<Size, string> = {
  xs: 'h-6 px-2 text-2xs gap-1',
  sm: 'h-7 px-3 text-xs gap-1.5',
  md: 'h-8 px-4 text-sm gap-2',
  lg: 'h-10 px-5 text-sm gap-2',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'secondary', size = 'md', loading, leftIcon, rightIcon, children, className = '', disabled, ...props }, ref) => {
    const isDisabled = disabled || loading
    return (
      <button
        ref={ref}
        disabled={isDisabled}
        className={[
          'inline-flex items-center justify-center font-medium rounded transition-all duration-100 cursor-pointer select-none',
          'focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2 focus-visible:ring-offset-navy-900',
          'disabled:opacity-40 disabled:cursor-not-allowed disabled:pointer-events-none',
          variantClasses[variant],
          sizeClasses[size],
          className,
        ].join(' ')}
        {...props}
      >
        {loading ? (
          <span className="animate-spin w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full" />
        ) : leftIcon}
        {children}
        {!loading && rightIcon}
      </button>
    )
  }
)
Button.displayName = 'Button'
