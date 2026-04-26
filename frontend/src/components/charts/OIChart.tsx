'use client'

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { Feature } from '@/types'

interface OIChartProps {
  data: Feature[]
  height?: number
}

export default function OIChart({ data, height = 200 }: OIChartProps) {
  const chartData = data.map((d) => ({
    timestamp: d.timestamp,
    open_interest: d.open_interest,
    oi_change_pct: d.oi_change_pct,
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2d2d2d" />
        <XAxis dataKey="timestamp" tick={{ fill: '#9ca3af', fontSize: 12 }} />
        <YAxis yAxisId="left" tick={{ fill: '#9ca3af', fontSize: 12 }} />
        <YAxis yAxisId="right" orientation="right" tick={{ fill: '#9ca3af', fontSize: 12 }} />
        <Tooltip
          contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
          labelStyle={{ color: '#f3f4f6' }}
        />
        <Legend />
        <Line
          yAxisId="left"
          type="monotone"
          dataKey="open_interest"
          stroke="#3b82f6"
          name="Open Interest"
          dot={false}
        />
        <Line
          yAxisId="right"
          type="monotone"
          dataKey="oi_change_pct"
          stroke="#f59e0b"
          name="OI Change %"
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
