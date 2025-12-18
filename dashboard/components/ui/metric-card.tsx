import { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface MetricCardProps {
  label: string
  value: string | number
  description?: string
  icon?: ReactNode
  className?: string
  color?: string
  bgColor?: string
}

export function MetricCard({
  label,
  value,
  description,
  icon,
  className,
  color = 'text-gray-900 dark:text-white',
  bgColor = 'bg-gray-50 dark:bg-gray-900/20',
}: MetricCardProps) {
  return (
    <div className={cn(bgColor, 'rounded-lg p-4 border border-current/10', className)}>
      {icon && (
        <div className="flex items-start justify-between mb-3">
          <div className={cn('p-2 rounded-lg', bgColor)}>
            {icon}
          </div>
        </div>
      )}
      <div>
        <p className="text-xs font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-1">
          {label}
        </p>
        <p className={cn('text-3xl font-bold mb-2', color)}>
          {value}
        </p>
        {description && (
          <p className="text-xs text-gray-600 dark:text-gray-400">
            {description}
          </p>
        )}
      </div>
    </div>
  )
}
