import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '@/auth/AuthContext'

interface NavItem {
  path: string
  label: string
  icon: React.ReactNode
  exact?: boolean
}

const navItems: NavItem[] = [
  {
    path: '/',
    label: 'Dashboard',
    exact: true,
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <rect x="1" y="1" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.5"/>
        <rect x="9" y="1" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.5"/>
        <rect x="1" y="9" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.5"/>
        <rect x="9" y="9" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.5"/>
      </svg>
    ),
  },
  {
    path: '/experiments',
    label: 'Experiments',
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M6 1v5.5L3 11.5c-.5 1 .2 2.5 1.5 2.5h7c1.3 0 2-.5 1.5-2.5L10 6.5V1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M5 1h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        <circle cx="7" cy="10" r="1" fill="currentColor"/>
      </svg>
    ),
  },
  {
    path: '/experiments/new',
    label: 'New Experiment',
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M8 5v6M5 8h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    path: '/bulk-uploads',
    label: 'Bulk Uploads',
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M2 11v2a1 1 0 001 1h10a1 1 0 001-1v-2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        <path d="M8 2v8M5 5l3-3 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ),
  },
  {
    path: '/samples',
    label: 'Samples',
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="3" stroke="currentColor" strokeWidth="1.5"/>
        <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2 2"/>
      </svg>
    ),
  },
  {
    path: '/chemicals',
    label: 'Chemicals',
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M5 1h6M6 1v4L3.5 10.5C3 11.5 3 13 4 13.5c.5.25 1 .5 4 .5s3.5-.25 4-.5c1-.5 1-2 .5-3L10 5V1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M4.5 10h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    path: '/analysis',
    label: 'Analysis',
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M1 12L5 8l3 3 3-4 3 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M1 3h14" stroke="currentColor" strokeWidth="1" strokeDasharray="1 2"/>
      </svg>
    ),
  },
]

/** Root app shell: sidebar navigation, top bar, and main content outlet. */
export function AppLayout() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()

  const handleSignOut = async () => {
    await signOut()
    navigate('/login')
  }

  return (
    <div className="flex h-screen overflow-hidden bg-surface-base">
      {/* Sidebar */}
      <aside className="flex flex-col w-[240px] shrink-0 bg-navy-900 border-r border-surface-border">
        {/* Logo */}
        <div className="flex items-center gap-3 px-4 h-14 border-b border-surface-border shrink-0">
          <img src="/logo.png" alt="Addis Energy" className="w-7 h-7 rounded object-contain" />
          <div className="min-w-0">
            <p className="text-xs font-semibold text-ink-primary leading-tight truncate">Addis Energy</p>
            <p className="text-2xs text-ink-muted leading-tight">Lab Tracker</p>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-3 px-2">
          <ul className="flex flex-col gap-0.5">
            {navItems.map((item) => (
              <li key={item.path}>
                <NavLink
                  to={item.path}
                  end={item.exact}
                  className={({ isActive }) => [
                    'flex items-center gap-2.5 px-3 py-2 rounded text-sm transition-all duration-100',
                    isActive
                      ? 'bg-red-500/15 text-ink-primary border-l-2 border-red-500 pl-[10px]'
                      : 'text-ink-secondary hover:text-ink-primary hover:bg-surface-raised border-l-2 border-transparent pl-[10px]',
                  ].join(' ')}
                >
                  <span className="shrink-0">{item.icon}</span>
                  <span className="truncate">{item.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        {/* User / Sign out */}
        <div className="shrink-0 border-t border-surface-border p-3">
          <div className="flex items-center gap-2.5 px-2 py-1.5">
            <div className="w-6 h-6 rounded bg-red-500/20 flex items-center justify-center shrink-0">
              <span className="text-2xs font-bold text-red-400">
                {user?.displayName?.[0]?.toUpperCase() ?? user?.email?.[0]?.toUpperCase() ?? '?'}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-ink-primary truncate">
                {user?.displayName ?? user?.email ?? 'Researcher'}
              </p>
              <p className="text-2xs text-ink-muted truncate">{user?.email}</p>
            </div>
            <button
              onClick={handleSignOut}
              title="Sign out"
              className="text-ink-muted hover:text-ink-primary transition-colors shrink-0"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M5 2H2a1 1 0 00-1 1v8a1 1 0 001 1h3M9 10l3-3-3-3M12 7H5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="h-14 border-b border-surface-border bg-surface-raised/50 backdrop-blur-sm flex items-center px-6 shrink-0">
          <div className="flex-1" />
          {/* Could add global search, notifications here in M5+ */}
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
