import { MessageSquare, Users, Clock, Wrench, TrendingUp, CheckCircle } from 'lucide-react'
import type { BookstackMetrics } from '@/lib/bookstack-types'

interface MetricCardProps {
  label: string
  value: string | number
  sub?: string
  icon: React.ReactNode
  accent?: string
}

function MetricCard({ label, value, sub, icon, accent = 'from-vector-magenta to-vector-violet' }: MetricCardProps) {
  return (
    <div className="rounded-xl border border-white/10 bg-slate-800/60 p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{label}</span>
        <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${accent} flex items-center justify-center`}>
          {icon}
        </div>
      </div>
      <div>
        <p className="text-3xl font-bold text-white">{value}</p>
        {sub && <p className="text-xs text-slate-400 mt-1">{sub}</p>}
      </div>
    </div>
  )
}

interface QueryMetricsProps {
  metrics: BookstackMetrics
}

export default function QueryMetrics({ metrics }: QueryMetricsProps) {
  const successPct = Math.round(metrics.success_rate * 100)

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold text-white">Overview</h2>
        <p className="text-sm text-slate-400 mt-0.5">All-time query statistics</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <MetricCard
          label="Total Queries"
          value={metrics.total_queries.toLocaleString()}
          sub={`${metrics.queries_today} today`}
          icon={<MessageSquare className="w-4 h-4 text-white" />}
          accent="from-vector-magenta to-vector-violet"
        />
        <MetricCard
          label="This Week"
          value={metrics.queries_this_week.toLocaleString()}
          sub="last 7 days"
          icon={<TrendingUp className="w-4 h-4 text-white" />}
          accent="from-vector-violet to-vector-cobalt"
        />
        <MetricCard
          label="Unique Users"
          value={metrics.unique_users.toLocaleString()}
          sub="distinct users"
          icon={<Users className="w-4 h-4 text-white" />}
          accent="from-vector-cobalt to-vector-violet"
        />
        <MetricCard
          label="Success Rate"
          value={`${successPct}%`}
          sub={`${metrics.successful_queries} answered`}
          icon={<CheckCircle className="w-4 h-4 text-white" />}
          accent="from-emerald-500 to-teal-600"
        />
        <MetricCard
          label="Avg Duration"
          value={`${metrics.avg_duration_seconds.toFixed(1)}s`}
          sub="per query"
          icon={<Clock className="w-4 h-4 text-white" />}
          accent="from-amber-500 to-orange-600"
        />
        <MetricCard
          label="Avg Tools / Query"
          value={metrics.avg_tool_calls_per_query.toFixed(1)}
          sub="tool calls per query"
          icon={<Wrench className="w-4 h-4 text-white" />}
          accent="from-purple-500 to-pink-600"
        />
      </div>

      {/* Success / error bar */}
      {metrics.total_queries > 0 && (
        <div className="rounded-xl border border-white/10 bg-slate-800/60 p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-slate-300">Answer Rate</span>
            <span className="text-sm text-slate-400">
              {metrics.successful_queries} answered · {metrics.error_queries} errored
            </span>
          </div>
          <div className="h-2 rounded-full bg-slate-700 overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-400 transition-all duration-500"
              style={{ width: `${successPct}%` }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
