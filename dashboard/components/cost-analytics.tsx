'use client'

import { useState } from 'react'
import { DollarSign, TrendingDown, Percent, PieChart } from 'lucide-react'
import type { BotMetrics, PRSummary } from '@/lib/types'
import { Card, CardHeader, CardTitle, CardDescription, MetricCard } from './ui'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { VECTOR_COLORS } from '@/lib/constants'

interface CostAnalyticsProps {
  metrics: BotMetrics
  prSummaries: PRSummary[]
}

interface FailureTypeCost {
  name: string
  cost: number
  count: number
  avgCost: number
  color: string
}

const FAILURE_TYPE_COLORS: Record<string, string> = {
  test: VECTOR_COLORS.violet,
  lint: VECTOR_COLORS.turquoise,
  security: VECTOR_COLORS.magenta,
  build: VECTOR_COLORS.cobalt,
  merge_conflict: '#FF9E00',
  unknown: '#64748b',
}

const FAILURE_TYPE_LABELS: Record<string, string> = {
  test: 'Test Failures',
  lint: 'Linting Issues',
  security: 'Security Audits',
  build: 'Build Failures',
  merge_conflict: 'Merge Conflicts',
  unknown: 'Unknown',
}

export default function CostAnalytics({ metrics, prSummaries }: CostAnalyticsProps) {
  const stats = metrics.stats
  const [hoveredBar, setHoveredBar] = useState<string | null>(null)

  // Prepare cost breakdown by failure type
  const costByFailureType: FailureTypeCost[] = Object.entries(metrics.by_failure_type)
    .map(([type, data]) => ({
      name: FAILURE_TYPE_LABELS[type] || type,
      cost: data.total_cost,
      count: data.count,
      avgCost: data.avg_cost,
      color: FAILURE_TYPE_COLORS[type] || '#64748b',
    }))
    .sort((a, b) => b.cost - a.cost)

  // Format currency - always show 2 decimal places (cents)
  const formatCurrency = (value: number | undefined): string => {
    if (value === undefined || value === null) {
      return '$0.00'
    }
    return `$${value.toFixed(2)}`
  }

  // Calculate percentage of total for each failure type
  const getPercentage = (cost: number): number => {
    return stats.total_cost_usd > 0 ? (cost / stats.total_cost_usd) * 100 : 0
  }

  const metricsData = [
    {
      label: 'Total Cost',
      value: formatCurrency(stats.total_cost_usd),
      description: 'Cumulative cost for all bot attempts',
      icon: <DollarSign className="w-5 h-5" style={{ color: VECTOR_COLORS.magenta }} />,
      color: `text-[${VECTOR_COLORS.magenta}]`,
      bgColor: `bg-[${VECTOR_COLORS.magenta}]/10`,
    },
    {
      label: 'Avg Cost per Attempt',
      value: formatCurrency(stats.avg_cost_per_attempt),
      description: 'Average cost including failed attempts',
      icon: <TrendingDown className="w-5 h-5" style={{ color: VECTOR_COLORS.cobalt }} />,
      color: `text-[${VECTOR_COLORS.cobalt}]`,
      bgColor: `bg-[${VECTOR_COLORS.cobalt}]/10`,
    },
    {
      label: 'Avg Cost per Success',
      value: formatCurrency(stats.avg_cost_per_success),
      description: 'Average cost for successful fixes only',
      icon: <Percent className="w-5 h-5" style={{ color: VECTOR_COLORS.turquoise }} />,
      color: `text-[${VECTOR_COLORS.turquoise}]`,
      bgColor: `bg-[${VECTOR_COLORS.turquoise}]/10`,
    },
    {
      label: 'Fixes Tracked',
      value: prSummaries.filter(pr => pr.type === 'bot_fix' && pr.cost_usd !== null).length,
      description: 'Total attempts with cost data',
      icon: <PieChart className="w-5 h-5" style={{ color: VECTOR_COLORS.violet }} />,
      color: `text-[${VECTOR_COLORS.violet}]`,
      bgColor: `bg-[${VECTOR_COLORS.violet}]/10`,
    },
  ]

  // Chart styling configuration
  const CHART_CONFIG = {
    cartesianGrid: {
      strokeDasharray: '3 3',
      stroke: '#334155',
      opacity: 0.3,
    },
    axis: {
      stroke: '#64748b',
      style: { fontSize: '11px' },
      tickLine: false,
    },
    tooltip: {
      contentStyle: {
        backgroundColor: '#1e293b',
        border: 'none',
        borderRadius: '8px',
        color: '#fff',
        padding: '8px 12px',
      },
      labelStyle: { color: '#94a3b8', marginBottom: '4px' },
    },
  }

  if (stats.total_cost_usd === 0 || costByFailureType.length === 0) {
    return (
      <Card className="rounded-2xl shadow-xl border-2">
        <CardHeader className="flex items-center justify-between mb-4">
          <div>
            <CardTitle className="text-2xl mb-1">Cost</CardTitle>
            <CardDescription>API costs for automated PR fixes</CardDescription>
          </div>
        </CardHeader>
        <div className="h-48 flex items-center justify-center text-gray-500 dark:text-gray-400">
          <div className="text-center">
            <DollarSign className="w-10 h-10 mx-auto mb-3 text-gray-400" />
            <p className="text-sm">No cost data available yet</p>
            <p className="text-xs mt-1">Cost tracking will appear as the bot fixes PRs</p>
          </div>
        </div>
      </Card>
    )
  }

  return (
    <Card className="rounded-2xl shadow-xl border-2">
      <CardHeader className="flex items-center justify-between mb-4">
        <div>
          <CardTitle className="text-2xl mb-1">Cost</CardTitle>
          <CardDescription>API costs for automated PR fixes</CardDescription>
        </div>
      </CardHeader>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
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

      {/* Cost Breakdown by Failure Type */}
      {costByFailureType.length > 0 && (
        <div className="space-y-3">
          <div>
            <h4 className="text-base font-semibold text-gray-900 dark:text-white mb-3">
              Cost Breakdown by Failure Type
            </h4>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={costByFailureType}>
                  <CartesianGrid {...CHART_CONFIG.cartesianGrid} />
                  <XAxis
                    dataKey="name"
                    {...CHART_CONFIG.axis}
                    angle={-35}
                    textAnchor="end"
                    height={60}
                    interval={0}
                  />
                  <YAxis
                    {...CHART_CONFIG.axis}
                    tickFormatter={(value) => `$${value.toFixed(2)}`}
                  />
                  <Tooltip
                    {...CHART_CONFIG.tooltip}
                    formatter={(value: number) => [
                      formatCurrency(value),
                      'Cost'
                    ]}
                    labelFormatter={(label) => {
                      const data = costByFailureType.find(d => d.name === label)
                      return data ? `${label} (${data.count} fixes)` : label
                    }}
                  />
                  <Bar
                    dataKey="cost"
                    radius={[6, 6, 0, 0]}
                    onMouseEnter={(data) => setHoveredBar(data.name)}
                    onMouseLeave={() => setHoveredBar(null)}
                  >
                    {costByFailureType.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={entry.color}
                        opacity={hoveredBar === entry.name || hoveredBar === null ? 1 : 0.6}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Detailed Cost Table */}
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  <th className="text-left py-2 px-3 font-semibold text-gray-700 dark:text-gray-300">
                    Failure Type
                  </th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-700 dark:text-gray-300">
                    Total Cost
                  </th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-700 dark:text-gray-300">
                    Fixes
                  </th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-700 dark:text-gray-300">
                    Avg Cost
                  </th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-700 dark:text-gray-300">
                    % of Total
                  </th>
                </tr>
              </thead>
              <tbody>
                {costByFailureType.map((item, idx) => (
                  <tr
                    key={idx}
                    className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
                  >
                    <td className="py-2 px-3">
                      <div className="flex items-center space-x-2">
                        <div
                          className="w-2 h-2 rounded-full"
                          style={{ backgroundColor: item.color }}
                        />
                        <span className="font-medium text-gray-900 dark:text-white">
                          {item.name}
                        </span>
                      </div>
                    </td>
                    <td className="text-right py-2 px-3 font-mono text-gray-900 dark:text-white">
                      {formatCurrency(item.cost)}
                    </td>
                    <td className="text-right py-2 px-3 text-gray-600 dark:text-gray-400">
                      {item.count}
                    </td>
                    <td className="text-right py-2 px-3 font-mono text-gray-600 dark:text-gray-400">
                      {formatCurrency(item.avgCost)}
                    </td>
                    <td className="text-right py-2 px-3 text-gray-600 dark:text-gray-400">
                      {getPercentage(item.cost).toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="font-semibold bg-gray-50 dark:bg-gray-800/50">
                  <td className="py-2 px-3 text-gray-900 dark:text-white">Total</td>
                  <td className="text-right py-2 px-3 font-mono text-gray-900 dark:text-white">
                    {formatCurrency(stats.total_cost_usd)}
                  </td>
                  <td className="text-right py-2 px-3 text-gray-600 dark:text-gray-400">
                    {costByFailureType.reduce((sum, item) => sum + item.count, 0)}
                  </td>
                  <td className="text-right py-2 px-3 font-mono text-gray-600 dark:text-gray-400">
                    {formatCurrency(stats.avg_cost_per_attempt)}
                  </td>
                  <td className="text-right py-2 px-3 text-gray-600 dark:text-gray-400">
                    100%
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      )}
    </Card>
  )
}
