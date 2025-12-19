'use client'

import type { PRSummary } from '@/lib/types'
import { ArrowUpDown, ExternalLink, Clock } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { Input, Select, StatusBadge, FailureTypeBadge } from './ui'
import { useTableData } from '@/lib/hooks'
import { getRepoName, formatFixTime } from '@/lib/utils'
import { CLASSES } from '@/lib/constants'

interface OverviewTableProps {
  prSummaries: PRSummary[]
}

type SortField = 'timestamp' | 'repo' | 'status' | 'failure_type' | 'fix_time_hours'

export default function OverviewTable({ prSummaries }: OverviewTableProps) {
  // Filter out auto-merge entries since they don't involve agent fixes
  const botFixesOnly = prSummaries.filter(pr => pr.failure_type !== 'auto_merge')

  const {
    data: processedData,
    sortField,
    sortDirection,
    searchQuery,
    filters,
    filterOptions,
    handleSort,
    setSearchQuery,
    setFilter,
    totalCount,
    filteredCount,
  } = useTableData<PRSummary>(botFixesOnly, {
    initialSortField: 'timestamp',
    initialSortDirection: 'desc',
    searchFields: ['repo', 'title', 'author'],
    filterFields: ['status', 'failure_type'],
  })

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

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-4 items-end">
        <Input
          type="text"
          placeholder="Search repo, title, or author..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          showSearchIcon={true}
        />

        <div className="flex flex-col gap-1.5 min-w-[180px]">
          <label className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wide px-1">
            Status
          </label>
          <Select
            value={filters['status'] || 'all'}
            onChange={(e) => setFilter('status', e.target.value)}
            className="w-full"
          >
            <option value="all">All Statuses</option>
            {(filterOptions['status'] as string[] | undefined)?.map((status) => (
              <option key={status} value={status}>
                {status.replace('_', ' ')}
              </option>
            ))}
          </Select>
        </div>

        <div className="flex flex-col gap-1.5 min-w-[200px]">
          <label className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wide px-1">
            Failure Type
          </label>
          <Select
            value={filters['failure_type'] || 'all'}
            onChange={(e) => setFilter('failure_type', e.target.value)}
            className="w-full"
          >
            <option value="all">All Failure Types</option>
            {(filterOptions['failure_type'] as string[] | undefined)?.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {/* Results count */}
      <p className="text-sm text-gray-600 dark:text-gray-400">
        Showing {filteredCount} of {totalCount} PRs
      </p>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-900/50">
            <tr>
              <th
                onClick={() => handleSort('repo')}
                className={`${CLASSES.tableHeader} cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800`}
              >
                <div className="flex items-center space-x-1">
                  <span>Repository</span>
                  <SortIcon field="repo" />
                </div>
              </th>
              <th className={CLASSES.tableHeader}>
                PR
              </th>
              <th
                onClick={() => handleSort('failure_type')}
                className={`${CLASSES.tableHeader} cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800`}
              >
                <div className="flex items-center space-x-1">
                  <span>Type</span>
                  <SortIcon field="failure_type" />
                </div>
              </th>
              <th
                onClick={() => handleSort('status')}
                className={`${CLASSES.tableHeader} cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800`}
              >
                <div className="flex items-center space-x-1">
                  <span>Status</span>
                  <SortIcon field="status" />
                </div>
              </th>
              <th
                onClick={() => handleSort('fix_time_hours')}
                className={`${CLASSES.tableHeader} cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800`}
              >
                <div className="flex items-center space-x-1">
                  <span>Fix Time</span>
                  <SortIcon field="fix_time_hours" />
                </div>
              </th>
              <th
                onClick={() => handleSort('timestamp')}
                className={`${CLASSES.tableHeader} cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800`}
              >
                <div className="flex items-center space-x-1">
                  <span>Time</span>
                  <SortIcon field="timestamp" />
                </div>
              </th>
              <th className={`${CLASSES.tableHeader} text-right`}>
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
            {processedData.length === 0 ? (
              <tr>
                <td colSpan={7} className={`${CLASSES.tableCell} py-12 text-center text-gray-500 dark:text-gray-400`}>
                  No PRs found matching your filters
                </td>
              </tr>
            ) : (
              processedData.map((pr) => (
                <tr
                  key={`${pr.repo}-${pr.pr_number}`}
                  className={CLASSES.hoverRow}
                >
                  <td className={CLASSES.tableCell}>
                    <div className="text-sm font-medium text-gray-900 dark:text-white">
                      {getRepoName(pr.repo)}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 truncate max-w-xs">
                      {pr.title}
                    </div>
                  </td>
                  <td className={CLASSES.tableCell}>
                    <a
                      href={pr.pr_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={`text-sm ${CLASSES.link} font-mono`}
                    >
                      #{pr.pr_number}
                    </a>
                  </td>
                  <td className={CLASSES.tableCell}>
                    <FailureTypeBadge type={pr.failure_type} />
                  </td>
                  <td className={CLASSES.tableCell}>
                    <StatusBadge status={pr.status} />
                  </td>
                  <td className={`${CLASSES.tableCell} text-sm text-gray-600 dark:text-gray-400`}>
                    {pr.fix_time_hours ? (
                      <div className="flex items-center space-x-1">
                        <Clock className="w-3 h-3" />
                        <span>{formatFixTime(pr.fix_time_hours)}</span>
                      </div>
                    ) : (
                      <span className="text-gray-400 dark:text-gray-600">-</span>
                    )}
                  </td>
                  <td className={`${CLASSES.tableCell} text-sm text-gray-600 dark:text-gray-400`}>
                    {formatDistanceToNow(new Date(pr.timestamp), { addSuffix: true })}
                  </td>
                  <td className={`${CLASSES.tableCell} text-right text-sm font-medium`}>
                    <a
                      href={`/aieng-bot-maintain/pr/${encodeURIComponent(pr.repo)}/${pr.pr_number}`}
                      className={`${CLASSES.link} hover:text-blue-800 dark:hover:text-blue-300 inline-flex items-center space-x-1`}
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
