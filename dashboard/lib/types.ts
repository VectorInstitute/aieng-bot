/**
 * Type definitions for Bot Dashboard
 */

// Agent execution trace types
export interface AgentTrace {
  metadata: {
    workflow_run_id: string
    github_run_url?: string
    workflow_url?: string
    timestamp?: string
    pr: {
      repo: string
      number: number
      title: string
      author: string
      url: string
    }
    merge_type?: 'auto_merge' | 'agent_fix'
    failure?: {
      type: 'test' | 'lint' | 'security' | 'build' | 'unknown'
      checks: string[]
      logs_truncated: string
    }
  }
  execution: {
    start_time: string
    end_time?: string | null
    duration_seconds: number | null
    model: string | null
    tools_allowed?: string[]
  }
  events: AgentEvent[]
  result: {
    status: 'SUCCESS' | 'FAILED' | 'PARTIAL' | 'IN_PROGRESS'
    changes_made: number
    files_modified: string[]
    commit_sha: string | null
    commit_url: string | null
    merge_method?: 'auto_merge' | 'agent_fix'
  }
}

export interface AgentEvent {
  seq: number
  timestamp: string
  type: 'REASONING' | 'TOOL_CALL' | 'ACTION' | 'ERROR' | 'INFO'
  content: string
  tool?: string
  parameters?: Record<string, unknown>
  result_summary?: string
}

// Bot metrics types
export interface BotMetrics {
  snapshot_date: string
  stats: {
    total_prs_scanned: number
    prs_auto_merged: number
    prs_bot_fixed: number
    prs_failed: number
    success_rate: number
    avg_fix_time_hours: number
  }
  by_failure_type: Record<string, {
    count: number
    fixed: number
    failed: number
    success_rate: number
  }>
  by_repo: Record<string, {
    total_prs: number
    auto_merged: number
    bot_fixed: number
    failed: number
    success_rate: number
  }>
}

export interface BotMetricsHistory {
  snapshots: BotMetrics[]
  last_updated: string | null
}

// Trace index for fast lookups
export interface TraceIndexEntry {
  repo: string
  pr_number: number
  trace_path: string
  workflow_run_id: string
  timestamp: string
  status?: 'SUCCESS' | 'FAILED' | 'PARTIAL'
}

export interface TraceIndex {
  traces: TraceIndexEntry[]
  last_updated: string
}

// PR summary for overview table
export interface PRSummary extends Record<string, unknown> {
  repo: string
  pr_number: number
  title: string
  author: string
  failure_type: string
  status: 'SUCCESS' | 'FAILED' | 'PARTIAL' | 'IN_PROGRESS'
  fix_time_hours: number | null
  timestamp: string
  trace_path: string
  pr_url: string
  workflow_run_url: string
}

// Authentication types
export interface User {
  email: string
  name: string
  picture?: string
}

export interface SessionData {
  isAuthenticated: boolean
  tokens?: {
    access_token: string
    refresh_token?: string
    expires_at: number
  }
  user?: User
  // OAuth PKCE flow temporary fields
  state?: string
  codeVerifier?: string
  nonce?: string
}
