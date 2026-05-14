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

export interface ResearchDashboardData {
  run: ResearchRun;
  assets: ResearchAssetSummaryResponse;
  comparison: ResearchComparisonResponse;
  validation: ResearchValidationAggregationResponse;
}

export type ResearchExecutionWorkflowStatus =
  | 'completed'
  | 'partial'
  | 'blocked'
  | 'skipped'
  | 'failed';
export type ResearchEvidenceDecision =
  | 'continue'
  | 'refine'
  | 'reject'
  | 'data_blocked'
  | 'inconclusive';
export type ResearchExecutionWorkflowType =
  | 'crypto_multi_asset'
  | 'proxy_ohlcv'
  | 'xau_vol_oi'
  | 'evidence_summary';

export interface CryptoResearchWorkflowConfig {
  enabled?: boolean;
  workflow_type?: ResearchExecutionWorkflowType;
  primary_assets?: string[];
  optional_assets?: string[];
  timeframe?: string;
  processed_feature_root?: string | null;
  required_capabilities?: string[];
  existing_research_run_id?: string | null;
}

export interface ProxyResearchWorkflowConfig {
  enabled?: boolean;
  workflow_type?: ResearchExecutionWorkflowType;
  assets?: string[];
  provider?: string;
  timeframe?: string;
  processed_feature_root?: string | null;
  required_capabilities?: string[];
  existing_research_run_id?: string | null;
}

export interface XauVolOiWorkflowConfig {
  enabled?: boolean;
  workflow_type?: ResearchExecutionWorkflowType;
  options_oi_file_path?: string | null;
  existing_xau_report_id?: string | null;
  spot_reference?: Record<string, unknown> | null;
  futures_reference?: Record<string, unknown> | null;
  manual_basis?: number | null;
  volatility_snapshot?: Record<string, unknown> | null;
  include_2sd_range?: boolean;
  required_capabilities?: string[];
}

export interface ResearchExecutionRunRequest {
  name?: string | null;
  description?: string | null;
  crypto?: CryptoResearchWorkflowConfig | null;
  proxy?: ProxyResearchWorkflowConfig | null;
  xau?: XauVolOiWorkflowConfig | null;
  evidence_options?: Record<string, unknown>;
  reference_report_ids?: string[];
  research_only_acknowledged: boolean;
}

export interface ResearchExecutionPreflightResult {
  workflow_type: ResearchExecutionWorkflowType;
  status: ResearchExecutionWorkflowStatus;
  asset: string | null;
  source_identity: string | null;
  ready: boolean;
  feature_path: string | null;
  row_count: number | null;
  date_start: string | null;
  date_end: string | null;
  missing_data_actions: string[];
  unsupported_capabilities: string[];
  capability_snapshot: Record<string, unknown>;
  warnings: string[];
  limitations: string[];
}

export interface ResearchExecutionWorkflowResult {
  workflow_type: ResearchExecutionWorkflowType;
  status: ResearchExecutionWorkflowStatus;
  decision: ResearchEvidenceDecision;
  decision_reason: string;
  report_ids: string[];
  asset_results: ResearchExecutionPreflightResult[];
  warnings: string[];
  limitations: string[];
  missing_data_actions: string[];
}

export interface ResearchEvidenceSummary {
  execution_run_id: string;
  status: ResearchExecutionWorkflowStatus;
  decision: ResearchEvidenceDecision;
  workflow_results: ResearchExecutionWorkflowResult[];
  crypto_summary: Record<string, unknown> | null;
  proxy_summary: Record<string, unknown> | null;
  xau_summary: Record<string, unknown> | null;
  missing_data_checklist: string[];
  limitations: string[];
  research_only_warnings: string[];
  created_at: string;
}

export interface ResearchExecutionRun {
  execution_run_id: string;
  name: string | null;
  normalized_config: ResearchExecutionRunRequest;
  preflight_results: ResearchExecutionPreflightResult[];
  evidence_summary: ResearchEvidenceSummary | null;
  artifact_paths: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface ResearchExecutionRunSummary {
  execution_run_id: string;
  name: string | null;
  status: ResearchExecutionWorkflowStatus;
  decision: ResearchEvidenceDecision;
  completed_workflow_count: number;
  blocked_workflow_count: number;
  partial_workflow_count: number;
  failed_workflow_count: number;
  created_at: string;
  artifact_root: string;
}

export interface ResearchExecutionRunListResponse {
  runs: ResearchExecutionRunSummary[];
}

export interface ResearchExecutionMissingDataResponse {
  execution_run_id: string;
  missing_data_checklist: string[];
}

export interface ResearchExecutionWorkflowStatusCounts {
  completed: number;
  partial: number;
  blocked: number;
  skipped: number;
  failed: number;
}

export interface ResearchExecutionDashboardData {
  run: ResearchExecutionRun;
  evidence: ResearchEvidenceSummary;
  missingData: ResearchExecutionMissingDataResponse;
  statusCounts: ResearchExecutionWorkflowStatusCounts;
}

export type XauReferenceType = 'spot' | 'proxy' | 'futures' | 'manual';
export type XauFreshnessStatus = 'fresh' | 'stale' | 'unknown';
export type XauBasisSource = 'computed' | 'manual' | 'unavailable';
export type XauTimestampAlignmentStatus = 'aligned' | 'mismatched' | 'unknown';
export type XauOptionType = 'call' | 'put' | 'unknown';
export type XauVolatilitySource = 'iv' | 'realized_volatility' | 'manual' | 'unavailable';
export type XauWallType = 'call' | 'put' | 'mixed' | 'unknown';
export type XauFreshnessFactorStatus = 'confirmed' | 'neutral' | 'stale' | 'unavailable';
export type XauZoneType =
  | 'support_candidate'
  | 'resistance_candidate'
  | 'pin_risk_zone'
  | 'squeeze_risk_zone'
  | 'breakout_candidate'
  | 'reversal_candidate'
  | 'no_trade_zone';
export type XauZoneConfidence = 'high' | 'medium' | 'low' | 'unavailable';
export type XauReportStatus = 'completed' | 'partial' | 'blocked';
export type XauReportFormat = 'json' | 'markdown' | 'both';

export interface XauReferencePrice {
  source: string;
  symbol: string;
  price: number;
  timestamp: string | null;
  reference_type: XauReferenceType;
  freshness_status: XauFreshnessStatus;
  notes: string[];
}

export interface XauBasisSnapshot {
  basis: number | null;
  basis_source: XauBasisSource;
  futures_reference: XauReferencePrice | null;
  spot_reference: XauReferencePrice | null;
  timestamp_alignment_status: XauTimestampAlignmentStatus;
  mapping_available: boolean;
  notes: string[];
}

export interface XauVolatilitySnapshot {
  implied_volatility: number | null;
  realized_volatility: number | null;
  manual_expected_move: number | null;
  source: XauVolatilitySource;
  days_to_expiry: number | null;
  notes: string[];
}

export interface XauExpectedRange {
  source: XauVolatilitySource;
  reference_price: number | null;
  expected_move: number | null;
  lower_1sd: number | null;
  upper_1sd: number | null;
  lower_2sd: number | null;
  upper_2sd: number | null;
  days_to_expiry: number | null;
  unavailable_reason: string | null;
  notes: string[];
}

export interface XauVolOiReportRequest {
  options_oi_file_path: string;
  session_date?: string | null;
  spot_reference?: XauReferencePrice | null;
  futures_reference?: XauReferencePrice | null;
  manual_basis?: number | null;
  volatility_snapshot?: XauVolatilitySnapshot | null;
  include_2sd_range?: boolean;
  min_wall_score?: number;
  report_format?: XauReportFormat;
}

export interface XauOptionsImportReport {
  file_path: string;
  is_valid: boolean;
  source_row_count: number;
  accepted_row_count: number;
  rejected_row_count: number;
  required_columns_missing: string[];
  optional_columns_present: string[];
  timestamp_column: string | null;
  errors: string[];
  warnings: string[];
  instructions: string[];
}

export interface XauReportArtifact {
  artifact_type: string;
  path: string;
  format: 'json' | 'markdown' | 'parquet';
  rows: number | null;
  created_at: string;
}

export interface XauOiWall {
  wall_id: string;
  expiry: string;
  strike: number;
  spot_equivalent_level: number | null;
  basis: number | null;
  option_type: XauWallType;
  open_interest: number;
  total_expiry_open_interest: number;
  oi_share: number;
  expiry_weight: number;
  freshness_factor: number;
  wall_score: number;
  freshness_status: XauFreshnessFactorStatus;
  notes: string[];
  limitations: string[];
}

export interface XauZone {
  zone_id: string;
  zone_type: XauZoneType;
  level: number | null;
  lower_bound: number | null;
  upper_bound: number | null;
  linked_wall_ids: string[];
  wall_score: number | null;
  pin_risk_score: number | null;
  squeeze_risk_score: number | null;
  confidence: XauZoneConfidence;
  no_trade_warning: boolean;
  notes: string[];
  limitations: string[];
}

export interface XauVolOiReport {
  report_id: string;
  status: XauReportStatus;
  created_at: string;
  session_date: string | null;
  request: XauVolOiReportRequest;
  source_validation: XauOptionsImportReport;
  basis_snapshot: XauBasisSnapshot | null;
  expected_range: XauExpectedRange | null;
  source_row_count: number;
  accepted_row_count: number;
  rejected_row_count: number;
  wall_count: number;
  zone_count: number;
  warnings: string[];
  limitations: string[];
  missing_data_instructions: string[];
  walls: XauOiWall[];
  zones: XauZone[];
  artifacts: XauReportArtifact[];
}

export interface XauVolOiReportSummary {
  report_id: string;
  status: XauReportStatus;
  created_at: string;
  session_date: string | null;
  source_row_count: number;
  wall_count: number;
  zone_count: number;
  warning_count: number;
}

export interface XauVolOiReportListResponse {
  reports: XauVolOiReportSummary[];
}

export interface XauWallTableResponse {
  report_id: string;
  data: XauOiWall[];
}

export interface XauZoneTableResponse {
  report_id: string;
  data: XauZone[];
}

export interface XauDashboardData {
  report: XauVolOiReport;
  walls: XauWallTableResponse;
  zones: XauZoneTableResponse;
}

export type XauReactionLabel =
  | 'REVERSAL_CANDIDATE'
  | 'BREAKOUT_CANDIDATE'
  | 'PIN_MAGNET'
  | 'SQUEEZE_RISK'
  | 'VACUUM_TO_NEXT_WALL'
  | 'NO_TRADE';
export type XauReactionConfidenceLabel = 'high' | 'medium' | 'low' | 'blocked' | 'unknown';
export type XauReactionReportStatus = 'completed' | 'partial' | 'blocked';
export type XauReactionReportFormat = 'json' | 'markdown' | 'both';
export type XauReactionEventRiskState = 'clear' | 'elevated' | 'blocked' | 'unknown';
export type XauReactionFreshnessState = 'VALID' | 'THIN' | 'STALE' | 'PRIOR_DAY' | 'UNKNOWN';
export type XauReactionVrpRegime = 'iv_premium' | 'balanced' | 'rv_premium' | 'unknown';
export type XauReactionIvEdgeState = 'inside' | 'at_edge' | 'beyond_edge' | 'unknown';
export type XauReactionRvExtensionState =
  | 'inside'
  | 'extended'
  | 'beyond_range'
  | 'unknown';
export type XauReactionOpenSide = 'above_open' | 'below_open' | 'at_open' | 'unknown';
export type XauReactionOpenFlipState =
  | 'no_flip'
  | 'crossed_without_acceptance'
  | 'accepted_flip'
  | 'unknown';
export type XauReactionOpenSupportResistance =
  | 'support_test'
  | 'resistance_test'
  | 'boundary'
  | 'unknown';
export type XauReactionAcceptanceDirection = 'above' | 'below' | 'unknown';
export type XauRewardRiskState =
  | 'meets_minimum'
  | 'below_minimum'
  | 'unavailable'
  | 'not_applicable';

export interface XauFreshnessResult {
  state: XauReactionFreshnessState;
  age_minutes: number | null;
  confidence_label: XauReactionConfidenceLabel;
  no_trade_reason: string | null;
  notes: string[];
}

export interface XauVolRegimeResult {
  realized_volatility: number | null;
  vrp: number | null;
  vrp_regime: XauReactionVrpRegime;
  iv_edge_state: XauReactionIvEdgeState;
  rv_extension_state: XauReactionRvExtensionState;
  confidence_label: XauReactionConfidenceLabel;
  notes: string[];
}

export interface XauOpenRegimeResult {
  open_side: XauReactionOpenSide;
  open_distance_points: number | null;
  open_flip_state: XauReactionOpenFlipState;
  open_as_support_or_resistance: XauReactionOpenSupportResistance;
  confidence_label: XauReactionConfidenceLabel;
  notes: string[];
}

export interface XauAcceptanceResult {
  wall_id: string | null;
  zone_id: string | null;
  accepted_beyond_wall: boolean;
  wick_rejection: boolean;
  failed_breakout: boolean;
  confirmed_breakout: boolean;
  direction: XauReactionAcceptanceDirection;
  confidence_label: XauReactionConfidenceLabel;
  notes: string[];
}

export interface XauReactionReportRequest {
  source_report_id: string;
  current_price?: number | null;
  current_timestamp?: string | null;
  freshness_input?: Record<string, unknown> | null;
  vol_regime_input?: Record<string, unknown> | null;
  open_regime_input?: Record<string, unknown> | null;
  acceptance_inputs?: Array<Record<string, unknown>>;
  event_risk_state?: XauReactionEventRiskState;
  max_total_risk_per_idea?: number | null;
  max_recovery_legs?: number;
  minimum_rr?: number | null;
  wall_buffer_points?: number;
  report_format?: XauReactionReportFormat;
  research_only_acknowledged: boolean;
}

export interface XauReactionReportSummary {
  report_id: string;
  source_report_id: string;
  status: XauReactionReportStatus;
  created_at: string;
  session_date: string | null;
  reaction_count: number;
  no_trade_count: number;
  risk_plan_count: number;
  warning_count: number;
}

export interface XauReactionRow {
  reaction_id: string;
  source_report_id: string;
  wall_id: string | null;
  zone_id: string | null;
  reaction_label: XauReactionLabel;
  confidence_label: XauReactionConfidenceLabel;
  explanation_notes: string[];
  no_trade_reasons: string[];
  invalidation_level: number | null;
  target_level_1: number | null;
  target_level_2: number | null;
  next_wall_reference: string | null;
  freshness_state: XauFreshnessResult;
  vol_regime_state: XauVolRegimeResult;
  open_regime_state: XauOpenRegimeResult;
  acceptance_state: XauAcceptanceResult | null;
  event_risk_state: XauReactionEventRiskState;
  research_only_warning: string;
}

export interface XauRiskPlan {
  plan_id: string;
  reaction_id: string;
  reaction_label: XauReactionLabel;
  entry_condition_text: string | null;
  invalidation_level: number | null;
  stop_buffer_points: number | null;
  target_1: number | null;
  target_2: number | null;
  max_total_risk_per_idea: number | null;
  max_recovery_legs: number;
  minimum_rr: number | null;
  rr_state: XauRewardRiskState;
  cancel_conditions: string[];
  risk_notes: string[];
}

export interface XauReactionReport {
  report_id: string;
  source_report_id: string;
  status: XauReactionReportStatus;
  created_at: string;
  session_date: string | null;
  request: XauReactionReportRequest;
  source_wall_count: number;
  source_zone_count: number;
  reaction_count: number;
  no_trade_count: number;
  risk_plan_count: number;
  freshness_state: XauFreshnessResult;
  vol_regime_state: XauVolRegimeResult;
  open_regime_state: XauOpenRegimeResult;
  reactions: XauReactionRow[];
  risk_plans: XauRiskPlan[];
  warnings: string[];
  limitations: string[];
  artifacts: XauReportArtifact[];
}

export interface XauReactionReportListResponse {
  reports: XauReactionReportSummary[];
}

export interface XauReactionRowsResponse {
  report_id: string;
  data: XauReactionRow[];
}

export interface XauRiskPlanRowsResponse {
  report_id: string;
  data: XauRiskPlan[];
}

export interface XauReactionDashboardData {
  report: XauReactionReport;
  reactions: XauReactionRowsResponse;
  riskPlan: XauRiskPlanRowsResponse;
}

export type QuikStrikeViewType =
  | 'intraday_volume'
  | 'eod_volume'
  | 'open_interest'
  | 'oi_change'
  | 'churn';
export type QuikStrikeStatus = 'completed' | 'partial' | 'blocked' | 'failed';
export type QuikStrikeConversionStatus = 'completed' | 'blocked' | 'failed';
export type QuikStrikeStrikeMappingConfidence = 'high' | 'partial' | 'conflict' | 'unknown';

export interface QuikStrikeStrikeMapping {
  confidence: QuikStrikeStrikeMappingConfidence;
  method: string;
  matched_point_count: number;
  unmatched_point_count: number;
  conflict_count: number;
  evidence: string[];
  warnings: string[];
  limitations: string[];
}

export interface QuikStrikeArtifact {
  artifact_type: string;
  path: string;
  format: string;
  rows: number | null;
  created_at: string;
  limitations: string[];
}

export interface QuikStrikeExtractionSummary {
  extraction_id: string;
  status: QuikStrikeStatus;
  created_at: string;
  completed_at: string | null;
  requested_view_count: number;
  completed_view_count: number;
  missing_view_count: number;
  row_count: number;
  strike_mapping_confidence: QuikStrikeStrikeMappingConfidence;
  conversion_eligible: boolean;
  conversion_status: QuikStrikeConversionStatus | null;
  artifact_count: number;
  warning_count: number;
  limitation_count: number;
}

export interface QuikStrikeExtractionListResponse {
  extractions: QuikStrikeExtractionSummary[];
}

export interface QuikStrikeViewSummary {
  view_type: QuikStrikeViewType;
  row_count: number;
  put_row_count: number;
  call_row_count: number;
}

export interface QuikStrikeConversionResult {
  conversion_id: string;
  extraction_id: string;
  status: QuikStrikeConversionStatus;
  row_count: number;
  output_artifacts: QuikStrikeArtifact[];
  blocked_reasons: string[];
  warnings: string[];
  limitations: string[];
}

export interface QuikStrikeExtractionReport {
  extraction_id: string;
  status: QuikStrikeStatus;
  created_at: string;
  completed_at: string | null;
  request_summary: {
    requested_views?: QuikStrikeViewType[];
    completed_views?: QuikStrikeViewType[];
    partial_views?: QuikStrikeViewType[];
    missing_views?: QuikStrikeViewType[];
    conversion_eligible?: boolean;
  };
  view_summaries: QuikStrikeViewSummary[];
  row_count: number;
  strike_mapping: QuikStrikeStrikeMapping;
  conversion_result: QuikStrikeConversionResult | null;
  artifacts: QuikStrikeArtifact[];
  warnings: string[];
  limitations: string[];
  research_only_warnings: string[];
}

export interface QuikStrikeNormalizedRow {
  row_id: string;
  extraction_id: string;
  capture_timestamp: string;
  product: string;
  option_product_code: string;
  futures_symbol: string | null;
  expiration: string | null;
  dte: number | null;
  future_reference_price: number | null;
  view_type: QuikStrikeViewType;
  strike: number;
  strike_id: string | null;
  option_type: 'put' | 'call';
  value: number;
  value_type: string;
  vol_settle: number | null;
  range_label: string | null;
  sigma_label: string | null;
  source_view: string;
  strike_mapping_confidence: QuikStrikeStrikeMappingConfidence;
  extraction_warnings: string[];
  extraction_limitations: string[];
}

export interface QuikStrikeRowsResponse {
  extraction_id: string;
  rows: QuikStrikeNormalizedRow[];
}

export interface QuikStrikeXauVolOiRow {
  timestamp: string;
  expiry: string;
  strike: number;
  option_type: 'put' | 'call';
  open_interest: number | null;
  oi_change: number | null;
  volume: number | null;
  intraday_volume: number | null;
  eod_volume: number | null;
  churn: number | null;
  implied_volatility: number | null;
  underlying_futures_price: number | null;
  dte: number | null;
  source: string;
  source_view: string;
  source_extraction_id: string;
  limitations: string[];
}

export interface QuikStrikeConversionRowsResponse {
  extraction_id: string;
  conversion_result: QuikStrikeConversionResult | null;
  rows: QuikStrikeXauVolOiRow[];
}

export interface QuikStrikeDashboardData {
  report: QuikStrikeExtractionReport;
  rows: QuikStrikeRowsResponse;
  conversion: QuikStrikeConversionRowsResponse;
}

export type QuikStrikeMatrixViewType =
  | 'open_interest_matrix'
  | 'oi_change_matrix'
  | 'volume_matrix';
export type QuikStrikeMatrixStatus = 'completed' | 'partial' | 'blocked' | 'failed';
export type QuikStrikeMatrixConversionStatus = 'completed' | 'blocked' | 'failed';
export type QuikStrikeMatrixMappingStatus = 'valid' | 'partial' | 'blocked';
export type QuikStrikeMatrixCellState = 'available' | 'unavailable' | 'blank' | 'invalid';
export type QuikStrikeMatrixOptionType = 'call' | 'put' | 'combined';

export interface QuikStrikeMatrixArtifact {
  artifact_type: string;
  path: string;
  format: string;
  rows: number | null;
  created_at: string;
  limitations: string[];
}

export interface QuikStrikeMatrixMapping {
  status: QuikStrikeMatrixMappingStatus;
  table_present: boolean;
  strike_rows_found: number;
  expiration_columns_found: number;
  option_side_mapping: string;
  numeric_cell_count: number;
  unavailable_cell_count: number;
  duplicate_row_count: number;
  blocked_reasons: string[];
  warnings: string[];
  limitations: string[];
}

export interface QuikStrikeMatrixExtractionSummary {
  extraction_id: string;
  status: QuikStrikeMatrixStatus;
  created_at: string;
  completed_at: string | null;
  requested_view_count: number;
  completed_view_count: number;
  missing_view_count: number;
  row_count: number;
  strike_count: number;
  expiration_count: number;
  unavailable_cell_count: number;
  conversion_eligible: boolean;
  conversion_status: QuikStrikeMatrixConversionStatus | null;
  artifact_count: number;
  warning_count: number;
  limitation_count: number;
}

export interface QuikStrikeMatrixExtractionListResponse {
  extractions: QuikStrikeMatrixExtractionSummary[];
}

export interface QuikStrikeMatrixViewSummary {
  view_type: QuikStrikeMatrixViewType;
  row_count: number;
  strike_count: number;
  expiration_count: number;
  unavailable_cell_count: number;
}

export interface QuikStrikeMatrixConversionResult {
  conversion_id: string;
  extraction_id: string;
  status: QuikStrikeMatrixConversionStatus;
  row_count: number;
  output_artifacts: QuikStrikeMatrixArtifact[];
  blocked_reasons: string[];
  warnings: string[];
  limitations: string[];
}

export interface QuikStrikeMatrixExtractionReport {
  extraction_id: string;
  status: QuikStrikeMatrixStatus;
  created_at: string;
  completed_at: string | null;
  request_summary: {
    requested_views?: QuikStrikeMatrixViewType[];
    completed_views?: QuikStrikeMatrixViewType[];
    partial_views?: QuikStrikeMatrixViewType[];
    missing_views?: QuikStrikeMatrixViewType[];
    conversion_eligible?: boolean;
  };
  view_summaries: QuikStrikeMatrixViewSummary[];
  row_count: number;
  strike_count: number;
  expiration_count: number;
  unavailable_cell_count: number;
  mapping: QuikStrikeMatrixMapping;
  conversion_result: QuikStrikeMatrixConversionResult | null;
  artifacts: QuikStrikeMatrixArtifact[];
  warnings: string[];
  limitations: string[];
  research_only_warnings: string[];
}

export interface QuikStrikeMatrixNormalizedRow {
  row_id: string;
  extraction_id: string;
  capture_timestamp: string;
  product: string;
  option_product_code: string;
  futures_symbol: string | null;
  source_menu: string;
  view_type: QuikStrikeMatrixViewType;
  strike: number | null;
  expiration: string | null;
  dte: number | null;
  future_reference_price: number | null;
  option_type: QuikStrikeMatrixOptionType | null;
  value: number | null;
  value_type: string;
  cell_state: QuikStrikeMatrixCellState;
  table_row_label: string;
  table_column_label: string;
  extraction_warnings: string[];
  extraction_limitations: string[];
}

export interface QuikStrikeMatrixRowsResponse {
  extraction_id: string;
  rows: QuikStrikeMatrixNormalizedRow[];
}

export interface QuikStrikeMatrixXauVolOiRow {
  timestamp: string;
  expiry: string;
  strike: number;
  option_type: QuikStrikeMatrixOptionType;
  open_interest: number | null;
  oi_change: number | null;
  volume: number | null;
  source: string;
  source_menu: string;
  source_view: string;
  source_extraction_id: string;
  table_row_label: string;
  table_column_label: string;
  futures_symbol: string | null;
  dte: number | null;
  underlying_futures_price: number | null;
  limitations: string[];
}

export interface QuikStrikeMatrixConversionRowsResponse {
  extraction_id: string;
  conversion_result: QuikStrikeMatrixConversionResult | null;
  rows: QuikStrikeMatrixXauVolOiRow[];
}

export interface QuikStrikeMatrixDashboardData {
  report: QuikStrikeMatrixExtractionReport;
  rows: QuikStrikeMatrixRowsResponse;
  conversion: QuikStrikeMatrixConversionRowsResponse;
}

export type XauFusionSourceType = 'vol2vol' | 'matrix' | 'fused';
export type XauFusionMatchStatus =
  | 'matched'
  | 'vol2vol_only'
  | 'matrix_only'
  | 'conflict'
  | 'blocked';
export type XauFusionAgreementStatus =
  | 'agreement'
  | 'disagreement'
  | 'unavailable'
  | 'not_comparable';
export type XauFusionContextStatus =
  | 'available'
  | 'partial'
  | 'unavailable'
  | 'conflict'
  | 'blocked';
export type XauFusionReportStatus = 'completed' | 'partial' | 'blocked' | 'failed';
export type XauFusionArtifactType =
  | 'metadata'
  | 'fused_rows_json'
  | 'fused_rows_parquet'
  | 'xau_vol_oi_input_csv'
  | 'xau_vol_oi_input_parquet'
  | 'report_json'
  | 'report_markdown';
export type XauFusionArtifactFormat = 'json' | 'csv' | 'parquet' | 'markdown';

export interface XauQuikStrikeFusionRequest {
  vol2vol_report_id: string;
  matrix_report_id: string;
  xauusd_spot_reference?: number | null;
  gc_futures_reference?: number | null;
  session_open_price?: number | null;
  realized_volatility?: number | null;
  candle_context?: Array<Record<string, unknown>> | Record<string, unknown>;
  create_xau_vol_oi_report?: boolean;
  create_xau_reaction_report?: boolean;
  run_label?: string | null;
  persist_report?: boolean;
  research_only_acknowledged: boolean;
}

export interface XauQuikStrikeSourceRef {
  source_type: Exclude<XauFusionSourceType, 'fused'>;
  report_id: string;
  status: string;
  product: string | null;
  option_product_code: string | null;
  row_count: number;
  conversion_status: string | null;
  warnings: string[];
  limitations: string[];
  artifact_paths: string[];
}

export interface XauFusionMatchKey {
  strike: number;
  expiration: string | null;
  expiration_code: string | null;
  expiration_key: string | null;
  option_type: string;
  value_type: string;
}

export interface XauFusionSourceValue {
  source_type: Exclude<XauFusionSourceType, 'fused'>;
  source_report_id: string;
  source_row_id: string | null;
  value: number | null;
  value_type: string;
  source_view: string | null;
  strike: number | null;
  expiration: string | null;
  expiration_code: string | null;
  option_type: string | null;
  future_reference_price: number | null;
  dte: number | null;
  vol_settle: number | null;
  range_label: string | null;
  sigma_label: string | null;
  warnings: string[];
  limitations: string[];
}

export interface XauFusionCoverageSummary {
  matched_key_count: number;
  vol2vol_only_key_count: number;
  matrix_only_key_count: number;
  conflict_key_count: number;
  blocked_key_count: number;
  strike_count: number;
  expiration_count: number;
  option_type_count: number;
  value_type_count: number;
}

export interface XauFusionRow {
  fusion_row_id: string;
  fusion_report_id: string;
  match_key: XauFusionMatchKey;
  source_type: XauFusionSourceType;
  match_status: XauFusionMatchStatus;
  agreement_status: XauFusionAgreementStatus;
  vol2vol_value: XauFusionSourceValue | null;
  matrix_value: XauFusionSourceValue | null;
  basis_points: number | null;
  spot_equivalent_level: number | null;
  source_agreement_notes: string[];
  missing_context_notes: string[];
  warnings: string[];
  limitations: string[];
}

export interface XauFusionMissingContextItem {
  context_key: string;
  status: XauFusionContextStatus;
  severity: string;
  blocks_fusion: boolean;
  blocks_reaction_confidence: boolean;
  message: string;
  source_refs: string[];
}

export interface XauFusionBasisState {
  status: XauFusionContextStatus;
  xauusd_spot_reference: number | null;
  gc_futures_reference: number | null;
  basis_points: number | null;
  calculation_note: string | null;
  warnings: string[];
}

export interface XauFusionContextSummary {
  basis_status: XauFusionContextStatus;
  iv_range_status: XauFusionContextStatus;
  open_regime_status: XauFusionContextStatus;
  candle_acceptance_status: XauFusionContextStatus;
  realized_volatility_status: XauFusionContextStatus;
  source_agreement_status: XauFusionContextStatus;
  missing_context: XauFusionMissingContextItem[];
}

export interface XauFusionDownstreamResult {
  xau_vol_oi_report_id: string | null;
  xau_reaction_report_id: string | null;
  xau_report_status: string | null;
  reaction_report_status: string | null;
  reaction_row_count: number | null;
  no_trade_count: number | null;
  all_reactions_no_trade: boolean | null;
  notes: string[];
}

export interface XauFusionArtifact {
  artifact_type: XauFusionArtifactType;
  path: string;
  format: XauFusionArtifactFormat;
  rows: number | null;
  created_at: string;
  limitations: string[];
}

export interface XauQuikStrikeFusionSummary {
  report_id: string;
  status: XauFusionReportStatus;
  created_at: string;
  vol2vol_report_id: string;
  matrix_report_id: string;
  fused_row_count: number;
  strike_count: number;
  expiration_count: number;
  basis_status: XauFusionContextStatus;
  iv_range_status: XauFusionContextStatus;
  open_regime_status: XauFusionContextStatus;
  candle_acceptance_status: XauFusionContextStatus;
  xau_vol_oi_report_id: string | null;
  xau_reaction_report_id: string | null;
  all_reactions_no_trade: boolean | null;
  warning_count: number;
}

export interface XauQuikStrikeFusionReport {
  report_id: string;
  status: XauFusionReportStatus;
  created_at: string;
  completed_at: string | null;
  request: XauQuikStrikeFusionRequest | null;
  vol2vol_source: XauQuikStrikeSourceRef;
  matrix_source: XauQuikStrikeSourceRef;
  coverage: XauFusionCoverageSummary | null;
  context_summary: XauFusionContextSummary | null;
  basis_state: XauFusionBasisState | null;
  fused_row_count: number;
  xau_vol_oi_input_row_count: number;
  fused_rows: XauFusionRow[];
  downstream_result: XauFusionDownstreamResult | null;
  artifacts: XauFusionArtifact[];
  warnings: string[];
  limitations: string[];
  research_only_warnings: string[];
}

export interface XauQuikStrikeFusionListResponse {
  reports: XauQuikStrikeFusionSummary[];
}

export interface XauFusionRowsResponse {
  report_id: string;
  rows: XauFusionRow[];
}

export interface XauFusionMissingContextResponse {
  report_id: string;
  missing_context: XauFusionMissingContextItem[];
}

export interface XauQuikStrikeFusionDashboardData {
  report: XauQuikStrikeFusionReport;
  rows: XauFusionRowsResponse;
  missingContext: XauFusionMissingContextResponse;
}

export type XauForwardJournalSourceType =
  | 'quikstrike_vol2vol'
  | 'quikstrike_matrix'
  | 'xau_quikstrike_fusion'
  | 'xau_vol_oi'
  | 'xau_reaction';
export type XauForwardJournalEntryStatus = 'completed' | 'partial' | 'blocked' | 'failed';
export type XauForwardOutcomeWindow = '30m' | '1h' | '4h' | 'session_close' | 'next_day';
export type XauForwardOutcomeLabel =
  | 'wall_held'
  | 'wall_rejected'
  | 'wall_accepted_break'
  | 'moved_to_next_wall'
  | 'reversed_before_target'
  | 'stayed_inside_range'
  | 'no_trade_was_correct'
  | 'inconclusive'
  | 'pending';
export type XauForwardOutcomeStatus =
  | 'pending'
  | 'completed'
  | 'partial'
  | 'inconclusive'
  | 'conflict'
  | 'blocked';
export type XauForwardArtifactType =
  | 'metadata'
  | 'entry_json'
  | 'outcomes_json'
  | 'report_json'
  | 'report_markdown';
export type XauForwardArtifactFormat = 'json' | 'markdown';

export interface XauForwardJournalNote {
  note_id: string | null;
  text: string;
  created_at: string;
  source: string;
}

export type XauForwardJournalNoteInput = string | Partial<XauForwardJournalNote>;

export interface XauForwardSourceReportRef {
  source_type: XauForwardJournalSourceType;
  report_id: string;
  status: string;
  created_at: string | null;
  product: string | null;
  expiration: string | null;
  expiration_code: string | null;
  row_count: number;
  warnings: string[];
  limitations: string[];
  artifact_paths: string[];
}

export interface XauForwardJournalCreateRequest {
  snapshot_time: string;
  capture_window?: string;
  capture_session?: string | null;
  vol2vol_report_id: string;
  matrix_report_id: string;
  fusion_report_id: string;
  xau_vol_oi_report_id: string;
  xau_reaction_report_id: string;
  spot_price_at_snapshot?: number | null;
  futures_price_at_snapshot?: number | null;
  basis?: number | null;
  session_open_price?: number | null;
  event_news_flag?: string | boolean | null;
  notes?: XauForwardJournalNoteInput[];
  persist_report?: boolean;
  research_only_acknowledged: boolean;
}

export interface XauForwardSnapshotContext {
  snapshot_time: string;
  capture_window: string;
  capture_session: string | null;
  product: string | null;
  expiration: string | null;
  expiration_code: string | null;
  spot_price_at_snapshot: number | null;
  futures_price_at_snapshot: number | null;
  basis: number | null;
  session_open_price: number | null;
  event_news_flag: string | boolean | null;
  missing_context: string[];
  notes: XauForwardJournalNote[];
}

export interface XauForwardWallSummary {
  summary_id: string;
  wall_type: string;
  source_report_id: string;
  strike: number;
  expiration: string | null;
  expiration_code: string | null;
  option_type: string | null;
  open_interest: number | null;
  oi_change: number | null;
  volume: number | null;
  wall_score: number | null;
  rank: number;
  notes: XauForwardJournalNote[];
  limitations: string[];
}

export interface XauForwardReactionSummary {
  reaction_id: string;
  source_report_id: string;
  wall_id: string | null;
  zone_id: string | null;
  reaction_label: string;
  confidence_label: string | null;
  no_trade_reasons: string[];
  bounded_risk_annotation_count: number;
  notes: XauForwardJournalNote[];
  limitations: string[];
}

export interface XauForwardMissingContextItem {
  context_key: string;
  status: string;
  severity: string;
  message: string;
  source_report_ids: string[];
  blocks_outcome_label: boolean;
  blocks_reaction_review: boolean;
}

export interface XauForwardOutcomeObservation {
  window: XauForwardOutcomeWindow;
  status: XauForwardOutcomeStatus;
  label: XauForwardOutcomeLabel;
  observation_start: string | null;
  observation_end: string | null;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  reference_wall_id: string | null;
  reference_wall_level: number | null;
  next_wall_reference: string | null;
  notes: XauForwardJournalNote[];
  limitations: string[];
  updated_at: string;
}

export interface XauForwardOutcomeUpdateRequest {
  outcomes: Array<
    Partial<XauForwardOutcomeObservation> & {
      window: XauForwardOutcomeWindow;
    }
  >;
  update_note?: string | null;
  research_only_acknowledged: boolean;
}

export interface XauForwardJournalArtifact {
  artifact_type: XauForwardArtifactType;
  path: string;
  format: XauForwardArtifactFormat;
  rows: number | null;
  created_at: string;
  limitations: string[];
}

export interface XauForwardJournalEntry {
  journal_id: string;
  snapshot_key: string;
  status: XauForwardJournalEntryStatus;
  created_at: string;
  updated_at: string;
  snapshot: XauForwardSnapshotContext;
  source_reports: XauForwardSourceReportRef[];
  top_oi_walls: XauForwardWallSummary[];
  top_oi_change_walls: XauForwardWallSummary[];
  top_volume_walls: XauForwardWallSummary[];
  reaction_summaries: XauForwardReactionSummary[];
  missing_context: XauForwardMissingContextItem[];
  outcomes: XauForwardOutcomeObservation[];
  notes: XauForwardJournalNote[];
  warnings: string[];
  limitations: string[];
  research_only_warnings: string[];
  artifacts: XauForwardJournalArtifact[];
}

export interface XauForwardJournalSummary {
  journal_id: string;
  snapshot_key: string;
  status: XauForwardJournalEntryStatus;
  snapshot_time: string;
  capture_window: string;
  capture_session: string | null;
  product: string | null;
  expiration: string | null;
  expiration_code: string | null;
  fusion_report_id: string | null;
  xau_vol_oi_report_id: string | null;
  xau_reaction_report_id: string | null;
  outcome_status: XauForwardOutcomeStatus;
  completed_outcome_count: number;
  pending_outcome_count: number;
  no_trade_count: number;
  warning_count: number;
}

export interface XauForwardJournalListResponse {
  entries: XauForwardJournalSummary[];
}

export interface XauForwardOutcomeResponse {
  journal_id: string;
  outcomes: XauForwardOutcomeObservation[];
  updated_at: string;
  warnings: string[];
  limitations: string[];
}

export interface XauForwardJournalDashboardData {
  entries: XauForwardJournalSummary[];
  selected_entry: XauForwardJournalEntry | null;
  outcomes: XauForwardOutcomeResponse | null;
}

export type FreeDerivativesSource =
  | 'cftc_cot'
  | 'gvz'
  | 'deribit_public_options';
export type FreeDerivativesRunStatus = 'completed' | 'partial' | 'blocked' | 'failed';
export type FreeDerivativesSourceStatus = 'completed' | 'partial' | 'skipped' | 'failed';
export type FreeDerivativesReportFormat = 'json' | 'markdown' | 'both';
export type FreeDerivativesArtifactFormat = 'json' | 'csv' | 'parquet' | 'markdown' | 'zip';
export type FreeDerivativesArtifactType =
  | 'raw_cftc'
  | 'processed_cftc'
  | 'raw_gvz'
  | 'processed_gvz'
  | 'raw_deribit_instruments'
  | 'raw_deribit_summary'
  | 'processed_deribit_options'
  | 'processed_deribit_walls'
  | 'run_metadata'
  | 'run_json'
  | 'run_markdown';
export type CftcCotReportCategory = 'futures_only' | 'futures_and_options_combined';

export interface CftcCotRequest {
  years?: number[];
  categories?: CftcCotReportCategory[];
  source_urls?: string[];
  local_fixture_paths?: string[];
  market_filters?: string[];
}

export interface GvzRequest {
  series_id?: string;
  start_date?: string | null;
  end_date?: string | null;
  source_url?: string | null;
  local_fixture_path?: string | null;
}

export interface DeribitOptionsRequest {
  underlyings?: string[];
  include_expired?: boolean;
  snapshot_timestamp?: string | null;
  fixture_instruments_path?: string | null;
  fixture_summary_path?: string | null;
}

export interface FreeDerivativesBootstrapRequest {
  include_cftc?: boolean;
  include_gvz?: boolean;
  include_deribit?: boolean;
  cftc?: CftcCotRequest;
  gvz?: GvzRequest;
  deribit?: DeribitOptionsRequest;
  run_label?: string | null;
  report_format?: FreeDerivativesReportFormat;
  research_only_acknowledged: boolean;
}

export interface FreeDerivativesArtifact {
  artifact_type: FreeDerivativesArtifactType;
  source: FreeDerivativesSource;
  path: string;
  format: FreeDerivativesArtifactFormat;
  rows: number | null;
  created_at: string;
  limitations: string[];
}

export interface FreeDerivativesSourceResult {
  source: FreeDerivativesSource;
  status: FreeDerivativesSourceStatus;
  requested_items: string[];
  completed_items: string[];
  skipped_items: string[];
  failed_items: string[];
  row_count: number;
  instrument_count: number;
  coverage_start: string | null;
  coverage_end: string | null;
  snapshot_timestamp: string | null;
  artifacts: FreeDerivativesArtifact[];
  warnings: string[];
  limitations: string[];
  missing_data_actions: string[];
}

export interface FreeDerivativesBootstrapRun {
  run_id: string;
  status: FreeDerivativesRunStatus;
  created_at: string;
  completed_at: string | null;
  request: FreeDerivativesBootstrapRequest;
  source_results: FreeDerivativesSourceResult[];
  artifacts: FreeDerivativesArtifact[];
  warnings: string[];
  limitations: string[];
  missing_data_actions: string[];
  research_only_warnings: string[];
}

export interface FreeDerivativesBootstrapRunSummary {
  run_id: string;
  status: FreeDerivativesRunStatus;
  created_at: string;
  completed_at: string | null;
  completed_source_count: number;
  partial_source_count: number;
  failed_source_count: number;
  artifact_count: number;
  warning_count: number;
  limitation_count: number;
}

export interface FreeDerivativesBootstrapRunListResponse {
  runs: FreeDerivativesBootstrapRunSummary[];
}

export type DataSourceProviderType =
  | 'binance_public'
  | 'yahoo_finance'
  | 'local_file'
  | 'cftc_cot'
  | 'gvz'
  | 'deribit_public_options'
  | 'kaiko_optional'
  | 'tardis_optional'
  | 'coinglass_optional'
  | 'cryptoquant_optional'
  | 'cme_quikstrike_local_or_optional'
  | 'forbidden_private_trading';

export type DataSourceReadinessStatus =
  | 'ready'
  | 'configured'
  | 'missing'
  | 'unavailable_optional'
  | 'unsupported'
  | 'blocked'
  | 'forbidden';

export type DataSourceTier =
  | 'tier_0_public_local'
  | 'tier_1_optional_paid_research'
  | 'tier_2_forbidden_v0';

export type DataSourceWorkflowType =
  | 'crypto_multi_asset'
  | 'proxy_ohlcv'
  | 'xau_vol_oi'
  | 'free_derivatives'
  | 'optional_vendor'
  | 'first_evidence_run';

export type FirstEvidenceRunStatus = 'completed' | 'partial' | 'blocked' | 'failed';
export type MissingDataSeverity = 'blocking' | 'optional' | 'informational';

export interface DataSourceCapability {
  provider_type: DataSourceProviderType;
  display_name: string;
  tier: DataSourceTier;
  supports: string[];
  unsupported: string[];
  requires_key: boolean;
  requires_local_file: boolean;
  is_optional: boolean;
  limitations: string[];
  forbidden_reason: string | null;
}

export interface DataSourceMissingDataAction {
  action_id: string;
  workflow_type: DataSourceWorkflowType;
  provider_type: DataSourceProviderType;
  asset: string | null;
  severity: MissingDataSeverity;
  title: string;
  instructions: string[];
  required_columns: string[];
  optional_columns: string[];
  blocking: boolean;
}

export interface DataSourceProviderStatus {
  provider_type: DataSourceProviderType;
  status: DataSourceReadinessStatus;
  configured: boolean;
  env_var_name: string | null;
  secret_value_returned: boolean;
  capabilities: DataSourceCapability;
  warnings: string[];
  limitations: string[];
  missing_actions: DataSourceMissingDataAction[];
}

export interface DataSourceReadiness {
  generated_at: string;
  provider_statuses: DataSourceProviderStatus[];
  capability_matrix: DataSourceCapability[];
  public_sources_available: boolean;
  optional_sources_missing: DataSourceProviderType[];
  forbidden_sources_detected: DataSourceProviderType[];
  missing_data_actions: DataSourceMissingDataAction[];
  research_only_warnings: string[];
}

export interface DataSourceCapabilityListResponse {
  capabilities: DataSourceCapability[];
}

export interface DataSourceMissingDataResponse {
  actions: DataSourceMissingDataAction[];
}

export interface DataSourcePreflightRequest {
  crypto_assets?: string[];
  optional_crypto_assets?: string[];
  crypto_timeframe?: string;
  proxy_assets?: string[];
  proxy_timeframe?: string;
  processed_feature_root?: string | null;
  xau_options_oi_file_path?: string | null;
  require_optional_vendors?: DataSourceProviderType[];
  requested_capabilities?: string[];
  research_only_acknowledged: boolean;
}

export interface DataSourcePreflightAssetResult {
  asset: string | null;
  provider_type: DataSourceProviderType;
  status: DataSourceReadinessStatus;
  feature_path: string | null;
  row_count: number | null;
  missing_data_actions: DataSourceMissingDataAction[];
  unsupported_capabilities: string[];
  warnings: string[];
  limitations: string[];
}

export interface DataSourcePreflightResult {
  status: FirstEvidenceRunStatus;
  readiness: DataSourceReadiness;
  crypto_results: DataSourcePreflightAssetResult[];
  proxy_results: DataSourcePreflightAssetResult[];
  xau_result: DataSourcePreflightAssetResult | null;
  optional_vendor_results: DataSourceProviderStatus[];
  unsupported_capabilities: string[];
  missing_data_actions: DataSourceMissingDataAction[];
  warnings: string[];
  limitations: string[];
}

export interface FirstEvidenceRunRequest {
  name?: string | null;
  preflight: DataSourcePreflightRequest;
  use_existing_research_report_ids?: string[];
  use_existing_xau_report_id?: string | null;
  run_when_partial?: boolean;
  research_only_acknowledged: boolean;
}

export interface FirstEvidenceRunResult {
  first_run_id: string;
  status: FirstEvidenceRunStatus;
  execution_run_id: string | null;
  evidence_report_path: string | null;
  decision: ResearchEvidenceDecision | null;
  linked_research_report_ids: string[];
  linked_xau_report_ids: string[];
  preflight_result: DataSourcePreflightResult;
  evidence_summary: ResearchEvidenceSummary | null;
  missing_data_actions: DataSourceMissingDataAction[];
  research_only_warnings: string[];
  limitations: string[];
  created_at: string;
}

export interface DataSourceBootstrapRequest {
  include_binance?: boolean;
  binance_symbols?: string[];
  optional_binance_symbols?: string[];
  binance_timeframes?: string[];
  include_binance_open_interest?: boolean;
  include_binance_funding?: boolean;
  include_yahoo?: boolean;
  yahoo_symbols?: string[];
  yahoo_timeframes?: string[];
  days?: number;
  start_time?: string | null;
  end_time?: string | null;
  run_preflight_after?: boolean;
  include_xau_local_instructions?: boolean;
  research_only_acknowledged: boolean;
}

export type DataSourceBootstrapProvider = 'binance_public' | 'yahoo_finance';

export interface DataSourceBootstrapArtifact {
  provider_type: DataSourceProviderType;
  data_type: string;
  path: string;
  row_count: number;
  start_timestamp: string | null;
  end_timestamp: string | null;
  limitations: string[];
}

export interface DataSourceBootstrapAssetSummary {
  provider_type: DataSourceProviderType;
  symbol: string;
  timeframe: string;
  status: FirstEvidenceRunStatus;
  raw_artifacts: DataSourceBootstrapArtifact[];
  processed_feature_path: string | null;
  row_count: number;
  start_timestamp: string | null;
  end_timestamp: string | null;
  unsupported_capabilities: string[];
  warnings: string[];
  limitations: string[];
}

export interface DataSourceBootstrapRunResult {
  bootstrap_run_id: string;
  status: FirstEvidenceRunStatus;
  created_at: string;
  raw_root: string;
  processed_root: string;
  asset_summaries: DataSourceBootstrapAssetSummary[];
  preflight_result: DataSourcePreflightResult | null;
  missing_data_actions: DataSourceMissingDataAction[];
  research_only_warnings: string[];
  limitations: string[];
}

export interface DataSourceBootstrapRunListResponse {
  runs: DataSourceBootstrapRunResult[];
}

export interface DataSourceDashboardData {
  readiness: DataSourceReadiness;
  capabilities: DataSourceCapabilityListResponse;
  missingData: DataSourceMissingDataResponse;
  bootstrapRuns: DataSourceBootstrapRunListResponse;
  freeDerivativesRuns: FreeDerivativesBootstrapRunListResponse;
  latestFreeDerivativesRun: FreeDerivativesBootstrapRun | null;
}
