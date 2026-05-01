from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class XauBaseModel(BaseModel):
    """Strict base model for research-only XAU schemas."""

    model_config = ConfigDict(extra="forbid")


class XauReferenceType(StrEnum):
    SPOT = "spot"
    PROXY = "proxy"
    FUTURES = "futures"
    MANUAL = "manual"


class XauFreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class XauBasisSource(StrEnum):
    COMPUTED = "computed"
    MANUAL = "manual"
    UNAVAILABLE = "unavailable"


class XauTimestampAlignmentStatus(StrEnum):
    ALIGNED = "aligned"
    MISMATCHED = "mismatched"
    UNKNOWN = "unknown"


class XauOptionType(StrEnum):
    CALL = "call"
    PUT = "put"
    UNKNOWN = "unknown"


class XauVolatilitySource(StrEnum):
    IV = "iv"
    REALIZED_VOLATILITY = "realized_volatility"
    MANUAL = "manual"
    UNAVAILABLE = "unavailable"


class XauWallType(StrEnum):
    CALL = "call"
    PUT = "put"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class XauFreshnessFactorStatus(StrEnum):
    CONFIRMED = "confirmed"
    NEUTRAL = "neutral"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class XauZoneType(StrEnum):
    SUPPORT_CANDIDATE = "support_candidate"
    RESISTANCE_CANDIDATE = "resistance_candidate"
    PIN_RISK_ZONE = "pin_risk_zone"
    SQUEEZE_RISK_ZONE = "squeeze_risk_zone"
    BREAKOUT_CANDIDATE = "breakout_candidate"
    REVERSAL_CANDIDATE = "reversal_candidate"
    NO_TRADE_ZONE = "no_trade_zone"


class XauZoneConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNAVAILABLE = "unavailable"


class XauReportFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    BOTH = "both"


class XauReferencePrice(XauBaseModel):
    """Spot, proxy, futures, or manual price reference used in wall analysis."""

    source: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    price: float = Field(..., gt=0)
    timestamp: datetime | None = None
    reference_type: XauReferenceType
    freshness_status: XauFreshnessStatus = XauFreshnessStatus.UNKNOWN
    notes: list[str] = Field(default_factory=list)

    @field_validator("source", "symbol")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class XauBasisSnapshot(XauBaseModel):
    """Basis calculation and spot-equivalent mapping readiness."""

    basis: float | None = None
    basis_source: XauBasisSource
    futures_reference: XauReferencePrice | None = None
    spot_reference: XauReferencePrice | None = None
    timestamp_alignment_status: XauTimestampAlignmentStatus = XauTimestampAlignmentStatus.UNKNOWN
    mapping_available: bool
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_mapping_state(self) -> "XauBasisSnapshot":
        if self.mapping_available and self.basis is None:
            raise ValueError("basis is required when mapping_available is true")
        if not self.mapping_available and self.basis_source != XauBasisSource.UNAVAILABLE:
            raise ValueError("unavailable mapping requires basis_source='unavailable'")
        return self


class XauOptionsOiRow(XauBaseModel):
    """Normalized gold options open-interest source row."""

    source_row_id: str
    timestamp: datetime
    expiry: date
    days_to_expiry: int = Field(..., ge=0)
    strike: float = Field(..., gt=0)
    option_type: XauOptionType
    open_interest: float = Field(..., ge=0)
    oi_change: float | None = None
    volume: float | None = Field(default=None, ge=0)
    implied_volatility: float | None = Field(default=None, gt=0)
    underlying_futures_price: float | None = Field(default=None, gt=0)
    xauusd_spot_price: float | None = Field(default=None, gt=0)
    delta: float | None = None
    gamma: float | None = None
    validation_notes: list[str] = Field(default_factory=list)

    @field_validator("source_row_id")
    @classmethod
    def validate_source_row_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("source_row_id must not be blank")
        return normalized

    @field_validator("option_type", mode="before")
    @classmethod
    def normalize_option_type(cls, value: Any) -> Any:
        if isinstance(value, XauOptionType):
            return value
        normalized = str(value).strip().lower()
        if normalized in {"c", "call", "calls"}:
            return XauOptionType.CALL
        if normalized in {"p", "put", "puts"}:
            return XauOptionType.PUT
        return XauOptionType.UNKNOWN


class XauVolatilitySnapshot(XauBaseModel):
    """Available volatility or manually supplied expected-range inputs."""

    implied_volatility: float | None = Field(default=None, gt=0)
    realized_volatility: float | None = Field(default=None, gt=0)
    manual_expected_move: float | None = Field(default=None, gt=0)
    source: XauVolatilitySource = XauVolatilitySource.UNAVAILABLE
    days_to_expiry: int | None = Field(default=None, ge=0)
    notes: list[str] = Field(default_factory=list)


class XauExpectedRange(XauBaseModel):
    """Computed or unavailable expected range for a reference price."""

    source: XauVolatilitySource
    reference_price: float | None = Field(default=None, gt=0)
    expected_move: float | None = Field(default=None, ge=0)
    lower_1sd: float | None = None
    upper_1sd: float | None = None
    lower_2sd: float | None = None
    upper_2sd: float | None = None
    days_to_expiry: int | None = Field(default=None, ge=0)
    unavailable_reason: str | None = None
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_range_state(self) -> "XauExpectedRange":
        if self.source == XauVolatilitySource.UNAVAILABLE and not self.unavailable_reason:
            raise ValueError("unavailable_reason is required when source is unavailable")
        if self.source != XauVolatilitySource.UNAVAILABLE:
            required = [self.reference_price, self.expected_move, self.lower_1sd, self.upper_1sd]
            if any(value is None for value in required):
                raise ValueError("available ranges require reference_price and 1SD bounds")
        return self


class XauOiWall(XauBaseModel):
    """Basis-adjusted options OI wall row."""

    wall_id: str
    expiry: date
    strike: float = Field(..., gt=0)
    spot_equivalent_level: float | None = None
    basis: float | None = None
    option_type: XauWallType
    open_interest: float = Field(..., ge=0)
    total_expiry_open_interest: float = Field(..., gt=0)
    oi_share: float = Field(..., ge=0, le=1)
    expiry_weight: float = Field(..., ge=0)
    freshness_factor: float = Field(..., ge=0)
    wall_score: float = Field(..., ge=0)
    freshness_status: XauFreshnessFactorStatus
    notes: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class XauZone(XauBaseModel):
    """Classified research zone derived from XAU wall evidence."""

    zone_id: str
    zone_type: XauZoneType
    level: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    linked_wall_ids: list[str] = Field(default_factory=list)
    wall_score: float | None = Field(default=None, ge=0)
    pin_risk_score: float | None = Field(default=None, ge=0)
    squeeze_risk_score: float | None = Field(default=None, ge=0)
    confidence: XauZoneConfidence
    no_trade_warning: bool
    notes: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class XauVolOiReportRequest(XauBaseModel):
    """Request to run one local XAU volatility and OI wall report."""

    options_oi_file_path: Path
    session_date: date | None = None
    spot_reference: XauReferencePrice | None = None
    futures_reference: XauReferencePrice | None = None
    manual_basis: float | None = None
    volatility_snapshot: XauVolatilitySnapshot | None = None
    include_2sd_range: bool = False
    min_wall_score: float = Field(default=0.0, ge=0)
    report_format: XauReportFormat = XauReportFormat.BOTH

    @model_validator(mode="after")
    def validate_research_only_references(self) -> "XauVolOiReportRequest":
        if self.spot_reference and self.spot_reference.reference_type not in {
            XauReferenceType.SPOT,
            XauReferenceType.PROXY,
            XauReferenceType.MANUAL,
        }:
            raise ValueError("spot_reference must be spot, proxy, or manual")
        if self.futures_reference and self.futures_reference.reference_type not in {
            XauReferenceType.FUTURES,
            XauReferenceType.MANUAL,
        }:
            raise ValueError("futures_reference must be futures or manual")
        return self


class XauOptionsImportReport(XauBaseModel):
    """Validation outcome for a local gold options OI file."""

    file_path: str
    is_valid: bool
    source_row_count: int = Field(..., ge=0)
    accepted_row_count: int = Field(..., ge=0)
    rejected_row_count: int = Field(..., ge=0)
    required_columns_missing: list[str] = Field(default_factory=list)
    optional_columns_present: list[str] = Field(default_factory=list)
    timestamp_column: str | None = None
    rows: list[XauOptionsOiRow] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
