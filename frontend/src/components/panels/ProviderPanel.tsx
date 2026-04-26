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
    <div className="flex items-center justify-between rounded border border-gray-700 px-3 py-2 text-sm">
      <span className="text-gray-300">{label}</span>
      <span className={supported ? 'text-emerald-400' : 'text-amber-400'}>
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
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <label className="space-y-2 text-sm text-gray-300">
          <span>Provider</span>
          <select
            value={selectedProviderName}
            onChange={(event) => onProviderChange(event.target.value)}
            disabled={disabled}
            className="w-full rounded border border-gray-700 bg-gray-900 px-3 py-2 text-white"
          >
            {providers.map((provider) => (
              <option key={provider.provider} value={provider.provider}>
                {provider.display_name}
              </option>
            ))}
          </select>
        </label>

        <label className="space-y-2 text-sm text-gray-300">
          <span>Symbol</span>
          <select
            value={selectedSymbol}
            onChange={(event) => onSymbolChange(event.target.value)}
            disabled={disabled || symbols.length === 0}
            className="w-full rounded border border-gray-700 bg-gray-900 px-3 py-2 text-white"
          >
            {symbols.map((symbol) => (
              <option key={symbol.symbol} value={symbol.symbol}>
                {symbol.symbol}
              </option>
            ))}
          </select>
        </label>

        <label className="space-y-2 text-sm text-gray-300">
          <span>Timeframe</span>
          <select
            value={selectedTimeframe}
            onChange={(event) => onTimeframeChange(event.target.value)}
            disabled={disabled || timeframes.length === 0}
            className="w-full rounded border border-gray-700 bg-gray-900 px-3 py-2 text-white"
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
        <div className="mt-4 grid grid-cols-1 md:grid-cols-4 gap-3">
          <CapabilityBadge label="OHLCV" supported={selectedProvider.supports_ohlcv} />
          <CapabilityBadge label="Open Interest" supported={selectedProvider.supports_open_interest} />
          <CapabilityBadge label="Funding" supported={selectedProvider.supports_funding_rate} />
          <CapabilityBadge label="Auth" supported={!selectedProvider.requires_auth} />
        </div>
      )}
    </div>
  )
}