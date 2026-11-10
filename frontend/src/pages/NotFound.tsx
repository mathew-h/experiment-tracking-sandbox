import { Link, useLocation } from 'react-router-dom'
import { Breadcrumb } from '@/components/ui'

const START_PAGES = [
  { label: 'Dashboard', to: '/' },
  { label: 'Experiments', to: '/experiments' },
  { label: 'HPHT', to: '/hpht' },
  { label: 'Core Floods', to: '/core-floods' },
] as const

/** Shown for any URL no route matches (issue #159). It used to redirect to the
 *  dashboard silently, so a typo or stale bookmark gave no hint what went wrong. */
export function NotFoundPage() {
  const { pathname, search } = useLocation()
  return (
    <div className="space-y-4">
      <Breadcrumb items={[{ label: 'Not found' }]} />
      <div className="space-y-2">
        <h1 className="text-lg font-semibold text-ink-primary">Page not found</h1>
        <p className="text-sm text-ink-secondary">
          Nothing lives at <span className="font-mono-data text-ink-primary">{pathname + search}</span>.
        </p>
      </div>
      <nav aria-label="Start pages" className="flex flex-wrap gap-4 text-sm">
        {START_PAGES.map((page) => (
          <Link key={page.to} to={page.to} className="text-red-400 hover:text-red-300">
            {page.label}
          </Link>
        ))}
      </nav>
    </div>
  )
}
