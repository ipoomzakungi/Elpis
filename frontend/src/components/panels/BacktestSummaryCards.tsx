'use client'

import { BacktestMetrics } from '@/types'

interface BacktestSummaryCardsProps {
  metrics?: BacktestMetrics | null
  totalReturnPct?: number | null
  maxDrawdownPct?: number | null
  profitFactor?: number | null
  winRate?: number | null
  expectancy?: number | null
  numberOfTrades?: number | null
}

function formatMetric(value?: number | null, suffix = '') {
  if (value === null || value === undefined) return 'n/a'
  return `${value.toFixed(2)}${suffix}`
}

export default function BacktestSummaryCards({
  metrics: summary,
  totalReturnPct,
  maxDrawdownPct,
  profitFactor,
  winRate,
  expectancy,
  numberOfTrades,
}: BacktestSummaryCardsProps) {
  const metrics = [
    { label: 'Total Return', value: formatMetric(summary?.total_return_pct ?? totalReturnPct, '%') },
    { label: 'Max Drawdown', value: formatMetric(summary?.max_drawdown_pct ?? maxDrawdownPct, '%') },
    { label: 'Profit Factor', value: formatMetric(summary?.profit_factor ?? profitFactor) },
    { label: 'Win Rate', value: formatMetric(toPercent(summary?.win_rate ?? winRate), '%') },
    { label: 'Expectancy', value: formatMetric(summary?.expectancy ?? expectancy) },
    { label: 'Trades', value: summary?.number_of_trades ?? numberOfTrades ?? 'n/a' },
  ]

  return (
    <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
      {metrics.map((metric) => (
        <div key={metric.label} className="bg-gray-800 rounded-md p-4">
          <div className="text-xs uppercase text-gray-400">{metric.label}</div>
          <div className="mt-2 text-lg font-semibold">{metric.value}</div>
        </div>
      ))}
    </div>
  )
}

function toPercent(value?: number | null) {
  if (value === null || value === undefined) return value
  return value * 100
}