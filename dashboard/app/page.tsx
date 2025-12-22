import { redirect } from 'next/navigation'
import { isAuthenticated, getCurrentUser } from '@/lib/session'
import { fetchBotActivityLog, activityLogToPRSummaries, enrichPRSummaries, computeMetricsFromPRSummaries } from '@/lib/data-fetcher'
import OverviewTable from '@/components/overview-table'
import AutoMergeTable from '@/components/auto-merge-table'
import PRVelocityChart from '@/components/pr-velocity-chart'
import PerformanceMetrics from '@/components/performance-metrics'
import CostAnalytics from '@/components/cost-analytics'
import type { PRSummary, BotMetrics } from '@/lib/types'
import { Activity, Info } from 'lucide-react'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export default async function DashboardPage() {
  // Check authentication
  const authenticated = await isAuthenticated()
  if (!authenticated) {
    redirect('/login')
  }

  const user = await getCurrentUser()

  // Fetch activity log from GCS (includes both auto-merges and bot fixes)
  let allPRSummaries: PRSummary[] = []
  let recentPRSummaries: PRSummary[] = []
  let metrics: BotMetrics | null = null

  try {
    const activityLog = await fetchBotActivityLog()
    if (activityLog && activityLog.activities.length > 0) {
      // Convert activities to PR summaries
      const summaries = activityLogToPRSummaries(activityLog)

      // Enrich with trace data (only for bot_fix entries, auto_merge already has all data)
      allPRSummaries = await enrichPRSummaries(summaries)

      // Compute metrics from ALL activities (includes auto-merges, no time filter)
      metrics = computeMetricsFromPRSummaries(allPRSummaries)

      // Filter to last 30 days for tables only
      const thirtyDaysAgo = new Date()
      thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30)
      recentPRSummaries = allPRSummaries
        .filter(s => new Date(s.timestamp) >= thirtyDaysAgo)
        .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
    }
  } catch (error) {
    console.error('Error fetching activity data:', error)
  }

  // Show empty state if no data
  if (!metrics || allPRSummaries.length === 0) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
        {/* Vector Brand Header Accent */}
        <div className="h-1 bg-gradient-to-r from-vector-magenta via-vector-violet to-vector-cobalt"></div>

        <div className="p-4 md:p-8">
          <div className="max-w-7xl mx-auto">
            <div className="mb-8 animate-fade-in">
              <div className="flex items-center justify-between">
                <div>
                  <h1 className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-vector-magenta via-vector-violet to-vector-cobalt bg-clip-text text-transparent mb-2">
                    Maintenance Analytics
                  </h1>
                  <p className="text-slate-700 dark:text-slate-300 text-lg">
                    Automated pull request maintenance across Vector Institute repositories
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  {user && (
                    <div className="text-right">
                      <p className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide">Signed in as</p>
                      <p className="text-sm font-semibold bg-gradient-to-r from-vector-magenta to-vector-violet bg-clip-text text-transparent">{user.email}</p>
                    </div>
                  )}
                  <a
                    href="/aieng-bot-maintain/api/auth/logout"
                    className="px-4 py-2 text-sm font-semibold text-white bg-gradient-to-r from-slate-600 to-slate-700 hover:from-vector-magenta hover:to-vector-violet rounded-lg shadow-sm hover:shadow-md transition-all duration-200"
                  >
                    Logout
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="max-w-7xl mx-auto px-4 md:px-8 pb-8">
          <div className="text-center py-16 card">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br from-vector-magenta/10 to-vector-violet/10 rounded-full mb-4">
              <Activity className="w-8 h-8 text-vector-magenta" />
            </div>
            <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">
              No Data Available
            </h2>
            <p className="text-slate-600 dark:text-slate-400 mb-4">
              The bot hasn&apos;t processed any PRs yet. Data will appear here once the bot starts monitoring and fixing PRs.
            </p>
            <div className="text-sm text-slate-500 dark:text-slate-500">
              <p>Trigger the bot workflow to fix a PR:</p>
              <code className="block mt-2 p-2 bg-slate-100 dark:bg-slate-800 rounded text-xs">
                gh workflow run fix-remote-pr.yml --field target_repo=&quot;VectorInstitute/repo-name&quot; --field pr_number=&quot;123&quot;
              </code>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      {/* Vector Brand Header Accent */}
      <div className="h-1 bg-gradient-to-r from-vector-magenta via-vector-violet to-vector-cobalt"></div>

      <div className="p-4 md:p-8">
        <div className="max-w-7xl mx-auto">
          <div className="mb-8 animate-fade-in">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-vector-magenta via-vector-violet to-vector-cobalt bg-clip-text text-transparent mb-2">
                  Maintenance Analytics
                </h1>
                <p className="text-slate-700 dark:text-slate-300 text-lg">
                  Automated pull request maintenance across Vector Institute repositories
                </p>
              </div>
              <div className="flex items-center gap-4">
                {user && (
                  <div className="text-right">
                    <p className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide">Signed in as</p>
                    <p className="text-sm font-semibold bg-gradient-to-r from-vector-magenta to-vector-violet bg-clip-text text-transparent">{user.email}</p>
                  </div>
                )}
                <a
                  href="/aieng-bot-maintain/api/auth/logout"
                  className="px-4 py-2 text-sm font-semibold text-white bg-gradient-to-r from-slate-600 to-slate-700 hover:from-vector-magenta hover:to-vector-violet rounded-lg shadow-sm hover:shadow-md transition-all duration-200"
                >
                  Logout
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 md:px-8 pb-8">
        <div className="space-y-8">
      {/* Performance Metrics */}
      <PerformanceMetrics metrics={metrics} />

      {/* PR Velocity Chart */}
      <PRVelocityChart prSummaries={recentPRSummaries} />

      {/* Cost Analytics */}
      <CostAnalytics metrics={metrics} prSummaries={allPRSummaries} />

      {/* Auto-Merged PRs Table */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <div className="flex items-center gap-2 mb-4">
          <h3 className="text-xl font-bold text-gray-900 dark:text-white">
            Recent PR Merges
          </h3>
          <div className="group relative">
            <Info className="w-4 h-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 cursor-help" />
            <div className="absolute left-0 top-6 hidden group-hover:block z-50 w-48 px-3 py-2 text-xs bg-gray-900 dark:bg-gray-700 text-white rounded-lg shadow-lg">
              Showing PRs from the last 30 days
              <div className="absolute -top-1 left-4 w-2 h-2 bg-gray-900 dark:bg-gray-700 transform rotate-45"></div>
            </div>
          </div>
        </div>
        {recentPRSummaries.filter(pr => pr.type === 'auto_merge').length === 0 ? (
          <div className="text-center py-12">
            <div className="inline-flex items-center justify-center w-12 h-12 bg-slate-100 dark:bg-slate-700 rounded-full mb-3">
              <Activity className="w-6 h-6 text-slate-400" />
            </div>
            <p className="text-slate-600 dark:text-slate-400 text-sm">
              No auto-merged PRs recorded in the last 30 days.
            </p>
          </div>
        ) : (
          <AutoMergeTable prSummaries={recentPRSummaries} />
        )}
      </div>

      {/* Bot Fixed PRs Table */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <div className="flex items-center gap-2 mb-4">
          <h3 className="text-xl font-bold text-gray-900 dark:text-white">
            Recent PR Fixes
          </h3>
          <div className="group relative">
            <Info className="w-4 h-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 cursor-help" />
            <div className="absolute left-0 top-6 hidden group-hover:block z-50 w-48 px-3 py-2 text-xs bg-gray-900 dark:bg-gray-700 text-white rounded-lg shadow-lg">
              Showing PRs from the last 30 days
              <div className="absolute -top-1 left-4 w-2 h-2 bg-gray-900 dark:bg-gray-700 transform rotate-45"></div>
            </div>
          </div>
        </div>
        {recentPRSummaries.filter(pr => pr.type === 'bot_fix').length === 0 ? (
          <div className="text-center py-12">
            <div className="inline-flex items-center justify-center w-12 h-12 bg-slate-100 dark:bg-slate-700 rounded-full mb-3">
              <Activity className="w-6 h-6 text-slate-400" />
            </div>
            <p className="text-slate-600 dark:text-slate-400 text-sm">
              No PR fixes recorded in the last 30 days.
            </p>
          </div>
        ) : (
          <OverviewTable prSummaries={recentPRSummaries} />
        )}
      </div>
        </div>
      </div>
    </div>
  )
}
