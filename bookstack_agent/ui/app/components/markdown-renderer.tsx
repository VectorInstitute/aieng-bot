/**
 * MarkdownRenderer — richly styled React-Markdown renderer.
 *
 * Custom components for every meaningful markdown element so the output
 * looks polished against the dark slate background without needing the
 * @tailwindcss/typography plugin.
 *
 * Block <pre><code> is intercepted at the <pre> level so react-syntax-highlighter
 * gets the language hint; inline <code> falls through to the lightweight pill style.
 *
 * Tables get the most attention: scrollable container, sticky header, zebra rows,
 * hover highlight, and proper Vector-brand accent on the header.
 */

import React from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import remarkGfm from 'remark-gfm'

// ---------------------------------------------------------------------------
// Copy-to-clipboard button for code blocks
// ---------------------------------------------------------------------------

function CopyButton({ code }: { code: string }) {
  const [copied, setCopied] = React.useState(false)
  const timeoutRef = React.useRef<ReturnType<typeof setTimeout> | null>(null)

  React.useEffect(() => {
    return () => {
      if (timeoutRef.current !== null) clearTimeout(timeoutRef.current)
    }
  }, [])

  const copy = () => {
    navigator.clipboard
      .writeText(code)
      .then(() => {
        setCopied(true)
        if (timeoutRef.current !== null) clearTimeout(timeoutRef.current)
        timeoutRef.current = setTimeout(() => setCopied(false), 1500)
      })
      .catch(() => {
        // Clipboard access denied (insecure origin / permissions) — ignore
      })
  }
  return (
    <button
      onClick={copy}
      className="text-[10px] font-mono text-slate-500 hover:text-slate-300 transition-colors px-2 py-0.5 rounded border border-slate-700/50 hover:border-slate-600"
    >
      {copied ? 'copied' : 'copy'}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Component map
// ---------------------------------------------------------------------------

const components: Components = {

  // ---- Headings -----------------------------------------------------------

  h1: ({ children }) => (
    <h1 className="text-xl font-bold text-white mt-7 mb-3 first:mt-0 pb-2 border-b border-slate-800">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-base font-semibold text-white mt-6 mb-2.5 first:mt-0 pb-1.5 border-b border-slate-800/70">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-sm font-semibold text-slate-100 mt-4 mb-2 first:mt-0">
      {children}
    </h3>
  ),
  h4: ({ children }) => (
    <h4 className="text-sm font-medium text-slate-200 mt-3 mb-1.5 first:mt-0">
      {children}
    </h4>
  ),

  // ---- Block-level --------------------------------------------------------

  p: ({ children }) => (
    <p className="text-slate-300 leading-[1.7] mb-3 last:mb-0">
      {children}
    </p>
  ),

  hr: () => <hr className="border-slate-800 my-5" />,

  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-vector-violet/50 pl-4 my-3 text-slate-400 italic [&>p]:mb-0">
      {children}
    </blockquote>
  ),

  // ---- Lists --------------------------------------------------------------

  ul: ({ children }) => (
    <ul className="list-none pl-0 mb-3 space-y-1 text-slate-300">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal list-outside pl-5 mb-3 space-y-1 text-slate-300">
      {children}
    </ol>
  ),
  li: ({ children }) => (
    <li className="leading-[1.65] flex gap-2 items-baseline pl-0
                   [ul>&]:before:content-['–'] [ul>&]:before:text-slate-600 [ul>&]:before:shrink-0">
      <span>{children}</span>
    </li>
  ),

  // ---- Inline -------------------------------------------------------------

  strong: ({ children }) => (
    <strong className="font-semibold text-slate-100">{children}</strong>
  ),
  em: ({ children }) => (
    <em className="italic text-slate-300">{children}</em>
  ),
  del: ({ children }) => (
    <del className="text-slate-500 line-through">{children}</del>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-violet-400 hover:text-violet-300 underline underline-offset-[3px] decoration-violet-500/40 hover:decoration-violet-400/70 transition-colors"
    >
      {children}
    </a>
  ),

  // ---- Inline code --------------------------------------------------------
  // Block code is handled in <pre> below; this only runs for `inline` code.

  code: ({ className, children }) => {
    // If className has a language- prefix this is a fenced block inside <pre>;
    // the <pre> override below will have already rendered it with SyntaxHighlighter.
    // We return null here to avoid double-rendering.
    if (className?.startsWith('language-')) return null

    return (
      <code className="inline-block bg-slate-800/80 text-violet-300 px-[5px] py-[1px] rounded text-[0.82em] font-mono border border-slate-700/40 leading-normal">
        {children}
      </code>
    )
  },

  // ---- Code blocks --------------------------------------------------------
  // Intercept <pre> so we can pull the language class out of the nested <code>
  // and pass it to SyntaxHighlighter before react-markdown renders the child.

  pre: ({ children }) => {
    // Find the <code> child — react-markdown wraps fenced blocks as <pre><code>
    const codeEl = React.Children.toArray(children).find(
      (c): c is React.ReactElement<{ className?: string; children: string }> =>
        React.isValidElement(c),
    )

    if (!codeEl) return <pre>{children}</pre>

    const className = codeEl.props.className ?? ''
    const match = /language-(\w+)/.exec(className)
    const language = match?.[1] ?? 'text'
    const rawCode = String(codeEl.props.children ?? '').replace(/\n$/, '')

    return (
      <div className="my-4 rounded-xl overflow-hidden border border-slate-700/50 bg-[#1e1e1e]">
        {/* Header bar: language label + copy button */}
        <div className="flex items-center justify-between px-4 py-2 bg-slate-800/60 border-b border-slate-700/50">
          <span className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">
            {language === 'text' ? 'code' : language}
          </span>
          <CopyButton code={rawCode} />
        </div>
        <SyntaxHighlighter
          language={language}
          style={vscDarkPlus}
          customStyle={{
            margin: 0,
            padding: '1rem',
            background: 'transparent',
            fontSize: '0.8rem',
            lineHeight: '1.6',
          }}
          codeTagProps={{ style: { fontFamily: 'ui-monospace, monospace' } }}
          PreTag="div"
        >
          {rawCode}
        </SyntaxHighlighter>
      </div>
    )
  },

  // ---- Tables -------------------------------------------------------------
  // Wrapped in a scrollable container so wide tables don't overflow the chat.
  // Header: subtle gradient tint. Body: zebra rows + hover highlight.

  table: ({ children }) => (
    <div className="my-4 w-full overflow-x-auto rounded-xl border border-slate-700/60 shadow-sm">
      <table className="w-full text-sm border-collapse">
        {children}
      </table>
    </div>
  ),

  thead: ({ children }) => (
    <thead className="bg-gradient-to-r from-slate-800 to-slate-800/60 border-b border-slate-700/60">
      {children}
    </thead>
  ),

  tbody: ({ children }) => (
    <tbody className="divide-y divide-slate-800/60">
      {children}
    </tbody>
  ),

  tr: ({ children }) => (
    <tr className="transition-colors hover:bg-slate-800/30 even:bg-slate-900/30">
      {children}
    </tr>
  ),

  th: ({ children }) => (
    <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-300 uppercase tracking-wider whitespace-nowrap">
      {children}
    </th>
  ),

  td: ({ children }) => (
    <td className="px-4 py-2.5 text-slate-300 align-top leading-relaxed">
      {children}
    </td>
  ),
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

interface MarkdownRendererProps {
  children: string
  /** Show a blinking cursor at the end (while streaming). */
  streaming?: boolean
}

export function MarkdownRenderer({ children, streaming = false }: MarkdownRendererProps) {
  return (
    <div className="min-w-0">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
      {streaming && (
        <span className="inline-block w-[2px] h-[0.9em] bg-slate-400 ml-0.5 align-middle animate-pulse rounded-sm" />
      )}
    </div>
  )
}
