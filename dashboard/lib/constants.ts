/**
 * Central configuration and constants for the dashboard
 */

// Status types and their styling
export const STATUS_TYPES = {
  SUCCESS: {
    label: 'Success',
    bg: 'bg-green-100 dark:bg-green-900/20',
    text: 'text-green-700 dark:text-green-400',
    color: '#22c55e',
  },
  FAILED: {
    label: 'Failed',
    bg: 'bg-red-100 dark:bg-red-900/20',
    text: 'text-red-700 dark:text-red-400',
    color: '#ef4444',
  },
  PARTIAL: {
    label: 'Partial',
    bg: 'bg-yellow-100 dark:bg-yellow-900/20',
    text: 'text-yellow-700 dark:text-yellow-400',
    color: '#eab308',
  },
  IN_PROGRESS: {
    label: 'In Progress',
    bg: 'bg-blue-100 dark:bg-blue-900/20',
    text: 'text-blue-700 dark:text-blue-400',
    color: '#3b82f6',
  },
} as const

// Failure types and their styling
export const FAILURE_TYPES = {
  test: {
    label: 'Test',
    bg: 'bg-purple-100 dark:bg-purple-900/20',
    text: 'text-purple-700 dark:text-purple-400',
    color: '#a855f7',
  },
  lint: {
    label: 'Lint',
    bg: 'bg-blue-100 dark:bg-blue-900/20',
    text: 'text-blue-700 dark:text-blue-400',
    color: '#3b82f6',
  },
  security: {
    label: 'Security',
    bg: 'bg-orange-100 dark:bg-orange-900/20',
    text: 'text-orange-700 dark:text-orange-400',
    color: '#f97316',
  },
  build: {
    label: 'Build',
    bg: 'bg-pink-100 dark:bg-pink-900/20',
    text: 'text-pink-700 dark:text-pink-400',
    color: '#ec4899',
  },
  merge_conflict: {
    label: 'Merge Conflict',
    bg: 'bg-red-100 dark:bg-red-900/20',
    text: 'text-red-700 dark:text-red-400',
    color: '#ef4444',
  },
  unknown: {
    label: 'Unknown',
    bg: 'bg-gray-100 dark:bg-gray-900/20',
    text: 'text-gray-700 dark:text-gray-400',
    color: '#6b7280',
  },
  auto_merge: {
    label: 'Auto-Merge',
    bg: 'bg-teal-100 dark:bg-teal-900/20',
    text: 'text-teal-700 dark:text-teal-400',
    color: '#14b8a6',
  },
} as const

// Vector Institute brand colors
export const VECTOR_COLORS = {
  magenta: '#EB088A',
  black: '#000000',
  grey: '#E9E8E8',
  cobalt: '#313CFF',
  violet: '#8A25C9',
  turquoise: '#48C0D9',
  tangerine: '#FF9E00',
  lime: '#CFF933',
} as const

// Chart colors following Vector brand
export const CHART_COLORS = {
  autoMerged: VECTOR_COLORS.turquoise,
  botFixed: VECTOR_COLORS.violet,
  failed: VECTOR_COLORS.magenta,
  success: '#22c55e',
} as const

// Common CSS class strings for consistency
export const CLASSES = {
  card: 'bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700',
  cardPadding: 'p-6',
  input: 'px-4 py-2.5 border-2 border-slate-200 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:border-vector-violet focus:ring-2 focus:ring-vector-violet/20 transition-all duration-200 shadow-sm hover:border-slate-300 dark:hover:border-slate-500',
  select: 'px-4 py-2.5 border-2 border-slate-200 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-none focus:border-vector-magenta focus:ring-2 focus:ring-vector-magenta/20 transition-all duration-200 shadow-sm hover:border-slate-300 dark:hover:border-slate-500 cursor-pointer',
  button: 'px-4 py-2 rounded-lg font-medium transition-all duration-200',
  buttonPrimary: 'bg-gradient-to-r from-vector-magenta to-vector-violet text-white hover:shadow-lg',
  buttonSecondary: 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white hover:bg-gray-200 dark:hover:bg-gray-600',
  heading: 'text-gray-900 dark:text-white font-bold',
  textMuted: 'text-gray-600 dark:text-gray-400',
  textSmall: 'text-sm',
  textExtraSmall: 'text-xs',
  badge: 'px-2 py-1 text-xs font-medium rounded-full',
  link: 'text-blue-600 dark:text-blue-400 hover:underline',
  divider: 'border-t border-gray-200 dark:border-gray-700',
  hoverRow: 'hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors',
  tableHeader: 'px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider',
  tableCell: 'px-6 py-4 whitespace-nowrap',
} as const

// Gradient classes for Vector branding
export const GRADIENTS = {
  primary: 'bg-gradient-to-r from-vector-magenta via-vector-violet to-vector-cobalt',
  text: 'bg-gradient-to-r from-vector-magenta via-vector-violet to-vector-cobalt bg-clip-text text-transparent',
  accent: 'h-1 bg-gradient-to-r from-vector-magenta via-vector-violet to-vector-cobalt',
} as const

export type StatusType = keyof typeof STATUS_TYPES
export type FailureType = keyof typeof FAILURE_TYPES
