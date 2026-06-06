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
    CME_NATIVE = "cme_native"
    DERIVED_FROM_IV = "derived_from_iv"
    UNAVAILABLE = "unavailable"


class XauExpectedRangeSource(StrEnum):
    CME_NATIVE = "cme_native"
    DERIVED_FROM_IV = "derived_from_iv"
    UNAVAILABLE = "unavailable"


class XauExpectedRangeExtractionQuality(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class XauExpectedRangeSourceStatus(StrEnum):
    PRELIMINARY = "preliminary"
    FINAL = "final"
    UNKNOWN = "unknown"


class XauDailyStructuralMapReadiness(StrEnum):
    STRUCTURAL_MAP_READY = "structural_map_ready"
    PARTIAL_MISSING_BASIS = "partial_missing_basis"
    PARTIAL_MISSING_EXPECTED_RANGE = "partial_missing_expected_range"
    PARTIAL_MISSING_SESSION_OPEN = "partial_missing_session_open"
    BLOCKED_INSUFFICIENT_CONTEXT = "blocked_insufficient_context"


class XauDailyStructuralMapWallMappingStatus(StrEnum):
    MAPPED = "mapped"
    BASIS_UNAVAILABLE = "basis_unavailable"
    RANGE_UNAVAILABLE = "range_unavailable"
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


class XauReportStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class XauArtifactType(StrEnum):
    METADATA = "metadata"
    SOURCE_VALIDATION = "source_validation"
    REPORT_JSON = "report_json"
    REPORT_MARKDOWN = "report_markdown"
    WALLS = "walls"
    ZONES = "zones"


class XauArtifactFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    PARQUET = "parquet"


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
    report_level_iv: float | None = Field(default=None, gt=0)
    fractional_dte: float | None = Field(default=None, ge=0)
    expected_move: float | None = Field(default=None, ge=0)
    cme_numeric_1sd: float | None = Field(default=None, ge=0)
    cme_numeric_2sd: float | None = Field(default=None, ge=0)
    cme_numeric_3sd: float | None = Field(default=None, ge=0)
    lower_1sd: float | None = None
    upper_1sd: float | None = None
    lower_2sd: float | None = None
    upper_2sd: float | None = None
    lower_3sd: float | None = None
    upper_3sd: float | None = None
    days_to_expiry: int | None = Field(default=None, ge=0)
    range_source: XauExpectedRangeSource | None = None
    extraction_quality: XauExpectedRangeExtractionQuality | None = None
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


class XauExpectedRangeSnapshot(XauBaseModel):
    """Point-in-time CME expected-range context for XAU/GC research."""

    source_report_id: str
    source_view: str
    capture_timestamp: datetime
    official_release_ts: datetime | None = None
    source_status: XauExpectedRangeSourceStatus = XauExpectedRangeSourceStatus.UNKNOWN
    product: str
    option_product_code: str
    futures_symbol: str | None = None
    expiration_code: str | None = None
    expiry_date: date | None = None
    reference_futures_price: float | None = Field(default=None, gt=0)
    report_level_iv: float | None = Field(default=None, gt=0)
    vol_settle: float | None = Field(default=None, gt=0)
    fractional_dte: float | None = Field(default=None, ge=0)
    cme_numeric_1sd: float | None = Field(default=None, ge=0)
    cme_numeric_2sd: float | None = Field(default=None, ge=0)
    cme_numeric_3sd: float | None = Field(default=None, ge=0)
    upper_1sd: float | None = None
    lower_1sd: float | None = None
    upper_2sd: float | None = None
    lower_2sd: float | None = None
    upper_3sd: float | None = None
    lower_3sd: float | None = None
    range_source: XauExpectedRangeSource
    extraction_quality: XauExpectedRangeExtractionQuality
    limitations: list[str] = Field(default_factory=list)

    @field_validator(
        "source_report_id",
        "source_view",
        "product",
        "option_product_code",
        "futures_symbol",
        "expiration_code",
    )
    @classmethod
    def normalize_snapshot_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).split())
        if not normalized:
            raise ValueError("expected-range snapshot text fields must not be blank")
        return normalized

    @field_validator("limitations")
    @classmethod
    def normalize_limitations(cls, values: list[str]) -> list[str]:
        return _dedupe_strings(values)

    @model_validator(mode="after")
    def validate_range_state(self) -> "XauExpectedRangeSnapshot":
        native_fields = [
            self.cme_numeric_1sd,
            self.cme_numeric_2sd,
            self.cme_numeric_3sd,
            self.upper_1sd,
            self.lower_1sd,
            self.upper_2sd,
            self.lower_2sd,
            self.upper_3sd,
            self.lower_3sd,
        ]
        if self.range_source == XauExpectedRangeSource.CME_NATIVE and any(
            value is None for value in native_fields
        ):
            raise ValueError("CME-native expected range requires numeric 1SD/2SD/3SD bands")
        if self.range_source == XauExpectedRangeSource.DERIVED_FROM_IV:
            required = [
                self.reference_futures_price,
                self.report_level_iv,
                self.fractional_dte,
                *native_fields,
            ]
            if any(value is None for value in required):
                raise ValueError("IV-derived expected range requires reference, IV, DTE, and bands")
        if (
            self.range_source == XauExpectedRangeSource.UNAVAILABLE
            and not self.limitations
        ):
            raise ValueError("unavailable expected range requires a limitation")
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


class XauDailyStructuralMapRange(XauBaseModel):
    """Expected-range context carried into one daily structural map."""

    expected_range_source: XauExpectedRangeSource | None = None
    report_level_iv: float | None = Field(default=None, gt=0)
    fractional_dte: float | None = Field(default=None, ge=0)
    lower_1sd: float | None = None
    upper_1sd: float | None = None
    lower_2sd: float | None = None
    upper_2sd: float | None = None
    lower_3sd: float | None = None
    upper_3sd: float | None = None
    limitations: list[str] = Field(default_factory=list)

    @field_validator("limitations")
    @classmethod
    def normalize_limitations(cls, values: list[str]) -> list[str]:
        return _dedupe_strings(values)


class XauDailyStructuralMapBasis(XauBaseModel):
    """Basis context used to map CME futures strikes to the traded chart."""

    basis: float | None = None
    basis_source: XauBasisSource
    basis_mapping_available: bool
    basis_timestamp_alignment_status: XauTimestampAlignmentStatus = (
        XauTimestampAlignmentStatus.UNKNOWN
    )
    limitations: list[str] = Field(default_factory=list)

    @field_validator("limitations")
    @classmethod
    def normalize_limitations(cls, values: list[str]) -> list[str]:
        return _dedupe_strings(values)

    @model_validator(mode="after")
    def validate_mapping_state(self) -> "XauDailyStructuralMapBasis":
        if self.basis_mapping_available and self.basis is None:
            raise ValueError("basis is required when basis_mapping_available is true")
        if (
            not self.basis_mapping_available
            and self.basis_source != XauBasisSource.UNAVAILABLE
        ):
            raise ValueError("unavailable basis mapping requires basis_source='unavailable'")
        return self


class XauDailyStructuralMapWall(XauBaseModel):
    """One XAU structural-map wall row enriched with map-only annotations."""

    wall_id: str
    expiry: date
    expiration_code: str | None = None
    strike: float = Field(..., gt=0)
    wall_type: XauWallType
    open_interest: float = Field(..., ge=0)
    oi_change: float | None = None
    volume: float | None = Field(default=None, ge=0)
    wall_score: float = Field(..., ge=0)
    freshness_state: XauFreshnessFactorStatus
    spot_equivalent_level: float | None = Field(default=None, gt=0)
    distance_to_traded_price: float | None = None
    distance_to_session_open: float | None = None
    inside_1sd: bool | None = None
    inside_2sd: bool | None = None
    near_expected_range_boundary: bool | None = None
    open_side_vs_wall: str | None = None
    mapping_status: XauDailyStructuralMapWallMappingStatus
    limitations: list[str] = Field(default_factory=list)

    @field_validator("wall_id")
    @classmethod
    def normalize_wall_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("wall_id must not be blank")
        return normalized

    @field_validator("expiration_code", "open_side_vs_wall")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator("limitations")
    @classmethod
    def normalize_limitations(cls, values: list[str]) -> list[str]:
        return _dedupe_strings(values)

    @model_validator(mode="after")
    def validate_mapping_status(self) -> "XauDailyStructuralMapWall":
        if (
            self.mapping_status == XauDailyStructuralMapWallMappingStatus.MAPPED
            and self.spot_equivalent_level is None
        ):
            raise ValueError("mapped structural-map walls require spot_equivalent_level")
        if (
            self.spot_equivalent_level is None
            and self.distance_to_traded_price is not None
        ):
            raise ValueError("distance_to_traded_price requires spot_equivalent_level")
        if (
            self.spot_equivalent_level is None
            and self.distance_to_session_open is not None
        ):
            raise ValueError("distance_to_session_open requires spot_equivalent_level")
        return self


class XauDailyStructuralMap(XauBaseModel):
    """One research-only daily map of expected range, basis, walls, and readiness."""

    map_id: str
    session_date: date
    created_at: datetime
    source_product: str
    option_product_code: str | None = None
    futures_symbol: str | None = None
    expiration_code: str | None = None
    expiry_date: date | None = None
    reference_futures_price: float | None = Field(default=None, gt=0)
    traded_instrument: str
    traded_reference_price: float | None = Field(default=None, gt=0)
    basis: float | None = None
    basis_source: XauBasisSource
    basis_mapping_available: bool
    basis_timestamp_alignment_status: XauTimestampAlignmentStatus = (
        XauTimestampAlignmentStatus.UNKNOWN
    )
    expected_range_source: XauExpectedRangeSource | None = None
    report_level_iv: float | None = Field(default=None, gt=0)
    fractional_dte: float | None = Field(default=None, ge=0)
    lower_1sd: float | None = None
    upper_1sd: float | None = None
    lower_2sd: float | None = None
    upper_2sd: float | None = None
    lower_3sd: float | None = None
    upper_3sd: float | None = None
    session_open_price: float | None = Field(default=None, gt=0)
    session_open_source: str | None = None
    session_open_available: bool
    open_side_vs_1sd: str | None = None
    open_distance_points: float | None = None
    wall_count: int = Field(ge=0)
    walls: list[XauDailyStructuralMapWall] = Field(default_factory=list)
    data_quality_state: XauDailyStructuralMapReadiness
    signal_allowed: bool = False
    no_signal_reasons: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("map_id", "source_product", "traded_instrument")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("structural-map text fields must not be blank")
        return normalized

    @field_validator(
        "option_product_code",
        "futures_symbol",
        "expiration_code",
        "session_open_source",
        "open_side_vs_1sd",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator("no_signal_reasons", "limitations")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        return _dedupe_strings(values)

    @model_validator(mode="after")
    def validate_map_state(self) -> "XauDailyStructuralMap":
        if self.wall_count != len(self.walls):
            raise ValueError("wall_count must match walls length")
        if self.signal_allowed:
            raise ValueError("Feature 018 structural maps cannot enable signals")
        if not self.no_signal_reasons:
            raise ValueError("structural maps require at least one no_signal_reason")
        if self.basis_mapping_available and self.basis is None:
            raise ValueError("basis is required when basis_mapping_available is true")
        if (
            not self.basis_mapping_available
            and self.basis_source != XauBasisSource.UNAVAILABLE
        ):
            raise ValueError("unavailable basis mapping requires basis_source='unavailable'")
        if self.session_open_available and self.session_open_price is None:
            raise ValueError("session_open_price is required when session_open_available is true")
        if not self.session_open_available and self.session_open_price is not None:
            raise ValueError("session_open_price requires session_open_available")
        return self


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


class XauReportArtifact(XauBaseModel):
    """Persisted XAU report artifact reference."""

    artifact_type: XauArtifactType
    path: str
    format: XauArtifactFormat
    rows: int | None = Field(default=None, ge=0)
    created_at: datetime


class XauVolOiReport(XauBaseModel):
    """Persisted XAU Vol-OI report metadata."""

    report_id: str
    source_kind: str = "operational"
    status: XauReportStatus
    created_at: datetime
    session_date: date | None = None
    request: XauVolOiReportRequest
    source_validation: XauOptionsImportReport
    basis_snapshot: XauBasisSnapshot | None = None
    expected_range: XauExpectedRange | None = None
    expected_range_snapshot: XauExpectedRangeSnapshot | None = None
    source_row_count: int = Field(..., ge=0)
    accepted_row_count: int = Field(..., ge=0)
    rejected_row_count: int = Field(..., ge=0)
    wall_count: int = Field(default=0, ge=0)
    zone_count: int = Field(default=0, ge=0)
    walls: list[XauOiWall] = Field(default_factory=list)
    zones: list[XauZone] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    missing_data_instructions: list[str] = Field(default_factory=list)
    artifacts: list[XauReportArtifact] = Field(default_factory=list)


class XauVolOiReportSummary(XauBaseModel):
    """List row for saved XAU Vol-OI reports."""

    report_id: str
    source_kind: str = "operational"
    status: XauReportStatus
    created_at: datetime
    session_date: date | None = None
    source_row_count: int = Field(..., ge=0)
    wall_count: int = Field(..., ge=0)
    zone_count: int = Field(..., ge=0)
    warning_count: int = Field(..., ge=0)


class XauVolOiReportListResponse(XauBaseModel):
    reports: list[XauVolOiReportSummary] = Field(default_factory=list)


class XauWallTableResponse(XauBaseModel):
    report_id: str
    data: list[XauOiWall] = Field(default_factory=list)


class XauZoneTableResponse(XauBaseModel):
    report_id: str
    data: list[XauZone] = Field(default_factory=list)


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value).split())
        if normalized and normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)
    return deduped
