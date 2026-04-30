from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from src.models.backtest import (
    BacktestStatus,
    CostStressProfileName,
    ReportArtifact,
    ReportFormat,
    StrictModel,
)


class ResearchAssetClass(StrEnum):
    CRYPTO = "crypto"
    EQUITY_PROXY = "equity_proxy"
    GOLD_PROXY = "gold_proxy"
    MACRO_PROXY = "macro_proxy"
    LOCAL_DATASET = "local_dataset"


class ResearchFeatureGroup(StrEnum):
    OHLCV = "ohlcv"
    REGIME = "regime"
    OPEN_INTEREST = "oi"
    FUNDING = "funding"
    VOLUME_CONFIRMATION = "volume_confirmation"


class ResearchPreflightStatus(StrEnum):
    READY = "ready"
    MISSING_DATA = "missing_data"
    INCOMPLETE_FEATURES = "incomplete_features"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"


class ResearchAssetRunStatus(StrEnum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    PARTIAL = "partial"


class ResearchAssetClassification(StrEnum):
    ROBUST = "robust"
    FRAGILE = "fragile"
    MISSING_DATA = "missing_data"
    INCONCLUSIVE = "inconclusive"
    NOT_WORTH_CONTINUING = "not_worth_continuing"


class ConcentrationWarningLevel(StrEnum):
    NONE = "none"
    WATCH = "watch"
    HIGH = "high"


class ResearchBaseAssumptions(StrictModel):
    initial_equity: float = Field(default=10_000.0, gt=0)
    fee_rate: float = Field(default=0.0004, ge=0, le=0.1)
    slippage_rate: float = Field(default=0.0002, ge=0, le=0.1)
    risk_per_trade: float = Field(default=0.01, gt=0, le=1)
    allow_short: bool = True


class ResearchStrategySet(StrictModel):
    include_grid_range: bool = True
    include_breakout: bool = True
    baselines: list[str] = Field(default_factory=lambda: ["buy_hold", "price_breakout"])

    @model_validator(mode="after")
    def require_research_mode(self) -> "ResearchStrategySet":
        if not self.include_grid_range and not self.include_breakout and not self.baselines:
            raise ValueError("at least one strategy or baseline is required")
        return self


class ResearchSensitivityGrid(StrictModel):
    grid_entry_threshold: list[float] = Field(default_factory=lambda: [0.1, 0.15, 0.2])
    atr_stop_buffer: list[float] = Field(default_factory=lambda: [0.75, 1.0, 1.25])
    breakout_risk_reward_multiple: list[float] = Field(default_factory=lambda: [1.5, 2.0, 2.5])
    fee_slippage_profile: list[CostStressProfileName] = Field(
        default_factory=lambda: [
            CostStressProfileName.NORMAL,
            CostStressProfileName.HIGH_FEE,
        ]
    )


class ResearchWalkForwardConfig(StrictModel):
    split_count: int = Field(default=3, ge=1, le=20)
    minimum_rows_per_split: int = Field(default=20, ge=1)


class ResearchValidationConfig(StrictModel):
    stress_profiles: list[CostStressProfileName] = Field(
        default_factory=lambda: [
            CostStressProfileName.NORMAL,
            CostStressProfileName.HIGH_FEE,
            CostStressProfileName.HIGH_SLIPPAGE,
            CostStressProfileName.WORST_REASONABLE_COST,
        ]
    )
    sensitivity_grid: ResearchSensitivityGrid = Field(default_factory=ResearchSensitivityGrid)
    walk_forward: ResearchWalkForwardConfig = Field(default_factory=ResearchWalkForwardConfig)


class ResearchAssetConfig(StrictModel):
    symbol: str
    provider: str
    asset_class: ResearchAssetClass
    timeframe: str
    enabled: bool = True
    feature_path: Path | None = None
    required_feature_groups: list[ResearchFeatureGroup] = Field(
        default_factory=lambda: [ResearchFeatureGroup.OHLCV, ResearchFeatureGroup.REGIME]
    )
    display_name: str | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol is required")
        return normalized

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("provider is required")
        return normalized

    @field_validator("timeframe")
    @classmethod
    def normalize_timeframe(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("timeframe is required")
        return normalized


class ResearchRunRequest(StrictModel):
    assets: list[ResearchAssetConfig]
    default_asset_set: str | None = None
    base_assumptions: ResearchBaseAssumptions = Field(default_factory=ResearchBaseAssumptions)
    strategy_set: ResearchStrategySet = Field(default_factory=ResearchStrategySet)
    validation_config: ResearchValidationConfig = Field(default_factory=ResearchValidationConfig)
    report_format: ReportFormat = ReportFormat.BOTH
    include_blocked_assets: bool = True

    @model_validator(mode="after")
    def require_enabled_asset(self) -> "ResearchRunRequest":
        if not any(asset.enabled for asset in self.assets):
            raise ValueError("at least one enabled asset is required")
        return self


class ResearchCapabilitySnapshot(BaseModel):
    provider: str
    supports_ohlcv: bool = False
    supports_open_interest: bool = False
    supports_funding_rate: bool = False
    detected_ohlcv: bool = False
    detected_regime: bool = False
    detected_open_interest: bool = False
    detected_funding_rate: bool = False
    limitation_notes: list[str] = Field(default_factory=list)


class ResearchPreflightResult(BaseModel):
    symbol: str
    provider: str
    status: ResearchPreflightStatus
    feature_path: str
    row_count: int | None = None
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    capability_snapshot: ResearchCapabilitySnapshot
    missing_columns: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StrategyComparisonRow(BaseModel):
    symbol: str
    provider: str
    mode: str
    category: str
    total_return_pct: float | None = None
    max_drawdown_pct: float | None = None
    number_of_trades: int = Field(default=0, ge=0)
    profit_factor: float | None = None
    win_rate: float | None = None
    notes: list[str] = Field(default_factory=list)


class StressSurvivalRow(BaseModel):
    symbol: str
    mode: str
    profile: str
    outcome: str
    survived: bool | None = None
    notes: list[str] = Field(default_factory=list)


class WalkForwardStabilityRow(BaseModel):
    symbol: str
    split_id: str
    status: str
    row_count: int = Field(ge=0)
    trade_count: int = Field(default=0, ge=0)
    stable: bool | None = None
    notes: list[str] = Field(default_factory=list)


class RegimeCoverageAssetRow(BaseModel):
    symbol: str
    regime: str
    bar_count: int = Field(ge=0)
    trade_count: int = Field(default=0, ge=0)
    return_pct: float | None = None
    notes: list[str] = Field(default_factory=list)


class ConcentrationAssetRow(BaseModel):
    symbol: str
    top_1_profit_contribution_pct: float | None = None
    top_5_profit_contribution_pct: float | None = None
    top_10_profit_contribution_pct: float | None = None
    max_consecutive_losses: int = Field(default=0, ge=0)
    drawdown_recovery_status: str
    warning_level: ConcentrationWarningLevel = ConcentrationWarningLevel.NONE
    notes: list[str] = Field(default_factory=list)


class ResearchAssetResult(BaseModel):
    symbol: str
    provider: str
    asset_class: ResearchAssetClass
    status: ResearchAssetRunStatus
    classification: ResearchAssetClassification
    preflight: ResearchPreflightResult
    validation_run_id: str | None = None
    data_identity: dict[str, Any] = Field(default_factory=dict)
    strategy_comparison: list[StrategyComparisonRow] = Field(default_factory=list)
    stress_summary: list[StressSurvivalRow] = Field(default_factory=list)
    walk_forward_summary: list[WalkForwardStabilityRow] = Field(default_factory=list)
    regime_coverage_summary: list[RegimeCoverageAssetRow] = Field(default_factory=list)
    concentration_summary: list[ConcentrationAssetRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ResearchRun(BaseModel):
    research_run_id: str
    status: BacktestStatus
    created_at: datetime
    completed_at: datetime | None = None
    request: ResearchRunRequest
    assets: list[ResearchAssetResult] = Field(default_factory=list)
    completed_count: int = Field(default=0, ge=0)
    blocked_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    artifacts: list[ReportArtifact] = Field(default_factory=list)


class ResearchRunSummary(BaseModel):
    research_run_id: str
    status: BacktestStatus
    created_at: datetime
    completed_count: int = Field(default=0, ge=0)
    blocked_count: int = Field(default=0, ge=0)
    asset_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)


class ResearchRunListResponse(BaseModel):
    runs: list[ResearchRunSummary] = Field(default_factory=list)


class ResearchAssetSummaryResponse(BaseModel):
    research_run_id: str
    data: list[ResearchAssetResult] = Field(default_factory=list)


class ResearchComparisonResponse(BaseModel):
    research_run_id: str
    data: list[StrategyComparisonRow] = Field(default_factory=list)


class ResearchValidationAggregationResponse(BaseModel):
    research_run_id: str
    stress: list[StressSurvivalRow] = Field(default_factory=list)
    walk_forward: list[WalkForwardStabilityRow] = Field(default_factory=list)
    regime_coverage: list[RegimeCoverageAssetRow] = Field(default_factory=list)
    concentration: list[ConcentrationAssetRow] = Field(default_factory=list)

