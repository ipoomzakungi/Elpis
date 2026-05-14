import re
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SAFE_REPORT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
XAU_REACTION_RESEARCH_ONLY_WARNING = (
    "XAU reaction outputs are research annotations only and are not action instructions."
)


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


class XauReactionReportStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class XauReactionArtifactType(StrEnum):
    METADATA = "metadata"
    REPORT_JSON = "report_json"
    REPORT_MARKDOWN = "report_markdown"
    REACTIONS = "reactions"
    RISK_PLANS = "risk_plans"


class XauReactionArtifactFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    PARQUET = "parquet"


class XauReactionReportFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    BOTH = "both"


class XauEventRiskState(StrEnum):
    CLEAR = "clear"
    ELEVATED = "elevated"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class XauRewardRiskState(StrEnum):
    MEETS_MINIMUM = "meets_minimum"
    BELOW_MINIMUM = "below_minimum"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


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


class XauIntradayFreshnessInput(XauFreshnessInput):
    """Alias schema used by the reaction-report request contract."""


class XauFreshnessResult(XauReactionBaseModel):
    state: XauFreshnessState
    age_minutes: float | None = None
    confidence_label: XauConfidenceLabel
    no_trade_reason: str | None = None
    notes: list[str] = Field(default_factory=list)


class XauFreshnessAssessment(XauFreshnessResult):
    """Report-level freshness assessment used by reaction reports."""


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


class XauVolRegimeState(XauVolRegimeResult):
    """Report-level volatility regime state used by reaction reports."""


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


class XauOpenRegimeState(XauOpenRegimeResult):
    """Report-level session-open state used by reaction reports."""


class XauAcceptanceInput(XauReactionBaseModel):
    wall_id: str | None = None
    zone_id: str | None = None
    wall_level: float = Field(..., gt=0)
    high: float = Field(..., gt=0)
    low: float = Field(..., gt=0)
    close: float = Field(..., gt=0)
    next_bar_open: float | None = Field(default=None, gt=0)
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


class XauAcceptanceState(XauAcceptanceResult):
    """Report-level candle acceptance state used by reaction reports."""


class XauReactionReportRequest(XauReactionBaseModel):
    """Request to create a research-only XAU reaction report from feature 006 output."""

    source_report_id: str
    current_price: float | None = Field(default=None, gt=0)
    current_timestamp: datetime | None = None
    freshness_input: XauIntradayFreshnessInput | None = None
    vol_regime_input: XauVolRegimeInput | None = None
    open_regime_input: XauOpenRegimeInput | None = None
    acceptance_inputs: list[XauAcceptanceInput] = Field(default_factory=list)
    event_risk_state: XauEventRiskState = XauEventRiskState.UNKNOWN
    max_total_risk_per_idea: float | None = Field(default=None, gt=0)
    max_recovery_legs: int = Field(default=0, ge=0)
    minimum_rr: float | None = Field(default=None, gt=0)
    wall_buffer_points: float = Field(default=0.0, ge=0)
    report_format: XauReactionReportFormat = XauReactionReportFormat.BOTH
    research_only_acknowledged: bool

    @field_validator("source_report_id")
    @classmethod
    def validate_source_report_id(cls, value: str) -> str:
        return validate_filesystem_safe_id(value, label="source_report_id")

    @model_validator(mode="after")
    def validate_research_acknowledgement(self) -> "XauReactionReportRequest":
        if not self.research_only_acknowledged:
            raise ValueError("research_only_acknowledged must be true")
        return self


class XauReactionRow(XauReactionBaseModel):
    """One deterministic reaction candidate or no-trade row."""

    reaction_id: str
    source_report_id: str
    wall_id: str | None = None
    zone_id: str | None = None
    reaction_label: XauReactionLabel
    confidence_label: XauConfidenceLabel
    explanation_notes: list[str] = Field(default_factory=list)
    no_trade_reasons: list[str] = Field(default_factory=list)
    invalidation_level: float | None = None
    target_level_1: float | None = None
    target_level_2: float | None = None
    next_wall_reference: str | None = None
    freshness_state: XauFreshnessResult
    vol_regime_state: XauVolRegimeResult
    open_regime_state: XauOpenRegimeResult
    acceptance_state: XauAcceptanceResult | None = None
    event_risk_state: XauEventRiskState = XauEventRiskState.UNKNOWN
    research_only_warning: str = XAU_REACTION_RESEARCH_ONLY_WARNING

    @field_validator("reaction_id", "source_report_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_filesystem_safe_id(value, label=info.field_name)

    @model_validator(mode="after")
    def validate_no_trade_reasons(self) -> "XauReactionRow":
        if self.reaction_label == XauReactionLabel.NO_TRADE and not self.no_trade_reasons:
            raise ValueError("NO_TRADE reactions require at least one no_trade_reason")
        return self


class XauRiskPlan(XauReactionBaseModel):
    """Bounded research-only risk-plan annotation linked to one reaction row."""

    plan_id: str
    reaction_id: str
    reaction_label: XauReactionLabel
    entry_condition_text: str | None = None
    invalidation_level: float | None = None
    stop_buffer_points: float | None = Field(default=None, ge=0)
    target_1: float | None = None
    target_2: float | None = None
    max_total_risk_per_idea: float | None = Field(default=None, gt=0)
    max_recovery_legs: int = Field(default=0, ge=0)
    minimum_rr: float | None = Field(default=None, gt=0)
    rr_state: XauRewardRiskState
    cancel_conditions: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)

    @field_validator("plan_id", "reaction_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_filesystem_safe_id(value, label=info.field_name)

    @model_validator(mode="after")
    def validate_no_trade_has_no_entry_plan(self) -> "XauRiskPlan":
        if self.reaction_label == XauReactionLabel.NO_TRADE and self.entry_condition_text:
            raise ValueError("NO_TRADE risk plans must not include entry_condition_text")
        return self


class XauReactionReportArtifact(XauReactionBaseModel):
    artifact_type: XauReactionArtifactType
    path: str
    format: XauReactionArtifactFormat
    rows: int | None = Field(default=None, ge=0)
    created_at: datetime


class XauReactionReport(XauReactionBaseModel):
    """Persisted research-only XAU reaction report metadata and rows."""

    report_id: str
    source_kind: str = "operational"
    source_report_id: str
    status: XauReactionReportStatus
    created_at: datetime
    session_date: date | None = None
    request: XauReactionReportRequest
    source_wall_count: int = Field(default=0, ge=0)
    source_zone_count: int = Field(default=0, ge=0)
    reaction_count: int = Field(default=0, ge=0)
    no_trade_count: int = Field(default=0, ge=0)
    risk_plan_count: int = Field(default=0, ge=0)
    freshness_state: XauFreshnessResult
    vol_regime_state: XauVolRegimeResult
    open_regime_state: XauOpenRegimeResult
    reactions: list[XauReactionRow] = Field(default_factory=list)
    risk_plans: list[XauRiskPlan] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    artifacts: list[XauReactionReportArtifact] = Field(default_factory=list)

    @field_validator("report_id", "source_report_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_filesystem_safe_id(value, label=info.field_name)


class XauReactionReportSummary(XauReactionBaseModel):
    report_id: str
    source_kind: str = "operational"
    source_report_id: str
    status: XauReactionReportStatus
    created_at: datetime
    session_date: date | None = None
    reaction_count: int = Field(default=0, ge=0)
    no_trade_count: int = Field(default=0, ge=0)
    risk_plan_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)

    @field_validator("report_id", "source_report_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_filesystem_safe_id(value, label=info.field_name)


class XauReactionReportListResponse(XauReactionBaseModel):
    reports: list[XauReactionReportSummary] = Field(default_factory=list)


class XauReactionTableResponse(XauReactionBaseModel):
    report_id: str
    data: list[XauReactionRow] = Field(default_factory=list)

    @field_validator("report_id")
    @classmethod
    def validate_report_id(cls, value: str) -> str:
        return validate_filesystem_safe_id(value)


class XauRiskPlanTableResponse(XauReactionBaseModel):
    report_id: str
    data: list[XauRiskPlan] = Field(default_factory=list)

    @field_validator("report_id")
    @classmethod
    def validate_report_id(cls, value: str) -> str:
        return validate_filesystem_safe_id(value)


def _validate_range(lower: float | None, upper: float | None, label: str) -> None:
    if (lower is None) != (upper is None):
        raise ValueError(f"{label}_lower and {label}_upper must be supplied together")
    if lower is not None and upper is not None and lower >= upper:
        raise ValueError(f"{label}_lower must be less than {label}_upper")


def validate_filesystem_safe_id(value: str, *, label: str = "report_id") -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must not be blank")
    if not SAFE_REPORT_ID_PATTERN.fullmatch(normalized):
        raise ValueError(f"{label} must be filesystem-safe")
    return normalized
