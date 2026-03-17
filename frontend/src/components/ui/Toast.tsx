import { createContext, useContext, useState, useCallback, ReactNode } from 'react'

type ToastType = 'success' | 'error' | 'warning' | 'info'

interface ToastItem {
  id: string
  type: ToastType
  title: string
  message?: string
}

interface ToastContextValue {
  toast: (type: ToastType, title: string, message?: string) => void
  success: (title: string, message?: string) => void
  error: (title: string, message?: string) => void
  warning: (title: string, message?: string) => void
  info: (title: string, message?: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

const typeConfig: Record<ToastType, { icon: string; classes: string }> = {
  success: { icon: '✓', classes: 'border-status-success/40 bg-status-success/10 text-status-success' },
  error:   { icon: '✕', classes: 'border-status-error/40 bg-status-error/10 text-status-error' },
  warning: { icon: '⚠', classes: 'border-status-warning/40 bg-status-warning/10 text-status-warning' },
  info:    { icon: 'ℹ', classes: 'border-status-info/40 bg-status-info/10 text-status-info' },
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const addToast = useCallback((type: ToastType, title: string, message?: string) => {
    const id = Math.random().toString(36).slice(2, 9)
    setToasts((prev) => [...prev, { id, type, title, message }])
    setTimeout(() => dismiss(id), 5000)
  }, [dismiss])

  const value: ToastContextValue = {
    toast:   addToast,
    success: (t, m) => addToast('success', t, m),
    error:   (t, m) => addToast('error',   t, m),
    warning: (t, m) => addToast('warning', t, m),
    info:    (t, m) => addToast('info',    t, m),
  }

  return (
    <ToastContext.Provider value={value}>
      {children}
      {/* Toast portal */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none" aria-live="polite">
        {toasts.map((t) => {
          const { icon, classes } = typeConfig[t.type]
          return (
            <div
              key={t.id}
              className={[
                'pointer-events-auto flex items-start gap-3 p-3 rounded-lg border shadow-panel-lg',
                'bg-surface-overlay animate-slide-up min-w-[280px] max-w-[360px]',
                classes,
              ].join(' ')}
            >
              <span className="text-sm font-bold mt-0.5 shrink-0">{icon}</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-ink-primary">{t.title}</p>
                {t.message && <p className="text-xs text-ink-secondary mt-0.5">{t.message}</p>}
              </div>
              <button
                onClick={() => dismiss(t.id)}
                className="text-ink-muted hover:text-ink-primary transition-colors text-sm leading-none shrink-0 mt-0.5"
              >
                ✕
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
