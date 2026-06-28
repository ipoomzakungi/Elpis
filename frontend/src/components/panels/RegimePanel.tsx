'use client'

import { Regime, RegimeType } from '@/types'

interface RegimePanelProps {
  data: Regime[]
}

const regimeColors: Record<RegimeType, string> = {
  RANGE: 'bg-emerald-400',
  BREAKOUT_UP: 'bg-sky-400',
  BREAKOUT_DOWN: 'bg-rose-400',
  AVOID: 'bg-zinc-500',
}

export default function RegimePanel({ data }: RegimePanelProps) {
  // Count regimes
  const regimeCounts = data.reduce((acc, d) => {
    acc[d.regime] = (acc[d.regime] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  const total = data.length || 1

  return (
    <section className="rounded-md border border-white/10 bg-zinc-900/80 p-4 shadow-xl shadow-black/10">
      <div className="mb-4">
        <h3 className="text-base font-semibold text-white">Regime distribution</h3>
        <p className="mt-1 text-xs text-zinc-400">{data.length} classified bars</p>
      </div>
      <div className="space-y-3">
        {Object.entries(regimeColors).map(([regime, color]) => {
          const count = regimeCounts[regime] || 0
          const percentage = ((count / total) * 100).toFixed(1)
          return (
            <div key={regime} className="space-y-1.5">
              <div className="flex items-center justify-between gap-3 text-sm">
                <div className="flex min-w-0 items-center gap-2">
                  <div className={`h-2.5 w-2.5 shrink-0 rounded-full ${color}`} />
                  <span className="truncate font-medium text-zinc-100">{formatRegime(regime)}</span>
                </div>
                <span className="shrink-0 text-xs text-zinc-400">
                  {count} bars
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
                <div
                  className={`h-full rounded-full ${color} transition-all duration-500`}
                  style={{ width: `${percentage}%` }}
                  aria-label={`${formatRegime(regime)} ${percentage}%`}
                />
              </div>
              <div className="text-right text-xs text-zinc-500">{percentage}%</div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function formatRegime(regime: string) {
  return regime
    .toLowerCase()
    .split('_')
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(' ')
}
