'use client'

import { ProviderInfo, ProviderSymbol } from '@/types'

interface ProviderPanelProps {
  providers: ProviderInfo[]
  selectedProvider: ProviderInfo | null
  symbols: ProviderSymbol[]
  selectedProviderName: string
  selectedSymbol: string
  selectedTimeframe: string
  onProviderChange: (providerName: string) => void
  onSymbolChange: (symbol: string) => void
  onTimeframeChange: (timeframe: string) => void
  disabled?: boolean
}

function CapabilityBadge({ label, supported }: { label: string; supported: boolean }) {
  return (
    <div className="flex min-h-11 items-center justify-between rounded-md border border-white/10 bg-white/[0.03] px-3 py-2 text-sm transition hover:border-white/20">
      <span className="text-zinc-300">{label}</span>
      <span className={supported ? 'font-medium text-emerald-300' : 'font-medium text-amber-300'}>
        {supported ? 'Supported' : 'Not supported'}
      </span>
    </div>
  )
}

export default function ProviderPanel({
  providers,
  selectedProvider,
  symbols,
  selectedProviderName,
  selectedSymbol,
  selectedTimeframe,
  onProviderChange,
  onSymbolChange,
  onTimeframeChange,
  disabled = false,
}: ProviderPanelProps) {
  const timeframes = selectedProvider?.supported_timeframes ?? []

  return (
    <section className="rounded-md border border-white/10 bg-zinc-900/80 p-4 shadow-2xl shadow-black/20">
      <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-white">Data source setup</h2>
          <p className="mt-1 text-sm text-zinc-400">Choose the research feed before downloading or processing features.</p>
        </div>
        {selectedProvider && (
          <span className="rounded-md border border-sky-400/30 bg-sky-400/10 px-3 py-1.5 text-xs font-medium text-sky-200">
            {selectedProvider.display_name}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <label className="space-y-2 text-sm text-zinc-300">
          <span className="font-medium">Provider</span>
          <select
            value={selectedProviderName}
            onChange={(event) => onProviderChange(event.target.value)}
            disabled={disabled}
            className="h-11 w-full rounded-md border border-white/10 bg-zinc-950 px-3 py-2 text-white outline-none transition focus:border-sky-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {providers.map((provider) => (
              <option key={provider.provider} value={provider.provider}>
                {provider.display_name}
              </option>
            ))}
          </select>
        </label>

        <label className="space-y-2 text-sm text-zinc-300">
          <span className="font-medium">Symbol</span>
          <select
            value={selectedSymbol}
            onChange={(event) => onSymbolChange(event.target.value)}
            disabled={disabled || symbols.length === 0}
            className="h-11 w-full rounded-md border border-white/10 bg-zinc-950 px-3 py-2 text-white outline-none transition focus:border-sky-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {symbols.map((symbol) => (
              <option key={symbol.symbol} value={symbol.symbol}>
                {symbol.symbol}
              </option>
            ))}
          </select>
        </label>

        <label className="space-y-2 text-sm text-zinc-300">
          <span className="font-medium">Timeframe</span>
          <select
            value={selectedTimeframe}
            onChange={(event) => onTimeframeChange(event.target.value)}
            disabled={disabled || timeframes.length === 0}
            className="h-11 w-full rounded-md border border-white/10 bg-zinc-950 px-3 py-2 text-white outline-none transition focus:border-sky-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {timeframes.map((timeframe) => (
              <option key={timeframe} value={timeframe}>
                {timeframe}
              </option>
            ))}
          </select>
        </label>
      </div>

      {selectedProvider && (
        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-4">
          <CapabilityBadge label="OHLCV" supported={selectedProvider.supports_ohlcv} />
          <CapabilityBadge label="Open Interest" supported={selectedProvider.supports_open_interest} />
          <CapabilityBadge label="Funding" supported={selectedProvider.supports_funding_rate} />
          <CapabilityBadge label="Auth" supported={!selectedProvider.requires_auth} />
        </div>
      )}
    </section>
  )
}
