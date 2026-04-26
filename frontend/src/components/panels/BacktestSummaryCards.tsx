'use client'

interface BacktestSummaryCardsProps {
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
  totalReturnPct,
  maxDrawdownPct,
  profitFactor,
  winRate,
  expectancy,
  numberOfTrades,
}: BacktestSummaryCardsProps) {
  const metrics = [
    { label: 'Total Return', value: formatMetric(totalReturnPct, '%') },
    { label: 'Max Drawdown', value: formatMetric(maxDrawdownPct, '%') },
    { label: 'Profit Factor', value: formatMetric(profitFactor) },
    { label: 'Win Rate', value: formatMetric(winRate === undefined || winRate === null ? winRate : winRate * 100, '%') },
    { label: 'Expectancy', value: formatMetric(expectancy) },
    { label: 'Trades', value: numberOfTrades ?? 'n/a' },
  ]

  return (
    <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
      {metrics.map((metric) => (
        <div key={metric.label} className="bg-gray-800 rounded-lg p-4">
          <div className="text-xs uppercase text-gray-400">{metric.label}</div>
          <div className="mt-2 text-lg font-semibold">{metric.value}</div>
        </div>
      ))}
    </div>
  )
}