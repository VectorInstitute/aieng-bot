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
    const response = await fetch(`${GCS_BUCKET_URL}/data/traces_index.json`, {
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
    const response = await fetch(`${GCS_BUCKET_URL}/${tracePath}`, {
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
