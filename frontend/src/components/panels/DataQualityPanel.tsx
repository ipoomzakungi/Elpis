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
    <section className="rounded-md border border-white/10 bg-zinc-900/80 p-4 shadow-xl shadow-black/10">
      <div className="mb-4">
        <h3 className="text-base font-semibold text-white">Data quality</h3>
        <p className="mt-1 text-xs text-zinc-400">Local coverage checks for the selected research set.</p>
      </div>
      <div className="space-y-3">
        {Object.entries(data).map(([key, quality]) => (
          <div key={key} className="rounded-md border border-white/10 bg-white/[0.03] p-3">
            <div className="mb-3 flex items-center justify-between gap-3">
              <span className="font-medium capitalize text-zinc-100">{key.replace('_', ' ')}</span>
              <span
                className={`rounded-md px-2 py-1 text-xs font-medium ${
                  quality.total_records > 0
                    ? 'bg-emerald-400/10 text-emerald-200'
                    : 'bg-rose-400/10 text-rose-200'
                }`}
              >
                {quality.total_records > 0 ? 'Available' : 'Missing'}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-zinc-400">
              <Metric label="Records" value={quality.total_records} />
              <Metric label="Missing" value={quality.missing_timestamps} />
              <Metric label="Duplicates" value={quality.duplicate_timestamps} />
              <Metric label="Updated" value={formatTimestamp(quality.last_updated)} wide />
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function Metric({ label, value, wide = false }: { label: string; value: number | string; wide?: boolean }) {
  return (
    <div className={wide ? 'col-span-2 min-w-0' : 'min-w-0'}>
      <div className="text-[11px] uppercase text-zinc-500">{label}</div>
      <div className="mt-0.5 truncate text-sm font-medium text-zinc-200">{value}</div>
    </div>
  )
}
