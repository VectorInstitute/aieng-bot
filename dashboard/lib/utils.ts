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
 * Format duration in seconds to human-readable format
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return 'N/A'

  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)

  if (hours > 0) {
    const remainingMinutes = minutes % 60
    return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`
  }

  if (minutes > 0) {
    const remainingSeconds = seconds % 60
    return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`
  }

  return `${seconds}s`
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
 * Format percentage with specified decimal places
 */
export function formatPercentage(value: number, decimals: number = 1): string {
  return `${(value * 100).toFixed(decimals)}%`
}

/**
 * Calculate percentage from numerator and denominator
 */
export function calculatePercentage(numerator: number, denominator: number): number {
  if (denominator === 0) return 0
  return (numerator / denominator) * 100
}

/**
 * Truncate text to specified length with ellipsis
 */
export function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength) + '...'
}

/**
 * Extract repository name from full repo path (e.g., "VectorInstitute/repo" -> "repo")
 */
export function getRepoName(fullRepo: string): string {
  return fullRepo.split('/')[1] || fullRepo
}

/**
 * Format status label (e.g., "IN_PROGRESS" -> "In Progress")
 */
export function formatStatusLabel(status: string): string {
  return status.replace(/_/g, ' ')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ')
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

/**
 * Safely divide two numbers, returning 0 if denominator is 0
 */
export function safeDivide(numerator: number, denominator: number): number {
  return denominator === 0 ? 0 : numerator / denominator
}
