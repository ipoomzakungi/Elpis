export interface MarketData {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  quote_volume: number;
  trades: number;
  taker_buy_volume: number;
}

export interface OpenInterest {
  timestamp: string;
  symbol: string;
  open_interest: number;
  open_interest_value: number;
}

export interface FundingRate {
  timestamp: string;
  symbol: string;
  funding_rate: number;
  mark_price: number;
}

export interface Feature {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  atr: number;
  range_high: number;
  range_low: number;
  range_mid: number;
  open_interest: number | null;
  oi_change_pct: number | null;
  volume_ratio: number;
  funding_rate: number | null;
  funding_rate_change: number | null;
  funding_rate_cumsum: number | null;
}

export type RegimeType = 'RANGE' | 'BREAKOUT_UP' | 'BREAKOUT_DOWN' | 'AVOID';

export interface Regime {
  timestamp: string;
  regime: RegimeType;
  confidence: number;
  reason: string | null;
}

export interface DataQuality {
  data_type: string;
  total_records: number;
  missing_timestamps: number;
  duplicate_timestamps: number;
  first_timestamp: string | null;
  last_timestamp: string | null;
  last_updated: string;
}

export interface ApiResponse<T> {
  data: T[];
  meta: {
    symbol: string;
    interval: string;
    count: number;
    start_time?: string;
    end_time?: string;
    regime_counts?: Record<RegimeType, number>;
  };
}

export interface DownloadRequest {
  symbol?: string;
  interval?: string;
  days?: number;
}

export interface ProcessRequest {
  symbol?: string;
  interval?: string;
}

export interface TaskResponse {
  status: string;
  task_id: string;
  message: string;
}

export interface DataQualityResponse {
  ohlcv: DataQuality;
  open_interest: DataQuality;
  funding_rate: DataQuality;
}

export type ProviderDataType = 'ohlcv' | 'open_interest' | 'funding_rate' | 'features';

export interface ProviderCapability {
  data_type: ProviderDataType;
  supported: boolean;
  unsupported_reason: string | null;
}

export interface ProviderInfo {
  provider: string;
  display_name: string;
  supports_ohlcv: boolean;
  supports_open_interest: boolean;
  supports_funding_rate: boolean;
  requires_auth: boolean;
  supported_timeframes: string[];
  default_symbol: string | null;
  limitations: string[];
  capabilities: ProviderCapability[];
}

export interface ProviderSymbol {
  symbol: string;
  display_name: string | null;
  asset_class: string;
  supports_ohlcv: boolean;
  supports_open_interest: boolean;
  supports_funding_rate: boolean;
  notes: string[];
}

export interface ProvidersResponse {
  providers: ProviderInfo[];
}

export interface ProviderSymbolsResponse {
  provider: string;
  symbols: ProviderSymbol[];
}

export interface ProviderDownloadRequest {
  provider: string;
  symbol?: string;
  timeframe: string;
  days?: number;
  data_types?: ProviderDataType[];
  local_file_path?: string;
}

export interface UnsupportedCapability {
  provider: string;
  data_type: ProviderDataType;
  reason: string;
}

export interface DataArtifact {
  data_type: ProviderDataType;
  path: string;
  rows: number;
  provider: string;
  symbol: string;
  timeframe: string;
  first_timestamp: string | null;
  last_timestamp: string | null;
}

export interface ProviderDownloadResult {
  status: 'completed' | 'partial' | 'failed';
  provider: string;
  symbol: string;
  timeframe: string;
  completed_data_types: ProviderDataType[];
  skipped_data_types: UnsupportedCapability[];
  artifacts: DataArtifact[];
  message: string;
  warnings: string[];
}
