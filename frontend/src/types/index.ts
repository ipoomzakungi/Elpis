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
export type BacktestArtifactType =
  | 'metadata'
  | 'config'
  | 'trades'
  | 'equity'
  | 'metrics'
  | 'report_json'
  | 'report_markdown'
  | 'validation_metadata'
  | 'validation_config'
  | 'validation_stress'
  | 'validation_sensitivity'
  | 'validation_walk_forward'
  | 'validation_concentration'
  | 'validation_report_json'
  | 'validation_report_markdown'
  | 'research_metadata'
  | 'research_config'
  | 'research_asset_summary'
  | 'research_comparison'
  | 'research_stress_summary'
  | 'research_walk_forward_summary'
  | 'research_regime_coverage_summary'
  | 'research_concentration_summary'
  | 'research_report_json'
  | 'research_report_markdown';
export type BacktestArtifactFormat = 'json' | 'parquet' | 'markdown';
export type BacktestTradeSide = 'long' | 'short';
export type BacktestExitReason = 'take_profit' | 'stop_loss' | 'end_of_data' | 'invalidated';
export type ValidationStressProfileName = 'normal' | 'high_fee' | 'high_slippage' | 'worst_reasonable_cost';
export type ValidationSplitStatus = 'evaluated' | 'insufficient_data';
export type StressOutcome = 'remained_positive' | 'turned_negative' | 'no_trades' | 'not_evaluable';
export type DrawdownRecoveryStatus = 'recovered' | 'not_recovered' | 'not_applicable';

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
  total_return: number | null;
  total_return_pct: number | null;
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
  realized_equity: number | null;
  unrealized_pnl: number | null;
  total_equity: number | null;
  equity_basis: string;
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

export interface CapitalSizingConfig {
  buy_hold_capital_fraction: number;
  buy_hold_sizing_mode: 'capital_fraction' | 'risk_fractional';
  active_risk_per_trade: number | null;
  leverage: number;
  notional_cap_enabled: boolean;
}

export interface CostStressProfile {
  name: ValidationStressProfileName;
  fee_rate: number;
  slippage_rate: number;
  description: string;
}

export interface SensitivityGrid {
  grid_entry_threshold: number[];
  atr_stop_buffer: number[];
  breakout_risk_reward_multiple: number[];
  fee_slippage_profile: ValidationStressProfileName[];
}

export interface WalkForwardConfig {
  split_count: number;
  minimum_rows_per_split: number;
}

export interface ValidationRunRequest {
  base_config: BacktestRunConfig;
  capital_sizing: CapitalSizingConfig;
  stress_profiles: ValidationStressProfileName[];
  sensitivity_grid: SensitivityGrid;
  walk_forward: WalkForwardConfig;
  include_real_data_check: boolean;
}

export interface NotionalCapEvent {
  trade_id: string | null;
  strategy_mode: BacktestStrategyMode;
  requested_notional: number;
  capped_notional: number;
  available_equity: number;
  reason: string;
}

export interface ModeMetrics {
  strategy_mode: BacktestStrategyMode;
  category: string;
  total_return_pct: number | null;
  max_drawdown_pct: number | null;
  number_of_trades: number;
  profit_factor: number | null;
  win_rate: number | null;
  expectancy: number | null;
  equity_basis: string;
  notes: string[];
}

export interface StressResult {
  profile: CostStressProfile;
  strategy_mode: BacktestStrategyMode;
  category: string;
  metrics: ModeMetrics;
  outcome: StressOutcome;
  notes: string[];
}

export interface ParameterSensitivityResult {
  parameter_set_id: string;
  grid_entry_threshold: number | null;
  atr_stop_buffer: number | null;
  breakout_risk_reward_multiple: number | null;
  stress_profile_name: ValidationStressProfileName | null;
  strategy_mode: BacktestStrategyMode;
  metrics: ModeMetrics;
  fragility_flag: boolean;
  notes: string[];
}

export interface WalkForwardResult {
  split_id: string;
  start_timestamp: string;
  end_timestamp: string;
  row_count: number;
  trade_count: number;
  status: ValidationSplitStatus;
  mode_metrics: ModeMetrics[];
  notes: string[];
}

export interface RegimeCoverageReport {
  bar_counts: Record<string, number>;
  trades_per_regime: Record<string, number>;
  return_by_regime: Record<string, Record<string, unknown>>;
  coverage_notes: string[];
}

export interface TradeConcentrationReport {
  top_1_profit_contribution_pct: number | null;
  top_5_profit_contribution_pct: number | null;
  top_10_profit_contribution_pct: number | null;
  best_trades: BacktestTrade[];
  worst_trades: BacktestTrade[];
  max_consecutive_losses: number;
  drawdown_recovery_bars: number | null;
  drawdown_recovery_status: DrawdownRecoveryStatus;
  notes: string[];
}

export interface ValidationRun {
  validation_run_id: string;
  status: BacktestStatus;
  created_at: string;
  completed_at: string | null;
  symbol: string;
  provider: string | null;
  timeframe: string;
  source_backtest_config: BacktestRunConfig;
  data_identity: Record<string, unknown>;
  mode_metrics: ModeMetrics[];
  stress_results: StressResult[];
  sensitivity_results: ParameterSensitivityResult[];
  walk_forward_results: WalkForwardResult[];
  regime_coverage: RegimeCoverageReport;
  concentration_report: TradeConcentrationReport;
  notional_cap_events: NotionalCapEvent[];
  warnings: string[];
  artifacts: BacktestArtifact[];
}

export interface ValidationRunSummary {
  validation_run_id: string;
  status: BacktestStatus;
  created_at: string;
  symbol: string;
  provider: string | null;
  timeframe: string;
  mode_count: number;
  stress_profile_count: number;
  walk_forward_split_count: number;
  warnings: string[];
}

export interface ValidationRunListResponse {
  runs: ValidationRunSummary[];
}

export interface ValidationStressResponse {
  validation_run_id: string;
  data: StressResult[];
}

export interface ValidationSensitivityResponse {
  validation_run_id: string;
  data: ParameterSensitivityResult[];
}

export type ValidationStressTableRow = StressResult;
export type ValidationSensitivityTableRow = ParameterSensitivityResult;
export type ValidationWalkForwardTableRow = WalkForwardResult;

export interface ValidationWalkForwardResponse {
  validation_run_id: string;
  data: WalkForwardResult[];
}

export interface ValidationConcentrationResponse {
  validation_run_id: string;
  regime_coverage: RegimeCoverageReport;
  concentration_report: TradeConcentrationReport;
}

export interface RegimeCoverageTableRow {
  regime: string;
  bars: number;
  trades: number;
  net_pnl: number | null;
  return_pct: number | null;
}

export interface TradeConcentrationSummaryRow {
  metric: string;
  value: number | string | null;
}

export type ResearchAssetClass =
  | 'crypto'
  | 'equity_proxy'
  | 'gold_proxy'
  | 'macro_proxy'
  | 'local_dataset';
export type ResearchFeatureGroup = 'ohlcv' | 'regime' | 'oi' | 'funding' | 'volume_confirmation';
export type ResearchPreflightStatus =
  | 'ready'
  | 'missing_data'
  | 'incomplete_features'
  | 'unsupported_capability';
export type ResearchAssetRunStatus = 'completed' | 'blocked' | 'partial';
export type ResearchAssetClassification =
  | 'robust'
  | 'fragile'
  | 'missing_data'
  | 'inconclusive'
  | 'not_worth_continuing';
export type ConcentrationWarningLevel = 'none' | 'watch' | 'high';

export interface ResearchAssetConfig {
  symbol: string;
  provider: string;
  asset_class: ResearchAssetClass;
  timeframe: string;
  enabled: boolean;
  feature_path: string | null;
  required_feature_groups: ResearchFeatureGroup[];
  display_name: string | null;
}

export interface ResearchBaseAssumptions {
  initial_equity: number;
  fee_rate: number;
  slippage_rate: number;
  risk_per_trade: number;
  allow_short: boolean;
}

export interface ResearchStrategySet {
  include_grid_range: boolean;
  include_breakout: boolean;
  baselines: BacktestBaselineMode[];
}

export interface ResearchSensitivityGrid {
  grid_entry_threshold: number[];
  atr_stop_buffer: number[];
  breakout_risk_reward_multiple: number[];
  fee_slippage_profile: ValidationStressProfileName[];
}

export interface ResearchWalkForwardConfig {
  split_count: number;
  minimum_rows_per_split: number;
}

export interface ResearchValidationConfig {
  stress_profiles: ValidationStressProfileName[];
  sensitivity_grid: ResearchSensitivityGrid;
  walk_forward: ResearchWalkForwardConfig;
}

export interface ResearchRunRequest {
  assets: ResearchAssetConfig[];
  default_asset_set: string | null;
  base_assumptions: ResearchBaseAssumptions;
  strategy_set: ResearchStrategySet;
  validation_config: ResearchValidationConfig;
  report_format: 'json' | 'markdown' | 'both';
  include_blocked_assets: boolean;
}

export interface ResearchCapabilitySnapshot {
  provider: string;
  supports_ohlcv: boolean;
  supports_open_interest: boolean;
  supports_funding_rate: boolean;
  detected_ohlcv: boolean;
  detected_regime: boolean;
  detected_open_interest: boolean;
  detected_funding_rate: boolean;
  limitation_notes: string[];
}

export interface ResearchPreflightResult {
  symbol: string;
  provider: string;
  status: ResearchPreflightStatus;
  feature_path: string;
  row_count: number | null;
  first_timestamp: string | null;
  last_timestamp: string | null;
  capability_snapshot: ResearchCapabilitySnapshot;
  missing_columns: string[];
  instructions: string[];
  warnings: string[];
}

export interface StrategyComparisonRow {
  symbol: string;
  provider: string;
  mode: string;
  category: string;
  total_return_pct: number | null;
  max_drawdown_pct: number | null;
  number_of_trades: number;
  profit_factor: number | null;
  win_rate: number | null;
  notes: string[];
}

export interface StressSurvivalRow {
  symbol: string;
  mode: string;
  profile: string;
  outcome: string;
  survived: boolean | null;
  notes: string[];
}

export interface WalkForwardStabilityRow {
  symbol: string;
  split_id: string;
  status: string;
  row_count: number;
  trade_count: number;
  stable: boolean | null;
  notes: string[];
}

export interface RegimeCoverageAssetRow {
  symbol: string;
  regime: string;
  bar_count: number;
  trade_count: number;
  return_pct: number | null;
  notes: string[];
}

export interface ConcentrationAssetRow {
  symbol: string;
  top_1_profit_contribution_pct: number | null;
  top_5_profit_contribution_pct: number | null;
  top_10_profit_contribution_pct: number | null;
  max_consecutive_losses: number;
  drawdown_recovery_status: string;
  warning_level: ConcentrationWarningLevel;
  notes: string[];
}

export interface ResearchAssetResult {
  symbol: string;
  provider: string;
  asset_class: ResearchAssetClass;
  status: ResearchAssetRunStatus;
  classification: ResearchAssetClassification;
  preflight: ResearchPreflightResult;
  validation_run_id: string | null;
  data_identity: Record<string, unknown>;
  strategy_comparison: StrategyComparisonRow[];
  stress_summary: StressSurvivalRow[];
  walk_forward_summary: WalkForwardStabilityRow[];
  regime_coverage_summary: RegimeCoverageAssetRow[];
  concentration_summary: ConcentrationAssetRow[];
  warnings: string[];
  limitations: string[];
}

export interface ResearchRun {
  research_run_id: string;
  status: BacktestStatus;
  created_at: string;
  completed_at: string | null;
  request: ResearchRunRequest;
  assets: ResearchAssetResult[];
  completed_count: number;
  blocked_count: number;
  warnings: string[];
  limitations: string[];
  artifacts: BacktestArtifact[];
}

export interface ResearchRunSummary {
  research_run_id: string;
  status: BacktestStatus;
  created_at: string;
  completed_count: number;
  blocked_count: number;
  asset_count: number;
  warnings: string[];
}

export interface ResearchRunListResponse {
  runs: ResearchRunSummary[];
}

export interface ResearchAssetSummaryResponse {
  research_run_id: string;
  data: ResearchAssetResult[];
}

export interface ResearchComparisonResponse {
  research_run_id: string;
  data: StrategyComparisonRow[];
}

export interface ResearchValidationAggregationResponse {
  research_run_id: string;
  stress: StressSurvivalRow[];
  walk_forward: WalkForwardStabilityRow[];
  regime_coverage: RegimeCoverageAssetRow[];
  concentration: ConcentrationAssetRow[];
}
