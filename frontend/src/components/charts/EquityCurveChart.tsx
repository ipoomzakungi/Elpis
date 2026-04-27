'use client'

import { useMemo } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { BacktestEquityPoint, BacktestStrategyMode } from '@/types'

const COLORS: Record<string, string> = {
  grid_range: '#22c55e',
  breakout: '#38bdf8',
  buy_hold: '#f59e0b',
  price_breakout: '#a78bfa',
  no_trade: '#94a3b8',
}

interface EquityCurveChartProps {
  data?: BacktestEquityPoint[]
  height?: number
}

export default function EquityCurveChart({ data = [], height = 260 }: EquityCurveChartProps) {
  const { chartData, modes } = useMemo(() => toModeSeries(data, 'equity'), [data])

  if (chartData.length === 0) {
    return <div className="flex items-center justify-center text-sm text-gray-400" style={{ height }}>No equity data</div>
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2d2d2d" />
        <XAxis dataKey="timestamp" tick={{ fill: '#9ca3af', fontSize: 12 }} minTickGap={24} />
        <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
        <Tooltip
          contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
          labelStyle={{ color: '#f3f4f6' }}
        />
        <Legend wrapperStyle={{ color: '#d1d5db', fontSize: 12 }} />
        {modes.map((mode) => (
          <Line
            key={mode}
            type="monotone"
            dataKey={mode}
            stroke={COLORS[mode] ?? '#e5e7eb'}
            name={mode.replaceAll('_', ' ')}
            dot={false}
            strokeWidth={2}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

function toModeSeries(
  data: BacktestEquityPoint[],
  valueKey: 'equity' | 'drawdown_pct',
): { chartData: Array<Record<string, number | string>>; modes: BacktestStrategyMode[] } {
  const modes = Array.from(new Set(data.map((point) => point.strategy_mode)))
  const byTimestamp = new Map<string, Record<string, number | string>>()

  for (const point of data) {
    const bucket = byTimestamp.get(point.timestamp) ?? { timestamp: formatTick(point.timestamp) }
    bucket[point.strategy_mode] = point[valueKey]
    byTimestamp.set(point.timestamp, bucket)
  }

  return { chartData: Array.from(byTimestamp.values()), modes }
}

function formatTick(timestamp: string): string {
  return timestamp.replace('T', ' ').slice(5, 16)
}