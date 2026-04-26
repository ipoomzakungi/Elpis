'use client'

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

  if (error) {
    return (
      <div className="text-center p-8">
        <p className="text-red-400 mb-4">{error}</p>
        <button
          onClick={refetch}
          className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
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

      {/* Action buttons */}
      <div className="flex gap-4">
        <button
          onClick={handleDownload}
          disabled={downloading || selectedProvider?.provider === 'local_file'}
          className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 px-4 py-2 rounded"
        >
          {downloading ? 'Downloading...' : 'Download Data'}
        </button>
        <button
          onClick={handleProcess}
          disabled={processing || selectedProviderName !== 'binance'}
          className="bg-green-600 hover:bg-green-700 disabled:bg-gray-600 px-4 py-2 rounded"
        >
          {processing ? 'Processing...' : 'Process Features'}
        </button>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Main chart */}
        <div className="lg:col-span-3">
          <div className="bg-gray-800 rounded-lg p-4">
            <h2 className="text-lg font-semibold mb-4">Price Chart</h2>
            {features?.data ? (
              <CandlestickChart data={features.data} height={400} />
            ) : (
              <p className="text-gray-400">No data available. Click "Download Data" to start.</p>
            )}
          </div>
        </div>

        {/* Side panel */}
        <div className="space-y-4">
          {regimes?.data && <RegimePanel data={regimes.data} />}
          {dataQuality && <DataQualityPanel data={dataQuality} />}
        </div>
      </div>

      {/* Additional charts */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-md font-semibold mb-2">Open Interest</h3>
          {selectedProvider?.supports_open_interest === false ? (
            <p className="text-gray-400 text-sm">Not supported by this provider</p>
          ) : features?.data ? (
            <OIChart data={features.data} height={200} />
          ) : (
            <p className="text-gray-400 text-sm">No data</p>
          )}
        </div>

        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-md font-semibold mb-2">Funding Rate</h3>
          {selectedProvider?.supports_funding_rate === false ? (
            <p className="text-gray-400 text-sm">Not supported by this provider</p>
          ) : features?.data ? (
            <FundingChart data={features.data} height={200} />
          ) : (
            <p className="text-gray-400 text-sm">No data</p>
          )}
        </div>

        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-md font-semibold mb-2">Volume</h3>
          {features?.data ? (
            <VolumeChart data={features.data} height={200} />
          ) : (
            <p className="text-gray-400 text-sm">No data</p>
          )}
        </div>
      </div>
    </div>
  )
}
