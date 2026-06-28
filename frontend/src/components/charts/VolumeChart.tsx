'use client'

import { BarChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { Feature } from '@/types'

interface VolumeChartProps {
  data: Feature[]
  height?: number
}

export default function VolumeChart({ data, height = 200 }: VolumeChartProps) {
  const chartData = data.map((d) => ({
    timestamp: d.timestamp,
    volume: d.volume,
    volume_ratio: d.volume_ratio,
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
        <XAxis dataKey="timestamp" tick={{ fill: '#a1a1aa', fontSize: 12 }} />
        <YAxis yAxisId="left" tick={{ fill: '#a1a1aa', fontSize: 12 }} />
        <YAxis yAxisId="right" orientation="right" tick={{ fill: '#a1a1aa', fontSize: 12 }} />
        <Tooltip
          contentStyle={{ backgroundColor: '#18181b', border: '1px solid rgba(255,255,255,0.14)', borderRadius: 6 }}
          labelStyle={{ color: '#f4f4f5' }}
        />
        <Legend wrapperStyle={{ color: '#d4d4d8' }} />
        <Bar yAxisId="left" dataKey="volume" fill="#34d399" name="Volume" radius={[3, 3, 0, 0]} />
        <Line
          yAxisId="right"
          type="monotone"
          dataKey="volume_ratio"
          stroke="#fbbf24"
          name="Volume Ratio"
        />
      </BarChart>
    </ResponsiveContainer>
  )
}
