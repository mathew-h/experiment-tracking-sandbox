/**
 * Brand design tokens — single source of truth.
 * All colors, typography, and spacing reference these values.
 * Components must NOT hardcode hex values — always use these tokens or Tailwind classes.
 */

export const colors = {
  // Primary
  navyBase:    '#05172B',
  navyRaised:  '#0a2440',
  navyOverlay: '#0e3158',
  navyBorder:  '#1a3a5c',
  navyMuted:   '#133355',

  // Accent
  redPrimary:  '#FD4437',
  redDark:     '#d93020',
  redLight:    '#ff6b5e',

  // Text
  inkPrimary:   '#F0F4F8',
  inkSecondary: '#8BACC8',
  inkMuted:     '#4d6e8a',

  // Status
  statusOngoing:   '#22c55e',
  statusCompleted: '#38bdf8',
  statusCancelled: '#6b7280',
  statusWarning:   '#f59e0b',
  statusError:     '#FD4437',
} as const

export const fonts = {
  sans:    "'Inter', system-ui, sans-serif",
  mono:    "'JetBrains Mono', 'Fira Code', monospace",
  display: "'Inter', system-ui, sans-serif",
} as const

export const spacing = {
  sidebarWidth:     '240px',
  headerHeight:     '56px',
  contentMaxWidth:  '1400px',
  cardPadding:      '20px',
  sectionGap:       '24px',
} as const

export const transitions = {
  fast:   '100ms ease-out',
  base:   '200ms ease-out',
  slow:   '300ms cubic-bezier(0.16, 1, 0.3, 1)',
} as const

// Status → Tailwind color class mapping
export const statusColorMap = {
  ONGOING:   { text: 'text-status-ongoing',   bg: 'bg-status-ongoing/10',   dot: 'bg-status-ongoing' },
  COMPLETED: { text: 'text-status-completed', bg: 'bg-status-completed/10', dot: 'bg-status-completed' },
  CANCELLED: { text: 'text-status-cancelled', bg: 'bg-status-cancelled/10', dot: 'bg-status-cancelled' },
} as const
