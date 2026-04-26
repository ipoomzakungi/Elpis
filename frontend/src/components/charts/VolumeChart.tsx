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
        <CartesianGrid strokeDasharray="3 3" stroke="#2d2d2d" />
        <XAxis dataKey="timestamp" tick={{ fill: '#9ca3af', fontSize: 12 }} />
        <YAxis yAxisId="left" tick={{ fill: '#9ca3af', fontSize: 12 }} />
        <YAxis yAxisId="right" orientation="right" tick={{ fill: '#9ca3af', fontSize: 12 }} />
        <Tooltip
          contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
          labelStyle={{ color: '#f3f4f6' }}
        />
        <Legend />
        <Bar yAxisId="left" dataKey="volume" fill="#22c55e" name="Volume" />
        <Line
          yAxisId="right"
          type="monotone"
          dataKey="volume_ratio"
          stroke="#f59e0b"
          name="Volume Ratio"
        />
      </BarChart>
    </ResponsiveContainer>
  )
}
