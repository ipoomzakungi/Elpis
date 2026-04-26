'use client'

import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from 'recharts'

interface EquityCurvePoint {
  timestamp: string
  equity: number
}

interface EquityCurveChartProps {
  data?: EquityCurvePoint[]
  height?: number
}

export default function EquityCurveChart({ data = [], height = 260 }: EquityCurveChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2d2d2d" />
        <XAxis dataKey="timestamp" tick={{ fill: '#9ca3af', fontSize: 12 }} />
        <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
        <Tooltip
          contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
          labelStyle={{ color: '#f3f4f6' }}
        />
        <Line type="monotone" dataKey="equity" stroke="#22c55e" name="Equity" dot={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}