'use client'

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { Feature } from '@/types'

interface FundingChartProps {
  data: Feature[]
  height?: number
}

export default function FundingChart({ data, height = 200 }: FundingChartProps) {
  const chartData = data.map((d) => ({
    timestamp: d.timestamp,
    funding_rate: d.funding_rate,
    funding_rate_change: d.funding_rate_change,
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2d2d2d" />
        <XAxis dataKey="timestamp" tick={{ fill: '#9ca3af', fontSize: 12 }} />
        <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
        <Tooltip
          contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
          labelStyle={{ color: '#f3f4f6' }}
        />
        <Legend />
        <Line
          type="monotone"
          dataKey="funding_rate"
          stroke="#8b5cf6"
          name="Funding Rate"
          dot={false}
        />
        <Line
          type="monotone"
          dataKey="funding_rate_change"
          stroke="#ec4899"
          name="Rate Change"
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
