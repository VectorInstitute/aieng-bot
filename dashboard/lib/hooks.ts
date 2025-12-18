/**
 * Custom React hooks for common dashboard functionality
 */

import { useState, useMemo } from 'react'
import { searchFilter, sortBy, getUniqueValues } from './utils'

type SortDirection = 'asc' | 'desc'

/**
 * Hook for managing sortable and filterable table data
 */
export function useTableData<T extends Record<string, unknown>>(
  data: T[],
  config: {
    initialSortField: keyof T
    initialSortDirection?: SortDirection
    searchFields?: (keyof T)[]
    filterFields?: (keyof T)[]
  }
) {
  const {
    initialSortField,
    initialSortDirection = 'desc',
    searchFields = [],
    filterFields = [],
  } = config

  const [sortField, setSortField] = useState<keyof T>(initialSortField)
  const [sortDirection, setSortDirection] = useState<SortDirection>(initialSortDirection)
  const [searchQuery, setSearchQuery] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})

  // Get unique values for each filter field
  const filterOptions = useMemo(() => {
    const options: Record<string, T[keyof T][]> = {}
    filterFields.forEach(field => {
      options[field as string] = getUniqueValues(data, field)
    })
    return options
  }, [data, filterFields])

  // Apply filters, search, and sorting
  const processedData = useMemo(() => {
    let result = data

    // Apply field-specific filters
    Object.entries(filters).forEach(([field, value]) => {
      if (value !== 'all') {
        result = result.filter(item => item[field] === value)
      }
    })

    // Apply search filter
    if (searchQuery && searchFields.length > 0) {
      result = searchFilter(result, searchQuery, searchFields)
    }

    // Apply sorting
    result = sortBy(result, sortField, sortDirection)

    return result
  }, [data, filters, searchQuery, sortField, sortDirection, searchFields])

  const handleSort = (field: keyof T) => {
    if (sortField === field) {
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDirection('desc')
    }
  }

  const setFilter = (field: string, value: string) => {
    setFilters(prev => ({ ...prev, [field]: value }))
  }

  return {
    data: processedData,
    sortField,
    sortDirection,
    searchQuery,
    filters,
    filterOptions,
    handleSort,
    setSearchQuery,
    setFilter,
    totalCount: data.length,
    filteredCount: processedData.length,
  }
}
