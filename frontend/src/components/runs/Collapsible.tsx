import { useState, type ReactNode } from 'react'
import { Card } from '@/components/ui'

interface Props {
  title: string
  summary?: ReactNode
  /** Links shown after the summary, outside the toggle button (a link may not sit
   *  inside a button). Clicking the rest of the header still toggles (issue #158). */
  links?: ReactNode
  defaultOpen?: boolean
  /** Controlled mode: pass `open` with `onOpenChange`. */
  open?: boolean
  onOpenChange?: (open: boolean) => void
  children: ReactNode
}

const BUTTON = 'flex items-center gap-3 py-3 text-left'

/** A card section with a button header; children are unmounted while closed. */
export function Collapsible({ title, summary, links, defaultOpen = false, open, onOpenChange, children }: Props) {
  const [inner, setInner] = useState(defaultOpen)
  const isOpen = open ?? inner
  const toggle = () => {
    const next = !isOpen
    if (open === undefined) setInner(next)
    onOpenChange?.(next)
  }
  const label = (
    <>
      <span className="text-xs text-ink-muted" aria-hidden="true">{isOpen ? '▾' : '▸'}</span>
      <span className="text-xs font-semibold text-ink-secondary uppercase tracking-wider">{title}</span>
      {summary != null && <span className="text-xs text-ink-muted">{summary}</span>}
    </>
  )
  return (
    <Card padding="none">
      {links == null ? (
        <button type="button" aria-expanded={isOpen} onClick={toggle} className={`${BUTTON} w-full px-4`}>
          {label}
        </button>
      ) : (
        // The row takes the click so the space around the links still toggles; the
        // button has no handler of its own (its click, or Enter/Space, bubbles here),
        // and SegmentLink stops propagation so following a link never toggles.
        <div className="flex items-center cursor-pointer pr-4" onClick={toggle}>
          <button type="button" aria-expanded={isOpen} className={`${BUTTON} pl-4`}>
            {label}
          </button>
          <span className="ml-1 text-xs text-ink-muted">{links}</span>
          <span className="flex-1 self-stretch" aria-hidden="true" />
        </div>
      )}
      {isOpen && (
        <div role="region" aria-label={title} className="p-4 border-t border-surface-border">
          {children}
        </div>
      )}
    </Card>
  )
}
