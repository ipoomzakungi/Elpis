'use client'

import { DataQuality } from '@/types'

interface DataQualityPanelProps {
  data: {
    ohlcv: DataQuality
    open_interest: DataQuality
    funding_rate: DataQuality
  }
}

export default function DataQualityPanel({ data }: DataQualityPanelProps) {
  const formatTimestamp = (ts: string | null) => {
    if (!ts) return 'N/A'
    return new Date(ts).toLocaleString()
  }

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <h3 className="text-lg font-semibold mb-4">Data Quality</h3>
      <div className="space-y-4">
        {Object.entries(data).map(([key, quality]) => (
          <div key={key} className="border-b border-gray-700 pb-3 last:border-0">
            <div className="flex justify-between items-center mb-2">
              <span className="font-medium capitalize">{key.replace('_', ' ')}</span>
              <span className={`text-sm ${quality.total_records > 0 ? 'text-green-400' : 'text-red-400'}`}>
                {quality.total_records > 0 ? '✓ Available' : '✗ Missing'}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm text-gray-400">
              <div>Records: {quality.total_records}</div>
              <div>Missing: {quality.missing_timestamps}</div>
              <div>Duplicates: {quality.duplicate_timestamps}</div>
              <div>Updated: {formatTimestamp(quality.last_updated)}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
