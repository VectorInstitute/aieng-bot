'use client'

import { useState } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus, vs } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { ChevronDown, ChevronRight, Copy, Check } from 'lucide-react'

interface CodeDiffViewerProps {
  fileName: string
  oldCode?: string
  newCode: string
  language?: string
}

export default function CodeDiffViewer({
  fileName,
  oldCode,
  newCode,
  language = 'typescript',
}: CodeDiffViewerProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [showDiff, setShowDiff] = useState(!!oldCode)
  const [copied, setCopied] = useState(false)
  const [isDark, setIsDark] = useState(true)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(newCode)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  // Simple diff calculation (line by line)
  const calculateDiff = () => {
    if (!oldCode) return null

    const oldLines = oldCode.split('\n')
    const newLines = newCode.split('\n')

    const diff: Array<{ type: 'added' | 'removed' | 'unchanged'; content: string; lineNum?: number }> = []

    // Simple line-by-line comparison
    const maxLength = Math.max(oldLines.length, newLines.length)

    for (let i = 0; i < maxLength; i++) {
      const oldLine = oldLines[i]
      const newLine = newLines[i]

      if (oldLine === newLine) {
        diff.push({ type: 'unchanged', content: newLine || '', lineNum: i + 1 })
      } else {
        if (oldLine !== undefined) {
          diff.push({ type: 'removed', content: oldLine })
        }
        if (newLine !== undefined) {
          diff.push({ type: 'added', content: newLine, lineNum: i + 1 })
        }
      }
    }

    return diff
  }

  const diff = showDiff && oldCode ? calculateDiff() : null

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden bg-white dark:bg-gray-800">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 dark:bg-gray-900/50 border-b border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center space-x-2 text-sm font-medium text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
        >
          {isExpanded ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
          <code className="font-mono">{fileName}</code>
        </button>

        <div className="flex items-center space-x-2">
          {oldCode && (
            <button
              onClick={() => setShowDiff(!showDiff)}
              className="px-3 py-1 text-xs font-medium rounded border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
              {showDiff ? 'Hide Diff' : 'Show Diff'}
            </button>
          )}
          <button
            onClick={handleCopy}
            className="p-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
            title="Copy code"
          >
            {copied ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Content */}
      {isExpanded && (
        <div className="max-h-[600px] overflow-auto">
          {diff ? (
            // Diff view
            <div className="font-mono text-sm">
              {diff.map((line, idx) => {
                const bgColor =
                  line.type === 'added'
                    ? 'bg-green-50 dark:bg-green-900/20'
                    : line.type === 'removed'
                    ? 'bg-red-50 dark:bg-red-900/20'
                    : 'bg-white dark:bg-gray-800'

                const textColor =
                  line.type === 'added'
                    ? 'text-green-900 dark:text-green-200'
                    : line.type === 'removed'
                    ? 'text-red-900 dark:text-red-200'
                    : 'text-gray-900 dark:text-gray-200'

                const prefix =
                  line.type === 'added' ? '+ ' : line.type === 'removed' ? '- ' : '  '

                return (
                  <div
                    key={idx}
                    className={`px-4 py-0.5 ${bgColor} ${textColor} hover:bg-opacity-80 transition-colors`}
                  >
                    <span className="inline-block w-12 text-gray-500 dark:text-gray-500 select-none">
                      {line.lineNum || ''}
                    </span>
                    <span className="select-none mr-2">{prefix}</span>
                    <span>{line.content}</span>
                  </div>
                )
              })}
            </div>
          ) : (
            // Syntax highlighted view
            <SyntaxHighlighter
              language={language}
              style={isDark ? vscDarkPlus : vs}
              showLineNumbers
              customStyle={{
                margin: 0,
                borderRadius: 0,
                background: 'transparent',
              }}
              lineNumberStyle={{
                minWidth: '3em',
                paddingRight: '1em',
                color: '#6b7280',
                userSelect: 'none',
              }}
            >
              {newCode}
            </SyntaxHighlighter>
          )}
        </div>
      )}

      {!isExpanded && (
        <div className="px-4 py-2 text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/30">
          Click to expand code
        </div>
      )}
    </div>
  )
}
