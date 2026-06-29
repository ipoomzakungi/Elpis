from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import Field, model_validator

from src.models.xau import XauBaseModel


class XauSessionName(StrEnum):
    ASIA = "asia"
    LONDON = "london"
    NY_MACRO = "ny_macro"
    NY_CASH = "ny_cash"
    DAILY_ROLL = "daily_roll"
    CUSTOM = "custom"


class XauContextAvailabilityStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    STALE = "stale"


class XauBasisStatus(StrEnum):
    ALIGNED = "aligned"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    CONFLICT = "conflict"


class XauMappedLevelStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class XauVolatilityStatus(StrEnum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class XauCandleReactionState(StrEnum):
    ACCEPTED_ABOVE = "accepted_above"
    ACCEPTED_BELOW = "accepted_below"
    REJECTED_ABOVE = "rejected_above"
    REJECTED_BELOW = "rejected_below"
    CLOSE_BACK_INSIDE = "close_back_inside"
    FAILED_BREAKOUT = "failed_breakout"
    NEUTRAL = "neutral"
    UNAVAILABLE = "unavailable"


class XauMarketContextReadiness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class XauPriceBar(XauBaseModel):
    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float | None = Field(default=None, ge=0)
    symbol: str = "XAUUSD"
    timeframe: str = "1m"

    @model_validator(mode="after")
    def validate_ohlc(self) -> XauPriceBar:
        if self.low > self.high:
            raise ValueError("bar low must be <= high")
        if not self.low <= self.open <= self.high:
            raise ValueError("bar open must be inside high/low")
        if not self.low <= self.close <= self.high:
            raise ValueError("bar close must be inside high/low")
        if self.timestamp.tzinfo is None:
            raise ValueError("bar timestamp must be timezone-aware")
        return self


class XauSessionOpen(XauBaseModel):
    session_name: XauSessionName
    timezone: str
    open_time: datetime
    open_price: float | None = Field(default=None, gt=0)
    status: XauContextAvailabilityStatus
    notes: list[str] = Field(default_factory=list)
    open_side: str | None = None
    open_distance_points: float | None = None


class XauBasisSnapshot(XauBaseModel):
    xauusd_spot_price: float | None = Field(default=None, gt=0)
    gc_futures_price: float | None = Field(default=None, gt=0)
    basis_points: float | None = None
    basis_formula: str = "gc_futures_price - xauusd_spot_price"
    mapping_formula: str = "spot_equivalent_level = futures_level - basis_points"
    status: XauBasisStatus
    timestamp_alignment_seconds: float | None = Field(default=None, ge=0)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_available_basis(self) -> XauBasisSnapshot:
        if self.status == XauBasisStatus.ALIGNED and self.basis_points is None:
            raise ValueError("aligned basis requires basis_points")
        if self.status == XauBasisStatus.UNAVAILABLE and self.basis_points is not None:
            raise ValueError("unavailable basis must not carry basis_points")
        return self


class XauMappedLevel(XauBaseModel):
    source_level: float = Field(gt=0)
    mapped_level: float | None = Field(default=None, gt=0)
    basis_points: float | None = None
    mapping_status: XauMappedLevelStatus
    source: str


class XauVolatilitySnapshot(XauBaseModel):
    atr_5m: float | None = Field(default=None, gt=0)
    atr_15m: float | None = Field(default=None, gt=0)
    atr_1h: float | None = Field(default=None, gt=0)
    realized_vol_30m: float | None = Field(default=None, ge=0)
    realized_vol_session: float | None = Field(default=None, ge=0)
    rv_method: str = "sqrt_sum_squared_log_returns"
    status: XauVolatilityStatus
    warnings: list[str] = Field(default_factory=list)


class XauCandleState(XauBaseModel):
    level: float = Field(gt=0)
    timeframe: str
    state: XauCandleReactionState
    close: float | None = Field(default=None, gt=0)
    high: float | None = Field(default=None, gt=0)
    low: float | None = Field(default=None, gt=0)
    buffer_points: float = Field(ge=0)
    evidence: list[str] = Field(default_factory=list)


class XauMarketContextSnapshot(XauBaseModel):
    snapshot_id: str
    created_at: datetime
    session_date: date
    traded_symbol: str = "XAUUSD"
    cme_product: str = "GC/OG"
    fusion_report_id: str | None = None
    xauusd_spot_price: float | None = Field(default=None, gt=0)
    gc_futures_price: float | None = Field(default=None, gt=0)
    basis: XauBasisSnapshot
    active_session: XauSessionOpen | None = None
    session_opens: list[XauSessionOpen] = Field(default_factory=list)
    volatility: XauVolatilitySnapshot
    mapped_levels: list[XauMappedLevel] = Field(default_factory=list)
    nearest_mapped_wall: XauMappedLevel | None = None
    candle_states: list[XauCandleState] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    readiness: XauMarketContextReadiness
    signal_allowed: bool = False
    research_only: bool = True
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_research_only_state(self) -> XauMarketContextSnapshot:
        if self.signal_allowed:
            raise ValueError("XAU market context snapshots cannot enable signals")
        if not self.research_only:
            raise ValueError("XAU market context snapshots must remain research_only")
        return self

