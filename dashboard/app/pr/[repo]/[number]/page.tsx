import { redirect } from 'next/navigation'
import { isAuthenticated } from '@/lib/session'
import { fetchPRTrace } from '@/lib/data-fetcher'
import { notFound } from 'next/navigation'
import AgentTimeline from '@/components/agent-timeline'
import FailureAnalysis from '@/components/failure-analysis'
import ExecutionMetrics from '@/components/execution-metrics'
import SkillsUsage from '@/components/skills-usage'
import { Clock, GitBranch, User, ExternalLink } from 'lucide-react'

export const dynamic = 'force-dynamic'
export const revalidate = 0

interface PRPageProps {
  params: Promise<{
    repo: string
    number: string
  }>
}

export default async function PRPage({ params }: PRPageProps) {
  // Check authentication
  const authenticated = await isAuthenticated()

  if (!authenticated) {
    redirect('/login')
  }

  // Await params
  const { repo, number } = await params

  // Decode repo (it will be URL encoded)
  const decodedRepo = decodeURIComponent(repo)
  const fullRepo = decodedRepo.includes('/') ? decodedRepo : `VectorInstitute/${decodedRepo}`
  const prNumber = parseInt(number, 10)

  if (isNaN(prNumber)) {
    notFound()
  }

  // Fetch trace data
  const trace = await fetchPRTrace(fullRepo, prNumber)

  if (!trace) {
    notFound()
  }

  const duration = trace.execution.duration_seconds
    ? (trace.execution.duration_seconds / 60).toFixed(1)
    : 'N/A'

  const statusColor = {
    SUCCESS: 'text-green-600 bg-green-50 dark:bg-green-900/20 dark:text-green-400',
    FAILED: 'text-red-600 bg-red-50 dark:bg-red-900/20 dark:text-red-400',
    PARTIAL: 'text-yellow-600 bg-yellow-50 dark:bg-yellow-900/20 dark:text-yellow-400',
    IN_PROGRESS: 'text-blue-600 bg-blue-50 dark:bg-blue-900/20 dark:text-blue-400',
  }[trace.result.status]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <div className="flex items-start justify-between mb-4">
          <div className="flex-1">
            <div className="flex items-center space-x-3 mb-2">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                {trace.metadata.pr.title}
              </h1>
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${statusColor}`}>
                {trace.result.status}
              </span>
            </div>
            <div className="flex flex-wrap gap-4 text-sm text-gray-600 dark:text-gray-400">
              <div className="flex items-center space-x-2">
                <GitBranch className="w-4 h-4" />
                <a
                  href={trace.metadata.pr.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-blue-600 dark:hover:text-blue-400 flex items-center space-x-1"
                >
                  <span>{fullRepo}#{prNumber}</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
              <div className="flex items-center space-x-2">
                <User className="w-4 h-4" />
                <span>{trace.metadata.pr.author}</span>
              </div>
              <div className="flex items-center space-x-2">
                <Clock className="w-4 h-4" />
                <span>Duration: {duration} min</span>
              </div>
            </div>
          </div>
        </div>

        {/* Quick Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-6">
          <div className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
            <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              Files Modified
            </p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
              {trace.result.files_modified.length}
            </p>
          </div>
          <div className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
            <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              Changes Made
            </p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
              {trace.result.changes_made}
            </p>
          </div>
          <div className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
            <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              {trace.metadata.merge_type === 'auto_merge' ? 'Merge Type' : 'Failure Type'}
            </p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1 capitalize">
              {trace.metadata.failure?.type || trace.metadata.merge_type || 'Unknown'}
            </p>
          </div>
          <div className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
            <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              Events
            </p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
              {trace.events.length}
            </p>
          </div>
        </div>

        {/* Commit Link */}
        {trace.result.commit_url && (
          <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
            <a
              href={trace.result.commit_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-blue-600 dark:text-blue-400 hover:underline flex items-center space-x-1"
            >
              <span>View commit: {trace.result.commit_sha?.substring(0, 7)}</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        )}

        {/* Modified Files */}
        {trace.result.files_modified.length > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
            <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-2">
              Modified Files
            </h3>
            <div className="flex flex-wrap gap-2">
              {trace.result.files_modified.map((file, idx) => (
                <code
                  key={idx}
                  className="text-xs bg-gray-100 dark:bg-gray-900/50 text-gray-700 dark:text-gray-300 px-2 py-1 rounded"
                >
                  {file}
                </code>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Failure Analysis - only show for agent fixes */}
      {trace.metadata.failure && <FailureAnalysis failure={trace.metadata.failure} />}

      {/* Skills Usage - show discovered and used skills */}
      <SkillsUsage events={trace.events} />

      {/* Execution Metrics - show if metrics are available */}
      {trace.execution.metrics && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <ExecutionMetrics trace={trace} />
        </div>
      )}

      {/* Agent Timeline */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
          Agent Execution Timeline
        </h2>
        <AgentTimeline events={trace.events} />
      </div>

      {/* Links */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
          Related Links
        </h2>
        <div className="space-y-2">
          <a
            href={trace.metadata.github_run_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center space-x-2 text-blue-600 dark:text-blue-400 hover:underline"
          >
            <ExternalLink className="w-4 h-4" />
            <span>View GitHub Actions Run</span>
          </a>
          <a
            href={trace.metadata.pr.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center space-x-2 text-blue-600 dark:text-blue-400 hover:underline"
          >
            <ExternalLink className="w-4 h-4" />
            <span>View Pull Request</span>
          </a>
        </div>
      </div>
    </div>
  )
}
