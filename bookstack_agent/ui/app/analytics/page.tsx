import { redirect } from 'next/navigation'
import { isAuthenticated, getCurrentUser } from '@/lib/session'
import {
  fetchBookstackActivityLog,
  computeBookstackMetrics,
  filterRecentActivities,
  aggregateByDate,
} from '@/lib/bookstack-data-fetcher'
import QueryMetrics from './components/query-metrics'
import QueryVelocityChart from './components/query-velocity-chart'
import ToolUsageChart from './components/tool-usage-chart'
import RecentQueriesTable from './components/recent-queries-table'
import { BookOpen, Activity } from 'lucide-react'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export default async function BookstackAnalyticsPage() {
  const authenticated = await isAuthenticated()
  if (!authenticated) {
    redirect('/login')
  }

  const user = await getCurrentUser()

  const log = await fetchBookstackActivityLog()

  const Header = () => (
    <div className="p-4 md:p-8">
      <div className="max-w-7xl mx-auto">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-vector-magenta to-vector-violet flex items-center justify-center">
                <BookOpen className="w-5 h-5 text-white" />
              </div>
              <h1 className="text-4xl md:text-5xl font-bold text-gradient">
                BookStack Analytics
              </h1>
            </div>
            <p className="text-slate-400 text-lg">
              Usage insights for the Vector Institute knowledge-base assistant
            </p>
          </div>
          <div className="flex items-center gap-4">
            {user && (
              <div className="text-right">
                <p className="text-xs text-slate-500 uppercase tracking-wide">Signed in as</p>
                <p className="text-sm font-semibold text-gradient">{user.email}</p>
              </div>
            )}
            <a
              href="/aieng-bot/api/auth/logout"
              className="px-4 py-2 text-sm font-semibold text-white bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
            >
              Logout
            </a>
          </div>
        </div>
      </div>
    </div>
  )

  if (!log || log.activities.length === 0) {
    return (
      <div className="min-h-screen">
        <div className="h-1 bg-gradient-to-r from-vector-magenta via-vector-violet to-vector-cobalt" />
        <Header />
        <div className="max-w-7xl mx-auto px-4 md:px-8 pb-8">
          <div className="rounded-xl border border-white/10 bg-slate-800/60 py-16 text-center">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-vector-magenta/10 mb-4">
              <Activity className="w-8 h-8 text-vector-magenta" />
            </div>
            <h2 className="text-2xl font-bold text-white mb-2">No Data Yet</h2>
            <p className="text-slate-400 max-w-sm mx-auto">
              Analytics will appear here once users start asking questions.
            </p>
          </div>
        </div>
      </div>
    )
  }

  const metrics = computeBookstackMetrics(log)
  const recentActivities = filterRecentActivities(log.activities, 30)
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
  const velocityData = aggregateByDate(filterRecentActivities(log.activities, 90))

  return (
    <div className="min-h-screen">
      <div className="h-1 bg-gradient-to-r from-vector-magenta via-vector-violet to-vector-cobalt" />
      <Header />

      <div className="max-w-7xl mx-auto px-4 md:px-8 pb-12 space-y-6">
        {/* Metrics row */}
        <QueryMetrics metrics={metrics} />

        {/* Velocity + Tool usage side by side on large screens */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <QueryVelocityChart data={velocityData} />
          </div>
          <div>
            <ToolUsageChart metrics={metrics} />
          </div>
        </div>

        {/* Recent queries */}
        <RecentQueriesTable activities={recentActivities} />
      </div>
    </div>
  )
}
