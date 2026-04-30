from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FORBIDDEN_LIVE_TRADING_FIELDS = {
    "account",
    "accountid",
    "apikey",
    "apisecret",
    "broker",
    "brokerid",
    "exchangecredential",
    "exchangecredentials",
    "exchangesecret",
    "executeorder",
    "execution",
    "live",
    "livetrading",
    "margin",
    "order",
    "ordertype",
    "positionmanager",
    "privatekey",
    "secretkey",
    "wallet",
    "walletaddress",
}


def _normalize_guardrail_key(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _forbidden_live_trading_paths(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        matches: list[str] = []
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if _normalize_guardrail_key(str(key)) in FORBIDDEN_LIVE_TRADING_FIELDS:
                matches.append(path)
            matches.extend(_forbidden_live_trading_paths(item, path))
        return matches
    if isinstance(value, list):
        matches = []
        for index, item in enumerate(value):
            path = f"{prefix}.{index}" if prefix else str(index)
            matches.extend(_forbidden_live_trading_paths(item, path))
        return matches
    return []


class StrictModel(BaseModel):
    """Base model for persisted research configurations."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def reject_live_trading_fields(cls, value: Any) -> Any:
        matches = _forbidden_live_trading_paths(value)
        if matches:
            fields = ", ".join(sorted(set(matches)))
            raise ValueError(
                f"live-trading fields are not allowed in v0 research backtests: {fields}"
            )
        return value


class BacktestStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class StrategyMode(StrEnum):
    GRID_RANGE = "grid_range"
    BREAKOUT = "breakout"
    BUY_HOLD = "buy_hold"
    PRICE_BREAKOUT = "price_breakout"
    NO_TRADE = "no_trade"


class BaselineMode(StrEnum):
    BUY_HOLD = "buy_hold"
    PRICE_BREAKOUT = "price_breakout"
    NO_TRADE = "no_trade"


class TradeSide(StrEnum):
    LONG = "long"
    SHORT = "short"


class ExitReason(StrEnum):
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    END_OF_DATA = "end_of_data"
    INVALIDATED = "invalidated"


class ReportFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    BOTH = "both"


class CapitalSizingMode(StrEnum):
    CAPITAL_FRACTION = "capital_fraction"
    RISK_FRACTIONAL = "risk_fractional"


class CostStressProfileName(StrEnum):
    NORMAL = "normal"
    HIGH_FEE = "high_fee"
    HIGH_SLIPPAGE = "high_slippage"
    WORST_REASONABLE_COST = "worst_reasonable_cost"


class ValidationSplitStatus(StrEnum):
    EVALUATED = "evaluated"
    INSUFFICIENT_DATA = "insufficient_data"


class StressOutcome(StrEnum):
    REMAINED_POSITIVE = "remained_positive"
    TURNED_NEGATIVE = "turned_negative"
    NO_TRADES = "no_trades"
    NOT_EVALUABLE = "not_evaluable"


class DrawdownRecoveryStatus(StrEnum):
    RECOVERED = "recovered"
    NOT_RECOVERED = "not_recovered"
    NOT_APPLICABLE = "not_applicable"


class AmbiguousIntrabarPolicy(StrEnum):
    STOP_FIRST = "stop_first"


class ReportArtifactType(StrEnum):
    METADATA = "metadata"
    CONFIG = "config"
    TRADES = "trades"
    EQUITY = "equity"
    METRICS = "metrics"
    REPORT_JSON = "report_json"
    REPORT_MARKDOWN = "report_markdown"
    VALIDATION_METADATA = "validation_metadata"
    VALIDATION_CONFIG = "validation_config"
    VALIDATION_STRESS = "validation_stress"
    VALIDATION_SENSITIVITY = "validation_sensitivity"
    VALIDATION_WALK_FORWARD = "validation_walk_forward"
    VALIDATION_CONCENTRATION = "validation_concentration"
    VALIDATION_REPORT_JSON = "validation_report_json"
    VALIDATION_REPORT_MARKDOWN = "validation_report_markdown"


class ArtifactFormat(StrEnum):
    JSON = "json"
    PARQUET = "parquet"
    MARKDOWN = "markdown"


class TakeProfitConfig(StrictModel):
    mode: str = Field(default="range_mid", description="Take-profit mode")
    value: float | None = Field(default=None, gt=0, description="Optional take-profit value")


class BacktestAssumptions(StrictModel):
    fee_rate: float = Field(default=0.0004, ge=0, le=0.1)
    slippage_rate: float = Field(default=0.0002, ge=0, le=0.1)
    risk_per_trade: float = Field(default=0.01, gt=0, le=1)
    buy_hold_capital_fraction: float = Field(default=1.0, gt=0, le=1)
    max_positions: int = Field(default=1, ge=1, le=1)
    allow_short: bool = Field(default=True)
    allow_compounding: bool = Field(default=False)
    leverage: float = Field(default=1, ge=1, le=1)
    ambiguous_intrabar_policy: AmbiguousIntrabarPolicy = Field(
        default=AmbiguousIntrabarPolicy.STOP_FIRST
    )


class StrategyConfig(StrictModel):
    mode: StrategyMode = Field(..., description="Strategy or baseline mode")
    enabled: bool = Field(default=True)
    allow_short: bool | None = Field(default=None)
    entry_threshold: float | None = Field(default=None, ge=0)
    atr_buffer: float | None = Field(default=None, ge=0)
    take_profit: TakeProfitConfig | None = Field(default=None)
    risk_reward_multiple: float | None = Field(default=None, gt=0)


class BacktestRunRequest(StrictModel):
    symbol: str = Field(default="BTCUSDT")
    provider: str | None = Field(default="binance")
    timeframe: str = Field(default="15m")
    feature_path: Path | None = Field(default=None)
    initial_equity: float = Field(default=10000.0, gt=0)
    assumptions: BacktestAssumptions = Field(default_factory=BacktestAssumptions)
    strategies: list[StrategyConfig] = Field(default_factory=list)
    baselines: list[BaselineMode] = Field(default_factory=lambda: [BaselineMode.BUY_HOLD])
    report_format: ReportFormat = Field(default=ReportFormat.BOTH)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.upper().strip()
        if not normalized:
            raise ValueError("symbol is required")
        return normalized

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else value

    @field_validator("timeframe")
    @classmethod
    def normalize_timeframe(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("timeframe is required")
        return normalized

    @model_validator(mode="after")
    def validate_modes(self) -> "BacktestRunRequest":
        enabled_strategies = [strategy for strategy in self.strategies if strategy.enabled]
        if not enabled_strategies and not self.baselines:
            raise ValueError("at least one enabled strategy or baseline is required")
        return self


class StrategySignal(BaseModel):
    signal_id: str
    strategy_mode: StrategyMode
    signal_timestamp: datetime
    side: TradeSide
    entry_bar_index: int = Field(..., ge=0)
    stop_loss: float = Field(..., gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    regime: str | None = None
    reason: str


class Position(BaseModel):
    position_id: str
    strategy_mode: StrategyMode
    side: TradeSide
    entry_timestamp: datetime
    entry_price: float = Field(..., gt=0)
    quantity: float = Field(..., gt=0)
    notional: float = Field(..., gt=0)
    stop_loss: float = Field(..., gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    entry_fee: float = Field(default=0, ge=0)
    sizing_method: str = Field(default="risk_fractional")
    requested_notional: float | None = Field(default=None, gt=0)
    notional_cap: float | None = Field(default=None, gt=0)
    sizing_notes: list[str] = Field(default_factory=list)


class TradeRecord(BaseModel):
    trade_id: str
    run_id: str
    strategy_mode: StrategyMode
    provider: str | None = None
    symbol: str
    timeframe: str
    side: TradeSide
    regime_at_signal: str | None = None
    signal_timestamp: datetime
    entry_timestamp: datetime
    entry_price: float = Field(..., gt=0)
    exit_timestamp: datetime
    exit_price: float = Field(..., gt=0)
    exit_reason: ExitReason
    quantity: float = Field(..., gt=0)
    notional: float = Field(..., gt=0)
    gross_pnl: float
    fees: float = Field(..., ge=0)
    slippage: float = Field(..., ge=0)
    net_pnl: float
    return_pct: float
    holding_bars: int = Field(..., ge=0)
    assumptions_snapshot: dict[str, Any] = Field(default_factory=dict)


class EquityPoint(BaseModel):
    timestamp: datetime
    strategy_mode: StrategyMode
    equity: float = Field(..., ge=0)
    drawdown: float = Field(..., le=0)
    drawdown_pct: float = Field(..., le=0)
    realized_pnl: float
    open_position: bool
    realized_equity: float | None = Field(default=None, ge=0)
    unrealized_pnl: float | None = None
    total_equity: float | None = Field(default=None, ge=0)
    equity_basis: str = "realized_only"


class MetricsSummary(BaseModel):
    total_return: float | None
    total_return_pct: float | None
    max_drawdown: float
    max_drawdown_pct: float
    profit_factor: float | None = None
    win_rate: float | None = None
    average_win: float | None = None
    average_loss: float | None = None
    expectancy: float | None = None
    number_of_trades: int = Field(..., ge=0)
    average_holding_bars: float | None = None
    max_consecutive_losses: int = Field(..., ge=0)
    return_by_regime: dict[str, Any] = Field(default_factory=dict)
    return_by_strategy_mode: dict[str, Any] = Field(default_factory=dict)
    return_by_symbol_provider: dict[str, Any] = Field(default_factory=dict)
    baseline_comparison: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ReportArtifact(BaseModel):
    artifact_type: ReportArtifactType
    path: str
    format: ArtifactFormat
    rows: int | None = Field(default=None, ge=0)
    created_at: datetime
    content_hash: str | None = None


class BacktestRun(BaseModel):
    run_id: str
    status: BacktestStatus
    created_at: datetime
    completed_at: datetime | None = None
    symbol: str
    provider: str | None = None
    timeframe: str
    feature_path: str
    config: BacktestRunRequest
    config_hash: str | None = None
    data_identity: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    artifacts: list[ReportArtifact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class BacktestRunSummary(BaseModel):
    run_id: str
    status: BacktestStatus
    created_at: datetime
    symbol: str
    provider: str | None = None
    timeframe: str
    strategy_modes: list[StrategyMode] = Field(default_factory=list)
    baseline_modes: list[BaselineMode] = Field(default_factory=list)
    total_return_pct: float | None = None
    max_drawdown_pct: float | None = None


class BacktestRunResponse(BacktestRun):
    metrics: MetricsSummary | None = None


class BacktestRunListResponse(BaseModel):
    runs: list[BacktestRunSummary] = Field(default_factory=list)


class PaginationMeta(BaseModel):
    count: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)


class BacktestTradesResponse(BaseModel):
    data: list[TradeRecord]
    meta: PaginationMeta


class BacktestMetricsResponse(BaseModel):
    run_id: str
    summary: MetricsSummary
    return_by_regime: list[dict[str, Any]] = Field(default_factory=list)
    return_by_strategy_mode: list[dict[str, Any]] = Field(default_factory=list)
    return_by_symbol_provider: list[dict[str, Any]] = Field(default_factory=list)
    baseline_comparison: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class BacktestEquityResponse(BaseModel):
    run_id: str
    data: list[EquityPoint]
    meta: dict[str, int]


class CapitalSizingConfig(StrictModel):
    buy_hold_capital_fraction: float = Field(default=1.0, gt=0, le=1)
    buy_hold_sizing_mode: CapitalSizingMode = Field(default=CapitalSizingMode.CAPITAL_FRACTION)
    active_risk_per_trade: float | None = Field(default=None, gt=0, le=1)
    leverage: float = Field(default=1, ge=1, le=1)
    notional_cap_enabled: bool = Field(default=True)

    @model_validator(mode="after")
    def validate_no_leverage_cap(self) -> "CapitalSizingConfig":
        if not self.notional_cap_enabled:
            raise ValueError("notional cap must remain enabled in v0 validation")
        return self


class CostStressProfile(StrictModel):
    name: CostStressProfileName
    fee_rate: float = Field(..., ge=0, le=0.1)
    slippage_rate: float = Field(..., ge=0, le=0.1)
    description: str


class SensitivityGrid(StrictModel):
    grid_entry_threshold: list[float] = Field(default_factory=list)
    atr_stop_buffer: list[float] = Field(default_factory=list)
    breakout_risk_reward_multiple: list[float] = Field(default_factory=list)
    fee_slippage_profile: list[CostStressProfileName] = Field(default_factory=list)


class WalkForwardConfig(StrictModel):
    split_count: int = Field(default=3, ge=1, le=20)
    minimum_rows_per_split: int = Field(default=20, ge=1)


class ValidationRunRequest(StrictModel):
    base_config: BacktestRunRequest
    capital_sizing: CapitalSizingConfig = Field(default_factory=CapitalSizingConfig)
    stress_profiles: list[CostStressProfileName] = Field(default_factory=list)
    sensitivity_grid: SensitivityGrid = Field(default_factory=SensitivityGrid)
    walk_forward: WalkForwardConfig = Field(default_factory=WalkForwardConfig)
    include_real_data_check: bool = Field(default=True)


class NotionalCapEvent(BaseModel):
    trade_id: str | None = None
    strategy_mode: StrategyMode
    requested_notional: float = Field(..., gt=0)
    capped_notional: float = Field(..., gt=0)
    available_equity: float = Field(..., gt=0)
    reason: str


class ModeMetrics(BaseModel):
    strategy_mode: StrategyMode
    category: str
    total_return_pct: float | None = None
    max_drawdown_pct: float | None = None
    number_of_trades: int = Field(default=0, ge=0)
    profit_factor: float | None = None
    win_rate: float | None = None
    expectancy: float | None = None
    equity_basis: str = "realized_only"
    notes: list[str] = Field(default_factory=list)


class StressResult(BaseModel):
    profile: CostStressProfile
    strategy_mode: StrategyMode
    category: str
    metrics: ModeMetrics
    outcome: StressOutcome
    notes: list[str] = Field(default_factory=list)


class ParameterSensitivityResult(BaseModel):
    parameter_set_id: str
    grid_entry_threshold: float | None = None
    atr_stop_buffer: float | None = None
    breakout_risk_reward_multiple: float | None = None
    stress_profile_name: CostStressProfileName | None = None
    strategy_mode: StrategyMode
    metrics: ModeMetrics
    fragility_flag: bool = False
    notes: list[str] = Field(default_factory=list)


class WalkForwardResult(BaseModel):
    split_id: str
    start_timestamp: datetime
    end_timestamp: datetime
    row_count: int = Field(..., ge=0)
    trade_count: int = Field(default=0, ge=0)
    status: ValidationSplitStatus
    mode_metrics: list[ModeMetrics] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RegimeCoverageReport(BaseModel):
    bar_counts: dict[str, int] = Field(default_factory=dict)
    trades_per_regime: dict[str, int] = Field(default_factory=dict)
    return_by_regime: dict[str, Any] = Field(default_factory=dict)
    coverage_notes: list[str] = Field(default_factory=list)


class TradeConcentrationReport(BaseModel):
    top_1_profit_contribution_pct: float | None = None
    top_5_profit_contribution_pct: float | None = None
    top_10_profit_contribution_pct: float | None = None
    best_trades: list[TradeRecord] = Field(default_factory=list)
    worst_trades: list[TradeRecord] = Field(default_factory=list)
    max_consecutive_losses: int = Field(default=0, ge=0)
    drawdown_recovery_bars: int | None = Field(default=None, ge=0)
    drawdown_recovery_status: DrawdownRecoveryStatus = Field(
        default=DrawdownRecoveryStatus.NOT_APPLICABLE
    )
    notes: list[str] = Field(default_factory=list)


class ValidationRun(BaseModel):
    validation_run_id: str
    status: BacktestStatus
    created_at: datetime
    completed_at: datetime | None = None
    symbol: str
    provider: str | None = None
    timeframe: str
    source_backtest_config: BacktestRunRequest
    data_identity: dict[str, Any] = Field(default_factory=dict)
    mode_metrics: list[ModeMetrics] = Field(default_factory=list)
    stress_results: list[StressResult] = Field(default_factory=list)
    sensitivity_results: list[ParameterSensitivityResult] = Field(default_factory=list)
    walk_forward_results: list[WalkForwardResult] = Field(default_factory=list)
    regime_coverage: RegimeCoverageReport = Field(default_factory=RegimeCoverageReport)
    concentration_report: TradeConcentrationReport = Field(default_factory=TradeConcentrationReport)
    notional_cap_events: list[NotionalCapEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    artifacts: list[ReportArtifact] = Field(default_factory=list)


class ValidationRunSummary(BaseModel):
    validation_run_id: str
    status: BacktestStatus
    created_at: datetime
    symbol: str
    provider: str | None = None
    timeframe: str
    mode_count: int = Field(default=0, ge=0)
    stress_profile_count: int = Field(default=0, ge=0)
    walk_forward_split_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)


class ValidationRunListResponse(BaseModel):
    runs: list[ValidationRunSummary] = Field(default_factory=list)


class ValidationStressResponse(BaseModel):
    validation_run_id: str
    data: list[StressResult] = Field(default_factory=list)


class ValidationSensitivityResponse(BaseModel):
    validation_run_id: str
    data: list[ParameterSensitivityResult] = Field(default_factory=list)


class ValidationWalkForwardResponse(BaseModel):
    validation_run_id: str
    data: list[WalkForwardResult] = Field(default_factory=list)


class ValidationConcentrationResponse(BaseModel):
    validation_run_id: str
    regime_coverage: RegimeCoverageReport = Field(default_factory=RegimeCoverageReport)
    concentration_report: TradeConcentrationReport = Field(default_factory=TradeConcentrationReport)
