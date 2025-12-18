import { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { STATUS_TYPES, FAILURE_TYPES, CLASSES, StatusType, FailureType } from '@/lib/constants'

interface BadgeProps {
  children: ReactNode
  className?: string
  variant?: 'default' | 'success' | 'error' | 'warning' | 'info'
}

export function Badge({ children, className, variant = 'default' }: BadgeProps) {
  const variantClasses = {
    default: 'bg-gray-100 dark:bg-gray-900/20 text-gray-700 dark:text-gray-400',
    success: 'bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400',
    error: 'bg-red-100 dark:bg-red-900/20 text-red-700 dark:text-red-400',
    warning: 'bg-yellow-100 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400',
    info: 'bg-blue-100 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400',
  }

  return (
    <span className={cn(CLASSES.badge, variantClasses[variant], className)}>
      {children}
    </span>
  )
}

interface StatusBadgeProps {
  status: string
  className?: string
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const statusKey = status as StatusType
  const config = STATUS_TYPES[statusKey]

  if (!config) {
    return (
      <Badge variant="default" className={className}>
        {status}
      </Badge>
    )
  }

  return (
    <span className={cn(CLASSES.badge, config.bg, config.text, className)}>
      {config.label}
    </span>
  )
}

interface FailureTypeBadgeProps {
  type: string
  className?: string
}

export function FailureTypeBadge({ type, className }: FailureTypeBadgeProps) {
  const typeKey = type as FailureType
  const config = FAILURE_TYPES[typeKey]

  if (!config) {
    return (
      <Badge variant="default" className={className}>
        {type}
      </Badge>
    )
  }

  return (
    <span className={cn(CLASSES.badge, config.bg, config.text, className)}>
      {config.label}
    </span>
  )
}
