import { InputHTMLAttributes } from 'react'
import { ChevronDown, Search } from 'lucide-react'
import { cn } from '@/lib/utils'
import { CLASSES } from '@/lib/constants'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  className?: string
  showSearchIcon?: boolean
}

export function Input({ className, showSearchIcon = false, ...props }: InputProps) {
  if (showSearchIcon) {
    return (
      <div className="relative flex-1 min-w-[300px]">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 dark:text-slate-500 pointer-events-none" strokeWidth={2.5} />
        <input
          className={cn(CLASSES.input, 'pl-10 w-full', className)}
          {...props}
        />
      </div>
    )
  }

  return (
    <input
      className={cn(CLASSES.input, className)}
      {...props}
    />
  )
}

interface SelectProps extends InputHTMLAttributes<HTMLSelectElement> {
  className?: string
  children: React.ReactNode
}

export function Select({ className, children, ...props }: SelectProps) {
  return (
    <div className={cn("relative inline-block", className)}>
      <select
        className={cn(CLASSES.select, 'appearance-none pr-10 w-full')}
        style={{
          backgroundImage: 'none',
          WebkitAppearance: 'none',
          MozAppearance: 'none',
        }}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 dark:text-slate-400 pointer-events-none"
        strokeWidth={2.5}
      />
    </div>
  )
}
