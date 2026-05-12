from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class XauReactionBaseModel(BaseModel):
    """Strict base model for research-only XAU reaction schemas."""

    model_config = ConfigDict(extra="forbid")


class XauFreshnessState(StrEnum):
    VALID = "VALID"
    THIN = "THIN"
    STALE = "STALE"
    PRIOR_DAY = "PRIOR_DAY"
    UNKNOWN = "UNKNOWN"


class XauReactionLabel(StrEnum):
    REVERSAL_CANDIDATE = "REVERSAL_CANDIDATE"
    BREAKOUT_CANDIDATE = "BREAKOUT_CANDIDATE"
    PIN_MAGNET = "PIN_MAGNET"
    SQUEEZE_RISK = "SQUEEZE_RISK"
    VACUUM_TO_NEXT_WALL = "VACUUM_TO_NEXT_WALL"
    NO_TRADE = "NO_TRADE"


class XauConfidenceLabel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class XauVrpRegime(StrEnum):
    IV_PREMIUM = "iv_premium"
    BALANCED = "balanced"
    RV_PREMIUM = "rv_premium"
    UNKNOWN = "unknown"


class XauIvEdgeState(StrEnum):
    INSIDE = "inside"
    AT_EDGE = "at_edge"
    BEYOND_EDGE = "beyond_edge"
    UNKNOWN = "unknown"


class XauRvExtensionState(StrEnum):
    INSIDE = "inside"
    EXTENDED = "extended"
    BEYOND_RANGE = "beyond_range"
    UNKNOWN = "unknown"


class XauInitialMoveDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"
    UNKNOWN = "unknown"


class XauOpenSide(StrEnum):
    ABOVE_OPEN = "above_open"
    BELOW_OPEN = "below_open"
    AT_OPEN = "at_open"
    UNKNOWN = "unknown"


class XauOpenFlipState(StrEnum):
    NO_FLIP = "no_flip"
    CROSSED_WITHOUT_ACCEPTANCE = "crossed_without_acceptance"
    ACCEPTED_FLIP = "accepted_flip"
    UNKNOWN = "unknown"


class XauOpenSupportResistance(StrEnum):
    SUPPORT_TEST = "support_test"
    RESISTANCE_TEST = "resistance_test"
    BOUNDARY = "boundary"
    UNKNOWN = "unknown"


class XauAcceptanceDirection(StrEnum):
    ABOVE = "above"
    BELOW = "below"
    UNKNOWN = "unknown"


class XauFreshnessInput(XauReactionBaseModel):
    intraday_timestamp: datetime | None = None
    current_timestamp: datetime | None = None
    total_intraday_contracts: float | None = None
    min_contract_threshold: float = Field(..., gt=0)
    max_allowed_age_minutes: int = Field(..., gt=0)
    session_flag: str | None = None


class XauFreshnessResult(XauReactionBaseModel):
    state: XauFreshnessState
    age_minutes: float | None = None
    confidence_label: XauConfidenceLabel
    no_trade_reason: str | None = None
    notes: list[str] = Field(default_factory=list)


class XauVolRegimeInput(XauReactionBaseModel):
    implied_volatility: float | None = Field(default=None, gt=0)
    realized_volatility: float | None = Field(default=None, gt=0)
    price: float | None = Field(default=None, gt=0)
    iv_lower: float | None = None
    iv_upper: float | None = None
    rv_lower: float | None = None
    rv_upper: float | None = None
    price_series: list[float] = Field(default_factory=list)
    annualization_periods: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_ranges(self) -> "XauVolRegimeInput":
        _validate_range(self.iv_lower, self.iv_upper, "iv")
        _validate_range(self.rv_lower, self.rv_upper, "rv")
        if self.price_series and len(self.price_series) < 2:
            raise ValueError("price_series requires at least two values")
        if self.price_series and self.annualization_periods is None:
            raise ValueError("annualization_periods is required with price_series")
        if any(price <= 0 for price in self.price_series):
            raise ValueError("price_series values must be greater than 0")
        return self


class XauVolRegimeResult(XauReactionBaseModel):
    realized_volatility: float | None = None
    vrp: float | None = None
    vrp_regime: XauVrpRegime
    iv_edge_state: XauIvEdgeState
    rv_extension_state: XauRvExtensionState
    confidence_label: XauConfidenceLabel
    notes: list[str] = Field(default_factory=list)


class XauOpenRegimeInput(XauReactionBaseModel):
    session_open: float | None = Field(default=None, gt=0)
    current_price: float | None = Field(default=None, gt=0)
    initial_move_direction: XauInitialMoveDirection | None = None
    crossed_open_after_initial_move: bool | None = None
    acceptance_beyond_open: bool | None = None


class XauOpenRegimeResult(XauReactionBaseModel):
    open_side: XauOpenSide
    open_distance_points: float | None = None
    open_flip_state: XauOpenFlipState
    open_as_support_or_resistance: XauOpenSupportResistance
    confidence_label: XauConfidenceLabel
    notes: list[str] = Field(default_factory=list)


class XauAcceptanceInput(XauReactionBaseModel):
    wall_id: str | None = None
    zone_id: str | None = None
    wall_level: float
    high: float
    low: float
    close: float
    next_bar_open: float | None = None
    buffer_points: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def validate_ohlc(self) -> "XauAcceptanceInput":
        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
        if not self.low <= self.close <= self.high:
            raise ValueError("close must be inside the high-low range")
        return self


class XauAcceptanceResult(XauReactionBaseModel):
    wall_id: str | None = None
    zone_id: str | None = None
    accepted_beyond_wall: bool
    wick_rejection: bool
    failed_breakout: bool
    confirmed_breakout: bool
    direction: XauAcceptanceDirection
    confidence_label: XauConfidenceLabel
    notes: list[str] = Field(default_factory=list)


def _validate_range(lower: float | None, upper: float | None, label: str) -> None:
    if (lower is None) != (upper is None):
        raise ValueError(f"{label}_lower and {label}_upper must be supplied together")
    if lower is not None and upper is not None and lower >= upper:
        raise ValueError(f"{label}_lower must be less than {label}_upper")
