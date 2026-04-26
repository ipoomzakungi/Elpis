'use client'

import { Regime, RegimeType } from '@/types'

interface RegimePanelProps {
  data: Regime[]
}

const regimeColors: Record<RegimeType, string> = {
  RANGE: 'bg-green-500',
  BREAKOUT_UP: 'bg-blue-500',
  BREAKOUT_DOWN: 'bg-red-500',
  AVOID: 'bg-gray-500',
}

export default function RegimePanel({ data }: RegimePanelProps) {
  // Count regimes
  const regimeCounts = data.reduce((acc, d) => {
    acc[d.regime] = (acc[d.regime] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  const total = data.length || 1

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <h3 className="text-lg font-semibold mb-4">Regime Distribution</h3>
      <div className="grid grid-cols-2 gap-4">
        {Object.entries(regimeColors).map(([regime, color]) => {
          const count = regimeCounts[regime] || 0
          const percentage = ((count / total) * 100).toFixed(1)
          return (
            <div key={regime} className="flex items-center gap-2">
              <div className={`w-3 h-3 rounded-full ${color}`}></div>
              <div>
                <div className="text-sm font-medium">{regime}</div>
                <div className="text-xs text-gray-400">
                  {count} ({percentage}%)
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
