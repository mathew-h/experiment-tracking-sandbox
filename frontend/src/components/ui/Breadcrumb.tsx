import { Fragment, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

export interface BreadcrumbItem {
  label: ReactNode
  /** Route of the item; items without one render as plain text. */
  to?: string
  /** Set in the data font, for experiment and run IDs. */
  mono?: boolean
}

interface BreadcrumbProps {
  items: BreadcrumbItem[]
  /** Extra classes on the line, e.g. spacing below it. */
  className?: string
}

/** The page trail above a page title: linked items, then the current page as
 *  text, separated by `›`. Shared by the detail, group and run pages (issue #155). */
export function Breadcrumb({ items, className }: BreadcrumbProps) {
  return (
    <nav aria-label="Breadcrumb">
      <p className={['text-xs text-ink-muted', className].filter(Boolean).join(' ')}>
        {items.map((item, i) => {
          const mono = item.mono ? 'font-mono-data' : ''
          return (
            <Fragment key={i}>
              {i > 0 && <span className="mx-1.5">›</span>}
              {item.to ? (
                <Link to={item.to} className={['hover:text-ink-secondary', mono].filter(Boolean).join(' ')}>
                  {item.label}
                </Link>
              ) : (
                <span className={mono || undefined}>{item.label}</span>
              )}
            </Fragment>
          )
        })}
      </p>
    </nav>
  )
}
