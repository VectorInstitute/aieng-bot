'use client'

import { useState } from 'react'
import { AlertCircle, ChevronDown, ChevronRight, AlertTriangle, Shield, Wrench, Code } from 'lucide-react'

interface FailureAnalysisProps {
  failure: {
    type: string  // Primary type for backward compatibility
    types?: string[]  // Array of all failure types
    checks: string[]
  }
}

export default function FailureAnalysis({ failure }: FailureAnalysisProps) {
  const [isExpanded, setIsExpanded] = useState(true)

  // Get all failure types (use types array if available, otherwise fall back to single type)
  const failureTypes = failure.types && failure.types.length > 0
    ? failure.types
    : [failure.type]

  const hasMultipleTypes = failureTypes.length > 1

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
      case 'merge_conflict':
        return <AlertCircle className="w-6 h-6 text-pink-600 dark:text-pink-400" />
      case 'merge_only':
        return <Code className="w-6 h-6 text-green-600 dark:text-green-400" />
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
      case 'merge_conflict':
        return 'border-pink-200 dark:border-pink-800 bg-pink-50 dark:bg-pink-900/10'
      case 'merge_only':
        return 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/10'
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
      case 'merge_conflict':
        return 'Merge conflicts detected. The bot analyzed conflicting files and resolved conflicts following best practices.'
      case 'merge_only':
        return 'No failures detected. The bot rebased the PR and merged it successfully.'
      default:
        return 'Unclassified failure detected. The bot attempted to diagnose and resolve the issue.'
    }
  }

  // Format types for display
  const typesDisplay = failureTypes.map(t => t.charAt(0).toUpperCase() + t.slice(1)).join(', ')

  return (
    <div className={`border rounded-lg overflow-hidden ${getFailureColor(failureTypes[0])}`}>
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 cursor-pointer border-b border-current/10"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-1">
            {hasMultipleTypes ? (
              // Show multiple icons for multiple types
              failureTypes.slice(0, 3).map((type, idx) => (
                <span key={idx} className={idx > 0 ? '-ml-2' : ''}>
                  {getFailureIcon(type)}
                </span>
              ))
            ) : (
              getFailureIcon(failureTypes[0])
            )}
          </div>
          <div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">
              Failure Analysis: {typesDisplay}
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {hasMultipleTypes && <span className="font-medium">{failureTypes.length} failure types detected • </span>}
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
          {/* Description - show for each failure type */}
          {failureTypes.map((type, idx) => (
            <div key={idx} className="bg-white/50 dark:bg-gray-800/50 rounded-lg p-4">
              {hasMultipleTypes && (
                <div className="flex items-center space-x-2 mb-2">
                  {getFailureIcon(type)}
                  <span className="text-sm font-semibold text-gray-900 dark:text-white capitalize">
                    {type} Failure
                  </span>
                </div>
              )}
              <p className="text-sm text-gray-700 dark:text-gray-300">
                {getFailureDescription(type)}
              </p>
            </div>
          ))}

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

          {/* Insights - show strategies for all failure types */}
          <div className="bg-white/50 dark:bg-gray-800/50 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
              Resolution {hasMultipleTypes ? 'Strategies' : 'Strategy'}
            </h4>
            <ul className="space-y-2 text-sm text-gray-700 dark:text-gray-300">
              {failureTypes.includes('test') && (
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
              {failureTypes.includes('lint') && (
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
              {failureTypes.includes('security') && (
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
              {failureTypes.includes('build') && (
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
              {failureTypes.includes('merge_conflict') && (
                <>
                  <li className="flex items-start space-x-2">
                    <span className="text-pink-600 dark:text-pink-400 mt-0.5">•</span>
                    <span>Identified conflicting files and conflict markers</span>
                  </li>
                  <li className="flex items-start space-x-2">
                    <span className="text-pink-600 dark:text-pink-400 mt-0.5">•</span>
                    <span>For lock files: regenerated from dependency manifest</span>
                  </li>
                  <li className="flex items-start space-x-2">
                    <span className="text-pink-600 dark:text-pink-400 mt-0.5">•</span>
                    <span>For source files: merged changes preserving functionality</span>
                  </li>
                  <li className="flex items-start space-x-2">
                    <span className="text-pink-600 dark:text-pink-400 mt-0.5">•</span>
                    <span>Validated successful merge and removed conflict markers</span>
                  </li>
                </>
              )}
              {failureTypes.includes('merge_only') && (
                <>
                  <li className="flex items-start space-x-2">
                    <span className="text-green-600 dark:text-green-400 mt-0.5">•</span>
                    <span>Checked if PR branch needed rebasing</span>
                  </li>
                  <li className="flex items-start space-x-2">
                    <span className="text-green-600 dark:text-green-400 mt-0.5">•</span>
                    <span>Rebased onto latest main branch if needed</span>
                  </li>
                  <li className="flex items-start space-x-2">
                    <span className="text-green-600 dark:text-green-400 mt-0.5">•</span>
                    <span>Waited for CI to pass and merged the PR</span>
                  </li>
                </>
              )}
              {failureTypes.some(t => !['test', 'lint', 'security', 'build', 'merge_conflict', 'merge_only'].includes(t)) && (
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
