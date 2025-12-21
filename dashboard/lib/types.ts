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
      type: 'test' | 'lint' | 'security' | 'build' | 'merge_conflict' | 'unknown'
      checks: string[]
    }
  }
  execution: {
    start_time: string
    end_time?: string | null
    duration_seconds: number | null
    model: string | null
    tools_allowed?: string[]
    metrics?: {
      subtype: 'success' | 'error'
      duration_ms: number
      duration_api_ms: number
      is_error: boolean
      num_turns: number
      session_id: string
      total_cost_usd: number
      usage: {
        input_tokens: number
        cache_creation_input_tokens?: number
        cache_read_input_tokens?: number
        output_tokens: number
        server_tool_use?: {
          web_search_requests: number
          web_fetch_requests: number
        }
        service_tier?: string
        cache_creation?: {
          ephemeral_1h_input_tokens: number
          ephemeral_5m_input_tokens: number
        }
      }
    } | null
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
  type: 'REASONING' | 'TOOL_CALL' | 'TOOL_RESULT' | 'ACTION' | 'ERROR' | 'INFO'
  content: string
  tool?: string
  parameters?: Record<string, unknown>
  result_summary?: string
  tool_use_id?: string
  is_error?: boolean
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

// Bot activity log types (unified view of auto-merges and bot fixes)
export interface BotActivity {
  type: 'auto_merge' | 'bot_fix'
  repo: string
  pr_number: number
  pr_title: string
  pr_author: string
  pr_url: string
  timestamp: string
  workflow_run_id: string
  github_run_url: string
  status: 'SUCCESS' | 'FAILED' | 'PARTIAL'
  // Bot fix fields
  failure_type?: string
  trace_path?: string
  fix_time_hours?: number
  // Auto-merge fields
  was_rebased?: boolean
  rebase_time_seconds?: number
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
  type: 'auto_merge' | 'bot_fix'
  repo: string
  pr_number: number
  title: string
  author: string
  status: 'SUCCESS' | 'FAILED' | 'PARTIAL' | 'IN_PROGRESS'
  timestamp: string
  pr_url: string
  workflow_run_url: string
  // Bot fix specific
  failure_type?: string
  fix_time_hours?: number | null
  trace_path?: string
  // Auto-merge specific
  was_rebased?: boolean
  rebase_time_seconds?: number | null
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
