/**
 * Data fetching utilities for GCS storage.
 *
 * Detailed per-run traces are viewed in Langfuse; the dashboard only reads
 * the aggregate PR activity log (status, cost, duration) for the PR list
 * and analytics views.
 */

import type { BotMetrics, BotActivityLog, PRSummary } from './types'

const GCS_BUCKET_URL = 'https://storage.googleapis.com/bot-dashboard-vectorinstitute'

/**
 * Fetch bot activity log
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
 * Convert bot activity log to PR summaries for overview table
 */
export function activityLogToPRSummaries(log: BotActivityLog): PRSummary[] {
  return log.activities.map(activity => ({
    repo: activity.repo,
    pr_number: activity.pr_number,
    title: activity.pr_title,
    author: activity.pr_author,
    status: activity.status,
    timestamp: activity.timestamp,
    pr_url: activity.pr_url,
    workflow_run_url: activity.github_run_url,
    failure_type: activity.failure_type,
    fix_time_hours: activity.fix_time_hours || null,
    cost_usd: activity.cost_usd ?? null,
  }))
}

/**
 * Compute bot metrics from PR summaries
 */
export function computeMetricsFromPRSummaries(prSummaries: PRSummary[]): BotMetrics {
  const now = new Date().toISOString()

  // Calculate stats
  const totalPRs = prSummaries.length
  const fixedAndMerged = prSummaries.filter(pr => pr.status === 'SUCCESS').length
  const failed = prSummaries.filter(pr => pr.status === 'FAILED').length

  const successRate = totalPRs > 0 ? fixedAndMerged / totalPRs : 0

  const fixTimes = prSummaries
    .filter(pr => pr.fix_time_hours !== null)
    .map(pr => pr.fix_time_hours!)
  const avgFixTime = fixTimes.length > 0
    ? fixTimes.reduce((a, b) => a + b, 0) / fixTimes.length
    : 0

  // Calculate cost metrics
  const costsWithData = prSummaries
    .filter(pr => pr.cost_usd !== null && pr.cost_usd !== undefined)
    .map(pr => pr.cost_usd!)
  const totalCost = costsWithData.length > 0
    ? costsWithData.reduce((a, b) => a + b, 0)
    : 0

  // Average cost per attempt
  const avgCostPerAttempt = costsWithData.length > 0
    ? totalCost / costsWithData.length
    : 0

  // Average cost per successful fix only
  const successfulWithCost = prSummaries
    .filter(pr => pr.status === 'SUCCESS' && pr.cost_usd !== null && pr.cost_usd !== undefined)
  const avgCostPerSuccess = successfulWithCost.length > 0
    ? successfulWithCost.reduce((sum, pr) => sum + pr.cost_usd!, 0) / successfulWithCost.length
    : 0

  // Group by failure type
  const byFailureType: Record<string, { count: number; fixed: number; failed: number; success_rate: number; total_cost: number; avg_cost: number }> = {}
  prSummaries.forEach(pr => {
    if (pr.failure_type) {
      const type = pr.failure_type
      if (!byFailureType[type]) {
        byFailureType[type] = { count: 0, fixed: 0, failed: 0, success_rate: 0, total_cost: 0, avg_cost: 0 }
      }
      byFailureType[type].count++
      if (pr.status === 'SUCCESS') {
        byFailureType[type].fixed++
      }
      if (pr.status === 'FAILED') {
        byFailureType[type].failed++
      }
      if (pr.cost_usd !== null && pr.cost_usd !== undefined) {
        byFailureType[type].total_cost += pr.cost_usd
      }
    }
  })

  // Calculate success rates and average costs per failure type
  Object.keys(byFailureType).forEach(type => {
    const data = byFailureType[type]
    data.success_rate = data.count > 0 ? data.fixed / data.count : 0
    data.avg_cost = data.count > 0 ? data.total_cost / data.count : 0
  })

  // Group by repo
  const byRepo: Record<string, { total_prs: number; fixed: number; failed: number; success_rate: number; total_cost: number }> = {}
  prSummaries.forEach(pr => {
    if (!byRepo[pr.repo]) {
      byRepo[pr.repo] = { total_prs: 0, fixed: 0, failed: 0, success_rate: 0, total_cost: 0 }
    }
    byRepo[pr.repo].total_prs++
    if (pr.status === 'SUCCESS') {
      byRepo[pr.repo].fixed++
    }
    if (pr.status === 'FAILED') {
      byRepo[pr.repo].failed++
    }
    if (pr.cost_usd !== null && pr.cost_usd !== undefined) {
      byRepo[pr.repo].total_cost += pr.cost_usd
    }
  })

  // Calculate success rates per repo
  Object.keys(byRepo).forEach(repo => {
    const data = byRepo[repo]
    data.success_rate = data.total_prs > 0 ? data.fixed / data.total_prs : 0
  })

  return {
    snapshot_date: now,
    stats: {
      total_prs_scanned: totalPRs,
      prs_fixed_and_merged: fixedAndMerged,
      prs_failed: failed,
      success_rate: successRate,
      avg_fix_time_hours: avgFixTime,
      total_cost_usd: totalCost,
      avg_cost_per_attempt: avgCostPerAttempt,
      avg_cost_per_success: avgCostPerSuccess,
    },
    by_failure_type: byFailureType,
    by_repo: byRepo,
  }
}
