import Link from 'next/link'
import { BarChart2, Wrench, GitMerge, GitPullRequestArrow } from 'lucide-react'

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-8">
      {/* Top gradient line */}
      <div className="fixed top-0 left-0 right-0 h-px bg-gradient-to-r from-vector-magenta via-vector-violet to-vector-cobalt" />

      <div className="max-w-xl w-full flex flex-col items-center gap-12 animate-fade-in">

        {/* ASCII art */}
        <pre className="font-mono text-base leading-6 select-none" aria-hidden="true">{
`  ◦   ◦
 ┌─────┐
 │ ◉ ◉ │
 └──‿──┘`
        }</pre>

        {/* Identity */}
        <div className="text-center space-y-4">
          <div className="inline-block text-xs font-mono tracking-widest text-slate-500 uppercase mb-1">
            Vector Institute AI Engineering
          </div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-white">
            aieng-bot
          </h1>
          <p className="text-slate-400 text-base leading-relaxed max-w-sm mx-auto">
            Autonomously fixes CI failures, resolves merge conflicts, and merges
            Dependabot PRs across Vector Institute repositories.
          </p>
        </div>

        {/* Divider */}
        <div className="w-full border-t border-slate-800" />

        {/* Features */}
        <ul className="w-full space-y-2">
          {[
            { Icon: Wrench,              label: 'Fixes lint, test & build failures', color: 'text-vector-magenta' },
            { Icon: GitMerge,            label: 'Resolves merge conflicts',           color: 'text-vector-violet' },
            { Icon: GitPullRequestArrow, label: 'Auto-merges passing PRs',            color: 'text-vector-cobalt'  },
          ].map(({ Icon, label, color }) => (
            <li
              key={label}
              className="flex items-center gap-3.5 px-4 py-3 rounded-lg text-slate-400 text-sm"
            >
              <Icon className={`w-4 h-4 shrink-0 ${color}`} strokeWidth={1.75} />
              <span>{label}</span>
            </li>
          ))}
        </ul>

        {/* CTA */}
        <Link
          href="/analytics"
          className="flex items-center gap-2 px-7 py-3 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-vector-magenta via-vector-violet to-vector-cobalt hover:opacity-90 transition-opacity"
        >
          <BarChart2 className="w-4 h-4" />
          View Analytics
        </Link>

      </div>
    </div>
  )
}
