/**
 * Parse agent SDK message string representations to extract readable content
 */

export interface ParsedMessage {
  type: 'text' | 'tool_use' | 'tool_result' | 'system'
  content: string
  metadata?: {
    tool?: string
    toolUseId?: string
    isError?: boolean
    [key: string]: any
  }
}

/**
 * Extract content from TextBlock string
 * Example: TextBlock(text="Some text here")
 */
function parseTextBlock(input: string): ParsedMessage | null {
  const match = input.match(/TextBlock\(text=["'](.*)["']\)$/s)
  if (match) {
    return {
      type: 'text',
      content: match[1]
        .replace(/\\n/g, '\n')
        .replace(/\\'/g, "'")
        .replace(/\\"/g, '"')
    }
  }
  return null
}

/**
 * Extract content from ToolUseBlock string
 * Example: ToolUseBlock(id='toolu_123', name='Bash', input={'command': 'ls -la'})
 */
function parseToolUseBlock(input: string): ParsedMessage | null {
  // Extract tool name
  const nameMatch = input.match(/name=['"](\w+)['"]/)
  const tool = nameMatch ? nameMatch[1] : 'Unknown'

  // Extract input parameters
  const inputMatch = input.match(/input=(\{.*\})/)
  let content = `Tool: ${tool}`
  let metadata: any = { tool }

  if (inputMatch) {
    try {
      // Try to parse the input as JSON-like structure
      const inputStr = inputMatch[1]
        .replace(/'/g, '"')
        .replace(/True/g, 'true')
        .replace(/False/g, 'false')
        .replace(/None/g, 'null')

      const params = JSON.parse(inputStr)
      metadata.parameters = params

      // Format common parameters nicely
      if (params.command) {
        content = `$ ${params.command}`
      } else if (params.file_path) {
        content = `Read: ${params.file_path}`
      } else if (params.old_string && params.new_string) {
        content = `Edit file: ${params.file_path || 'unknown'}`
      } else {
        content = `${tool}: ${JSON.stringify(params, null, 2)}`
      }
    } catch (e) {
      // If parsing fails, just show the tool name
      content = `Tool: ${tool}`
    }
  }

  return {
    type: 'tool_use',
    content,
    metadata
  }
}

/**
 * Extract content from ToolResultBlock string
 * Example: ToolResultBlock(tool_use_id='toolu_123', content='Result here', is_error=False)
 */
function parseToolResultBlock(input: string): ParsedMessage | null {
  // Extract content
  const contentMatch = input.match(/content=['"](.*)['"],?\s*is_error/)
  if (!contentMatch) {
    // Try simpler match without is_error
    const simpleMatch = input.match(/content=['"](.*)['"]/)
    if (simpleMatch) {
      return {
        type: 'tool_result',
        content: simpleMatch[1]
          .replace(/\\n/g, '\n')
          .replace(/\\'/g, "'")
          .replace(/\\"/g, '"')
          .substring(0, 500) // Limit length for display
      }
    }
    return null
  }

  // Check if it's an error
  const isErrorMatch = input.match(/is_error=(True|False)/)
  const isError = isErrorMatch ? isErrorMatch[1] === 'True' : false

  let content = contentMatch[1]
    .replace(/\\n/g, '\n')
    .replace(/\\'/g, "'")
    .replace(/\\"/g, '"')

  // Truncate very long results
  if (content.length > 1000) {
    content = content.substring(0, 1000) + '\n... (truncated)'
  }

  return {
    type: 'tool_result',
    content,
    metadata: { isError }
  }
}

/**
 * Extract content from SystemMessage string
 */
function parseSystemMessage(input: string): ParsedMessage | null {
  const match = input.match(/SystemMessage\(subtype=['"](\w+)['"]/)
  if (match) {
    return {
      type: 'system',
      content: `System: ${match[1]}`,
      metadata: { subtype: match[1] }
    }
  }
  return null
}

/**
 * Extract content from ResultMessage string
 */
function parseResultMessage(input: string): ParsedMessage | null {
  const subtypeMatch = input.match(/subtype=['"](\w+)['"]/)
  const durationMatch = input.match(/duration_ms=(\d+)/)
  const turnsMatch = input.match(/num_turns=(\d+)/)

  if (subtypeMatch) {
    const parts = []
    parts.push(`Result: ${subtypeMatch[1]}`)

    if (durationMatch) {
      const seconds = (parseInt(durationMatch[1]) / 1000).toFixed(1)
      parts.push(`Duration: ${seconds}s`)
    }

    if (turnsMatch) {
      parts.push(`Turns: ${turnsMatch[1]}`)
    }

    return {
      type: 'system',
      content: parts.join(' • '),
      metadata: {
        subtype: subtypeMatch[1],
        duration: durationMatch ? parseInt(durationMatch[1]) : undefined,
        turns: turnsMatch ? parseInt(turnsMatch[1]) : undefined
      }
    }
  }
  return null
}

/**
 * Main parser function - tries different parsers and returns parsed content
 */
export function parseAgentMessage(input: string): ParsedMessage {
  // Try different parsers
  const parsers = [
    parseTextBlock,
    parseToolUseBlock,
    parseToolResultBlock,
    parseSystemMessage,
    parseResultMessage
  ]

  for (const parser of parsers) {
    const result = parser(input)
    if (result) {
      return result
    }
  }

  // Fallback: return input as-is but truncate if too long
  let content = input
  if (content.length > 500) {
    content = content.substring(0, 500) + '... (truncated)'
  }

  return {
    type: 'text',
    content
  }
}
