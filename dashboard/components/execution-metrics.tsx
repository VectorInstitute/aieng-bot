'use client'

import type { AgentTrace } from '@/lib/types'
import {
  Clock,
  DollarSign,
  BarChart3,
  CheckCircle2,
  XCircle,
  ArrowRightLeft,
  Database
} from 'lucide-react'

interface ExecutionMetricsProps {
  trace: AgentTrace
}

export default function ExecutionMetrics({ trace }: ExecutionMetricsProps) {
  const metrics = trace.execution.metrics

  if (!metrics) {
    return null
  }

  const isSuccess = metrics.subtype === 'success' && !metrics.is_error
  const durationSeconds = metrics.duration_ms / 1000
  const apiDurationSeconds = metrics.duration_api_ms / 1000
  const usage = metrics.usage || {}

  // Calculate token efficiency (with safe defaults)
  const inputTokens = usage.input_tokens || 0
  const outputTokens = usage.output_tokens || 0
  const cacheReadTokens = usage.cache_read_input_tokens || 0
  const cacheCreateTokens = usage.cache_creation_input_tokens || 0

  const totalTokens = inputTokens + outputTokens
  const cacheHitRate = cacheReadTokens
    ? ((cacheReadTokens / (inputTokens + cacheReadTokens)) * 100)
    : 0

  // Calculate cost breakdown
  const inputCost = inputTokens * 0.003 / 1000 // $3 per million
  const outputCost = outputTokens * 0.015 / 1000 // $15 per million
  const cacheCost = cacheCreateTokens * 0.00375 / 1000 // $3.75 per million
  const cacheReadCost = cacheReadTokens * 0.0003 / 1000 // $0.30 per million

  return (
    <div className="space-y-6">
      {/* Header with status */}
      <div className="flex items-center space-x-3 pb-4 border-b border-gray-200 dark:border-gray-700">
        {isSuccess ? (
          <CheckCircle2 className="w-6 h-6 text-green-600 dark:text-green-400" />
        ) : (
          <XCircle className="w-6 h-6 text-red-600 dark:text-red-400" />
        )}
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Execution Metrics
          </h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {metrics.num_turns} turns · Session: {metrics.session_id.substring(0, 8)}
          </p>
        </div>
      </div>

      {/* Key metrics cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Duration */}
        <div className="p-4 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
          <div className="flex items-center space-x-2 mb-2">
            <Clock className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            <span className="text-xs font-semibold text-blue-900 dark:text-blue-300 uppercase tracking-wide">
              Duration
            </span>
          </div>
          <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
            {durationSeconds.toFixed(1)}s
          </p>
          <p className="text-xs text-blue-600/70 dark:text-blue-400/70">
            {apiDurationSeconds.toFixed(1)}s API time
          </p>
        </div>

        {/* Cost */}
        <div className="p-4 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800">
          <div className="flex items-center space-x-2 mb-2">
            <DollarSign className="w-4 h-4 text-green-600 dark:text-green-400" />
            <span className="text-xs font-semibold text-green-900 dark:text-green-300 uppercase tracking-wide">
              Cost
            </span>
          </div>
          <p className="text-2xl font-bold text-green-600 dark:text-green-400">
            ${metrics.total_cost_usd.toFixed(4)}
          </p>
          <p className="text-xs text-green-600/70 dark:text-green-400/70">
            ${(metrics.total_cost_usd / metrics.num_turns).toFixed(4)} per turn
          </p>
        </div>

        {/* Turns */}
        <div className="p-4 rounded-lg bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800">
          <div className="flex items-center space-x-2 mb-2">
            <ArrowRightLeft className="w-4 h-4 text-purple-600 dark:text-purple-400" />
            <span className="text-xs font-semibold text-purple-900 dark:text-purple-300 uppercase tracking-wide">
              Turns
            </span>
          </div>
          <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">
            {metrics.num_turns}
          </p>
          <p className="text-xs text-purple-600/70 dark:text-purple-400/70">
            Agent iterations
          </p>
        </div>

        {/* Tokens */}
        <div className="p-4 rounded-lg bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800">
          <div className="flex items-center space-x-2 mb-2">
            <BarChart3 className="w-4 h-4 text-orange-600 dark:text-orange-400" />
            <span className="text-xs font-semibold text-orange-900 dark:text-orange-300 uppercase tracking-wide">
              Tokens
            </span>
          </div>
          <p className="text-2xl font-bold text-orange-600 dark:text-orange-400">
            {(totalTokens / 1000).toFixed(1)}k
          </p>
          <p className="text-xs text-orange-600/70 dark:text-orange-400/70">
            {inputTokens.toLocaleString()} in / {outputTokens.toLocaleString()} out
          </p>
        </div>
      </div>

      {/* Detailed breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Token usage breakdown */}
        <div className="p-4 rounded-lg bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700">
          <div className="flex items-center space-x-2 mb-3">
            <Database className="w-4 h-4 text-gray-600 dark:text-gray-400" />
            <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Token Usage</h4>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Input tokens:</span>
              <span className="font-medium text-gray-900 dark:text-white">
                {inputTokens.toLocaleString()}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Output tokens:</span>
              <span className="font-medium text-gray-900 dark:text-white">
                {outputTokens.toLocaleString()}
              </span>
            </div>
            {cacheReadTokens > 0 && (
              <div className="flex justify-between text-green-600 dark:text-green-400">
                <span>Cache read ({cacheHitRate.toFixed(1)}% hit rate):</span>
                <span className="font-medium">
                  {cacheReadTokens.toLocaleString()}
                </span>
              </div>
            )}
            {cacheCreateTokens > 0 && (
              <div className="flex justify-between text-blue-600 dark:text-blue-400">
                <span>Cache creation:</span>
                <span className="font-medium">
                  {cacheCreateTokens.toLocaleString()}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Cost breakdown */}
        <div className="p-4 rounded-lg bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700">
          <div className="flex items-center space-x-2 mb-3">
            <DollarSign className="w-4 h-4 text-gray-600 dark:text-gray-400" />
            <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Cost Breakdown</h4>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Input tokens:</span>
              <span className="font-medium text-gray-900 dark:text-white">
                ${inputCost.toFixed(4)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Output tokens:</span>
              <span className="font-medium text-gray-900 dark:text-white">
                ${outputCost.toFixed(4)}
              </span>
            </div>
            {cacheCost > 0 && (
              <div className="flex justify-between text-blue-600 dark:text-blue-400">
                <span>Cache creation:</span>
                <span className="font-medium">
                  ${cacheCost.toFixed(4)}
                </span>
              </div>
            )}
            {cacheReadCost > 0 && (
              <div className="flex justify-between text-green-600 dark:text-green-400">
                <span>Cache read (saved ${(cacheReadTokens * (0.003 - 0.0003) / 1000).toFixed(4)}):</span>
                <span className="font-medium">
                  ${cacheReadCost.toFixed(4)}
                </span>
              </div>
            )}
            <div className="pt-2 border-t border-gray-300 dark:border-gray-600 flex justify-between font-semibold">
              <span className="text-gray-900 dark:text-white">Total:</span>
              <span className="text-gray-900 dark:text-white">
                ${metrics.total_cost_usd.toFixed(4)}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
