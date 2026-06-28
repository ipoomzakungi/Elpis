'use client'

import type { ReactNode } from 'react'
import { useEffect, useMemo, useState } from 'react'
import { useMarketData } from '@/hooks/useMarketData'
import CandlestickChart from '@/components/charts/CandlestickChart'
import OIChart from '@/components/charts/OIChart'
import FundingChart from '@/components/charts/FundingChart'
import VolumeChart from '@/components/charts/VolumeChart'
import RegimePanel from '@/components/panels/RegimePanel'
import DataQualityPanel from '@/components/panels/DataQualityPanel'
import ProviderPanel from '@/components/panels/ProviderPanel'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import { api } from '@/services/api'
import { ProviderDataType, ProviderInfo, ProviderSymbol } from '@/types'

export default function Dashboard() {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [providerSymbols, setProviderSymbols] = useState<ProviderSymbol[]>([])
  const [selectedProviderName, setSelectedProviderName] = useState('binance')
  const [selectedSymbol, setSelectedSymbol] = useState('BTCUSDT')
  const [selectedTimeframe, setSelectedTimeframe] = useState('15m')
  const [downloading, setDownloading] = useState(false)
  const [processing, setProcessing] = useState(false)

  const selectedProvider = useMemo(
    () => providers.find((provider) => provider.provider === selectedProviderName) ?? null,
    [providers, selectedProviderName],
  )

  const useLegacyReadEndpoints = selectedProviderName === 'binance'
  const { features, regimes, dataQuality, loading, error, refetch } = useMarketData({
    symbol: selectedSymbol,
    interval: selectedTimeframe,
    supportsOpenInterest: selectedProvider?.supports_open_interest ?? true,
    supportsFundingRate: selectedProvider?.supports_funding_rate ?? true,
    useLegacyReadEndpoints,
  })

  useEffect(() => {
    let active = true

    api.getProviders()
      .then((response) => {
        if (!active) return
        setProviders(response.providers)
        const defaultProvider = response.providers.find((provider) => provider.provider === 'binance') ?? response.providers[0]
        if (defaultProvider) {
          setSelectedProviderName(defaultProvider.provider)
          setSelectedSymbol(defaultProvider.default_symbol ?? '')
          setSelectedTimeframe(defaultProvider.supported_timeframes[0] ?? '15m')
        }
      })
      .catch((err) => console.error('Provider metadata failed:', err))

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!selectedProviderName) return
    let active = true

    api.getProviderSymbols(selectedProviderName)
      .then((response) => {
        if (!active) return
        setProviderSymbols(response.symbols)
        const provider = providers.find((item) => item.provider === selectedProviderName)
        const nextSymbol = provider?.default_symbol ?? response.symbols[0]?.symbol ?? ''
        setSelectedSymbol(nextSymbol)
        setSelectedTimeframe(provider?.supported_timeframes[0] ?? '15m')
      })
      .catch((err) => console.error('Provider symbols failed:', err))

    return () => {
      active = false
    }
  }, [providers, selectedProviderName])

  const supportedDataTypes = useMemo(() => {
    const dataTypes: ProviderDataType[] = []
    if (selectedProvider?.supports_ohlcv) dataTypes.push('ohlcv')
    if (selectedProvider?.supports_open_interest) dataTypes.push('open_interest')
    if (selectedProvider?.supports_funding_rate) dataTypes.push('funding_rate')
    return dataTypes
  }, [selectedProvider])

  const featureCount = features?.data?.length ?? 0
  const latestFeature = featureCount > 0 ? features?.data[featureCount - 1] : null
  const canDownload = Boolean(selectedProvider && selectedProvider.provider !== 'local_file')
  const canProcess = selectedProviderName === 'binance'
  const workflowStatus = downloading
    ? 'Downloading data'
    : processing
      ? 'Processing features'
      : featureCount > 0
        ? 'Ready for review'
        : 'Waiting for local data'

  const handleDownload = async () => {
    if (!selectedProvider || selectedProvider.provider === 'local_file') return
    setDownloading(true)
    try {
      await api.downloadProvider({
        provider: selectedProvider.provider,
        symbol: selectedSymbol,
        timeframe: selectedTimeframe,
        days: 30,
        data_types: supportedDataTypes,
      })
      await refetch()
    } catch (err) {
      console.error('Download failed:', err)
    } finally {
      setDownloading(false)
    }
  }

  const handleProcess = async () => {
    if (selectedProviderName !== 'binance') return
    setProcessing(true)
    try {
      await api.process({ symbol: selectedSymbol, interval: selectedTimeframe })
      await refetch()
    } catch (err) {
      console.error('Processing failed:', err)
    } finally {
      setProcessing(false)
    }
  }

  if (loading) {
    return <LoadingSpinner />
  }

  return (
    <div className="space-y-6 animate-enter">
      <section className="overflow-hidden rounded-md border border-white/10 bg-zinc-900/80 shadow-2xl shadow-black/20">
        <div className="grid gap-6 p-5 lg:grid-cols-[1fr_auto] lg:items-center lg:p-6">
          <div className="min-w-0">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <span className="rounded-md border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 text-xs font-medium text-emerald-200">
                Research only
              </span>
              <span className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-zinc-300">
                {workflowStatus}
              </span>
            </div>
            <h1 className="text-2xl font-semibold tracking-normal text-white sm:text-3xl">
              Market regime workspace
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-400">
              Inspect price, open interest, funding, volume, regime labels, and local data quality without enabling trading or execution behavior.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:min-w-[32rem]">
            <SummaryTile label="Provider" value={selectedProvider?.display_name ?? 'Loading'} />
            <SummaryTile label="Symbol" value={selectedSymbol || 'n/a'} />
            <SummaryTile label="Timeframe" value={selectedTimeframe || 'n/a'} />
            <SummaryTile label="Bars" value={featureCount.toLocaleString()} />
          </div>
        </div>
      </section>

      {error && (
        <NoticePanel
          title="Some research data is not available yet"
          action={
            <button
              onClick={refetch}
              className="h-9 rounded-md bg-white px-3 text-sm font-medium text-zinc-950 transition hover:bg-zinc-200"
            >
              Retry
            </button>
          }
        >
          {error}
        </NoticePanel>
      )}

      <ProviderPanel
        providers={providers}
        selectedProvider={selectedProvider}
        symbols={providerSymbols}
        selectedProviderName={selectedProviderName}
        selectedSymbol={selectedSymbol}
        selectedTimeframe={selectedTimeframe}
        onProviderChange={setSelectedProviderName}
        onSymbolChange={setSelectedSymbol}
        onTimeframeChange={setSelectedTimeframe}
        disabled={downloading || processing}
      />

      <section className="grid gap-4 rounded-md border border-white/10 bg-zinc-900/80 p-4 shadow-xl shadow-black/10 lg:grid-cols-[1fr_auto] lg:items-center">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-white">Research workflow</h2>
          <p className="mt-1 text-sm text-zinc-400">
            Latest candle: {latestFeature?.timestamp ?? 'not loaded'}.
          </p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <ActionButton
            onClick={handleDownload}
            disabled={downloading || !canDownload}
            busy={downloading}
            tone="primary"
          >
            {downloading ? 'Downloading' : 'Download Data'}
          </ActionButton>
          <ActionButton
            onClick={handleProcess}
            disabled={processing || !canProcess}
            busy={processing}
            tone="success"
          >
            {processing ? 'Processing' : 'Process Features'}
          </ActionButton>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
        <div className="lg:col-span-3">
          <ChartPanel
            title="Price and range"
            subtitle="Candles with range high, mid, and low references."
          >
            {features?.data ? (
              <CandlestickChart data={features.data} height={400} />
            ) : (
              <EmptyState>No feature data available for the selected source.</EmptyState>
            )}
          </ChartPanel>
        </div>

        <div className="space-y-4 animate-enter-delay">
          {regimes?.data && <RegimePanel data={regimes.data} />}
          {dataQuality && <DataQualityPanel data={dataQuality} />}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <ChartPanel title="Open interest" compact>
          {selectedProvider?.supports_open_interest === false ? (
            <EmptyState compact>Not supported by this provider.</EmptyState>
          ) : features?.data ? (
            <OIChart data={features.data} height={200} />
          ) : (
            <EmptyState compact>No open interest data.</EmptyState>
          )}
        </ChartPanel>

        <ChartPanel title="Funding rate" compact>
          {selectedProvider?.supports_funding_rate === false ? (
            <EmptyState compact>Not supported by this provider.</EmptyState>
          ) : features?.data ? (
            <FundingChart data={features.data} height={200} />
          ) : (
            <EmptyState compact>No funding data.</EmptyState>
          )}
        </ChartPanel>

        <ChartPanel title="Volume" compact>
          {features?.data ? (
            <VolumeChart data={features.data} height={200} />
          ) : (
            <EmptyState compact>No volume data.</EmptyState>
          )}
        </ChartPanel>
      </div>
    </div>
  )
}

function SummaryTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="min-h-20 rounded-md border border-white/10 bg-white/[0.04] p-3">
      <div className="text-xs uppercase text-zinc-500">{label}</div>
      <div className="mt-2 truncate text-base font-semibold text-white">{value}</div>
    </div>
  )
}

function NoticePanel({
  action,
  children,
  title,
}: {
  action?: ReactNode
  children: ReactNode
  title: string
}) {
  return (
    <section className="flex flex-col gap-4 rounded-md border border-amber-300/30 bg-amber-300/10 p-4 text-amber-50 shadow-xl shadow-black/10 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h2 className="text-sm font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-amber-100/80">{children}</p>
      </div>
      {action}
    </section>
  )
}

function ActionButton({
  busy,
  children,
  disabled,
  onClick,
  tone,
}: {
  busy?: boolean
  children: ReactNode
  disabled?: boolean
  onClick: () => void
  tone: 'primary' | 'success'
}) {
  const toneClass =
    tone === 'success'
      ? 'bg-emerald-400 text-zinc-950 hover:bg-emerald-300'
      : 'bg-sky-300 text-zinc-950 hover:bg-sky-200'

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex h-11 min-w-40 items-center justify-center gap-2 rounded-md px-4 text-sm font-semibold transition focus:outline-none focus:ring-2 focus:ring-white/60 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400 ${toneClass}`}
    >
      {busy && <span className="h-2 w-2 rounded-full bg-current animate-soft-pulse" />}
      {children}
    </button>
  )
}

function ChartPanel({
  children,
  compact = false,
  subtitle,
  title,
}: {
  children: ReactNode
  compact?: boolean
  subtitle?: string
  title: string
}) {
  return (
    <section className="rounded-md border border-white/10 bg-zinc-900/80 p-4 shadow-xl shadow-black/10">
      <div className={compact ? 'mb-3' : 'mb-4 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between'}>
        <div>
          <h2 className={compact ? 'text-base font-semibold text-white' : 'text-lg font-semibold text-white'}>{title}</h2>
          {subtitle && <p className="mt-1 text-sm text-zinc-400">{subtitle}</p>}
        </div>
      </div>
      <div className="overflow-hidden rounded-md border border-white/10 bg-zinc-950/70 p-2">
        {children}
      </div>
    </section>
  )
}

function EmptyState({ children, compact = false }: { children: ReactNode; compact?: boolean }) {
  return (
    <div className={`grid place-items-center rounded-md border border-dashed border-white/15 bg-white/[0.03] text-center text-sm text-zinc-400 ${compact ? 'min-h-52 p-4' : 'min-h-96 p-6'}`}>
      {children}
    </div>
  )
}
