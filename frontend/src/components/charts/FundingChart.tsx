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
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
        <XAxis dataKey="timestamp" tick={{ fill: '#a1a1aa', fontSize: 12 }} />
        <YAxis tick={{ fill: '#a1a1aa', fontSize: 12 }} />
        <Tooltip
          contentStyle={{ backgroundColor: '#18181b', border: '1px solid rgba(255,255,255,0.14)', borderRadius: 6 }}
          labelStyle={{ color: '#f4f4f5' }}
        />
        <Legend wrapperStyle={{ color: '#d4d4d8' }} />
        <Line
          type="monotone"
          dataKey="funding_rate"
          stroke="#a78bfa"
          name="Funding Rate"
          dot={false}
        />
        <Line
          type="monotone"
          dataKey="funding_rate_change"
          stroke="#fb7185"
          name="Rate Change"
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
