/**
 * Data-fetching utilities for BookStack QA analytics.
 * All reads are from the public GCS bucket — no auth required on the read path.
 */

import type {
  BookstackActivity,
  BookstackActivityLog,
  BookstackMetrics,
  BookstackTrace,
} from './bookstack-types'

const GCS_BUCKET_URL = 'https://storage.googleapis.com/bot-dashboard-vectorinstitute'
const ACTIVITY_LOG_PATH = 'data/bookstack_activity_log.json'

/** Fetch the unified BookStack activity log from GCS. */
export async function fetchBookstackActivityLog(): Promise<BookstackActivityLog | null> {
  try {
    const cacheBuster = Date.now()
    const res = await fetch(
      `${GCS_BUCKET_URL}/${ACTIVITY_LOG_PATH}?t=${cacheBuster}`,
      { cache: 'no-store' },
    )
    if (!res.ok) {
      if (res.status !== 404) {
        console.error('Failed to fetch bookstack activity log:', res.statusText)
      }
      return null
    }
    return await res.json() as BookstackActivityLog
  } catch (err) {
    console.error('Error fetching bookstack activity log:', err)
    return null
  }
}

/** Fetch an individual per-query trace file from GCS. */
export async function fetchBookstackTrace(tracePath: string): Promise<BookstackTrace | null> {
  try {
    const cacheBuster = Date.now()
    const res = await fetch(
      `${GCS_BUCKET_URL}/${tracePath}?t=${cacheBuster}`,
      { cache: 'no-store' },
    )
    if (!res.ok) {
      console.error('Failed to fetch bookstack trace:', res.statusText)
      return null
    }
    return await res.json() as BookstackTrace
  } catch (err) {
    console.error('Error fetching bookstack trace:', err)
    return null
  }
}

/** Compute aggregate metrics from the activity log. */
export function computeBookstackMetrics(log: BookstackActivityLog): BookstackMetrics {
  const activities = log.activities

  const total = activities.length
  const successful = activities.filter(a => a.status === 'success').length
  const errors = activities.filter(a => a.status === 'error').length

  const sessions = new Set(activities.map(a => a.session_id))
  const users = new Set(activities.map(a => a.user_email).filter(Boolean))

  const durations = activities.map(a => a.duration_seconds).filter(d => d > 0)
  const avgDuration = durations.length > 0
    ? durations.reduce((s, d) => s + d, 0) / durations.length
    : 0

  const totalToolCalls = activities.reduce((s, a) => s + a.num_tool_calls, 0)
  const avgToolCalls = total > 0 ? totalToolCalls / total : 0

  const toolUsage = { search_bookstack: 0, get_page: 0, list_books: 0 }
  activities.forEach(a => {
    if (a.tool_call_counts) {
      // Use precise per-tool counts when available (new format)
      toolUsage.search_bookstack += a.tool_call_counts.search_bookstack ?? 0
      toolUsage.get_page += a.tool_call_counts.get_page ?? 0
      toolUsage.list_books += a.tool_call_counts.list_books ?? 0
    } else {
      // Fallback for legacy entries: count queries that used each tool
      a.tools_used.forEach(tool => {
        if (tool === 'search_bookstack') toolUsage.search_bookstack++
        else if (tool === 'get_page') toolUsage.get_page++
        else if (tool === 'list_books') toolUsage.list_books++
      })
    }
  })

  const now = new Date()
  const todayStart = new Date(now)
  todayStart.setHours(0, 0, 0, 0)
  const weekStart = new Date(now)
  weekStart.setDate(weekStart.getDate() - 7)

  const queriesToday = activities.filter(a => new Date(a.timestamp) >= todayStart).length
  const queriesThisWeek = activities.filter(a => new Date(a.timestamp) >= weekStart).length

  return {
    total_queries: total,
    successful_queries: successful,
    error_queries: errors,
    success_rate: total > 0 ? successful / total : 0,
    unique_sessions: sessions.size,
    unique_users: users.size,
    avg_duration_seconds: avgDuration,
    avg_tool_calls_per_query: avgToolCalls,
    total_tool_calls: totalToolCalls,
    queries_today: queriesToday,
    queries_this_week: queriesThisWeek,
    tool_usage: toolUsage,
  }
}

/** Slice the activity log to entries within the last N days. */
export function filterRecentActivities(
  activities: BookstackActivity[],
  days: number,
): BookstackActivity[] {
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() - days)
  return activities.filter(a => new Date(a.timestamp) >= cutoff)
}

/** Aggregate activities by calendar date for the velocity chart. */
export function aggregateByDate(
  activities: BookstackActivity[],
): Array<{ date: string; success: number; error: number; total: number }> {
  const byDate = new Map<
    string,
    { success: number; error: number; year: number; month: number; day: number }
  >()

  activities.forEach(a => {
    const d = new Date(a.timestamp)
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    if (!byDate.has(key)) {
      byDate.set(key, { success: 0, error: 0, year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate() })
    }
    const entry = byDate.get(key)!
    if (a.status === 'success') entry.success++
    else entry.error++
  })

  return Array.from(byDate.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([, v]) => ({
      date: new Date(v.year, v.month - 1, v.day).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
      }),
      success: v.success,
      error: v.error,
      total: v.success + v.error,
    }))
}
