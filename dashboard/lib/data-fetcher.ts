/**
 * Data fetching utilities for GCS storage
 */

import type { AgentTrace, BotMetrics, BotMetricsHistory, TraceIndex, PRSummary } from './types'

const GCS_BUCKET_URL = 'https://storage.googleapis.com/bot-dashboard-vectorinstitute'

/**
 * Fetch latest bot metrics
 */
export async function fetchBotMetrics(): Promise<BotMetrics | null> {
  try {
    const response = await fetch(`${GCS_BUCKET_URL}/data/bot_metrics_latest.json`, {
      cache: 'no-store',
    })

    if (!response.ok) {
      // Don't log 404s - expected when no data collected yet
      if (response.status !== 404) {
        console.error('Failed to fetch bot metrics:', response.statusText)
      }
      return null
    }

    return await response.json()
  } catch (error) {
    console.error('Error fetching bot metrics:', error)
    return null
  }
}

/**
 * Fetch historical bot metrics
 */
export async function fetchBotMetricsHistory(): Promise<BotMetricsHistory | null> {
  try {
    const response = await fetch(`${GCS_BUCKET_URL}/data/bot_metrics_history.json`, {
      cache: 'no-store',
    })

    if (!response.ok) {
      if (response.status !== 404) {
        console.error('Failed to fetch bot metrics history:', response.statusText)
      }
      return null
    }

    return await response.json()
  } catch (error) {
    console.error('Error fetching bot metrics history:', error)
    return null
  }
}

/**
 * Fetch traces index for fast lookups
 */
export async function fetchTraceIndex(): Promise<TraceIndex | null> {
  try {
    // Add cache-busting parameter to bypass CDN cache
    const cacheBuster = Date.now()
    const response = await fetch(`${GCS_BUCKET_URL}/data/traces_index.json?t=${cacheBuster}`, {
      cache: 'no-store',
    })

    if (!response.ok) {
      if (response.status !== 404) {
        console.error('Failed to fetch trace index:', response.statusText)
      }
      return null
    }

    return await response.json()
  } catch (error) {
    console.error('Error fetching trace index:', error)
    return null
  }
}

/**
 * Fetch specific agent trace
 */
export async function fetchAgentTrace(tracePath: string): Promise<AgentTrace | null> {
  try {
    // Add cache-busting parameter to bypass CDN cache
    const cacheBuster = Date.now()
    const response = await fetch(`${GCS_BUCKET_URL}/${tracePath}?t=${cacheBuster}`, {
      cache: 'no-store',
    })

    if (!response.ok) {
      console.error('Failed to fetch agent trace:', response.statusText)
      return null
    }

    return await response.json()
  } catch (error) {
    console.error('Error fetching agent trace:', error)
    return null
  }
}

/**
 * Fetch trace for specific PR (finds most recent trace)
 */
export async function fetchPRTrace(repo: string, prNumber: number): Promise<AgentTrace | null> {
  try {
    // First try to fetch the trace index
    const index = await fetchTraceIndex()

    if (index) {
      // Find matching trace in index
      const traceEntry = index.traces
        .filter(t => t.repo === repo && t.pr_number === prNumber)
        .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())[0]

      if (traceEntry) {
        return await fetchAgentTrace(traceEntry.trace_path)
      }
    }

    // Fallback: Try to construct likely path
    // Format: traces/YYYY/MM/DD/repo-name-pr-number-runid.json
    // We don't know the run ID, so this is a best-effort attempt
    console.warn('Trace index not found, cannot locate PR trace without index')
    return null
  } catch (error) {
    console.error('Error fetching PR trace:', error)
    return null
  }
}

/**
 * Convert trace index to PR summaries for overview table
 */
export function traceIndexToPRSummaries(index: TraceIndex): PRSummary[] {
  return index.traces.map(entry => ({
    repo: entry.repo,
    pr_number: entry.pr_number,
    title: '', // Will be filled when trace is loaded
    author: '', // Will be filled when trace is loaded
    failure_type: '', // Will be filled when trace is loaded
    status: entry.status || 'IN_PROGRESS',
    fix_time_hours: null, // Will be calculated when trace is loaded
    timestamp: entry.timestamp,
    trace_path: entry.trace_path,
    pr_url: `https://github.com/${entry.repo}/pull/${entry.pr_number}`,
    workflow_run_url: `https://github.com/VectorInstitute/aieng-bot-maintain/actions/runs/${entry.workflow_run_id}`,
  }))
}

/**
 * Enrich PR summaries with trace data
 */
export async function enrichPRSummaries(summaries: PRSummary[]): Promise<PRSummary[]> {
  const enriched = await Promise.all(
    summaries.map(async (summary) => {
      const trace = await fetchAgentTrace(summary.trace_path)

      if (!trace) {
        return summary
      }

      const duration = trace.execution.duration_seconds
        ? trace.execution.duration_seconds / 3600
        : null

      return {
        ...summary,
        title: trace.metadata.pr.title,
        author: trace.metadata.pr.author,
        failure_type: trace.metadata.failure.type,
        status: trace.result.status,
        fix_time_hours: duration,
      }
    })
  )

  return enriched
}

/**
 * Compute bot metrics from PR summaries
 */
export function computeMetricsFromPRSummaries(prSummaries: PRSummary[]): BotMetrics {
  const now = new Date().toISOString()

  // Calculate stats
  const totalPRs = prSummaries.length
  const successfulFixes = prSummaries.filter(pr => pr.status === 'SUCCESS').length
  const failedFixes = prSummaries.filter(pr => pr.status === 'FAILED').length
  const partialFixes = prSummaries.filter(pr => pr.status === 'PARTIAL').length
  const openPRs = prSummaries.filter(pr => pr.status === 'IN_PROGRESS').length

  const successRate = totalPRs > 0 ? successfulFixes / totalPRs : 0

  const fixTimes = prSummaries
    .filter(pr => pr.fix_time_hours !== null)
    .map(pr => pr.fix_time_hours!)
  const avgFixTime = fixTimes.length > 0
    ? fixTimes.reduce((a, b) => a + b, 0) / fixTimes.length
    : 0

  // Group by failure type
  const byFailureType: Record<string, any> = {}
  prSummaries.forEach(pr => {
    const type = pr.failure_type || 'unknown'
    if (!byFailureType[type]) {
      byFailureType[type] = { count: 0, fixed: 0, failed: 0, success_rate: 0 }
    }
    byFailureType[type].count++
    if (pr.status === 'SUCCESS') byFailureType[type].fixed++
    if (pr.status === 'FAILED') byFailureType[type].failed++
  })

  // Calculate success rates per failure type
  Object.keys(byFailureType).forEach(type => {
    const data = byFailureType[type]
    data.success_rate = data.count > 0 ? data.fixed / data.count : 0
  })

  // Group by repo
  const byRepo: Record<string, any> = {}
  prSummaries.forEach(pr => {
    if (!byRepo[pr.repo]) {
      byRepo[pr.repo] = { total_prs: 0, auto_merged: 0, bot_fixed: 0, failed: 0, success_rate: 0 }
    }
    byRepo[pr.repo].total_prs++
    if (pr.status === 'SUCCESS') byRepo[pr.repo].bot_fixed++
    if (pr.status === 'FAILED') byRepo[pr.repo].failed++
  })

  // Calculate success rates per repo
  Object.keys(byRepo).forEach(repo => {
    const data = byRepo[repo]
    data.success_rate = data.total_prs > 0 ? data.bot_fixed / data.total_prs : 0
  })

  return {
    snapshot_date: now,
    stats: {
      total_prs_scanned: totalPRs,
      prs_auto_merged: 0, // We don't track auto-merges in traces yet
      prs_bot_fixed: successfulFixes,
      prs_failed: failedFixes,
      prs_open: openPRs,
      success_rate: successRate,
      avg_fix_time_hours: avgFixTime,
    },
    by_failure_type: byFailureType,
    by_repo: byRepo,
  }
}
