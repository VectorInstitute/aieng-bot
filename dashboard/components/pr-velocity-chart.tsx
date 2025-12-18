'use client'

import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import type { PRSummary } from '@/lib/types'
import { Card, CardTitle } from './ui'
import { VECTOR_COLORS } from '@/lib/constants'

interface PRVelocityChartProps {
  prSummaries: PRSummary[]
}

interface ChartDataPoint {
  date: string
  autoMerged: number
  botFixed: number
  total: number
}

function aggregateByDate(prSummaries: PRSummary[]): ChartDataPoint[] {
  // Group PRs by date (YYYY-MM-DD format for proper sorting)
  const dataByDate = new Map<string, { autoMerged: number; botFixed: number; timestamp: number }>()

  prSummaries.forEach(pr => {
    const dateObj = new Date(pr.timestamp)
    const dateKey = dateObj.toISOString().split('T')[0] // YYYY-MM-DD format

    if (!dataByDate.has(dateKey)) {
      dataByDate.set(dateKey, { autoMerged: 0, botFixed: 0, timestamp: dateObj.getTime() })
    }

    const data = dataByDate.get(dateKey)!
    if (pr.failure_type === 'auto_merge' && pr.status === 'SUCCESS') {
      data.autoMerged++
    } else if (pr.status === 'SUCCESS') {
      data.botFixed++
    }
  })

  // Convert to array, sort chronologically, and format dates for display
  const sortedData = Array.from(dataByDate.entries())
    .sort((a, b) => a[1].timestamp - b[1].timestamp)
    .map(([dateKey, counts]) => ({
      date: new Date(dateKey).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      autoMerged: counts.autoMerged,
      botFixed: counts.botFixed,
      total: counts.autoMerged + counts.botFixed,
    }))

  return sortedData
}

function calculateYAxisDomain(data: ChartDataPoint[]): [number, number] {
  if (data.length === 0) return [0, 10]

  const maxValue = Math.max(...data.map(d => d.total))

  // Add 20% padding to max value
  const paddedMax = Math.ceil(maxValue * 1.2)

  // Round up to nearest nice number
  const roundToNice = (num: number): number => {
    if (num <= 10) return 10
    if (num <= 20) return 20
    if (num <= 50) return Math.ceil(num / 5) * 5
    if (num <= 100) return Math.ceil(num / 10) * 10
    return Math.ceil(num / 20) * 20
  }

  return [0, roundToNice(paddedMax)]
}

function shouldShowXAxisLabel(index: number, totalPoints: number): boolean {
  // Show labels intelligently based on data density
  if (totalPoints <= 7) return true // Show all for a week or less
  if (totalPoints <= 14) return index % 2 === 0 // Every 2nd day
  if (totalPoints <= 30) return index % 3 === 0 // Every 3rd day
  if (totalPoints <= 45) return index % 5 === 0 // Every 5th day
  return index % 7 === 0 // Every 7th day (weekly)
}

export default function PRVelocityChart({ prSummaries }: PRVelocityChartProps) {
  const chartData = aggregateByDate(prSummaries)
  const yAxisDomain = calculateYAxisDomain(chartData)

  // Chart styling configuration matching engagement chart
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
    legend: {
      wrapperStyle: { fontSize: '12px' },
    },
  }

  if (chartData.length === 0) {
    return (
      <Card className="rounded-2xl shadow-xl border-2">
        <CardTitle className="text-2xl mb-2">Maintenance Velocity</CardTitle>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
          Track PRs processed over time
        </p>
        <div className="h-80 flex items-center justify-center text-gray-500 dark:text-gray-400">
          No data available yet
        </div>
      </Card>
    )
  }

  return (
    <Card className="rounded-2xl shadow-xl border-2">
      <CardTitle className="text-2xl mb-2">Maintenance Velocity</CardTitle>
      <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
        Track PRs auto-merged and fixed over time
      </p>

      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="colorAutoMerged" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={VECTOR_COLORS.turquoise} stopOpacity={0.8} />
                <stop offset="95%" stopColor={VECTOR_COLORS.turquoise} stopOpacity={0.1} />
              </linearGradient>
              <linearGradient id="colorBotFixed" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={VECTOR_COLORS.violet} stopOpacity={0.8} />
                <stop offset="95%" stopColor={VECTOR_COLORS.violet} stopOpacity={0.1} />
              </linearGradient>
            </defs>
            <CartesianGrid {...CHART_CONFIG.cartesianGrid} />
            <XAxis
              dataKey="date"
              {...CHART_CONFIG.axis}
              interval="preserveStartEnd"
              tick={(props) => {
                const { x, y, payload, index } = props
                if (
                  index === 0 ||
                  index === chartData.length - 1 ||
                  shouldShowXAxisLabel(index, chartData.length)
                ) {
                  return (
                    <text x={x} y={y + 10} fill="#64748b" fontSize="11px" textAnchor="middle">
                      {payload.value}
                    </text>
                  )
                }
                return null
              }}
            />
            <YAxis
              {...CHART_CONFIG.axis}
              domain={yAxisDomain}
              allowDecimals={false}
              tickCount={6}
            />
            <Tooltip {...CHART_CONFIG.tooltip} />
            <Legend {...CHART_CONFIG.legend} />
            <Area
              type="monotone"
              dataKey="autoMerged"
              stackId="1"
              stroke={VECTOR_COLORS.turquoise}
              strokeWidth={2}
              fill="url(#colorAutoMerged)"
              name="Auto-merged"
            />
            <Area
              type="monotone"
              dataKey="botFixed"
              stackId="1"
              stroke={VECTOR_COLORS.violet}
              strokeWidth={2}
              fill="url(#colorBotFixed)"
              name="Bot Fixed"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}
