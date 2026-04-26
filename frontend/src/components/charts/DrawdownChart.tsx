'use client'

import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from 'recharts'

interface DrawdownPoint {
  timestamp: string
  drawdown_pct: number
}

interface DrawdownChartProps {
  data?: DrawdownPoint[]
  height?: number
}

export default function DrawdownChart({ data = [], height = 220 }: DrawdownChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2d2d2d" />
        <XAxis dataKey="timestamp" tick={{ fill: '#9ca3af', fontSize: 12 }} />
        <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
        <Tooltip
          contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
          labelStyle={{ color: '#f3f4f6' }}
        />
        <Area type="monotone" dataKey="drawdown_pct" stroke="#ef4444" fill="#7f1d1d" name="Drawdown %" />
      </AreaChart>
    </ResponsiveContainer>
  )
}