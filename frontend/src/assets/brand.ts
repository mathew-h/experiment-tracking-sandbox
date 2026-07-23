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
  statusQueued:    '#f59e0b',
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
  QUEUED:    { text: 'text-status-queued',    bg: 'bg-status-queued/10',    dot: 'bg-status-queued' },
} as const

/**
 * Chart series tokens (issue #70). Validated with the dataviz six-check
 * palette validator on surface #05172B (dark): lightness band, chroma,
 * CVD separation (worst adjacent dE 10.8), normal-vision floor, contrast
 * all PASS for the order [mean, ...series]. Assign by entity in fixed
 * order (replicate 0 -> series[0], a -> series[1], ...); never cycle hues.
 */
export const chartColors = {
  mean: colors.redPrimary,           // #FD4437 — the aggregate/mean series
  series: ['#0284c7', '#b45309', '#8b5cf6', '#059669'],
  grid: colors.navyBorder,           // recessive gridlines
  axis: colors.inkMuted,             // axis lines + ticks
  label: colors.inkSecondary,        // axis/legend text
} as const
