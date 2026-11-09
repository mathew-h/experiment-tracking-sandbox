import type { MouseEvent, ReactNode } from 'react'
import { Link } from 'react-router-dom'

interface SegmentLinkProps {
  /** Experiment ID of the segment or vial; the link goes to its detail page. */
  id: string
  /** Detail-page tab to open, sent as `?tab=` (read by the detail page from issue #162). */
  tab?: string
  /** Text to show in place of the ID, e.g. a replicate label. */
  children?: ReactNode
  /** Muted and struck through, for a vial excluded from the group mean. */
  outlier?: boolean
  /** Keep the surrounding text colour, underlined (inside a badge, issue #158). */
  inherit?: boolean
  /** Layout classes; the colour comes from `outlier`. */
  className?: string
  /** Keep the click from reaching a click-to-edit row around the link (default true). */
  stopPropagation?: boolean
}

const ID_LINK = 'text-red-400 hover:text-red-300'
const OUTLIER_LINK = 'text-ink-muted line-through hover:text-ink-secondary'
const INHERIT_LINK = 'underline decoration-dotted underline-offset-2 hover:opacity-80'

/** An experiment ID that links to its detail page. Every printed experiment ID
 *  with a detail page should be one of these (issue #155). */
export function SegmentLink({
  id,
  tab,
  children,
  outlier = false,
  inherit = false,
  className,
  stopPropagation = true,
}: SegmentLinkProps) {
  const to = `/experiments/${encodeURIComponent(id)}${tab ? `?tab=${encodeURIComponent(tab)}` : ''}`
  const onClick = stopPropagation ? (e: MouseEvent) => e.stopPropagation() : undefined
  return (
    <Link
      to={to}
      onClick={onClick}
      className={['font-mono-data', outlier ? OUTLIER_LINK : inherit ? INHERIT_LINK : ID_LINK, className].filter(Boolean).join(' ')}
    >
      {children ?? id}
    </Link>
  )
}
