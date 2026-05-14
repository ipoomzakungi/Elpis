import re
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from src.models.backtest import StrictModel, _normalize_guardrail_key

SAFE_QUIKSTRIKE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
QUIKSTRIKE_RESEARCH_ONLY_WARNING = (
    "QuikStrike extraction outputs are local-only research artifacts, not execution inputs."
)

FORBIDDEN_QUIKSTRIKE_FIELDS = {
    "account",
    "accountid",
    "apikey",
    "apisecret",
    "authorization",
    "authorizationheader",
    "bearer",
    "broker",
    "browserprofile",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "endpointreplay",
    "eventvalidation",
    "fullurl",
    "har",
    "harfile",
    "header",
    "headers",
    "order",
    "orderid",
    "password",
    "private",
    "privatekey",
    "privateurl",
    "profilepath",
    "requestheader",
    "requestheaders",
    "responsebody",
    "screenshot",
    "screenshotpath",
    "secret",
    "secretkey",
    "session",
    "sessionid",
    "sessiontoken",
    "setcookie",
    "token",
    "url",
    "username",
    "viewstate",
    "wallet",
}

FORBIDDEN_QUIKSTRIKE_VALUE_PATTERNS = (
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"__VIEWSTATE", re.IGNORECASE),
    re.compile(r"__EVENTVALIDATION", re.IGNORECASE),
    re.compile(r"\bAuthorization\s*:", re.IGNORECASE),
    re.compile(r"\bCookie\s*:", re.IGNORECASE),
    re.compile(r"\bSet-Cookie\s*:", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
)


class QuikStrikeBaseModel(StrictModel):
    """Strict base model for local-only QuikStrike research schemas."""

    @model_validator(mode="before")
    @classmethod
    def reject_secret_session_fields(cls, value: Any) -> Any:
        ensure_no_forbidden_quikstrike_content(value)
        return value


class QuikStrikeViewType(StrEnum):
    INTRADAY_VOLUME = "intraday_volume"
    EOD_VOLUME = "eod_volume"
    OPEN_INTEREST = "open_interest"
    OI_CHANGE = "oi_change"
    CHURN = "churn"


class QuikStrikeSeriesType(StrEnum):
    PUT = "put"
    CALL = "call"
    VOL_SETTLE = "vol_settle"
    RANGES = "ranges"
    UNKNOWN = "unknown"


class QuikStrikeOptionType(StrEnum):
    PUT = "put"
    CALL = "call"


class QuikStrikeExtractionStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"


class QuikStrikeConversionStatus(StrEnum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class QuikStrikeStrikeMappingConfidence(StrEnum):
    HIGH = "high"
    PARTIAL = "partial"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


class QuikStrikeArtifactType(StrEnum):
    RAW_NORMALIZED_ROWS_JSON = "raw_normalized_rows_json"
    RAW_NORMALIZED_ROWS_PARQUET = "raw_normalized_rows_parquet"
    RAW_METADATA = "raw_metadata"
    PROCESSED_XAU_VOL_OI_CSV = "processed_xau_vol_oi_csv"
    PROCESSED_XAU_VOL_OI_PARQUET = "processed_xau_vol_oi_parquet"
    CONVERSION_METADATA = "conversion_metadata"
    REPORT_JSON = "report_json"
    REPORT_MARKDOWN = "report_markdown"


class QuikStrikeReportFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    BOTH = "both"


class QuikStrikeArtifactFormat(StrEnum):
    JSON = "json"
    CSV = "csv"
    PARQUET = "parquet"
    MARKDOWN = "markdown"


class QuikStrikeDomMetadata(QuikStrikeBaseModel):
    product: str
    option_product_code: str
    futures_symbol: str | None = None
    expiration: date | None = None
    expiration_code: str | None = None
    dte: float | None = Field(default=None, ge=0)
    future_reference_price: float | None = Field(default=None, gt=0)
    source_view: str = "QUIKOPTIONS VOL2VOL"
    selected_view_type: QuikStrikeViewType
    surface: str = "QUIKOPTIONS VOL2VOL"
    raw_header_text: str
    raw_selector_text: str | None = None
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator(
        "product",
        "option_product_code",
        "futures_symbol",
        "expiration_code",
        "source_view",
        "surface",
        "raw_header_text",
        "raw_selector_text",
        mode="before",
    )
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).split())
        if not normalized:
            raise ValueError("QuikStrike text fields must not be blank")
        return normalized

    @field_validator("warnings", "limitations")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)

    @model_validator(mode="after")
    def validate_supported_gold_surface(self) -> "QuikStrikeDomMetadata":
        product_scope = f"{self.product} {self.option_product_code}".lower()
        if "gold" not in product_scope and "og|gc" not in product_scope:
            raise ValueError("QuikStrike metadata must describe Gold (OG|GC)")
        if "quikoptions" not in self.surface.lower() or "vol2vol" not in self.surface.lower():
            raise ValueError("QuikStrike metadata must describe QUIKOPTIONS VOL2VOL")
        return self


class QuikStrikePoint(QuikStrikeBaseModel):
    series_type: QuikStrikeSeriesType
    x: float | None = None
    y: float | None = None
    x2: float | None = None
    name: str | None = None
    category: str | None = None
    strike_id: str | None = None
    range_label: str | None = None
    sigma_label: str | None = None
    metadata_keys: list[str] = Field(default_factory=list)

    @field_validator("name", "category", "strike_id", "range_label", "sigma_label")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).split())
        return normalized or None

    @field_validator("metadata_keys")
    @classmethod
    def normalize_metadata_keys(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)

    @model_validator(mode="after")
    def validate_required_numeric_points(self) -> "QuikStrikePoint":
        if self.series_type in {QuikStrikeSeriesType.PUT, QuikStrikeSeriesType.CALL}:
            if self.x is None or self.y is None:
                raise ValueError("Put/Call QuikStrike points require numeric x and y")
        return self


class QuikStrikeSeriesSnapshot(QuikStrikeBaseModel):
    series_name: str
    series_type: QuikStrikeSeriesType
    point_count: int = Field(ge=0)
    points: list[QuikStrikePoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("series_name")
    @classmethod
    def normalize_series_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("series_name must not be blank")
        return normalized

    @field_validator("warnings", "limitations")
    @classmethod
    def normalize_series_lists(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)


class QuikStrikeHighchartsSnapshot(QuikStrikeBaseModel):
    chart_title: str | None = None
    view_type: QuikStrikeViewType
    series: list[QuikStrikeSeriesSnapshot] = Field(default_factory=list)
    chart_warnings: list[str] = Field(default_factory=list)
    chart_limitations: list[str] = Field(default_factory=list)

    @field_validator("chart_title")
    @classmethod
    def normalize_chart_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator("chart_warnings", "chart_limitations")
    @classmethod
    def normalize_chart_lists(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)


class QuikStrikeStrikeMappingValidation(QuikStrikeBaseModel):
    confidence: QuikStrikeStrikeMappingConfidence
    method: str
    matched_point_count: int = Field(ge=0)
    unmatched_point_count: int = Field(ge=0)
    conflict_count: int = Field(ge=0)
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("strike mapping method must not be blank")
        return normalized

    @field_validator("evidence", "warnings", "limitations")
    @classmethod
    def normalize_mapping_lists(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)


class QuikStrikeArtifact(QuikStrikeBaseModel):
    artifact_type: QuikStrikeArtifactType
    path: str
    format: QuikStrikeArtifactFormat
    rows: int | None = Field(default=None, ge=0)
    created_at: datetime
    limitations: list[str] = Field(default_factory=list)

    @field_validator("path")
    @classmethod
    def validate_artifact_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip()
        allowed_prefixes = (
            "data/raw/quikstrike/",
            "data/processed/quikstrike/",
            "data/reports/quikstrike/",
        )
        if not normalized.startswith(allowed_prefixes):
            raise ValueError("QuikStrike artifact paths must stay under ignored local roots")
        if ".." in normalized.split("/"):
            raise ValueError("QuikStrike artifact paths must not include parent traversal")
        return normalized

    @field_validator("limitations")
    @classmethod
    def normalize_artifact_limitations(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)


class QuikStrikeExtractionRequest(QuikStrikeBaseModel):
    requested_views: list[QuikStrikeViewType]
    dom_metadata_by_view: dict[QuikStrikeViewType, QuikStrikeDomMetadata]
    highcharts_by_view: dict[QuikStrikeViewType, QuikStrikeHighchartsSnapshot]
    run_label: str | None = None
    report_format: QuikStrikeReportFormat = QuikStrikeReportFormat.BOTH
    research_only_acknowledged: bool

    @field_validator("requested_views")
    @classmethod
    def normalize_requested_views(
        cls, values: list[QuikStrikeViewType]
    ) -> list[QuikStrikeViewType]:
        deduped = list(dict.fromkeys(values))
        if not deduped:
            raise ValueError("at least one QuikStrike view is required")
        return deduped

    @field_validator("run_label")
    @classmethod
    def validate_run_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_quikstrike_safe_id(value)

    @model_validator(mode="after")
    def validate_request_consistency(self) -> "QuikStrikeExtractionRequest":
        if not self.research_only_acknowledged:
            raise ValueError("research_only_acknowledged must be true")
        for view in self.requested_views:
            if view not in self.dom_metadata_by_view:
                raise ValueError(f"missing DOM metadata for requested view: {view}")
            if view not in self.highcharts_by_view:
                raise ValueError(f"missing Highcharts snapshot for requested view: {view}")
            if self.dom_metadata_by_view[view].selected_view_type != view:
                raise ValueError(f"DOM metadata view mismatch for requested view: {view}")
            if self.highcharts_by_view[view].view_type != view:
                raise ValueError(f"Highcharts view mismatch for requested view: {view}")
        return self


class QuikStrikeNormalizedRow(QuikStrikeBaseModel):
    row_id: str
    extraction_id: str
    capture_timestamp: datetime
    product: str
    option_product_code: str
    futures_symbol: str | None = None
    expiration: date | None = None
    expiration_code: str | None = None
    dte: float | None = Field(default=None, ge=0)
    future_reference_price: float | None = Field(default=None, gt=0)
    view_type: QuikStrikeViewType
    strike: float
    strike_id: str | None = None
    option_type: QuikStrikeOptionType
    value: float
    value_type: str
    vol_settle: float | None = None
    range_label: str | None = None
    sigma_label: str | None = None
    source_view: str
    strike_mapping_confidence: QuikStrikeStrikeMappingConfidence
    extraction_warnings: list[str] = Field(default_factory=list)
    extraction_limitations: list[str] = Field(default_factory=list)

    @field_validator("row_id", "extraction_id")
    @classmethod
    def validate_ids(cls, value: str) -> str:
        return validate_quikstrike_safe_id(value.replace(":", "_"))

    @field_validator(
        "product",
        "option_product_code",
        "futures_symbol",
        "expiration_code",
        "strike_id",
        "value_type",
        "range_label",
        "sigma_label",
        "source_view",
    )
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).split())
        if not normalized:
            raise ValueError("QuikStrike normalized row text fields must not be blank")
        return normalized

    @field_validator("extraction_warnings", "extraction_limitations")
    @classmethod
    def normalize_row_lists(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)

    @model_validator(mode="after")
    def validate_value_type_matches_view(self) -> "QuikStrikeNormalizedRow":
        expected_value_type = value_type_for_view(self.view_type)
        if self.value_type != expected_value_type:
            raise ValueError(
                "QuikStrike normalized row value_type must match selected view type"
            )
        return self


class QuikStrikeXauVolOiRow(QuikStrikeBaseModel):
    timestamp: datetime
    expiry: date | None = None
    expiration_code: str | None = None
    strike: float
    option_type: QuikStrikeOptionType
    open_interest: float | None = None
    oi_change: float | None = None
    volume: float | None = None
    intraday_volume: float | None = None
    eod_volume: float | None = None
    churn: float | None = None
    implied_volatility: float | None = None
    underlying_futures_price: float | None = None
    dte: float | None = Field(default=None, ge=0)
    source: str = "quikstrike_highcharts_local"
    source_view: str
    source_extraction_id: str
    limitations: list[str] = Field(default_factory=list)

    @field_validator("expiration_code", "source", "source_view", "source_extraction_id")
    @classmethod
    def normalize_source_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).split())
        if not normalized:
            raise ValueError("QuikStrike XAU Vol-OI source fields must not be blank")
        return normalized

    @field_validator("source_extraction_id")
    @classmethod
    def validate_source_extraction_id(cls, value: str) -> str:
        return validate_quikstrike_safe_id(value)

    @field_validator("limitations")
    @classmethod
    def normalize_xau_row_limitations(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)

    @model_validator(mode="after")
    def validate_expiration_reference(self) -> "QuikStrikeXauVolOiRow":
        if self.expiry is None and self.expiration_code is None:
            raise ValueError("QuikStrike XAU Vol-OI rows require expiry or expiration_code")
        return self


class QuikStrikeExtractionResult(QuikStrikeBaseModel):
    extraction_id: str
    status: QuikStrikeExtractionStatus
    created_at: datetime
    completed_at: datetime | None = None
    requested_views: list[QuikStrikeViewType] = Field(default_factory=list)
    completed_views: list[QuikStrikeViewType] = Field(default_factory=list)
    partial_views: list[QuikStrikeViewType] = Field(default_factory=list)
    missing_views: list[QuikStrikeViewType] = Field(default_factory=list)
    row_count: int = Field(ge=0)
    put_row_count: int = Field(ge=0)
    call_row_count: int = Field(ge=0)
    strike_mapping: QuikStrikeStrikeMappingValidation
    conversion_eligible: bool
    artifacts: list[QuikStrikeArtifact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    research_only_warnings: list[str] = Field(
        default_factory=lambda: [QUIKSTRIKE_RESEARCH_ONLY_WARNING]
    )

    @field_validator("extraction_id")
    @classmethod
    def validate_extraction_id(cls, value: str) -> str:
        return validate_quikstrike_safe_id(value)

    @field_validator("warnings", "limitations", "research_only_warnings")
    @classmethod
    def normalize_result_lists(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)

    @model_validator(mode="after")
    def validate_conversion_eligibility(self) -> "QuikStrikeExtractionResult":
        if (
            self.conversion_eligible
            and self.strike_mapping.confidence
            not in {
                QuikStrikeStrikeMappingConfidence.HIGH,
                QuikStrikeStrikeMappingConfidence.PARTIAL,
            }
        ):
            raise ValueError(
                "conversion_eligible requires high or acceptable partial strike mapping"
            )
        return self


class QuikStrikeConversionResult(QuikStrikeBaseModel):
    conversion_id: str
    extraction_id: str
    status: QuikStrikeConversionStatus
    row_count: int = Field(ge=0)
    output_artifacts: list[QuikStrikeArtifact] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("conversion_id", "extraction_id")
    @classmethod
    def validate_result_ids(cls, value: str) -> str:
        return validate_quikstrike_safe_id(value)

    @field_validator("blocked_reasons", "warnings", "limitations")
    @classmethod
    def normalize_conversion_lists(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)

    @model_validator(mode="after")
    def validate_blocked_reasons(self) -> "QuikStrikeConversionResult":
        if self.status == QuikStrikeConversionStatus.BLOCKED and not self.blocked_reasons:
            raise ValueError("blocked conversion requires at least one blocked reason")
        if self.status == QuikStrikeConversionStatus.COMPLETED and not self.output_artifacts:
            raise ValueError("completed conversion requires output artifacts")
        return self


class QuikStrikeExtractionReport(QuikStrikeBaseModel):
    extraction_id: str
    source_kind: str = "operational"
    status: QuikStrikeExtractionStatus
    created_at: datetime
    completed_at: datetime | None = None
    request_summary: dict[str, Any] = Field(default_factory=dict)
    view_summaries: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = Field(ge=0)
    strike_mapping: QuikStrikeStrikeMappingValidation
    conversion_result: QuikStrikeConversionResult | None = None
    artifacts: list[QuikStrikeArtifact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    research_only_warnings: list[str] = Field(
        default_factory=lambda: [QUIKSTRIKE_RESEARCH_ONLY_WARNING]
    )

    @field_validator("extraction_id")
    @classmethod
    def validate_report_extraction_id(cls, value: str) -> str:
        return validate_quikstrike_safe_id(value)

    @field_validator("warnings", "limitations", "research_only_warnings")
    @classmethod
    def normalize_report_lists(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)


class QuikStrikeExtractionSummary(QuikStrikeBaseModel):
    extraction_id: str
    source_kind: str = "operational"
    status: QuikStrikeExtractionStatus
    created_at: datetime
    completed_at: datetime | None = None
    requested_view_count: int = Field(ge=0)
    completed_view_count: int = Field(ge=0)
    missing_view_count: int = Field(ge=0)
    row_count: int = Field(ge=0)
    strike_mapping_confidence: QuikStrikeStrikeMappingConfidence
    conversion_eligible: bool
    conversion_status: QuikStrikeConversionStatus | None = None
    artifact_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    limitation_count: int = Field(ge=0)

    @field_validator("extraction_id")
    @classmethod
    def validate_summary_extraction_id(cls, value: str) -> str:
        return validate_quikstrike_safe_id(value)


class QuikStrikeExtractionListResponse(QuikStrikeBaseModel):
    extractions: list[QuikStrikeExtractionSummary] = Field(default_factory=list)


class QuikStrikeRowsResponse(QuikStrikeBaseModel):
    extraction_id: str
    rows: list[QuikStrikeNormalizedRow] = Field(default_factory=list)

    @field_validator("extraction_id")
    @classmethod
    def validate_rows_extraction_id(cls, value: str) -> str:
        return validate_quikstrike_safe_id(value)


class QuikStrikeConversionRowsResponse(QuikStrikeBaseModel):
    extraction_id: str
    conversion_result: QuikStrikeConversionResult | None = None
    rows: list[QuikStrikeXauVolOiRow] = Field(default_factory=list)

    @field_validator("extraction_id")
    @classmethod
    def validate_conversion_rows_extraction_id(cls, value: str) -> str:
        return validate_quikstrike_safe_id(value)


def value_type_for_view(view_type: QuikStrikeViewType | str) -> str:
    normalized = QuikStrikeViewType(view_type)
    return normalized.value


def validate_quikstrike_safe_id(value: str) -> str:
    normalized = value.strip()
    if not normalized or not SAFE_QUIKSTRIKE_ID_PATTERN.fullmatch(normalized):
        raise ValueError("QuikStrike ids must be filesystem-safe")
    return normalized


def ensure_no_forbidden_quikstrike_content(value: Any, prefix: str = "") -> None:
    matches = _forbidden_quikstrike_paths(value, prefix)
    if matches:
        fields = ", ".join(sorted(set(matches)))
        raise ValueError(
            "QuikStrike extraction payloads must not include secret/session fields: "
            f"{fields}"
        )


def _forbidden_quikstrike_paths(value: Any, prefix: str = "") -> list[str]:
    matches: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            normalized_key = _normalize_guardrail_key(str(key))
            if normalized_key in FORBIDDEN_QUIKSTRIKE_FIELDS:
                matches.append(path)
            matches.extend(_forbidden_quikstrike_paths(item, path))
        return matches
    if isinstance(value, list):
        for index, item in enumerate(value):
            path = f"{prefix}.{index}" if prefix else str(index)
            matches.extend(_forbidden_quikstrike_paths(item, path))
        return matches
    if isinstance(value, str):
        for pattern in FORBIDDEN_QUIKSTRIKE_VALUE_PATTERNS:
            if pattern.search(value):
                matches.append(prefix or "<value>")
                break
    return matches


def _dedupe_nonblank_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value).split())
        if normalized and normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)
    return deduped
