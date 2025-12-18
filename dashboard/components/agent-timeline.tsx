'use client'

import { useState } from 'react'
import type { AgentEvent } from '@/lib/types'
import { parseAgentMessage } from '@/lib/parse-agent-message'
import {
  Brain,
  Wrench,
  Activity,
  AlertCircle,
  Info,
  ChevronDown,
  ChevronRight,
  FileEdit,
  Search,
  Terminal,
  CheckCircle
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

interface AgentTimelineProps {
  events: AgentEvent[]
}

export default function AgentTimeline({ events }: AgentTimelineProps) {
  const [expandedEvents, setExpandedEvents] = useState<Set<number>>(new Set())

  const toggleEvent = (seq: number) => {
    const newExpanded = new Set(expandedEvents)
    if (newExpanded.has(seq)) {
      newExpanded.delete(seq)
    } else {
      newExpanded.add(seq)
    }
    setExpandedEvents(newExpanded)
  }

  const getEventIcon = (type: string, tool?: string) => {
    // For TOOL_RESULT events, show check icon
    if (type === 'TOOL_RESULT') {
      return <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
    }

    switch (type) {
      case 'REASONING':
        return <Brain className="w-5 h-5 text-purple-600 dark:text-purple-400" />
      case 'TOOL_CALL':
        if (tool === 'Read') return <Search className="w-5 h-5 text-blue-600 dark:text-blue-400" />
        if (tool === 'Edit' || tool === 'Write') return <FileEdit className="w-5 h-5 text-green-600 dark:text-green-400" />
        if (tool === 'Bash') return <Terminal className="w-5 h-5 text-orange-600 dark:text-orange-400" />
        return <Wrench className="w-5 h-5 text-blue-600 dark:text-blue-400" />
      case 'ACTION':
        return <Activity className="w-5 h-5 text-green-600 dark:text-green-400" />
      case 'ERROR':
        return <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400" />
      case 'INFO':
        return <Info className="w-5 h-5 text-gray-600 dark:text-gray-400" />
      default:
        return <Info className="w-5 h-5 text-gray-600 dark:text-gray-400" />
    }
  }

  const getEventColor = (type: string) => {
    switch (type) {
      case 'REASONING':
        return 'border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-900/10'
      case 'TOOL_CALL':
        return 'border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/10'
      case 'TOOL_RESULT':
        return 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/10'
      case 'ACTION':
        return 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/10'
      case 'ERROR':
        return 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/10'
      case 'INFO':
        return 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/10'
      default:
        return 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/10'
    }
  }

  const formatTimestamp = (timestamp: string) => {
    try {
      return formatDistanceToNow(new Date(timestamp), { addSuffix: true })
    } catch {
      return timestamp
    }
  }

  const hasDetails = (event: AgentEvent) => {
    return (
      (event.parameters && Object.keys(event.parameters).length > 0) ||
      event.result_summary
    )
  }

  return (
    <div className="space-y-3">
      {events.length === 0 ? (
        <p className="text-center text-gray-500 dark:text-gray-400 py-8">
          No events recorded
        </p>
      ) : (
        events.map((event, index) => {
          const isExpanded = expandedEvents.has(event.seq)
          const showDetails = hasDetails(event)

          // Parse the content to make it more readable
          const parsed = parseAgentMessage(event.content)
          const displayContent = parsed.content

          return (
            <div
              key={event.seq}
              className={`relative border rounded-lg p-4 transition-all ${getEventColor(event.type)}`}
            >
              {/* Timeline connector */}
              {index < events.length - 1 && (
                <div className="absolute left-8 top-full h-3 w-0.5 bg-gray-300 dark:bg-gray-600" />
              )}

              <div className="flex items-start space-x-3">
                {/* Icon */}
                <div className="flex-shrink-0 mt-0.5">
                  {getEventIcon(event.type, event.tool || parsed.metadata?.tool)}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <div className="flex items-center space-x-2 mb-1">
                        <span className="text-sm font-medium text-gray-900 dark:text-white">
                          {event.type.replace('_', ' ')}
                        </span>
                        {(event.tool || parsed.metadata?.tool) && (
                          <span className="text-xs font-mono px-2 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
                            {event.tool || parsed.metadata?.tool}
                          </span>
                        )}
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          #{event.seq}
                        </span>
                      </div>

                      {/* Display parsed content */}
                      {parsed.type === 'tool_use' && parsed.metadata?.parameters?.command ? (
                        <div className="bg-gray-900 dark:bg-black rounded p-3 overflow-x-auto">
                          <code className="text-xs text-green-400 font-mono">
                            {displayContent}
                          </code>
                        </div>
                      ) : (
                        <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words">
                          {displayContent}
                        </p>
                      )}
                    </div>

                    {/* Expand button */}
                    {showDetails && (
                      <button
                        onClick={() => toggleEvent(event.seq)}
                        className="flex-shrink-0 ml-2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
                      >
                        {isExpanded ? (
                          <ChevronDown className="w-5 h-5" />
                        ) : (
                          <ChevronRight className="w-5 h-5" />
                        )}
                      </button>
                    )}
                  </div>

                  {/* Timestamp */}
                  <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                    {formatTimestamp(event.timestamp)}
                  </div>

                  {/* Expanded details */}
                  {isExpanded && showDetails && (
                    <div className="mt-3 pt-3 border-t border-gray-300 dark:border-gray-600 space-y-3">
                      {/* Parameters */}
                      {event.parameters && Object.keys(event.parameters).length > 0 && (
                        <div>
                          <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
                            Parameters
                          </h4>
                          <div className="bg-gray-100 dark:bg-gray-800 rounded p-3 overflow-x-auto">
                            <pre className="text-xs text-gray-800 dark:text-gray-200 font-mono">
                              {JSON.stringify(event.parameters, null, 2)}
                            </pre>
                          </div>
                        </div>
                      )}

                      {/* Result Summary */}
                      {event.result_summary && (
                        <div>
                          <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
                            Result
                          </h4>
                          <div className="bg-gray-100 dark:bg-gray-800 rounded p-3">
                            <p className="text-xs text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                              {event.result_summary}
                            </p>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )
        })
      )}

      {/* Summary */}
      {events.length > 0 && (
        <div className="mt-6 pt-4 border-t border-gray-200 dark:border-gray-700">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {events.length}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">Total Events</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                {events.filter(e => e.type === 'TOOL_CALL').length}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">Tool Calls</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">
                {events.filter(e => e.type === 'REASONING').length}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">Reasoning</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-red-600 dark:text-red-400">
                {events.filter(e => e.type === 'ERROR').length}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">Errors</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
