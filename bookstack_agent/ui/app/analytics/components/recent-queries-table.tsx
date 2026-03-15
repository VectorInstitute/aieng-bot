'use client'

import { useState } from 'react'
import { Search, ChevronDown, ChevronUp, Clock, CheckCircle, XCircle, Wrench, User } from 'lucide-react'
import type { BookstackActivity, BookstackTrace } from '@/lib/bookstack-types'

const TOOL_COLORS: Record<string, string> = {
  search_bookstack: 'bg-violet-900/60 text-violet-300 border-violet-700/50',
  get_page: 'bg-blue-900/60 text-blue-300 border-blue-700/50',
  list_books: 'bg-pink-900/60 text-pink-300 border-pink-700/50',
}

const TOOL_SHORT: Record<string, string> = {
  search_bookstack: 'Search',
  get_page: 'Read',
  list_books: 'List',
}

function ToolBadge({ tool }: { tool: string }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium border ${TOOL_COLORS[tool] ?? 'bg-slate-800 text-slate-300 border-slate-600'}`}>
      {TOOL_SHORT[tool] ?? tool}
    </span>
  )
}

function TraceModal({
  activity,
  trace,
  onClose,
}: {
  activity: BookstackActivity
  trace: BookstackTrace | null
  onClose: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-xl border border-white/10 bg-slate-900 shadow-2xl">
        <div className="sticky top-0 bg-slate-900 border-b border-white/10 px-6 py-4 flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <p className="text-xs text-slate-400 mb-1">
              {new Date(activity.timestamp).toLocaleString()} · {activity.duration_seconds.toFixed(1)}s
            </p>
            <p className="text-sm font-semibold text-white leading-snug line-clamp-3">{activity.question}</p>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 text-slate-400 hover:text-white transition-colors text-xl leading-none"
          >
            ✕
          </button>
        </div>

        <div className="p-6 space-y-5">
          {/* Tool calls */}
          {trace && trace.tool_calls.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                Agent Tool Calls
              </p>
              <div className="space-y-2">
                {trace.tool_calls.map((tc) => (
                  <div key={tc.seq} className="rounded-lg border border-white/8 bg-slate-800/60 p-3">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-xs text-slate-500">#{tc.seq}</span>
                      <ToolBadge tool={tc.tool} />
                      {tc.tool === 'get_page' && tc.input.page_title && (
                        <span className="text-xs text-slate-300 font-medium truncate">
                          {String(tc.input.page_title)}
                        </span>
                      )}
                    </div>
                    <pre className="text-xs text-slate-500 whitespace-pre-wrap break-words font-mono leading-relaxed">
                      {tc.tool === 'get_page'
                        ? `page_id: ${tc.input.page_id}`
                        : JSON.stringify(tc.input, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Answer */}
          {trace && trace.answer && (
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                Answer Preview
              </p>
              <div className="rounded-lg border border-white/8 bg-slate-800/60 p-4">
                <p className="text-sm text-slate-300 leading-relaxed line-clamp-10 whitespace-pre-wrap">
                  {trace.answer}
                </p>
              </div>
            </div>
          )}

          {!trace && (
            <p className="text-sm text-slate-500 text-center py-4">
              Trace data not available for this query.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

interface RecentQueriesTableProps {
  activities: BookstackActivity[]
}

export default function RecentQueriesTable({ activities }: RecentQueriesTableProps) {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'success' | 'error'>('all')
  const [page, setPage] = useState(0)
  const [expandedTrace, setExpandedTrace] = useState<{
    activity: BookstackActivity
    trace: BookstackTrace | null
    loading: boolean
  } | null>(null)

  const PAGE_SIZE = 10

  const filtered = activities
    .filter(a => statusFilter === 'all' || a.status === statusFilter)
    .filter(a => !search || a.question.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  const openTrace = async (activity: BookstackActivity) => {
    setExpandedTrace({ activity, trace: null, loading: true })
    try {
      const res = await fetch(
        `/aieng-bot/api/bookstack-trace?path=${encodeURIComponent(activity.trace_path)}`,
      )
      const trace: BookstackTrace | null = res.ok ? await res.json() : null
      setExpandedTrace({ activity, trace, loading: false })
    } catch {
      setExpandedTrace({ activity, trace: null, loading: false })
    }
  }

  return (
    <div className="rounded-xl border border-white/10 bg-slate-800/60 p-6">
      <div className="mb-5">
        <h2 className="text-xl font-bold text-white">Recent Queries</h2>
        <p className="text-sm text-slate-400 mt-0.5">Last 30 days — click a row to view the agent trace</p>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 mb-5">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            placeholder="Search questions…"
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(0) }}
            className="w-full pl-9 pr-3 py-2 text-sm bg-slate-700/60 border border-white/10 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-vector-violet"
          />
        </div>
        <select
          value={statusFilter}
          onChange={e => { setStatusFilter(e.target.value as 'all' | 'success' | 'error'); setPage(0) }}
          className="px-3 py-2 text-sm bg-slate-700/60 border border-white/10 rounded-lg text-slate-200 focus:outline-none focus:ring-1 focus:ring-vector-violet"
        >
          <option value="all">All statuses</option>
          <option value="success">Answered</option>
          <option value="error">Error</option>
        </select>
      </div>

      {/* Table */}
      {paged.length === 0 ? (
        <div className="text-center py-12 text-slate-500 text-sm">
          No queries match your filters.
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="pb-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Question</th>
                  <th className="pb-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider hidden md:table-cell">Tools</th>
                  <th className="pb-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider hidden lg:table-cell">User</th>
                  <th className="pb-3 text-right text-xs font-semibold text-slate-400 uppercase tracking-wider hidden sm:table-cell">Duration</th>
                  <th className="pb-3 text-center text-xs font-semibold text-slate-400 uppercase tracking-wider">Status</th>
                  <th className="pb-3 text-right text-xs font-semibold text-slate-400 uppercase tracking-wider">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {paged.map((activity, i) => (
                  <tr
                    key={`${activity.session_id}-${i}`}
                    className="hover:bg-white/5 cursor-pointer transition-colors group"
                    onClick={() => openTrace(activity)}
                  >
                    <td className="py-3 pr-4">
                      <p className="text-slate-200 line-clamp-2 leading-snug group-hover:text-white transition-colors">
                        {activity.question}
                      </p>
                    </td>
                    <td className="py-3 pr-4 hidden md:table-cell">
                      <div className="flex flex-wrap gap-1">
                        {activity.tools_used.map(t => (
                          <ToolBadge key={t} tool={t} />
                        ))}
                        {activity.num_tool_calls > 0 && (
                          <span className="flex items-center gap-1 text-xs text-slate-500">
                            <Wrench className="w-3 h-3" />
                            {activity.num_tool_calls}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 pr-4 hidden lg:table-cell">
                      {activity.user_email ? (
                        <span className="flex items-center gap-1 text-xs text-slate-400">
                          <User className="w-3 h-3 shrink-0" />
                          <span className="truncate max-w-[140px]">{activity.user_email}</span>
                        </span>
                      ) : (
                        <span className="text-xs text-slate-600">—</span>
                      )}
                    </td>
                    <td className="py-3 pr-4 text-right hidden sm:table-cell">
                      <span className="flex items-center justify-end gap-1 text-slate-400 text-xs">
                        <Clock className="w-3 h-3" />
                        {activity.duration_seconds.toFixed(1)}s
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-center">
                      {activity.status === 'success' ? (
                        <CheckCircle className="w-4 h-4 text-emerald-400 inline-block" />
                      ) : (
                        <XCircle className="w-4 h-4 text-red-400 inline-block" />
                      )}
                    </td>
                    <td className="py-3 text-right text-xs text-slate-500 whitespace-nowrap">
                      {new Date(activity.timestamp).toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4 pt-4 border-t border-white/10">
              <span className="text-xs text-slate-500">
                {filtered.length} queries · page {page + 1} of {totalPages}
              </span>
              <div className="flex gap-2">
                <button
                  disabled={page === 0}
                  onClick={() => setPage(p => p - 1)}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg border border-white/10 text-slate-300 hover:bg-white/5 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronUp className="w-3 h-3 rotate-[-90deg]" /> Prev
                </button>
                <button
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage(p => p + 1)}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg border border-white/10 text-slate-300 hover:bg-white/5 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Next <ChevronDown className="w-3 h-3 rotate-[-90deg]" />
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Trace modal */}
      {expandedTrace && (
        <TraceModal
          activity={expandedTrace.activity}
          trace={expandedTrace.loading ? null : expandedTrace.trace}
          onClose={() => setExpandedTrace(null)}
        />
      )}
    </div>
  )
}
