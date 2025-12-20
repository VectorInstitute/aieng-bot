'use client'

import type { PRSummary } from '@/lib/types'
import { ArrowUpDown, ExternalLink, Clock, GitMerge, GitBranch } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { Input, Select } from './ui'
import { useTableData } from '@/lib/hooks'
import { getRepoName } from '@/lib/utils'
import { CLASSES } from '@/lib/constants'

interface AutoMergeTableProps {
  prSummaries: PRSummary[]
}

type SortField = 'timestamp' | 'repo' | 'was_rebased' | 'rebase_time_seconds'

export default function AutoMergeTable({ prSummaries }: AutoMergeTableProps) {
  // Filter to auto-merge entries only
  const autoMergesOnly = prSummaries.filter(pr => pr.type === 'auto_merge')

  const {
    data: processedData,
    sortField,
    sortDirection,
    searchQuery,
    filters,
    handleSort,
    setSearchQuery,
    setFilter,
    totalCount,
    filteredCount,
  } = useTableData<PRSummary>(autoMergesOnly, {
    initialSortField: 'timestamp',
    initialSortDirection: 'desc',
    searchFields: ['repo', 'title', 'author'],
    filterFields: ['was_rebased'],
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

  const formatRebaseTime = (seconds?: number | null) => {
    if (!seconds) return '-'
    if (seconds < 60) return `${Math.round(seconds)}s`
    return `${Math.round(seconds / 60)}m ${Math.round(seconds % 60)}s`
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
            Rebased
          </label>
          <Select
            value={filters['was_rebased'] !== undefined ? filters['was_rebased'] : 'all'}
            onChange={(e) => setFilter('was_rebased', e.target.value === 'all' ? undefined : e.target.value)}
            className="w-full"
          >
            <option value="all">All</option>
            <option value="true">Rebased</option>
            <option value="false">Not Rebased</option>
          </Select>
        </div>
      </div>

      {/* Results count */}
      <p className="text-sm text-gray-600 dark:text-gray-400">
        Showing {filteredCount} of {totalCount} auto-merged PRs
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
              <th className={CLASSES.tableHeader}>
                Author
              </th>
              <th
                onClick={() => handleSort('was_rebased')}
                className={`${CLASSES.tableHeader} cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800`}
              >
                <div className="flex items-center space-x-1">
                  <span>Rebased</span>
                  <SortIcon field="was_rebased" />
                </div>
              </th>
              <th
                onClick={() => handleSort('rebase_time_seconds')}
                className={`${CLASSES.tableHeader} cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800`}
              >
                <div className="flex items-center space-x-1">
                  <span>Rebase Time</span>
                  <SortIcon field="rebase_time_seconds" />
                </div>
              </th>
              <th
                onClick={() => handleSort('timestamp')}
                className={`${CLASSES.tableHeader} cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800`}
              >
                <div className="flex items-center space-x-1">
                  <span>Merged</span>
                  <SortIcon field="timestamp" />
                </div>
              </th>
              <th className={CLASSES.tableHeader}>
                Links
              </th>
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
            {processedData.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-6 py-12 text-center">
                  <div className="text-gray-500 dark:text-gray-400">
                    No auto-merged PRs found matching your filters
                  </div>
                </td>
              </tr>
            ) : (
              processedData.map((pr) => (
                <tr
                  key={`${pr.repo}-${pr.pr_number}-${pr.timestamp}`}
                  className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                >
                  <td className={CLASSES.tableCell}>
                    <span className="font-medium text-gray-900 dark:text-white">
                      {getRepoName(pr.repo)}
                    </span>
                  </td>
                  <td className={CLASSES.tableCell}>
                    <div className="flex flex-col">
                      <span className="font-mono text-sm text-vector-violet font-semibold">
                        #{pr.pr_number}
                      </span>
                      <span className="text-xs text-gray-600 dark:text-gray-400 truncate max-w-xs" title={pr.title}>
                        {pr.title}
                      </span>
                    </div>
                  </td>
                  <td className={CLASSES.tableCell}>
                    <span className="text-xs px-2 py-1 rounded-full bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 font-medium">
                      {pr.author}
                    </span>
                  </td>
                  <td className={CLASSES.tableCell}>
                    {pr.was_rebased ? (
                      <div className="flex items-center gap-1.5 text-vector-magenta">
                        <GitBranch className="w-4 h-4" />
                        <span className="text-sm font-medium">Yes</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
                        <GitMerge className="w-4 h-4" />
                        <span className="text-sm">No</span>
                      </div>
                    )}
                  </td>
                  <td className={CLASSES.tableCell}>
                    <div className="flex items-center gap-1.5 text-gray-700 dark:text-gray-300">
                      <Clock className="w-3.5 h-3.5" />
                      <span className="text-sm font-mono">
                        {pr.was_rebased ? formatRebaseTime(pr.rebase_time_seconds) : '-'}
                      </span>
                    </div>
                  </td>
                  <td className={CLASSES.tableCell}>
                    <span className="text-xs text-gray-600 dark:text-gray-400">
                      {formatDistanceToNow(new Date(pr.timestamp), { addSuffix: true })}
                    </span>
                  </td>
                  <td className={CLASSES.tableCell}>
                    <div className="flex items-center gap-2">
                      <a
                        href={pr.pr_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-vector-violet hover:text-vector-magenta dark:text-vector-violet dark:hover:text-vector-magenta transition-colors"
                        title="View PR"
                      >
                        PR
                        <ExternalLink className="w-3 h-3" />
                      </a>
                      <a
                        href={pr.workflow_run_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200 transition-colors"
                        title="View workflow run"
                      >
                        Run
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    </div>
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
