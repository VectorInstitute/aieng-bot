'use client'

import { Sparkles, CheckCircle, XCircle, Clock } from 'lucide-react'
import { format } from 'date-fns'

interface SkillCall {
  skill: string
  timestamp: string
  success: boolean
  seq: number
}

interface SkillsUsageProps {
  events: Array<{
    seq: number
    timestamp: string
    type: string
    tool?: string
    parameters?: {
      skill?: string
    }
    content?: string
  }>
}

export default function SkillsUsage({ events }: SkillsUsageProps) {
  // Extract skill calls from events
  const skillCalls: SkillCall[] = events
    .filter((event) => event.type === 'TOOL_CALL' && event.tool === 'Skill')
    .map((event) => {
      const nextEvent = events.find(
        (e) => e.seq === event.seq + 1 && (e.type === 'TOOL_RESULT' || e.type === 'ERROR')
      )
      return {
        skill: event.parameters?.skill || 'unknown',
        timestamp: event.timestamp,
        success: nextEvent?.type === 'TOOL_RESULT',
        seq: event.seq,
      }
    })

  if (skillCalls.length === 0) {
    return null
  }

  // Get unique skills (in case of retries, we only show the latest attempt)
  const uniqueSkills = skillCalls.reduce(
    (acc, call) => {
      acc[call.skill] = call
      return acc
    },
    {} as Record<string, SkillCall>
  )

  const skillsUsed = Object.values(uniqueSkills)
  const successfulSkills = skillsUsed.filter((s) => s.success)
  const failedSkills = skillsUsed.filter((s) => !s.success)

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center space-x-2 mb-4">
        <Sparkles className="w-5 h-5 text-purple-600 dark:text-purple-400" />
        <h2 className="text-xl font-bold text-gray-900 dark:text-white">Skills Discovered & Used</h2>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-3">
          <p className="text-xs text-purple-600 dark:text-purple-400 uppercase tracking-wide">
            Skills Invoked
          </p>
          <p className="text-2xl font-bold text-purple-900 dark:text-purple-100 mt-1">
            {skillsUsed.length}
          </p>
        </div>
        <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-3">
          <p className="text-xs text-green-600 dark:text-green-400 uppercase tracking-wide">
            Successful
          </p>
          <p className="text-2xl font-bold text-green-900 dark:text-green-100 mt-1">
            {successfulSkills.length}
          </p>
        </div>
        <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-3">
          <p className="text-xs text-red-600 dark:text-red-400 uppercase tracking-wide">Failed</p>
          <p className="text-2xl font-bold text-red-900 dark:text-red-100 mt-1">
            {failedSkills.length}
          </p>
        </div>
      </div>

      {/* Skills List */}
      <div className="space-y-3">
        {skillsUsed.map((call) => (
          <div
            key={call.skill}
            className={`flex items-start space-x-3 p-4 rounded-lg border-l-4 ${
              call.success
                ? 'bg-green-50 dark:bg-green-900/10 border-green-500'
                : 'bg-red-50 dark:bg-red-900/10 border-red-500'
            }`}
          >
            <div className="flex-shrink-0 mt-0.5">
              {call.success ? (
                <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
              ) : (
                <XCircle className="w-5 h-5 text-red-600 dark:text-red-400" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center space-x-2 mb-1">
                <code className="text-sm font-semibold text-gray-900 dark:text-white">
                  {call.skill}
                </code>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    call.success
                      ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                      : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                  }`}
                >
                  {call.success ? 'Executed' : 'Failed'}
                </span>
              </div>
              <div className="flex items-center space-x-2 text-xs text-gray-500 dark:text-gray-400">
                <Clock className="w-3 h-3" />
                <time dateTime={call.timestamp}>
                  {format(new Date(call.timestamp), 'h:mm:ss a')} (step {call.seq})
                </time>
              </div>
              {call.success && (
                <p className="mt-2 text-sm text-gray-700 dark:text-gray-300">
                  Skill loaded from{' '}
                  <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded">
                    .claude/skills/{call.skill}/SKILL.md
                  </code>
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
