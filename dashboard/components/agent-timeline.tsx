'use client'

import { useState, useMemo } from 'react'
import type { AgentEvent } from '@/lib/types'
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
  CheckCircle,
  CornerDownRight,
  Globe
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

interface AgentTimelineProps {
  events: AgentEvent[]
}

interface HierarchicalEvent {
  event: AgentEvent
  result?: AgentEvent
}

export default function AgentTimeline({ events }: AgentTimelineProps) {
  // Start with all events collapsed by default
  const [expandedEvents, setExpandedEvents] = useState<Set<number>>(new Set())

  // Transform flat events into hierarchical structure
  const hierarchicalEvents = useMemo(() => {
    const rootEvents: HierarchicalEvent[] = []
    const resultEvents = new Map<string, AgentEvent>()

    // First pass: collect all TOOL_RESULT events
    events.forEach(event => {
      if (event.type === 'TOOL_RESULT' && event.tool_use_id) {
        resultEvents.set(event.tool_use_id, event)
      }
    })

    // Second pass: build hierarchical structure
    events.forEach(event => {
      if (event.type === 'TOOL_RESULT') {
        // Skip TOOL_RESULT events in root - they'll be nested under TOOL_CALL
        return
      }

      const hierarchicalEvent: HierarchicalEvent = { event }

      // If this is a TOOL_CALL with a tool_use_id, attach its result
      if (event.type === 'TOOL_CALL' && event.tool_use_id) {
        const result = resultEvents.get(event.tool_use_id)
        if (result) {
          hierarchicalEvent.result = result
        }
      }

      rootEvents.push(hierarchicalEvent)
    })

    return rootEvents
  }, [events])

  const toggleEvent = (seq: number) => {
    const newExpanded = new Set(expandedEvents)
    if (newExpanded.has(seq)) {
      newExpanded.delete(seq)
    } else {
      newExpanded.add(seq)
    }
    setExpandedEvents(newExpanded)
  }

  const expandAll = () => {
    setExpandedEvents(new Set(hierarchicalEvents.map(e => e.event.seq)))
  }

  const collapseAll = () => {
    setExpandedEvents(new Set())
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
        if (tool === 'WebSearch') return <Globe className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
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

  const renderEventContent = (event: AgentEvent, isExpanded: boolean, isBashCommand: boolean) => {
    const displayContent = event.content

    return (
      <>
        {/* Compact header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2 flex-1 min-w-0">
            <span className="text-xs font-semibold text-gray-900 dark:text-white uppercase tracking-wide">
              {event.type.replace('_', ' ')}
            </span>
            {event.tool && (
              <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
                {event.tool}
              </span>
            )}
            <span className="text-xs text-gray-400">
              #{event.seq}
            </span>
            {/* Preview of content when collapsed */}
            {!isExpanded && (
              <span className="text-xs text-gray-500 dark:text-gray-400 truncate flex-1 min-w-0">
                {displayContent.split('\n')[0].substring(0, 60)}
                {displayContent.length > 60 && '...'}
              </span>
            )}
          </div>

          <div className="flex items-center space-x-2 flex-shrink-0">
            {/* Timestamp */}
            <span className="text-xs text-gray-400">
              {formatTimestamp(event.timestamp)}
            </span>
            {/* Expand button */}
            <div className="text-gray-400">
              {isExpanded ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
            </div>
          </div>
        </div>

        {/* Expanded content */}
        {isExpanded && (
          <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700" onClick={(e) => e.stopPropagation()}>
            {/* Display content - special formatting for bash commands */}
            {isBashCommand ? (
              <div className="bg-gray-900 dark:bg-black rounded p-3 overflow-x-auto">
                <code className="text-xs text-green-400 font-mono">
                  {displayContent}
                </code>
              </div>
            ) : (
              <div className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words max-h-96 overflow-y-auto">
                {displayContent}
              </div>
            )}

            {/* Additional details when expanded */}
            {hasDetails(event) && (
              <div className="mt-3 space-y-3">
                {/* Parameters */}
                {event.parameters && Object.keys(event.parameters).length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5">
                      Parameters
                    </h4>
                    <div className="bg-gray-100 dark:bg-gray-800 rounded p-2 overflow-x-auto">
                      <pre className="text-xs text-gray-800 dark:text-gray-200 font-mono">
                        {JSON.stringify(event.parameters, null, 2)}
                      </pre>
                    </div>
                  </div>
                )}

                {/* Result Summary */}
                {event.result_summary && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5">
                      Result
                    </h4>
                    <div className="bg-gray-100 dark:bg-gray-800 rounded p-2">
                      <p className="text-xs text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                        {event.result_summary}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </>
    )
  }

  return (
    <div className="space-y-3">
      {/* Expand/Collapse controls */}
      {hierarchicalEvents.length > 0 && (
        <div className="flex items-center justify-between mb-4 pb-3 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center space-x-2">
            <Activity className="w-5 h-5 text-gray-600 dark:text-gray-400" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Agent Execution Timeline
            </h3>
            <span className="text-sm text-gray-500 dark:text-gray-400">
              ({hierarchicalEvents.length} steps)
            </span>
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={expandAll}
              className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
            >
              Expand All
            </button>
            <span className="text-gray-400">|</span>
            <button
              onClick={collapseAll}
              className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
            >
              Collapse All
            </button>
          </div>
        </div>
      )}

      {hierarchicalEvents.length === 0 ? (
        <p className="text-center text-gray-500 dark:text-gray-400 py-8">
          No events recorded
        </p>
      ) : (
        hierarchicalEvents.map((hierarchicalEvent, index) => {
          const event = hierarchicalEvent.event
          const result = hierarchicalEvent.result
          const isExpanded = expandedEvents.has(event.seq)
          const displayContent = event.content
          const isBashCommand = event.type === 'TOOL_CALL' && event.tool === 'Bash' && displayContent.startsWith('$')

          return (
            <div key={event.seq} className="relative">
              {/* Main event */}
              <div
                className={`relative border rounded-lg transition-all hover:shadow-md cursor-pointer ${getEventColor(event.type)}`}
                onClick={() => toggleEvent(event.seq)}
              >
                {/* Timeline connector */}
                {index < hierarchicalEvents.length - 1 && (
                  <div className="absolute left-6 top-full h-3 w-0.5 bg-gray-300 dark:bg-gray-600" />
                )}

                <div className="flex items-start space-x-3 p-3">
                  {/* Icon */}
                  <div className="flex-shrink-0 mt-0.5">
                    {getEventIcon(event.type, event.tool)}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    {renderEventContent(event, isExpanded, isBashCommand)}
                  </div>
                </div>
              </div>

              {/* Nested tool result (if exists and parent is expanded) */}
              {result && isExpanded && (
                <div className="ml-8 mt-2 relative">
                  {/* Connector line */}
                  <div className="absolute left-2 top-0 bottom-0 w-0.5 bg-gray-300 dark:bg-gray-600" />
                  <div className="absolute left-2 top-4 w-4 h-0.5 bg-gray-300 dark:bg-gray-600" />

                  {/* Tool result card */}
                  <div
                    className={`ml-6 border rounded-lg transition-all ${getEventColor('TOOL_RESULT')}`}
                  >
                    <div className="flex items-start space-x-3 p-3">
                      {/* Result icon */}
                      <div className="flex-shrink-0 mt-0.5">
                        <CornerDownRight className="w-4 h-4 text-gray-400 dark:text-gray-500" />
                      </div>

                      {/* Result content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center space-x-2 mb-2">
                          <CheckCircle className="w-4 h-4 text-green-600 dark:text-green-400" />
                          <span className="text-xs font-semibold text-gray-900 dark:text-white uppercase tracking-wide">
                            Result
                          </span>
                          <span className="text-xs text-gray-400">
                            #{result.seq}
                          </span>
                        </div>

                        {/* Result content */}
                        <div className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words max-h-64 overflow-y-auto bg-gray-50 dark:bg-gray-800/50 rounded p-2">
                          {result.content}
                        </div>

                        {/* Result summary if available */}
                        {result.result_summary && (
                          <div className="mt-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                            <p className="text-xs text-gray-600 dark:text-gray-400">
                              {result.result_summary}
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )
        })
      )}

      {/* Summary */}
      {events.length > 0 && (
        <div className="mt-6 pt-4 border-t border-gray-200 dark:border-gray-700">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {events.length}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">Events</p>
            </div>
            <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20">
              <p className="text-xl font-bold text-blue-600 dark:text-blue-400">
                {events.filter(e => e.type === 'TOOL_CALL').length}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">Tool Calls</p>
            </div>
            <div className="p-3 rounded-lg bg-purple-50 dark:bg-purple-900/20">
              <p className="text-xl font-bold text-purple-600 dark:text-purple-400">
                {events.filter(e => e.type === 'REASONING').length}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">Reasoning</p>
            </div>
            <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20">
              <p className="text-xl font-bold text-red-600 dark:text-red-400">
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
