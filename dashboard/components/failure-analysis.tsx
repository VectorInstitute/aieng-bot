'use client'

import { useState } from 'react'
import { AlertCircle, ChevronDown, ChevronRight, AlertTriangle, Shield, Wrench, Code } from 'lucide-react'

interface FailureAnalysisProps {
  failure: {
    type: 'test' | 'lint' | 'security' | 'build' | 'unknown'
    checks: string[]
    logs_truncated: string
  }
}

export default function FailureAnalysis({ failure }: FailureAnalysisProps) {
  const [isExpanded, setIsExpanded] = useState(true)
  const [showFullLogs, setShowFullLogs] = useState(false)

  const getFailureIcon = (type: string) => {
    switch (type) {
      case 'test':
        return <AlertCircle className="w-6 h-6 text-purple-600 dark:text-purple-400" />
      case 'lint':
        return <Wrench className="w-6 h-6 text-blue-600 dark:text-blue-400" />
      case 'security':
        return <Shield className="w-6 h-6 text-red-600 dark:text-red-400" />
      case 'build':
        return <Code className="w-6 h-6 text-orange-600 dark:text-orange-400" />
      default:
        return <AlertTriangle className="w-6 h-6 text-yellow-600 dark:text-yellow-400" />
    }
  }

  const getFailureColor = (type: string) => {
    switch (type) {
      case 'test':
        return 'border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-900/10'
      case 'lint':
        return 'border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/10'
      case 'security':
        return 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/10'
      case 'build':
        return 'border-orange-200 dark:border-orange-800 bg-orange-50 dark:bg-orange-900/10'
      default:
        return 'border-yellow-200 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-900/10'
    }
  }

  const getFailureDescription = (type: string) => {
    switch (type) {
      case 'test':
        return 'Test suite failures detected. The bot analyzed failing tests and applied fixes to restore functionality.'
      case 'lint':
        return 'Code style and linting issues detected. The bot automatically reformatted and fixed code quality issues.'
      case 'security':
        return 'Security vulnerabilities detected. The bot analyzed and resolved security issues in dependencies.'
      case 'build':
        return 'Build compilation errors detected. The bot fixed configuration and code issues to restore builds.'
      default:
        return 'Unclassified failure detected. The bot attempted to diagnose and resolve the issue.'
    }
  }

  // Process logs for better display
  const processedLogs = failure.logs_truncated
  const logLines = processedLogs.split('\n')
  const displayLogs = showFullLogs ? processedLogs : logLines.slice(0, 50).join('\n')
  const hasMoreLogs = logLines.length > 50

  return (
    <div className={`border rounded-lg overflow-hidden ${getFailureColor(failure.type)}`}>
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 cursor-pointer border-b border-current/10"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center space-x-3">
          {getFailureIcon(failure.type)}
          <div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">
              Failure Analysis: {failure.type.charAt(0).toUpperCase() + failure.type.slice(1)}
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {failure.checks.length} check{failure.checks.length !== 1 ? 's' : ''} failed
            </p>
          </div>
        </div>
        {isExpanded ? (
          <ChevronDown className="w-5 h-5 text-gray-600 dark:text-gray-400" />
        ) : (
          <ChevronRight className="w-5 h-5 text-gray-600 dark:text-gray-400" />
        )}
      </div>

      {/* Content */}
      {isExpanded && (
        <div className="p-4 space-y-4">
          {/* Description */}
          <div className="bg-white/50 dark:bg-gray-800/50 rounded-lg p-4">
            <p className="text-sm text-gray-700 dark:text-gray-300">
              {getFailureDescription(failure.type)}
            </p>
          </div>

          {/* Failed Checks */}
          <div>
            <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
              Failed Checks
            </h4>
            <div className="space-y-1">
              {failure.checks.map((check, idx) => (
                <div
                  key={idx}
                  className="flex items-center space-x-2 text-sm text-gray-700 dark:text-gray-300"
                >
                  <AlertCircle className="w-4 h-4 text-red-500" />
                  <code className="font-mono bg-white/50 dark:bg-gray-800/50 px-2 py-0.5 rounded">
                    {check}
                  </code>
                </div>
              ))}
            </div>
          </div>

          {/* Failure Logs */}
          {processedLogs && processedLogs.trim() && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-semibold text-gray-900 dark:text-white">
                  Failure Logs
                </h4>
                {hasMoreLogs && (
                  <button
                    onClick={() => setShowFullLogs(!showFullLogs)}
                    className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    {showFullLogs ? 'Show Less' : `Show All (${logLines.length} lines)`}
                  </button>
                )}
              </div>
              <div className="bg-gray-900 dark:bg-black rounded-lg p-4 overflow-x-auto max-h-[400px] overflow-y-auto">
                <pre className="text-xs text-gray-100 font-mono whitespace-pre-wrap break-words">
                  {displayLogs}
                </pre>
              </div>
              {!showFullLogs && hasMoreLogs && (
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                  Showing first 50 lines. Click &quot;Show All&quot; to see complete logs.
                </p>
              )}
            </div>
          )}

          {/* Insights */}
          <div className="bg-white/50 dark:bg-gray-800/50 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
              Resolution Strategy
            </h4>
            <ul className="space-y-2 text-sm text-gray-700 dark:text-gray-300">
              {failure.type === 'test' && (
                <>
                  <li className="flex items-start space-x-2">
                    <span className="text-purple-600 dark:text-purple-400 mt-0.5">•</span>
                    <span>Analyzed test failures and identified breaking changes</span>
                  </li>
                  <li className="flex items-start space-x-2">
                    <span className="text-purple-600 dark:text-purple-400 mt-0.5">•</span>
                    <span>Updated test assertions and mocks to match new behavior</span>
                  </li>
                  <li className="flex items-start space-x-2">
                    <span className="text-purple-600 dark:text-purple-400 mt-0.5">•</span>
                    <span>Verified fixes preserve original test intent</span>
                  </li>
                </>
              )}
              {failure.type === 'lint' && (
                <>
                  <li className="flex items-start space-x-2">
                    <span className="text-blue-600 dark:text-blue-400 mt-0.5">•</span>
                    <span>Ran auto-fix commands for linting and formatting</span>
                  </li>
                  <li className="flex items-start space-x-2">
                    <span className="text-blue-600 dark:text-blue-400 mt-0.5">•</span>
                    <span>Applied code style corrections following project conventions</span>
                  </li>
                  <li className="flex items-start space-x-2">
                    <span className="text-blue-600 dark:text-blue-400 mt-0.5">•</span>
                    <span>Validated all linting rules pass</span>
                  </li>
                </>
              )}
              {failure.type === 'security' && (
                <>
                  <li className="flex items-start space-x-2">
                    <span className="text-red-600 dark:text-red-400 mt-0.5">•</span>
                    <span>Identified vulnerable dependencies</span>
                  </li>
                  <li className="flex items-start space-x-2">
                    <span className="text-red-600 dark:text-red-400 mt-0.5">•</span>
                    <span>Updated to patched versions or applied workarounds</span>
                  </li>
                  <li className="flex items-start space-x-2">
                    <span className="text-red-600 dark:text-red-400 mt-0.5">•</span>
                    <span>Verified security scans pass</span>
                  </li>
                </>
              )}
              {failure.type === 'build' && (
                <>
                  <li className="flex items-start space-x-2">
                    <span className="text-orange-600 dark:text-orange-400 mt-0.5">•</span>
                    <span>Analyzed build errors and dependency issues</span>
                  </li>
                  <li className="flex items-start space-x-2">
                    <span className="text-orange-600 dark:text-orange-400 mt-0.5">•</span>
                    <span>Fixed type errors and missing imports</span>
                  </li>
                  <li className="flex items-start space-x-2">
                    <span className="text-orange-600 dark:text-orange-400 mt-0.5">•</span>
                    <span>Validated successful compilation</span>
                  </li>
                </>
              )}
              {failure.type === 'unknown' && (
                <>
                  <li className="flex items-start space-x-2">
                    <span className="text-yellow-600 dark:text-yellow-400 mt-0.5">•</span>
                    <span>Analyzed failure logs to identify issue type</span>
                  </li>
                  <li className="flex items-start space-x-2">
                    <span className="text-yellow-600 dark:text-yellow-400 mt-0.5">•</span>
                    <span>Applied general-purpose fixes</span>
                  </li>
                  <li className="flex items-start space-x-2">
                    <span className="text-yellow-600 dark:text-yellow-400 mt-0.5">•</span>
                    <span>Verified resolution</span>
                  </li>
                </>
              )}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}
