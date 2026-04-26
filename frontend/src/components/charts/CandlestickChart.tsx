'use client'

import { useEffect, useRef } from 'react'
import { createChart, IChartApi, ISeriesApi, CandlestickData, LineData } from 'lightweight-charts'
import { Feature } from '@/types'

interface CandlestickChartProps {
  data: Feature[]
  height?: number
}

export default function CandlestickChart({ data, height = 400 }: CandlestickChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!chartContainerRef.current || data.length === 0) return

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: height,
      layout: {
        background: { color: '#1a1a1a' },
        textColor: '#d1d5db',
      },
      grid: {
        vertLines: { color: '#2d2d2d' },
        horzLines: { color: '#2d2d2d' },
      },
    })

    chartRef.current = chart

    // Candlestick series
    const candlestickSeries = chart.addCandlestickSeries({
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderDownColor: '#ef4444',
      borderUpColor: '#22c55e',
      wickDownColor: '#ef4444',
      wickUpColor: '#22c55e',
    })

    const candlestickData: CandlestickData[] = data.map((d) => ({
      time: d.timestamp as any,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }))

    candlestickSeries.setData(candlestickData)

    // Range High line
    const rangeHighSeries = chart.addLineSeries({
      color: '#3b82f6',
      lineWidth: 1,
      lineStyle: 2,
      title: 'Range High',
    })

    const rangeHighData: LineData[] = data.map((d) => ({
      time: d.timestamp as any,
      value: d.range_high,
    }))

    rangeHighSeries.setData(rangeHighData)

    // Range Low line
    const rangeLowSeries = chart.addLineSeries({
      color: '#3b82f6',
      lineWidth: 1,
      lineStyle: 2,
      title: 'Range Low',
    })

    const rangeLowData: LineData[] = data.map((d) => ({
      time: d.timestamp as any,
      value: d.range_low,
    }))

    rangeLowSeries.setData(rangeLowData)

    // Range Mid line
    const rangeMidSeries = chart.addLineSeries({
      color: '#6b7280',
      lineWidth: 1,
      lineStyle: 1,
      title: 'Range Mid',
    })

    const rangeMidData: LineData[] = data.map((d) => ({
      time: d.timestamp as any,
      value: d.range_mid,
    }))

    rangeMidSeries.setData(rangeMidData)

    chart.timeScale().fitContent()

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth })
      }
    }

    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [data, height])

  return <div ref={chartContainerRef} className="w-full" />
}
