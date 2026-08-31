/**
 * Type definitions for Bot Dashboard
 *
 * Detailed per-run execution traces (tool calls, generations) are viewed in
 * Langfuse, not modeled here - the dashboard only tracks PR outcome summaries.
 */

// Bot metrics types (computed from activity log)
export interface BotMetrics {
  snapshot_date: string
  stats: {
    total_prs_scanned: number
    prs_fixed_and_merged: number
    prs_failed: number
    success_rate: number
    avg_fix_time_hours: number
    total_cost_usd: number
    avg_cost_per_attempt: number
    avg_cost_per_success: number
  }
  by_failure_type: Record<string, {
    count: number
    fixed: number
    failed: number
    success_rate: number
    total_cost: number
    avg_cost: number
  }>
  by_repo: Record<string, {
    total_prs: number
    fixed: number
    failed: number
    success_rate: number
    total_cost: number
  }>
}

// Bot activity log types - single unified activity type
export interface BotActivity {
  repo: string
  pr_number: number
  pr_title: string
  pr_author: string
  pr_url: string
  timestamp: string
  workflow_run_id: string
  github_run_url: string
  status: 'SUCCESS' | 'FAILED'
  failure_type: string  // Primary type for backward compatibility
  failure_types?: string[]  // Array of all failure types (lint, test, build, security, etc.)
  cost_usd: number | null
  fix_time_hours: number
}

export interface BotActivityLog {
  activities: BotActivity[]
  last_updated: string | null
}

export interface BotMetricsHistory {
  snapshots: BotMetrics[]
  last_updated: string | null
}

// PR summary for overview table
export interface PRSummary extends Record<string, unknown> {
  repo: string
  pr_number: number
  title: string
  author: string
  status: 'SUCCESS' | 'FAILED'
  timestamp: string
  pr_url: string
  workflow_run_url: string
  failure_type: string  // Primary type for backward compatibility
  failure_types?: string[]  // Array of all failure types
  fix_time_hours: number | null
  cost_usd: number | null
}

// Authentication types
export interface User {
  email: string
  name: string
  picture?: string
}

export interface SessionData {
  isAuthenticated: boolean
  user?: User
  // OAuth PKCE flow temporary fields
  state?: string
  codeVerifier?: string
  nonce?: string
}
