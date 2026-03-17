import { forwardRef, SelectHTMLAttributes, ReactNode, useId } from 'react'

interface SelectOption {
  value: string
  label: string
  disabled?: boolean
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  hint?: string
  options: SelectOption[]
  placeholder?: string
  leftIcon?: ReactNode
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, hint, options, placeholder, leftIcon, className = '', id, ...props }, ref) => {
    const generatedId = useId()
    const selectId = id ?? generatedId
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label htmlFor={selectId} className="text-xs font-medium text-ink-secondary uppercase tracking-wider">
            {label}
          </label>
        )}
        <div className="relative flex items-center">
          {leftIcon && (
            <span className="absolute left-3 text-ink-muted pointer-events-none z-10">{leftIcon}</span>
          )}
          <select
            ref={ref}
            id={selectId}
            className={[
              'w-full h-8 bg-surface-raised border rounded text-sm text-ink-primary appearance-none cursor-pointer',
              'transition-colors duration-100',
              'focus:outline-none focus:border-red-500 focus:ring-1 focus:ring-red-500/30',
              error ? 'border-red-500' : 'border-surface-border hover:border-ink-muted',
              leftIcon ? 'pl-9' : 'pl-3',
              'pr-8',
              'disabled:opacity-40 disabled:cursor-not-allowed',
              className,
            ].join(' ')}
            {...props}
          >
            {placeholder && <option value="">{placeholder}</option>}
            {options.map((opt) => (
              <option key={opt.value} value={opt.value} disabled={opt.disabled}>
                {opt.label}
              </option>
            ))}
          </select>
          <span className="absolute right-2.5 pointer-events-none text-ink-muted">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
              <path d="M2.5 4.5L6 8l3.5-3.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </span>
        </div>
        {error && <p className="text-xs text-red-400">{error}</p>}
        {hint && !error && <p className="text-xs text-ink-muted">{hint}</p>}
      </div>
    )
  }
)
Select.displayName = 'Select'
