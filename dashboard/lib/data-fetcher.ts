/**
 * Data fetching utilities for GCS storage
 */

import type { AgentTrace, BotMetrics, BotMetricsHistory, BotActivityLog, PRSummary } from './types'

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
 * Fetch bot activity log (unified view of auto-merges and bot fixes)
 */
export async function fetchBotActivityLog(): Promise<BotActivityLog | null> {
  try {
    // Add cache-busting parameter to bypass CDN cache
    const cacheBuster = Date.now()
    const response = await fetch(`${GCS_BUCKET_URL}/data/bot_activity_log.json?t=${cacheBuster}`, {
      cache: 'no-store',
    })

    if (!response.ok) {
      if (response.status !== 404) {
        console.error('Failed to fetch bot activity log:', response.statusText)
      }
      return null
    }

    return await response.json()
  } catch (error) {
    console.error('Error fetching bot activity log:', error)
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
    // Fetch the activity log to find the trace path
    const activityLog = await fetchBotActivityLog()

    if (activityLog) {
      // Find matching activity entry
      const activity = activityLog.activities
        .filter(a => a.repo === repo && a.pr_number === prNumber && a.type === 'bot_fix')
        .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())[0]

      if (activity && activity.trace_path) {
        return await fetchAgentTrace(activity.trace_path)
      }
    }

    console.warn('Activity log not found or PR has no trace (may be auto-merge)')
    return null
  } catch (error) {
    console.error('Error fetching PR trace:', error)
    return null
  }
}

/**
 * Convert bot activity log to PR summaries for overview table
 */
export function activityLogToPRSummaries(log: BotActivityLog): PRSummary[] {
  return log.activities.map(activity => ({
    type: activity.type,
    repo: activity.repo,
    pr_number: activity.pr_number,
    title: activity.pr_title,
    author: activity.pr_author,
    status: activity.status,
    timestamp: activity.timestamp,
    pr_url: activity.pr_url,
    workflow_run_url: activity.github_run_url,
    // Bot fix specific fields
    failure_type: activity.failure_type,
    fix_time_hours: activity.fix_time_hours || null,
    trace_path: activity.trace_path || '',
    // Auto-merge specific fields
    was_rebased: activity.was_rebased,
    rebase_time_seconds: activity.rebase_time_seconds || null,
  }))
}

/**
 * Enrich PR summaries with trace data (only for bot_fix entries that have traces)
 * Auto-merge entries already have all data from activity log
 */
export async function enrichPRSummaries(summaries: PRSummary[]): Promise<PRSummary[]> {
  const enriched = await Promise.all(
    summaries.map(async (summary) => {
      // Skip auto-merges and entries without trace paths
      if (summary.type === 'auto_merge' || !summary.trace_path) {
        return summary
      }

      // Fetch trace for bot_fix entries to get detailed execution info
      const trace = await fetchAgentTrace(summary.trace_path)

      if (!trace) {
        return summary
      }

      const duration = trace.execution.duration_seconds
        ? trace.execution.duration_seconds / 3600
        : null

      return {
        ...summary,
        status: trace.result.status,
        fix_time_hours: duration || summary.fix_time_hours,
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

  // Calculate stats - differentiate between auto-merge and bot fixes
  const totalPRs = prSummaries.length
  const autoMergedPRs = prSummaries.filter(pr => pr.type === 'auto_merge' && pr.status === 'SUCCESS').length
  const botFixedPRs = prSummaries.filter(pr => pr.type === 'bot_fix' && pr.status === 'SUCCESS').length
  const failedFixes = prSummaries.filter(pr => pr.status === 'FAILED').length
  // Note: PARTIAL is also treated as a failure - bot couldn't fully fix the PR

  // Success rate should only count bot fixes (not auto-merges)
  const totalAttempts = totalPRs - autoMergedPRs
  const successRate = totalAttempts > 0 ? botFixedPRs / totalAttempts : 0

  const fixTimes = prSummaries
    .filter(pr => pr.fix_time_hours !== null)
    .map(pr => pr.fix_time_hours!)
  const avgFixTime = fixTimes.length > 0
    ? fixTimes.reduce((a, b) => a + b, 0) / fixTimes.length
    : 0

  // Group by failure type (bot fixes only, auto-merges tracked separately)
  const byFailureType: Record<string, { count: number; fixed: number; failed: number; success_rate: number }> = {}
  prSummaries.forEach(pr => {
    if (pr.type === 'bot_fix' && pr.failure_type) {
      const type = pr.failure_type
      if (!byFailureType[type]) {
        byFailureType[type] = { count: 0, fixed: 0, failed: 0, success_rate: 0 }
      }
      byFailureType[type].count++
      if (pr.status === 'SUCCESS') {
        byFailureType[type].fixed++
      }
      if (pr.status === 'FAILED') {
        byFailureType[type].failed++
      }
    }
  })

  // Calculate success rates per failure type
  Object.keys(byFailureType).forEach(type => {
    const data = byFailureType[type]
    data.success_rate = data.count > 0 ? data.fixed / data.count : 0
  })

  // Group by repo
  const byRepo: Record<string, { total_prs: number; auto_merged: number; bot_fixed: number; failed: number; success_rate: number }> = {}
  prSummaries.forEach(pr => {
    if (!byRepo[pr.repo]) {
      byRepo[pr.repo] = { total_prs: 0, auto_merged: 0, bot_fixed: 0, failed: 0, success_rate: 0 }
    }
    byRepo[pr.repo].total_prs++
    if (pr.type === 'auto_merge' && pr.status === 'SUCCESS') {
      byRepo[pr.repo].auto_merged++
    } else if (pr.type === 'bot_fix' && pr.status === 'SUCCESS') {
      byRepo[pr.repo].bot_fixed++
    }
    if (pr.status === 'FAILED') byRepo[pr.repo].failed++
  })

  // Calculate success rates per repo (only for bot fix attempts, not auto-merges)
  Object.keys(byRepo).forEach(repo => {
    const data = byRepo[repo]
    const fixAttempts = data.total_prs - data.auto_merged
    data.success_rate = fixAttempts > 0 ? data.bot_fixed / fixAttempts : 0
  })

  return {
    snapshot_date: now,
    stats: {
      total_prs_scanned: totalPRs,
      prs_auto_merged: autoMergedPRs,
      prs_bot_fixed: botFixedPRs,
      prs_failed: failedFixes,
      success_rate: successRate,
      avg_fix_time_hours: avgFixTime,
    },
    by_failure_type: byFailureType,
    by_repo: byRepo,
  }
}
