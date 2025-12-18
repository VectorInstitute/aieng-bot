import { redirect } from 'next/navigation'
import { isAuthenticated, getCurrentUser } from '@/lib/session'
import { fetchTraceIndex, traceIndexToPRSummaries, enrichPRSummaries, computeMetricsFromPRSummaries } from '@/lib/data-fetcher'
import OverviewTable from '@/components/overview-table'
import MetricsCharts from '@/components/metrics-charts'
import PerformanceMetrics from '@/components/performance-metrics'
import type { PRSummary, BotMetrics } from '@/lib/types'
import { Activity } from 'lucide-react'
import Link from 'next/link'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export default async function DashboardPage() {
  // Check authentication
  const authenticated = await isAuthenticated()
  if (!authenticated) {
    redirect('/login')
  }

  const user = await getCurrentUser()

  // Fetch trace data directly from GCS and compute metrics
  let prSummaries: PRSummary[] = []
  let metrics: BotMetrics | null = null

  try {
    const index = await fetchTraceIndex()
    if (index && index.traces.length > 0) {
      const summaries = traceIndexToPRSummaries(index)
      // Limit to most recent 50 PRs for performance
      const recentSummaries = summaries
        .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
        .slice(0, 50)

      // Enrich with trace data
      prSummaries = await enrichPRSummaries(recentSummaries)

      // Compute metrics from traces
      metrics = computeMetricsFromPRSummaries(prSummaries)
    }
  } catch (error) {
    console.error('Error fetching trace data:', error)
  }

  // Show empty state if no data
  if (!metrics || prSummaries.length === 0) {
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
              The bot hasn't processed any PRs yet. Data will appear here once the bot starts monitoring and fixing PRs.
            </p>
            <div className="text-sm text-slate-500 dark:text-slate-500">
              <p>Trigger the bot workflow to fix a PR:</p>
              <code className="block mt-2 p-2 bg-slate-100 dark:bg-slate-800 rounded text-xs">
                gh workflow run fix-remote-pr.yml --field target_repo="VectorInstitute/repo-name" --field pr_number="123"
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

      {/* Key Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                Total PRs Scanned
              </p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white mt-2">
                {metrics.stats.total_prs_scanned}
              </p>
            </div>
            <div className="w-12 h-12 bg-blue-100 dark:bg-blue-900/30 rounded-lg flex items-center justify-center">
              <svg className="w-6 h-6 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                Auto-Merged
              </p>
              <p className="text-3xl font-bold text-green-600 dark:text-green-400 mt-2">
                {metrics.stats.prs_auto_merged}
              </p>
            </div>
            <div className="w-12 h-12 bg-green-100 dark:bg-green-900/30 rounded-lg flex items-center justify-center">
              <svg className="w-6 h-6 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                Bot Fixed
              </p>
              <p className="text-3xl font-bold text-vector-magenta mt-2">
                {metrics.stats.prs_bot_fixed}
              </p>
            </div>
            <div className="w-12 h-12 bg-vector-magenta/10 rounded-lg flex items-center justify-center">
              <svg className="w-6 h-6 text-vector-magenta" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                Success Rate
              </p>
              <p className="text-3xl font-bold text-vector-violet mt-2">
                {(metrics.stats.success_rate * 100).toFixed(0)}%
              </p>
            </div>
            <div className="w-12 h-12 bg-vector-violet/10 rounded-lg flex items-center justify-center">
              <svg className="w-6 h-6 text-vector-violet" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
          </div>
        </div>
      </div>

      {/* Performance Metrics */}
      <PerformanceMetrics metrics={metrics} />

      {/* Charts */}
      <MetricsCharts metrics={metrics} />

      {/* Recent PRs Table */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
          Recent PR Fixes
        </h3>
        {prSummaries.length === 0 ? (
          <div className="text-center py-12">
            <div className="inline-flex items-center justify-center w-12 h-12 bg-slate-100 dark:bg-slate-700 rounded-full mb-3">
              <Activity className="w-6 h-6 text-slate-400" />
            </div>
            <p className="text-slate-600 dark:text-slate-400 text-sm">
              No PR fixes recorded yet. The table will populate as the bot processes PRs.
            </p>
          </div>
        ) : (
          <OverviewTable prSummaries={prSummaries} />
        )}
      </div>
        </div>
      </div>
    </div>
  )
}
