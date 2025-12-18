'use client'

import type { BotMetrics } from '@/lib/types'
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

interface MetricsChartsProps {
  metrics: BotMetrics
}

export default function MetricsCharts({ metrics }: MetricsChartsProps) {
  // Prepare data for failure type chart
  const failureTypeData = Object.entries(metrics.by_failure_type).map(([type, data]) => ({
    name: type.charAt(0).toUpperCase() + type.slice(1),
    total: data.count,
    fixed: data.fixed,
    failed: data.failed,
    successRate: (data.success_rate * 100).toFixed(0),
  }))

  // Prepare data for repository chart (top 10)
  const repoData = Object.entries(metrics.by_repo)
    .sort((a, b) => b[1].total_prs - a[1].total_prs)
    .slice(0, 10)
    .map(([repo, data]) => ({
      name: repo.split('/')[1] || repo,
      'Auto-merged': data.auto_merged,
      'Bot Fixed': data.bot_fixed,
      Failed: data.failed,
      total: data.total_prs,
    }))

  // Prepare data for status pie chart - using Vector brand colors
  const statusData = [
    { name: 'Auto-merged', value: metrics.stats.prs_auto_merged, color: '#48C0D9' }, // Vector Turquoise
    { name: 'Bot Fixed', value: metrics.stats.prs_bot_fixed, color: '#8A25C9' }, // Vector Violet
    { name: 'Failed', value: metrics.stats.prs_failed, color: '#EB088A' }, // Vector Magenta
    { name: 'Open', value: metrics.stats.prs_open, color: '#313CFF' }, // Vector Cobalt
  ].filter(item => item.value > 0)

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Failure Type Success Rates */}
      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl border-2 border-slate-200 dark:border-slate-700 p-6">
        <h3 className="text-2xl font-bold text-slate-900 dark:text-white mb-6">
          Fix Success by Failure Type
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={failureTypeData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.3} />
            <XAxis
              dataKey="name"
              stroke="#64748b"
              style={{ fontSize: '11px' }}
              tickLine={false}
            />
            <YAxis
              stroke="#64748b"
              style={{ fontSize: '11px' }}
              tickLine={false}
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: 'none',
                borderRadius: '8px',
                color: '#fff',
                padding: '8px 12px'
              }}
              labelStyle={{ color: '#94a3b8', marginBottom: '4px' }}
            />
            <Legend wrapperStyle={{ fontSize: '12px' }} />
            <Bar dataKey="fixed" fill="#8A25C9" name="Fixed" radius={[4, 4, 0, 0]} />
            <Bar dataKey="failed" fill="#EB088A" name="Failed" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* PR Status Distribution */}
      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl border-2 border-slate-200 dark:border-slate-700 p-6">
        <h3 className="text-2xl font-bold text-slate-900 dark:text-white mb-6">
          PR Status Distribution
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie
              data={statusData}
              cx="50%"
              cy="50%"
              labelLine={false}
              label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              outerRadius={90}
              fill="#8884d8"
              dataKey="value"
              stroke="none"
            >
              {statusData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: 'none',
                borderRadius: '8px',
                color: '#fff',
                padding: '8px 12px'
              }}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="mt-6 grid grid-cols-2 gap-3 text-sm">
          {statusData.map((item) => (
            <div key={item.name} className="flex items-center space-x-2">
              <div
                className="w-4 h-4 rounded-full"
                style={{ backgroundColor: item.color }}
              />
              <span className="text-slate-700 dark:text-slate-300 font-medium">
                {item.name}: {item.value}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Repository Activity (Top 10) */}
      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl border-2 border-slate-200 dark:border-slate-700 p-6 lg:col-span-2">
        <h3 className="text-2xl font-bold text-slate-900 dark:text-white mb-6">
          Top Repositories by PR Activity
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={repoData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.3} />
            <XAxis
              type="number"
              stroke="#64748b"
              style={{ fontSize: '11px' }}
              tickLine={false}
              allowDecimals={false}
            />
            <YAxis
              dataKey="name"
              type="category"
              width={150}
              stroke="#64748b"
              style={{ fontSize: '11px' }}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: 'none',
                borderRadius: '8px',
                color: '#fff',
                padding: '8px 12px'
              }}
              labelStyle={{ color: '#94a3b8', marginBottom: '4px' }}
            />
            <Legend wrapperStyle={{ fontSize: '12px' }} />
            <Bar dataKey="Auto-merged" stackId="a" fill="#48C0D9" radius={[0, 4, 4, 0]} />
            <Bar dataKey="Bot Fixed" stackId="a" fill="#8A25C9" radius={[0, 4, 4, 0]} />
            <Bar dataKey="Failed" stackId="a" fill="#EB088A" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Success Rate by Failure Type Table */}
      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl border-2 border-slate-200 dark:border-slate-700 p-6 lg:col-span-2">
        <h3 className="text-2xl font-bold text-slate-900 dark:text-white mb-6">
          Success Rates by Failure Type
        </h3>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-700">
            <thead className="bg-slate-50 dark:bg-slate-900/50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Failure Type
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Total
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Fixed
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Failed
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Success Rate
                </th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-slate-800 divide-y divide-slate-200 dark:divide-slate-700">
              {failureTypeData.map((item) => (
                <tr key={item.name} className="hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-slate-900 dark:text-white">
                    {item.name}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-600 dark:text-slate-400">
                    {item.total}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium" style={{ color: '#8A25C9' }}>
                    {item.fixed}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium" style={{ color: '#EB088A' }}>
                    {item.failed}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center space-x-2">
                      <div className="flex-1 bg-slate-200 dark:bg-slate-700 rounded-full h-2.5 max-w-[120px]">
                        <div
                          className="h-2.5 rounded-full transition-all duration-300"
                          style={{
                            width: `${item.successRate}%`,
                            background: 'linear-gradient(90deg, #8A25C9 0%, #313CFF 100%)'
                          }}
                        />
                      </div>
                      <span className="text-sm font-semibold text-slate-900 dark:text-white min-w-[45px]">
                        {item.successRate}%
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
