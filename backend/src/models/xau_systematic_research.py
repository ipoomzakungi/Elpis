from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from src.models.xau import XauBaseModel
from src.models.xau_market_context import (
    XauBasisStatus,
    XauCandleReactionState,
    XauContextAvailabilityStatus,
    XauVolatilityStatus,
)


class XauSystematicCmeSourceMode(StrEnum):
    LATEST_EXISTING = "latest_existing"
    API_ONLY = "api_only"
    BROWSER_CDP = "browser_cdp"
    SUPPLIED_REPORTS = "supplied_reports"


class XauSystematicPriceProvider(StrEnum):
    LOCAL_BARS = "local_bars"
    LATEST_LOCAL_IMPORT = "latest_local_import"
    DUKASCOPY_NODE = "dukascopy_node"
    YFINANCE = "yfinance"
    MANUAL = "manual"


class XauSystematicSourceStatus(StrEnum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    STALE = "stale"
    BLOCKED = "blocked"


class XauSystematicReadiness(StrEnum):
    BLOCKED = "blocked"
    PARTIAL = "partial"
    READY_FOR_SHADOW_REVIEW = "ready_for_shadow_review"


class XauSystematicCycleRequest(XauBaseModel):
    cycle_label: str | None = None
    cycle_time: str | None = None
    timezone: str = "Asia/Bangkok"
    session_date: date | None = None
    cme_source_mode: XauSystematicCmeSourceMode
    vol2vol_report_id: str | None = None
    matrix_report_id: str | None = None
    fusion_report_id: str | None = None
    use_latest_fusion: bool = True
    traded_symbol: str = "XAUUSD"
    price_provider: XauSystematicPriceProvider
    price_bars_path: Path | None = None
    dukascopy_node_command_template: str | None = None
    dukascopy_symbol: str = "xauusd"
    dukascopy_timeframe: str = "m1"
    dukascopy_from: datetime | None = None
    dukascopy_to: datetime | None = None
    spot_symbol: str = "XAUUSD=X"
    gc_symbol: str = "GC=F"
    max_cme_age_minutes: int = Field(default=180, gt=0)
    max_price_age_minutes: int = Field(default=15, gt=0)
    max_basis_alignment_seconds: int = Field(default=120, gt=0)
    allow_stale_basis: bool = False
    output_root: Path | None = None
    overwrite: bool = False
    research_only_acknowledged: bool

    @model_validator(mode="after")
    def validate_research_acknowledgement(self) -> XauSystematicCycleRequest:
        if not self.research_only_acknowledged:
            raise ValueError("research_only_acknowledged must be true")
        if self.cycle_time not in (None, "10:00", "19:00", "manual"):
            raise ValueError("cycle_time must be one of 10:00, 19:00, manual, or null")
        if (
            self.price_provider == XauSystematicPriceProvider.DUKASCOPY_NODE
            and not self.dukascopy_node_command_template
        ):
            raise ValueError("dukascopy_node requires dukascopy_node_command_template")
        return self


class XauSourceManifest(XauBaseModel):
    cme_vol2vol_status: XauSystematicSourceStatus
    cme_matrix_status: XauSystematicSourceStatus
    fusion_status: XauSystematicSourceStatus
    traded_price_status: XauSystematicSourceStatus
    basis_status: XauSystematicSourceStatus
    session_open_status: XauSystematicSourceStatus
    volatility_status: XauSystematicSourceStatus
    candle_state_status: XauSystematicSourceStatus
    ai_pack_status: XauSystematicSourceStatus = XauSystematicSourceStatus.UNAVAILABLE
    missing_sources: list[str] = Field(default_factory=list)
    stale_sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class XauSystematicCmeState(XauBaseModel):
    vol2vol_report_id: str | None = None
    matrix_report_id: str | None = None
    fusion_report_id: str | None = None
    cme_created_at: datetime | None = None
    cme_age_minutes: float | None = Field(default=None, ge=0)
    row_counts: dict[str, int] = Field(default_factory=dict)
    strike_count: int = Field(default=0, ge=0)
    expiration_count: int = Field(default=0, ge=0)
    unavailable_cell_count: int = Field(default=0, ge=0)


class XauSystematicPriceState(XauBaseModel):
    traded_symbol: str
    provider: XauSystematicPriceProvider
    bars_path: Path | None = None
    latest_price: float | None = Field(default=None, gt=0)
    latest_price_timestamp: datetime | None = None
    price_age_minutes: float | None = Field(default=None, ge=0)


class XauSystematicBasisState(XauBaseModel):
    gc_futures_price: float | None = Field(default=None, gt=0)
    xauusd_spot_price: float | None = Field(default=None, gt=0)
    basis_points: float | None = None
    basis_formula: str = "gc_futures_price - xauusd_spot_price"
    mapping_formula: str = "spot_equivalent_level = cme_level - basis_points"
    basis_status: XauBasisStatus
    alignment_seconds: float | None = Field(default=None, ge=0)


class XauSystematicSessionState(XauBaseModel):
    active_session: str | None = None
    session_open: float | None = Field(default=None, gt=0)
    open_distance_points: float | None = None
    open_side: str | None = None


class XauSystematicVolatilityState(XauBaseModel):
    atr_5m: float | None = Field(default=None, gt=0)
    atr_15m: float | None = Field(default=None, gt=0)
    atr_1h: float | None = Field(default=None, gt=0)
    realized_vol_30m: float | None = Field(default=None, ge=0)
    realized_vol_session: float | None = Field(default=None, ge=0)
    status: XauVolatilityStatus


class XauSystematicMappedStructure(XauBaseModel):
    top_mapped_walls: list[dict[str, Any]] = Field(default_factory=list)
    nearest_mapped_wall: dict[str, Any] | None = None
    mapped_sd_bands: list[dict[str, Any]] = Field(default_factory=list)
    wall_distance_points: float | None = None
    wall_distance_atr: float | None = None


class XauSystematicRegimeStates(XauBaseModel):
    oi_state: str
    iv_state: str
    volume_state: str
    candle_state: str
    regime_state: str


class XauSystematicReadinessFlags(XauBaseModel):
    blocked: bool
    partial: bool
    ready_for_shadow_review: bool


class XauAlignedSourceState(XauBaseModel):
    cycle_id: str
    created_at: datetime
    session_date: date
    cycle_label: str | None = None
    cme: XauSystematicCmeState
    price: XauSystematicPriceState
    basis: XauSystematicBasisState
    session: XauSystematicSessionState
    volatility: XauSystematicVolatilityState
    mapped_structure: XauSystematicMappedStructure
    states: XauSystematicRegimeStates
    readiness: XauSystematicReadinessFlags
    no_trade_reasons: list[str] = Field(default_factory=list)
    signal_allowed: Literal[False] = False
    research_only: Literal[True] = True


class XauAiResearchPack(XauBaseModel):
    pack_id: str
    cycle_id: str
    created_at: datetime
    session_date: date
    cycle_label: str | None = None
    executive_summary: str
    source_status_table: list[dict[str, Any]]
    key_levels_table: list[dict[str, Any]]
    mapped_levels_table: list[dict[str, Any]]
    volatility_summary: dict[str, Any]
    basis_summary: dict[str, Any]
    session_summary: dict[str, Any]
    candle_summary: dict[str, Any]
    oi_iv_volume_summary: dict[str, Any]
    readiness: XauSystematicReadiness
    no_trade_reasons: list[str] = Field(default_factory=list)
    questions_for_human: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    machine_context: dict[str, Any] = Field(default_factory=dict)
    research_only: Literal[True] = True
    signal_allowed: Literal[False] = False


class XauSystematicCycleResult(XauBaseModel):
    cycle_id: str
    output_dir: Path
    readiness: XauSystematicReadiness
    source_manifest: XauSourceManifest
    aligned_state: XauAlignedSourceState
    ai_pack: XauAiResearchPack
    artifacts: dict[str, Path]
    signal_allowed: Literal[False] = False
    research_only: Literal[True] = True


class XauDukascopyNodeFetchResult(XauBaseModel):
    provider_status: XauSystematicSourceStatus
    provider_quality: str = "research_good"
    bars_path: Path | None = None
    bars_count: int = Field(default=0, ge=0)
    latest_price: float | None = Field(default=None, gt=0)
    latest_timestamp: datetime | None = None
    command: str | None = None
    stderr: str | None = None
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    signal_allowed: Literal[False] = False
    research_only: Literal[True] = True


def source_status_from_context_status(
    value: XauContextAvailabilityStatus | XauVolatilityStatus | XauCandleReactionState | None,
) -> XauSystematicSourceStatus:
    if value is None:
        return XauSystematicSourceStatus.UNAVAILABLE
    if value in {XauContextAvailabilityStatus.AVAILABLE, XauVolatilityStatus.AVAILABLE}:
        return XauSystematicSourceStatus.AVAILABLE
    if value == XauVolatilityStatus.PARTIAL:
        return XauSystematicSourceStatus.PARTIAL
    return XauSystematicSourceStatus.UNAVAILABLE
