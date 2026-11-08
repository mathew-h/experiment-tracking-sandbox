import { useState, type ReactNode } from 'react'
import { Card } from '@/components/ui'

interface Props {
  title: string
  summary?: ReactNode
  defaultOpen?: boolean
  /** Controlled mode: pass `open` with `onOpenChange`. */
  open?: boolean
  onOpenChange?: (open: boolean) => void
  children: ReactNode
}

/** A card section with a button header; children are unmounted while closed. */
export function Collapsible({ title, summary, defaultOpen = false, open, onOpenChange, children }: Props) {
  const [inner, setInner] = useState(defaultOpen)
  const isOpen = open ?? inner
  const toggle = () => {
    const next = !isOpen
    if (open === undefined) setInner(next)
    onOpenChange?.(next)
  }
  return (
    <Card padding="none">
      <button
        type="button"
        aria-expanded={isOpen}
        onClick={toggle}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <span className="text-xs text-ink-muted" aria-hidden="true">{isOpen ? '▾' : '▸'}</span>
        <span className="text-xs font-semibold text-ink-secondary uppercase tracking-wider">{title}</span>
        {summary != null && <span className="text-xs text-ink-muted">{summary}</span>}
      </button>
      {isOpen && (
        <div role="region" aria-label={title} className="p-4 border-t border-surface-border">
          {children}
        </div>
      )}
    </Card>
  )
}
