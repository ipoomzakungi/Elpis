'use client'

import { useState } from 'react'
import { useMarketData } from '@/hooks/useMarketData'
import CandlestickChart from '@/components/charts/CandlestickChart'
import OIChart from '@/components/charts/OIChart'
import FundingChart from '@/components/charts/FundingChart'
import VolumeChart from '@/components/charts/VolumeChart'
import RegimePanel from '@/components/panels/RegimePanel'
import DataQualityPanel from '@/components/panels/DataQualityPanel'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import { api } from '@/services/api'

export default function Dashboard() {
  const { ohlcv, openInterest, fundingRate, features, regimes, dataQuality, loading, error, refetch } = useMarketData()
  const [downloading, setDownloading] = useState(false)
  const [processing, setProcessing] = useState(false)

  const handleDownload = async () => {
    setDownloading(true)
    try {
      await api.download({ days: 30 })
      await refetch()
    } catch (err) {
      console.error('Download failed:', err)
    } finally {
      setDownloading(false)
    }
  }

  const handleProcess = async () => {
    setProcessing(true)
    try {
      await api.process()
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
      {/* Action buttons */}
      <div className="flex gap-4">
        <button
          onClick={handleDownload}
          disabled={downloading}
          className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 px-4 py-2 rounded"
        >
          {downloading ? 'Downloading...' : 'Download Data (30 days)'}
        </button>
        <button
          onClick={handleProcess}
          disabled={processing}
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
          {features?.data ? (
            <OIChart data={features.data} height={200} />
          ) : (
            <p className="text-gray-400 text-sm">No data</p>
          )}
        </div>

        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-md font-semibold mb-2">Funding Rate</h3>
          {features?.data ? (
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
