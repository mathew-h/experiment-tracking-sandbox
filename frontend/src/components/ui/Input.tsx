import { forwardRef, InputHTMLAttributes, ReactNode, useId } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  hint?: string
  leftIcon?: ReactNode
  rightElement?: ReactNode
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, leftIcon, rightElement, className = '', id, ...props }, ref) => {
    const generatedId = useId()
    const inputId = id ?? generatedId
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label htmlFor={inputId} className="text-xs font-medium text-ink-secondary uppercase tracking-wider">
            {label}
          </label>
        )}
        <div className="relative flex items-center">
          {leftIcon && (
            <span className="absolute left-3 text-ink-muted pointer-events-none">{leftIcon}</span>
          )}
          <input
            ref={ref}
            id={inputId}
            className={[
              'w-full h-8 bg-surface-raised border rounded text-sm text-ink-primary placeholder-ink-muted',
              'transition-colors duration-100',
              'focus:outline-none focus:border-red-500 focus:ring-1 focus:ring-red-500/30',
              error ? 'border-red-500 bg-red-500/5' : 'border-surface-border hover:border-ink-muted',
              leftIcon ? 'pl-9' : 'pl-3',
              rightElement ? 'pr-9' : 'pr-3',
              'disabled:opacity-40 disabled:cursor-not-allowed',
              className,
            ].join(' ')}
            {...props}
          />
          {rightElement && (
            <span className="absolute right-3 text-ink-muted">{rightElement}</span>
          )}
        </div>
        {error && <p className="text-xs text-red-400">{error}</p>}
        {hint && !error && <p className="text-xs text-ink-muted">{hint}</p>}
      </div>
    )
  }
)
Input.displayName = 'Input'
