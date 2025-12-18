'use client'

import { useState, useMemo } from 'react'
import type { PRSummary } from '@/lib/types'
import { ArrowUpDown, ExternalLink, Clock } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

interface OverviewTableProps {
  prSummaries: PRSummary[]
}

type SortField = 'timestamp' | 'repo' | 'status' | 'failure_type' | 'fix_time_hours'
type SortDirection = 'asc' | 'desc'

export default function OverviewTable({ prSummaries }: OverviewTableProps) {
  const [sortField, setSortField] = useState<SortField>('timestamp')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const [filterStatus, setFilterStatus] = useState<string>('all')
  const [filterType, setFilterType] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState('')

  // Get unique statuses and failure types for filters
  const statuses = useMemo(() => {
    const uniqueStatuses = new Set(prSummaries.map(pr => pr.status))
    return Array.from(uniqueStatuses)
  }, [prSummaries])

  const failureTypes = useMemo(() => {
    const uniqueTypes = new Set(prSummaries.map(pr => pr.failure_type).filter(Boolean))
    return Array.from(uniqueTypes)
  }, [prSummaries])

  // Filter and sort data
  const filteredAndSortedData = useMemo(() => {
    let filtered = prSummaries

    // Apply status filter
    if (filterStatus !== 'all') {
      filtered = filtered.filter(pr => pr.status === filterStatus)
    }

    // Apply failure type filter
    if (filterType !== 'all') {
      filtered = filtered.filter(pr => pr.failure_type === filterType)
    }

    // Apply search query
    if (searchQuery) {
      const query = searchQuery.toLowerCase()
      filtered = filtered.filter(
        pr =>
          pr.repo.toLowerCase().includes(query) ||
          pr.title.toLowerCase().includes(query) ||
          pr.author.toLowerCase().includes(query)
      )
    }

    // Sort
    return filtered.sort((a, b) => {
      let aVal: any = a[sortField]
      let bVal: any = b[sortField]

      if (sortField === 'timestamp') {
        aVal = new Date(aVal).getTime()
        bVal = new Date(bVal).getTime()
      } else if (sortField === 'fix_time_hours') {
        aVal = aVal || 0
        bVal = bVal || 0
      }

      if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1
      if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1
      return 0
    })
  }, [prSummaries, sortField, sortDirection, filterStatus, filterType, searchQuery])

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDirection('desc')
    }
  }

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) {
      return <ArrowUpDown className="w-4 h-4 opacity-30" />
    }
    return (
      <ArrowUpDown
        className={`w-4 h-4 ${sortDirection === 'desc' ? 'rotate-180' : ''} transition-transform`}
      />
    )
  }

  const getStatusBadge = (status: string) => {
    const config = {
      SUCCESS: { bg: 'bg-green-100 dark:bg-green-900/20', text: 'text-green-700 dark:text-green-400' },
      FAILED: { bg: 'bg-red-100 dark:bg-red-900/20', text: 'text-red-700 dark:text-red-400' },
      PARTIAL: { bg: 'bg-yellow-100 dark:bg-yellow-900/20', text: 'text-yellow-700 dark:text-yellow-400' },
      IN_PROGRESS: { bg: 'bg-blue-100 dark:bg-blue-900/20', text: 'text-blue-700 dark:text-blue-400' },
    }

    const style = config[status as keyof typeof config] || config.IN_PROGRESS

    return (
      <span className={`px-2 py-1 text-xs font-medium rounded-full ${style.bg} ${style.text}`}>
        {status.replace('_', ' ')}
      </span>
    )
  }

  const getFailureTypeBadge = (type: string) => {
    const colors = {
      test: 'bg-purple-100 dark:bg-purple-900/20 text-purple-700 dark:text-purple-400',
      lint: 'bg-blue-100 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400',
      security: 'bg-orange-100 dark:bg-orange-900/20 text-orange-700 dark:text-orange-400',
      build: 'bg-pink-100 dark:bg-pink-900/20 text-pink-700 dark:text-pink-400',
      unknown: 'bg-gray-100 dark:bg-gray-900/20 text-gray-700 dark:text-gray-400',
    }

    const color = colors[type as keyof typeof colors] || colors.unknown

    return (
      <span className={`px-2 py-1 text-xs font-medium rounded-full ${color}`}>
        {type}
      </span>
    )
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-4">
        <input
          type="text"
          placeholder="Search repo, title, or author..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="flex-1 min-w-[200px] px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />

        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="all">All Statuses</option>
          {statuses.map(status => (
            <option key={status} value={status}>{status.replace('_', ' ')}</option>
          ))}
        </select>

        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="all">All Failure Types</option>
          {failureTypes.map(type => (
            <option key={type} value={type}>{type}</option>
          ))}
        </select>
      </div>

      {/* Results count */}
      <p className="text-sm text-gray-600 dark:text-gray-400">
        Showing {filteredAndSortedData.length} of {prSummaries.length} PRs
      </p>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-900/50">
            <tr>
              <th
                onClick={() => handleSort('repo')}
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                <div className="flex items-center space-x-1">
                  <span>Repository</span>
                  <SortIcon field="repo" />
                </div>
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                PR
              </th>
              <th
                onClick={() => handleSort('failure_type')}
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                <div className="flex items-center space-x-1">
                  <span>Type</span>
                  <SortIcon field="failure_type" />
                </div>
              </th>
              <th
                onClick={() => handleSort('status')}
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                <div className="flex items-center space-x-1">
                  <span>Status</span>
                  <SortIcon field="status" />
                </div>
              </th>
              <th
                onClick={() => handleSort('fix_time_hours')}
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                <div className="flex items-center space-x-1">
                  <span>Fix Time</span>
                  <SortIcon field="fix_time_hours" />
                </div>
              </th>
              <th
                onClick={() => handleSort('timestamp')}
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                <div className="flex items-center space-x-1">
                  <span>Time</span>
                  <SortIcon field="timestamp" />
                </div>
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
            {filteredAndSortedData.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                  No PRs found matching your filters
                </td>
              </tr>
            ) : (
              filteredAndSortedData.map((pr) => (
                <tr
                  key={`${pr.repo}-${pr.pr_number}`}
                  className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                >
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900 dark:text-white">
                      {pr.repo.split('/')[1] || pr.repo}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 truncate max-w-xs">
                      {pr.title}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <a
                      href={pr.pr_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-blue-600 dark:text-blue-400 hover:underline font-mono"
                    >
                      #{pr.pr_number}
                    </a>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    {getFailureTypeBadge(pr.failure_type)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    {getStatusBadge(pr.status)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
                    {pr.fix_time_hours ? (
                      <div className="flex items-center space-x-1">
                        <Clock className="w-3 h-3" />
                        <span>{pr.fix_time_hours.toFixed(1)}h</span>
                      </div>
                    ) : (
                      <span className="text-gray-400 dark:text-gray-600">-</span>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
                    {formatDistanceToNow(new Date(pr.timestamp), { addSuffix: true })}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <a
                      href={`/aieng-bot-maintain/pr/${encodeURIComponent(pr.repo)}/${pr.pr_number}`}
                      className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 inline-flex items-center space-x-1"
                    >
                      <span>Details</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
