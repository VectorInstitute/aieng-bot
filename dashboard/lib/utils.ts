/**
 * Utility functions for common operations
 */

import { type ClassValue, clsx } from 'clsx'

/**
 * Merge class names using clsx
 */
export function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

/**
 * Format fix time in hours to human-readable format
 */
export function formatFixTime(hours: number | null | undefined): string {
  if (!hours) return 'N/A'

  if (hours < 1) {
    return `${Math.round(hours * 60)}m`
  }

  return `${hours.toFixed(1)}h`
}

/**
 * Extract repository name from full repo path (e.g., "VectorInstitute/repo" -> "repo")
 */
export function getRepoName(fullRepo: string): string {
  return fullRepo.split('/')[1] || fullRepo
}

/**
 * Sort array by field in specified direction
 */
export function sortBy<T>(
  array: T[],
  field: keyof T,
  direction: 'asc' | 'desc' = 'asc'
): T[] {
  return [...array].sort((a, b) => {
    const aVal = a[field]
    const bVal = b[field]

    // Handle null/undefined
    if (aVal == null) return 1
    if (bVal == null) return -1

    // Handle dates
    if (aVal instanceof Date && bVal instanceof Date) {
      const aTime = aVal.getTime()
      const bTime = bVal.getTime()
      if (aTime < bTime) return direction === 'asc' ? -1 : 1
      if (aTime > bTime) return direction === 'asc' ? 1 : -1
      return 0
    }

    if (aVal < bVal) return direction === 'asc' ? -1 : 1
    if (aVal > bVal) return direction === 'asc' ? 1 : -1
    return 0
  })
}

/**
 * Filter array by search query across multiple fields
 */
export function searchFilter<T>(
  items: T[],
  query: string,
  fields: (keyof T)[]
): T[] {
  if (!query) return items

  const lowerQuery = query.toLowerCase()
  return items.filter(item =>
    fields.some(field => {
      const value = item[field]
      return value != null && String(value).toLowerCase().includes(lowerQuery)
    })
  )
}

/**
 * Get unique values from array for a specific field
 */
export function getUniqueValues<T, K extends keyof T>(items: T[], field: K): T[K][] {
  const uniqueSet = new Set(items.map(item => item[field]).filter(Boolean))
  return Array.from(uniqueSet) as T[K][]
}
