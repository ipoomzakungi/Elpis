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
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
        <XAxis dataKey="timestamp" tick={{ fill: '#a1a1aa', fontSize: 12 }} />
        <YAxis yAxisId="left" tick={{ fill: '#a1a1aa', fontSize: 12 }} />
        <YAxis yAxisId="right" orientation="right" tick={{ fill: '#a1a1aa', fontSize: 12 }} />
        <Tooltip
          contentStyle={{ backgroundColor: '#18181b', border: '1px solid rgba(255,255,255,0.14)', borderRadius: 6 }}
          labelStyle={{ color: '#f4f4f5' }}
        />
        <Legend wrapperStyle={{ color: '#d4d4d8' }} />
        <Line
          yAxisId="left"
          type="monotone"
          dataKey="open_interest"
          stroke="#38bdf8"
          name="Open Interest"
          dot={false}
        />
        <Line
          yAxisId="right"
          type="monotone"
          dataKey="oi_change_pct"
          stroke="#fbbf24"
          name="OI Change %"
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
