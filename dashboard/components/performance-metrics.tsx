'use client'

import type { BotMetrics } from '@/lib/types'
import { Clock, TrendingUp, CheckCircle, XCircle, Timer } from 'lucide-react'

interface PerformanceMetricsProps {
  metrics: BotMetrics
}

export default function PerformanceMetrics({ metrics }: PerformanceMetricsProps) {
  const stats = metrics.stats

  // Calculate additional metrics
  const totalFixed = stats.prs_bot_fixed + stats.prs_auto_merged
  const totalProcessed = stats.total_prs_scanned
  const fixRate = totalProcessed > 0 ? (totalFixed / totalProcessed) * 100 : 0

  // Calculate average fix time in hours and format
  const avgFixTimeFormatted = stats.avg_fix_time_hours
    ? stats.avg_fix_time_hours < 1
      ? `${Math.round(stats.avg_fix_time_hours * 60)}m`
      : `${stats.avg_fix_time_hours.toFixed(1)}h`
    : 'N/A'

  const metrics_data = [
    {
      label: 'Overall Success Rate',
      value: `${(stats.success_rate * 100).toFixed(1)}%`,
      description: 'PRs successfully fixed or auto-merged',
      icon: <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />,
      color: 'text-green-600 dark:text-green-400',
      bgColor: 'bg-green-50 dark:bg-green-900/20',
    },
    {
      label: 'Average Fix Time',
      value: avgFixTimeFormatted,
      description: 'Average time to fix a failing PR',
      icon: <Clock className="w-5 h-5 text-blue-600 dark:text-blue-400" />,
      color: 'text-blue-600 dark:text-blue-400',
      bgColor: 'bg-blue-50 dark:bg-blue-900/20',
    },
    {
      label: 'Bot Intervention Rate',
      value: `${((stats.prs_bot_fixed / totalProcessed) * 100).toFixed(1)}%`,
      description: 'PRs requiring bot fixes vs auto-merge',
      icon: <TrendingUp className="w-5 h-5 text-purple-600 dark:text-purple-400" />,
      color: 'text-purple-600 dark:text-purple-400',
      bgColor: 'bg-purple-50 dark:bg-purple-900/20',
    },
    {
      label: 'Failure Rate',
      value: `${((stats.prs_failed / totalProcessed) * 100).toFixed(1)}%`,
      description: 'PRs that bot could not fix',
      icon: <XCircle className="w-5 h-5 text-red-600 dark:text-red-400" />,
      color: 'text-red-600 dark:text-red-400',
      bgColor: 'bg-red-50 dark:bg-red-900/20',
    },
  ]

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-xl font-bold text-gray-900 dark:text-white">
            Performance Metrics
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Bot efficiency and success rates
          </p>
        </div>
        <div className="flex items-center space-x-2 text-sm text-gray-600 dark:text-gray-400">
          <Timer className="w-4 h-4" />
          <span>Last updated: {metrics.snapshot_date}</span>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {metrics_data.map((metric, idx) => (
          <div
            key={idx}
            className={`${metric.bgColor} rounded-lg p-4 border border-current/10`}
          >
            <div className="flex items-start justify-between mb-3">
              <div className={`p-2 rounded-lg ${metric.bgColor}`}>
                {metric.icon}
              </div>
            </div>
            <div>
              <p className="text-xs font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-1">
                {metric.label}
              </p>
              <p className={`text-3xl font-bold ${metric.color} mb-2`}>
                {metric.value}
              </p>
              <p className="text-xs text-gray-600 dark:text-gray-400">
                {metric.description}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Progress Bars */}
      <div className="mt-6 space-y-4">
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              PR Resolution Breakdown
            </span>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {totalProcessed} total PRs
            </span>
          </div>
          <div className="flex h-4 rounded-full overflow-hidden bg-gray-200 dark:bg-gray-700">
            <div
              className="bg-green-500 flex items-center justify-center text-xs text-white font-medium"
              style={{ width: `${(stats.prs_auto_merged / totalProcessed) * 100}%` }}
              title={`Auto-merged: ${stats.prs_auto_merged}`}
            >
              {stats.prs_auto_merged > 0 && stats.prs_auto_merged / totalProcessed > 0.1 && (
                <span className="px-1">{stats.prs_auto_merged}</span>
              )}
            </div>
            <div
              className="bg-purple-500 flex items-center justify-center text-xs text-white font-medium"
              style={{ width: `${(stats.prs_bot_fixed / totalProcessed) * 100}%` }}
              title={`Bot Fixed: ${stats.prs_bot_fixed}`}
            >
              {stats.prs_bot_fixed > 0 && stats.prs_bot_fixed / totalProcessed > 0.1 && (
                <span className="px-1">{stats.prs_bot_fixed}</span>
              )}
            </div>
            <div
              className="bg-red-500 flex items-center justify-center text-xs text-white font-medium"
              style={{ width: `${(stats.prs_failed / totalProcessed) * 100}%` }}
              title={`Failed: ${stats.prs_failed}`}
            >
              {stats.prs_failed > 0 && stats.prs_failed / totalProcessed > 0.1 && (
                <span className="px-1">{stats.prs_failed}</span>
              )}
            </div>
            <div
              className="bg-blue-500 flex items-center justify-center text-xs text-white font-medium"
              style={{ width: `${(stats.prs_open / totalProcessed) * 100}%` }}
              title={`Open: ${stats.prs_open}`}
            >
              {stats.prs_open > 0 && stats.prs_open / totalProcessed > 0.1 && (
                <span className="px-1">{stats.prs_open}</span>
              )}
            </div>
          </div>
          <div className="flex items-center justify-between mt-2 text-xs text-gray-600 dark:text-gray-400">
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-1">
                <div className="w-3 h-3 rounded-full bg-green-500" />
                <span>Auto-merged ({stats.prs_auto_merged})</span>
              </div>
              <div className="flex items-center space-x-1">
                <div className="w-3 h-3 rounded-full bg-purple-500" />
                <span>Bot Fixed ({stats.prs_bot_fixed})</span>
              </div>
              <div className="flex items-center space-x-1">
                <div className="w-3 h-3 rounded-full bg-red-500" />
                <span>Failed ({stats.prs_failed})</span>
              </div>
              <div className="flex items-center space-x-1">
                <div className="w-3 h-3 rounded-full bg-blue-500" />
                <span>Open ({stats.prs_open})</span>
              </div>
            </div>
          </div>
        </div>

        {/* Success Rate Bar */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Overall Success Rate
            </span>
            <span className="text-sm font-bold text-green-600 dark:text-green-400">
              {(stats.success_rate * 100).toFixed(1)}%
            </span>
          </div>
          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3 overflow-hidden">
            <div
              className="bg-gradient-to-r from-green-500 to-green-600 h-3 rounded-full transition-all duration-500 ease-out"
              style={{ width: `${stats.success_rate * 100}%` }}
            />
          </div>
        </div>
      </div>

      {/* Additional Info */}
      <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-center">
          <div>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              {Object.keys(metrics.by_repo).length}
            </p>
            <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
              Repositories Monitored
            </p>
          </div>
          <div>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              {Object.keys(metrics.by_failure_type).length}
            </p>
            <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
              Failure Types Handled
            </p>
          </div>
          <div>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              {fixRate.toFixed(0)}%
            </p>
            <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
              Automation Rate
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
