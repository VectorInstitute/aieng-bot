'use client'

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'

type ChartPoint = {
  date: string
  success: number
  error: number
  total: number
}

const CHART_CONFIG = {
  grid: { strokeDasharray: '3 3', stroke: '#334155', opacity: 0.4 },
  axis: { stroke: '#64748b', style: { fontSize: '11px' }, tickLine: false },
  tooltip: {
    contentStyle: {
      backgroundColor: '#1e293b',
      border: 'none',
      borderRadius: '8px',
      color: '#fff',
      padding: '8px 12px',
    },
    labelStyle: { color: '#94a3b8', marginBottom: '4px' },
  },
}

function shouldShowLabel(index: number, total: number): boolean {
  if (total <= 7) return true
  if (total <= 14) return index % 2 === 0
  if (total <= 30) return index % 3 === 0
  if (total <= 45) return index % 5 === 0
  return index % 7 === 0
}

export default function QueryVelocityChart({ data }: { data: ChartPoint[] }) {
  const maxVal = data.length > 0 ? Math.max(...data.map(d => d.total)) : 0
  const yMax = maxVal <= 10 ? 10 : maxVal <= 20 ? 20 : Math.ceil(maxVal * 1.2 / 5) * 5

  return (
    <div className="rounded-xl border border-white/10 bg-slate-800/60 p-6">
      <div className="mb-5">
        <h2 className="text-xl font-bold text-white">Query Velocity</h2>
        <p className="text-sm text-slate-400 mt-0.5">Queries answered per day (last 90 days)</p>
      </div>

      {data.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-slate-500 text-sm">
          No data available yet
        </div>
      ) : (
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <defs>
                <linearGradient id="bsColorSuccess" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#8A25C9" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#8A25C9" stopOpacity={0.05} />
                </linearGradient>
                <linearGradient id="bsColorError" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#EB088A" stopOpacity={0.6} />
                  <stop offset="95%" stopColor="#EB088A" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid {...CHART_CONFIG.grid} />
              <XAxis
                dataKey="date"
                {...CHART_CONFIG.axis}
                interval="preserveStartEnd"
                tick={(props) => {
                  const { x, y, payload, index } = props as { x: number; y: number; payload: { value: string }; index: number }
                  if (index === 0 || index === data.length - 1 || shouldShowLabel(index, data.length)) {
                    return (
                      <text x={x} y={y + 10} fill="#64748b" fontSize="11px" textAnchor="middle">
                        {payload.value}
                      </text>
                    )
                  }
                  return <g />
                }}
              />
              <YAxis {...CHART_CONFIG.axis} domain={[0, yMax]} allowDecimals={false} />
              <Tooltip {...CHART_CONFIG.tooltip} />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              <Area
                type="linear"
                dataKey="success"
                name="Answered"
                stroke="#8A25C9"
                strokeWidth={2}
                fill="url(#bsColorSuccess)"
              />
              <Area
                type="linear"
                dataKey="error"
                name="Error"
                stroke="#EB088A"
                strokeWidth={2}
                fill="url(#bsColorError)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
