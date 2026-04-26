from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    """Base model for persisted research configurations."""

    model_config = ConfigDict(extra="forbid")


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


class MetricsSummary(BaseModel):
    total_return: float
    total_return_pct: float
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