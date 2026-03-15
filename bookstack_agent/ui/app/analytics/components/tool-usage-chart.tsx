'use client'

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import type { BookstackMetrics } from '@/lib/bookstack-types'

const TOOL_LABELS: Record<string, string> = {
  search_bookstack: 'Search',
  get_page: 'Read Page',
  list_books: 'List Books',
}

const TOOL_COLORS: Record<string, string> = {
  search_bookstack: '#8A25C9',
  get_page: '#313CFF',
  list_books: '#EB088A',
}

const TOOL_DESC: Record<string, string> = {
  search_bookstack: 'Full-text search across all books & pages',
  get_page: 'Fetch full page markdown by ID',
  list_books: 'List all available books',
}

export default function ToolUsageChart({ metrics }: { metrics: BookstackMetrics }) {
  const data = Object.entries(metrics.tool_usage).map(([tool, count]) => ({
    tool,
    label: TOOL_LABELS[tool] ?? tool,
    count,
    color: TOOL_COLORS[tool] ?? '#8A25C9',
  }))

  const total = data.reduce((s, d) => s + d.count, 0)

  return (
    <div className="rounded-xl border border-white/10 bg-slate-800/60 p-6">
      <div className="mb-6">
        <h2 className="text-xl font-bold text-white">Tool Usage</h2>
        <p className="text-sm text-slate-400 mt-0.5">
          {total.toLocaleString()} total calls across all queries
        </p>
      </div>

      {/* Full-width horizontal layout: bar chart left, breakdown cards right */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-center">
        {/* Bar chart */}
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.4} />
              <XAxis
                dataKey="label"
                stroke="#64748b"
                tick={{ fill: '#94a3b8', fontSize: 12 }}
                tickLine={false}
              />
              <YAxis
                stroke="#64748b"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                tickLine={false}
                allowDecimals={false}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: 'none',
                  borderRadius: '8px',
                  color: '#fff',
                }}
                labelStyle={{ color: '#94a3b8' }}
                cursor={{ fill: 'rgba(255,255,255,0.05)' }}
              />
              <Bar dataKey="count" name="Calls" radius={[4, 4, 0, 0]}>
                {data.map((entry) => (
                  <Cell key={entry.tool} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Breakdown cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {data.map((entry) => {
            const pct = total > 0 ? Math.round((entry.count / total) * 100) : 0
            return (
              <div
                key={entry.tool}
                className="rounded-lg border border-white/10 bg-slate-700/40 p-4"
              >
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className="inline-block w-2.5 h-2.5 rounded-full shrink-0"
                    style={{ backgroundColor: entry.color }}
                  />
                  <span className="text-sm font-semibold text-slate-200 truncate">
                    {entry.label}
                  </span>
                </div>
                <p className="text-2xl font-bold text-white">{entry.count.toLocaleString()}</p>
                <p className="text-xs text-slate-400 mt-0.5">{pct}% of calls</p>
                <div className="mt-2 h-1 rounded-full bg-slate-600 overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${pct}%`, backgroundColor: entry.color }}
                  />
                </div>
                <p className="text-xs text-slate-500 mt-2 leading-snug">{TOOL_DESC[entry.tool]}</p>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
