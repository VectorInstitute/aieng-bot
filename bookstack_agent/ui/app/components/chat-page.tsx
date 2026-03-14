'use client'

import { useEffect, useRef, useState } from 'react'
import { BookOpen, Send, Trash2, Search, FileText, List } from 'lucide-react'
import { MarkdownRenderer } from './markdown-renderer'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ToolStep = {
  tool: 'search_bookstack' | 'get_page' | 'list_books'
  input: Record<string, unknown>
}

type UserMessage = {
  role: 'user'
  content: string
}

type AssistantMessage = {
  role: 'assistant'
  /** Markdown content. Empty string while streaming; null while loading before first chunk. */
  content: string | null
  toolSteps: ToolStep[]
  /** True while the SSE stream is still open for this message. */
  streaming: boolean
}

type Message = UserMessage | AssistantMessage

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toolLabel(step: ToolStep): string {
  if (step.tool === 'search_bookstack') return `Searching: "${step.input.query}"`
  if (step.tool === 'get_page')         return `Reading page #${step.input.page_id}`
  return 'Listing all books'
}

function ToolIcon({ tool }: { tool: ToolStep['tool'] }) {
  const cls = 'w-3 h-3 shrink-0'
  if (tool === 'search_bookstack') return <Search className={cls} />
  if (tool === 'get_page')         return <FileText className={cls} />
  return <List className={cls} />
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ToolSteps({ steps }: { steps: ToolStep[] }) {
  if (steps.length === 0) return null
  return (
    <ul className="mb-3 space-y-1.5 border-l-2 border-slate-800 pl-3">
      {steps.map((s, i) => (
        <li key={i} className="flex items-center gap-2 text-xs text-slate-500">
          <ToolIcon tool={s.tool} />
          <span>{toolLabel(s)}</span>
        </li>
      ))}
    </ul>
  )
}

function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-end animate-fade-in">
      <div className="max-w-[80%] rounded-2xl rounded-tr-sm px-4 py-2.5 bg-vector-gradient text-white text-sm leading-relaxed shadow-lg">
        {content}
      </div>
    </div>
  )
}

function AssistantBubble({ msg }: { msg: AssistantMessage }) {
  const isIdle     = msg.content === null && !msg.streaming
  const isWaiting  = msg.content === null && msg.streaming && msg.toolSteps.length === 0
  const isStreaming = msg.streaming && msg.content !== null

  return (
    <div className="flex gap-3 animate-slide-up">
      {/* Avatar */}
      <div className="shrink-0 w-7 h-7 rounded-full bg-vector-gradient flex items-center justify-center text-white mt-0.5 shadow">
        <BookOpen className="w-3.5 h-3.5" />
      </div>

      <div className="min-w-0 flex-1 pt-0.5">
        <ToolSteps steps={msg.toolSteps} />

        {isIdle && null}

        {isWaiting && (
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <span className="animate-pulse">Thinking…</span>
          </div>
        )}

        {(isStreaming || (!msg.streaming && msg.content !== null)) && (
          <MarkdownRenderer streaming={isStreaming}>
            {msg.content ?? ''}
          </MarkdownRenderer>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const SUGGESTED = [
  'What are the onboarding steps for new team members?',
  'How do I request compute funding for a new bootcamp?',
  'What steps should I complete before open-sourcing a new project?',
]

export default function ChatPage() {
  const [messages, setMessages]   = useState<Message[]>([])
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)

  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef  = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function handleInputChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setInput(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void submit(input)
    }
  }

  function clearConversation() {
    // Optionally DELETE /api/session/:id on the backend
    if (sessionId) {
      void fetch(`/aieng-bot/api/session/${sessionId}`, { method: 'DELETE' }).catch(() => null)
    }
    setMessages([])
    setSessionId(null)
    setInput('')
  }

  /** Update the last (assistant) message immutably. */
  function patchLast(fn: (prev: AssistantMessage) => AssistantMessage) {
    setMessages((prev) => {
      const next = [...prev]
      const last = next[next.length - 1]
      if (last?.role === 'assistant') {
        next[next.length - 1] = fn(last)
      }
      return next
    })
  }

  async function submit(question: string) {
    const q = question.trim()
    if (!q || loading) return

    setInput('')
    if (inputRef.current) inputRef.current.style.height = 'auto'
    setLoading(true)

    // Append user + placeholder assistant message in one state update
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: q } satisfies UserMessage,
      { role: 'assistant', content: null, toolSteps: [], streaming: true } satisfies AssistantMessage,
    ])

    try {
      const res = await fetch('/aieng-bot/api/ask', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ question: q, session_id: sessionId }),
      })

      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

      const reader  = res.body.getReader()
      const decoder = new TextDecoder()
      let   buffer  = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (raw === '[DONE]') break

          let event: Record<string, unknown>
          try { event = JSON.parse(raw) } catch { continue }

          switch (event.type as string) {

            case 'session':
              setSessionId(event.session_id as string)
              break

            case 'tool_use':
              // Clear any in-progress streamed text (it was planning text, not the answer)
              patchLast((msg) => ({
                ...msg,
                content:   null,
                toolSteps: [
                  ...msg.toolSteps,
                  { tool: event.tool as ToolStep['tool'], input: event.input as Record<string, unknown> },
                ],
              }))
              break

            case 'text_chunk':
              // Append streaming text character-by-character
              patchLast((msg) => ({
                ...msg,
                content: (msg.content ?? '') + (event.chunk as string),
              }))
              break

            case 'answer':
              // Finalise: replace with authoritative complete text, stop cursor
              patchLast((msg) => ({
                ...msg,
                content:   event.text as string,
                streaming: false,
              }))
              break

            case 'error':
              patchLast((msg) => ({
                ...msg,
                content:   `⚠️ ${event.message as string}`,
                streaming: false,
              }))
              break
          }
        }
      }
    } catch (err) {
      patchLast((msg) => ({
        ...msg,
        content:   `⚠️ Could not reach the agent: ${err}`,
        streaming: false,
      }))
    } finally {
      // Ensure streaming flag is cleared even on unexpected stream end
      patchLast((msg) => (msg.streaming ? { ...msg, streaming: false } : msg))
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const isEmpty = messages.length === 0

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-slate-200">
      {/* Top gradient line */}
      <div className="fixed top-0 left-0 right-0 h-px bg-vector-gradient z-10" />

      {/* Header */}
      <header className="shrink-0 flex items-center justify-between px-6 pt-5 pb-4 border-b border-slate-800/50">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-vector-gradient flex items-center justify-center shadow-lg">
            <BookOpen className="w-4 h-4 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-white leading-none">BookStack QA</h1>
            <p className="text-xs text-slate-500 mt-0.5">Vector Institute internal docs</p>
          </div>
        </div>

        {!isEmpty && (
          <button
            onClick={clearConversation}
            className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors px-2.5 py-1.5 rounded-lg hover:bg-slate-800"
          >
            <Trash2 className="w-3.5 h-3.5" />
            New chat
          </button>
        )}
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">

          {isEmpty && (
            <div className="flex flex-col items-center gap-8 pt-10 animate-fade-in">
              <pre className="font-mono text-base leading-6 select-none text-slate-500" aria-hidden="true">{
`  ◦   ◦
 ┌─────┐
 │ ◉ ◉ │
 └──‿──┘`
              }</pre>
              <div className="text-center space-y-3">
                <div className="text-xs font-mono tracking-widest text-slate-500 uppercase">
                  Vector Institute AI Engineering
                </div>
                <h1 className="text-3xl font-bold tracking-tight text-white">
                  aieng-bot
                </h1>
              </div>
              <div className="flex flex-wrap justify-center gap-2">
                {SUGGESTED.map((s) => (
                  <button
                    key={s}
                    onClick={() => void submit(s)}
                    disabled={loading}
                    className="text-xs text-slate-400 hover:text-slate-200 bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 rounded-full px-3.5 py-1.5 transition-all disabled:opacity-40 leading-snug"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) =>
            msg.role === 'user'
              ? <UserBubble key={i} content={msg.content} />
              : <AssistantBubble key={i} msg={msg} />
          )}

          <div ref={bottomRef} />
        </div>
      </main>

      {/* Input */}
      <footer className="shrink-0 px-4 py-4 bg-gradient-to-t from-slate-950 via-slate-950/95 to-transparent">
        <div className="max-w-2xl mx-auto space-y-2">
          <div className={`relative flex items-end gap-2 bg-slate-900/80 border rounded-2xl px-4 py-3 shadow-lg shadow-black/20 transition-all duration-150 ${loading ? 'border-slate-800' : 'border-slate-700/80 focus-within:border-vector-violet/60 focus-within:shadow-vector-violet/5 focus-within:shadow-xl'}`}>
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Ask about internal docs…"
              disabled={loading}
              className="flex-1 bg-transparent text-sm text-slate-200 placeholder-slate-600 resize-none outline-none leading-relaxed min-h-[22px] max-h-36 disabled:opacity-50 py-0.5"
            />
            <button
              onClick={() => void submit(input)}
              disabled={!input.trim() || loading}
              className="shrink-0 w-7 h-7 rounded-lg flex items-center justify-center transition-all duration-150 disabled:opacity-20 enabled:bg-vector-gradient enabled:text-white enabled:hover:opacity-90 enabled:active:scale-95 disabled:text-slate-600"
              aria-label="Send"
            >
              {loading
                ? <span className="w-3.5 h-3.5 border-2 border-slate-600 border-t-slate-400 rounded-full animate-spin" />
                : <Send className="w-3 h-3" />
              }
            </button>
          </div>
          <p className="text-center text-[11px] text-slate-700 leading-none">
            Grounded in BookStack · <kbd className="font-sans not-italic">↵</kbd> to send · <kbd className="font-sans not-italic">⇧↵</kbd> new line
          </p>
        </div>
      </footer>
    </div>
  )
}
