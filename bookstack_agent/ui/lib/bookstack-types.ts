/**
 * Type definitions for BookStack QA Analytics
 */

/** One entry in the unified activity log — compact form for list/chart views. */
export interface BookstackActivity {
  session_id: string
  timestamp: string
  /** Question text, truncated to 300 chars in the log. */
  question: string
  /** Email of the authenticated user who asked the question, if available. */
  user_email?: string | null
  /** Unique tool names used during this query (e.g. ["search_bookstack", "get_page"]). */
  tools_used: string[]
  /** Total number of individual tool invocations. */
  num_tool_calls: number
  /** Per-tool invocation counts e.g. {"search_bookstack": 2, "get_page": 3}. */
  tool_call_counts?: Record<string, number>
  /** Byte length of the final answer. */
  answer_length: number
  duration_seconds: number
  status: 'success' | 'error'
  /** GCS path to the detailed trace file for this query. */
  trace_path: string
}

export interface BookstackActivityLog {
  activities: BookstackActivity[]
  last_updated: string | null
}

/** One tool call recorded inside a per-query trace file. */
export interface BookstackToolCall {
  seq: number
  tool: 'search_bookstack' | 'get_page' | 'list_books'
  input: Record<string, unknown>
}

/** Full per-query trace file — stored at trace_path in GCS. */
export interface BookstackTrace {
  session_id: string
  timestamp: string
  question: string
  tool_calls: BookstackToolCall[]
  answer: string
  duration_seconds: number
  status: 'success' | 'error'
}

/** Aggregated metrics computed from the activity log. */
export interface BookstackMetrics {
  total_queries: number
  successful_queries: number
  error_queries: number
  success_rate: number
  unique_sessions: number
  unique_users: number
  avg_duration_seconds: number
  avg_tool_calls_per_query: number
  total_tool_calls: number
  /** How many queries landed in the last 24 hours. */
  queries_today: number
  /** How many queries landed in the last 7 days. */
  queries_this_week: number
  tool_usage: {
    search_bookstack: number
    get_page: number
    list_books: number
  }
}
