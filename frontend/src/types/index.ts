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

export type BacktestStatus = 'completed' | 'failed' | 'partial';
export type BacktestStrategyMode = 'grid_range' | 'breakout' | 'buy_hold' | 'price_breakout' | 'no_trade';
export type BacktestBaselineMode = 'buy_hold' | 'price_breakout' | 'no_trade';
export type BacktestArtifactType = 'metadata' | 'config' | 'trades' | 'equity' | 'metrics' | 'report_json' | 'report_markdown';
export type BacktestArtifactFormat = 'json' | 'parquet' | 'markdown';
export type BacktestTradeSide = 'long' | 'short';
export type BacktestExitReason = 'take_profit' | 'stop_loss' | 'end_of_data' | 'invalidated';

export interface BacktestArtifact {
  artifact_type: BacktestArtifactType;
  path: string;
  format: BacktestArtifactFormat;
  rows: number | null;
  created_at: string;
  content_hash: string | null;
}

export interface BacktestRunSummary {
  run_id: string;
  status: BacktestStatus;
  created_at: string;
  symbol: string;
  provider: string | null;
  timeframe: string;
  strategy_modes: BacktestStrategyMode[];
  baseline_modes: BacktestBaselineMode[];
  total_return_pct: number | null;
  max_drawdown_pct: number | null;
}

export interface BacktestRunConfig {
  symbol: string;
  provider: string | null;
  timeframe: string;
  feature_path: string | null;
  initial_equity: number;
  assumptions: Record<string, unknown>;
  strategies: Array<Record<string, unknown>>;
  baselines: BacktestBaselineMode[];
  report_format: string;
}

export interface BacktestRun {
  run_id: string;
  status: BacktestStatus;
  created_at: string;
  completed_at: string | null;
  symbol: string;
  provider: string | null;
  timeframe: string;
  feature_path: string;
  config: BacktestRunConfig;
  config_hash: string | null;
  data_identity: Record<string, unknown>;
  limitations: string[];
  artifacts: BacktestArtifact[];
  warnings: string[];
}

export interface BacktestTrade {
  trade_id: string;
  run_id: string;
  strategy_mode: BacktestStrategyMode;
  provider: string | null;
  symbol: string;
  timeframe: string;
  side: BacktestTradeSide;
  regime_at_signal: string | null;
  signal_timestamp: string;
  entry_timestamp: string;
  entry_price: number;
  exit_timestamp: string;
  exit_price: number;
  exit_reason: BacktestExitReason;
  quantity: number;
  notional: number;
  gross_pnl: number;
  fees: number;
  slippage: number;
  net_pnl: number;
  return_pct: number;
  holding_bars: number;
  assumptions_snapshot?: Record<string, unknown>;
}

export interface BacktestMetrics {
  total_return: number;
  total_return_pct: number;
  max_drawdown: number;
  max_drawdown_pct: number;
  profit_factor: number | null;
  win_rate: number | null;
  average_win: number | null;
  average_loss: number | null;
  expectancy: number | null;
  number_of_trades: number;
  average_holding_bars: number | null;
  max_consecutive_losses: number;
  return_by_regime: Record<string, Record<string, unknown>>;
  return_by_strategy_mode: Record<string, Record<string, unknown>>;
  return_by_symbol_provider: Record<string, Record<string, unknown>>;
  baseline_comparison: Array<Record<string, unknown>>;
  notes: string[];
}

export interface BacktestEquityPoint {
  timestamp: string;
  strategy_mode: BacktestStrategyMode;
  equity: number;
  drawdown: number;
  drawdown_pct: number;
  realized_pnl: number;
  open_position: boolean;
}

export interface BacktestRunListResponse {
  runs: BacktestRunSummary[];
}

export interface BacktestTradesResponse {
  data: BacktestTrade[];
  meta: {
    count: number;
    limit: number;
    offset: number;
  };
}

export interface BacktestMetricsResponse {
  run_id: string;
  summary: BacktestMetrics;
  return_by_regime: Array<Record<string, unknown>>;
  return_by_strategy_mode: Array<Record<string, unknown>>;
  return_by_symbol_provider: Array<Record<string, unknown>>;
  baseline_comparison: Array<Record<string, unknown>>;
  notes: string[];
}

export interface BacktestEquityResponse {
  run_id: string;
  data: BacktestEquityPoint[];
  meta: {
    count: number;
  };
}
