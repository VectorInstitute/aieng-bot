'use client'

import { useState } from 'react'
import type { BotMetrics } from '@/lib/types'
import { Clock, TrendingUp, CheckCircle, Timer } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardDescription, MetricCard } from './ui'
import { formatFixTime } from '@/lib/utils'

interface PerformanceMetricsProps {
  metrics: BotMetrics
}

export default function PerformanceMetrics({ metrics }: PerformanceMetricsProps) {
  const stats = metrics.stats
  const totalProcessed = stats.total_prs_scanned
  const [hoveredSegment, setHoveredSegment] = useState<string | null>(null)

  const metricsData = [
    {
      label: 'Total PRs Scanned',
      value: totalProcessed,
      description: 'All PRs monitored by the bot',
      icon: <CheckCircle className="w-5 h-5" style={{ color: '#313CFF' }} />,
      color: 'text-[#313CFF]',
      bgColor: 'bg-[#313CFF]/10',
    },
    {
      label: 'Auto-Merged',
      value: stats.prs_auto_merged,
      description: 'PRs that passed without intervention',
      icon: <CheckCircle className="w-5 h-5" style={{ color: '#48C0D9' }} />,
      color: 'text-[#48C0D9]',
      bgColor: 'bg-[#48C0D9]/10',
    },
    {
      label: 'Bot Fixed',
      value: stats.prs_bot_fixed,
      description: 'PRs successfully fixed by the bot',
      icon: <TrendingUp className="w-5 h-5" style={{ color: '#8A25C9' }} />,
      color: 'text-[#8A25C9]',
      bgColor: 'bg-[#8A25C9]/10',
    },
    {
      label: 'Average Fix Time',
      value: formatFixTime(stats.avg_fix_time_hours),
      description: 'Average time to fix a failing PR',
      icon: <Clock className="w-5 h-5" style={{ color: '#FF9E00' }} />,
      color: 'text-[#FF9E00]',
      bgColor: 'bg-[#FF9E00]/10',
    },
  ]

  return (
    <Card>
      <CardHeader className="flex items-center justify-between mb-6">
        <div>
          <CardTitle>Performance Metrics</CardTitle>
          <CardDescription>Bot efficiency and success rates</CardDescription>
        </div>
        <div className="flex items-center space-x-2 text-sm text-gray-600 dark:text-gray-400">
          <Timer className="w-4 h-4" />
          <span>
            Last updated: {new Date(metrics.snapshot_date).toLocaleDateString('en-US', {
              month: 'short',
              day: 'numeric',
              year: 'numeric',
              hour: 'numeric',
              minute: '2-digit',
              hour12: true
            })}
          </span>
        </div>
      </CardHeader>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {metricsData.map((metric, idx) => (
          <MetricCard
            key={idx}
            label={metric.label}
            value={metric.value}
            description={metric.description}
            icon={metric.icon}
            color={metric.color}
            bgColor={metric.bgColor}
          />
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
          <div className="relative">
            <div className="flex h-4 rounded-full bg-gray-200 dark:bg-gray-700" style={{ overflow: 'hidden' }}>
              {stats.prs_auto_merged > 0 && (
                <div
                  className="relative flex items-center justify-center text-xs text-white font-medium transition-all hover:opacity-90 cursor-pointer"
                  style={{
                    width: `${(stats.prs_auto_merged / totalProcessed) * 100}%`,
                    backgroundColor: '#48C0D9'
                  }}
                  onMouseEnter={() => setHoveredSegment('auto_merged')}
                  onMouseLeave={() => setHoveredSegment(null)}
                >
                  {stats.prs_auto_merged / totalProcessed > 0.1 && (
                    <span className="px-1">{stats.prs_auto_merged}</span>
                  )}
                </div>
              )}
              {stats.prs_bot_fixed > 0 && (
                <div
                  className="relative flex items-center justify-center text-xs text-white font-medium transition-all hover:opacity-90 cursor-pointer"
                  style={{
                    width: `${(stats.prs_bot_fixed / totalProcessed) * 100}%`,
                    backgroundColor: '#8A25C9'
                  }}
                  onMouseEnter={() => setHoveredSegment('bot_fixed')}
                  onMouseLeave={() => setHoveredSegment(null)}
                >
                  {stats.prs_bot_fixed / totalProcessed > 0.1 && (
                    <span className="px-1">{stats.prs_bot_fixed}</span>
                  )}
                </div>
              )}
              {stats.prs_failed > 0 && (
                <div
                  className="relative flex items-center justify-center text-xs text-white font-medium transition-all hover:opacity-90 cursor-pointer"
                  style={{
                    width: `${(stats.prs_failed / totalProcessed) * 100}%`,
                    backgroundColor: '#EB088A'
                  }}
                  onMouseEnter={() => setHoveredSegment('failed')}
                  onMouseLeave={() => setHoveredSegment(null)}
                >
                  {stats.prs_failed / totalProcessed > 0.1 && (
                    <span className="px-1">{stats.prs_failed}</span>
                  )}
                </div>
              )}
            </div>

            {/* Tooltip positioned outside the overflow:hidden container */}
            {hoveredSegment && (
              <div className="absolute -top-12 left-1/2 transform -translate-x-1/2 z-50 pointer-events-none">
                <div className="bg-slate-900 dark:bg-slate-700 text-white text-xs rounded-lg px-3 py-2 shadow-xl whitespace-nowrap">
                  <div className="font-semibold">
                    {hoveredSegment === 'auto_merged' && `Auto-merged: ${stats.prs_auto_merged} PRs (${((stats.prs_auto_merged / totalProcessed) * 100).toFixed(1)}%)`}
                    {hoveredSegment === 'bot_fixed' && `Bot Fixed: ${stats.prs_bot_fixed} PRs (${((stats.prs_bot_fixed / totalProcessed) * 100).toFixed(1)}%)`}
                    {hoveredSegment === 'failed' && `Failed: ${stats.prs_failed} PRs (${((stats.prs_failed / totalProcessed) * 100).toFixed(1)}%)`}
                  </div>
                  {/* Tooltip arrow */}
                  <div className="absolute top-full -mt-1 left-1/2 transform -translate-x-1/2">
                    <div className="border-4 border-transparent border-t-slate-900 dark:border-t-slate-700"></div>
                  </div>
                </div>
              </div>
            )}
          </div>
          <div className="flex items-center justify-between mt-2 text-xs text-gray-600 dark:text-gray-400">
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-1">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: '#48C0D9' }} />
                <span>Auto-merged ({stats.prs_auto_merged})</span>
              </div>
              <div className="flex items-center space-x-1">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: '#8A25C9' }} />
                <span>Bot Fixed ({stats.prs_bot_fixed})</span>
              </div>
              <div className="flex items-center space-x-1">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: '#EB088A' }} />
                <span>Failed ({stats.prs_failed})</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Additional Info */}
      <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-center">
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
              {stats.prs_failed}
            </p>
            <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
              Failed PRs Needing Attention
            </p>
          </div>
        </div>
      </div>
    </Card>
  )
}
