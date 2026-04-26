import { useState, useEffect, useCallback } from 'react';
import { api } from '@/services/api';
import {
  ApiResponse,
  DataQualityResponse,
  Feature,
  FundingRate,
  MarketData,
  OpenInterest,
  Regime,
} from '@/types';

interface UseMarketDataOptions {
  symbol?: string;
  interval?: string;
  limit?: number;
  autoFetch?: boolean;
  supportsOpenInterest?: boolean;
  supportsFundingRate?: boolean;
  useLegacyReadEndpoints?: boolean;
}

export function useMarketData(options: UseMarketDataOptions = {}) {
  const {
    symbol = 'BTCUSDT',
    interval = '15m',
    limit = 1000,
    autoFetch = true,
    supportsOpenInterest = true,
    supportsFundingRate = true,
    useLegacyReadEndpoints = true,
  } = options;

  const [ohlcv, setOhlcv] = useState<ApiResponse<MarketData> | null>(null);
  const [openInterest, setOpenInterest] = useState<ApiResponse<OpenInterest> | null>(null);
  const [fundingRate, setFundingRate] = useState<ApiResponse<FundingRate> | null>(null);
  const [features, setFeatures] = useState<ApiResponse<Feature> | null>(null);
  const [regimes, setRegimes] = useState<ApiResponse<Regime> | null>(null);
  const [dataQuality, setDataQuality] = useState<DataQualityResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (!useLegacyReadEndpoints) {
        setOhlcv(null);
        setOpenInterest(null);
        setFundingRate(null);
        setFeatures(null);
        setRegimes(null);
        setDataQuality(null);
        return;
      }

      const [ohlcvData, oiData, frData, featData, regData, dqData] = await Promise.all([
        api.getOHLCV({ symbol, interval, limit }),
        supportsOpenInterest ? api.getOpenInterest({ symbol, interval, limit }) : Promise.resolve(null),
        supportsFundingRate ? api.getFundingRate({ symbol, limit }) : Promise.resolve(null),
        api.getFeatures({ symbol, interval, limit }),
        api.getRegimes({ symbol, interval, limit }),
        api.getDataQuality(symbol),
      ]);
      setOhlcv(ohlcvData);
      setOpenInterest(oiData);
      setFundingRate(frData);
      setFeatures(featData);
      setRegimes(regData);
      setDataQuality(dqData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  }, [symbol, interval, limit, supportsOpenInterest, supportsFundingRate, useLegacyReadEndpoints]);

  useEffect(() => {
    if (autoFetch) {
      fetchAll();
    }
  }, [autoFetch, fetchAll]);

  return {
    ohlcv,
    openInterest,
    fundingRate,
    features,
    regimes,
    dataQuality,
    loading,
    error,
    refetch: fetchAll,
  };
}
