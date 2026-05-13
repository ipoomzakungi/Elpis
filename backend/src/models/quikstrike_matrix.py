import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from src.models.backtest import StrictModel, _normalize_guardrail_key

SAFE_QUIKSTRIKE_MATRIX_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
QUIKSTRIKE_MATRIX_RESEARCH_ONLY_WARNING = (
    "QuikStrike Matrix extraction outputs are local-only research artifacts, not execution inputs."
)

FORBIDDEN_QUIKSTRIKE_MATRIX_FIELDS = {
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

FORBIDDEN_QUIKSTRIKE_MATRIX_VALUE_PATTERNS = (
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"__VIEWSTATE", re.IGNORECASE),
    re.compile(r"__EVENTVALIDATION", re.IGNORECASE),
    re.compile(r"\bAuthorization\s*:", re.IGNORECASE),
    re.compile(r"\bCookie\s*:", re.IGNORECASE),
    re.compile(r"\bSet-Cookie\s*:", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
)


class QuikStrikeMatrixBaseModel(StrictModel):
    """Strict base model for local-only QuikStrike Matrix research schemas."""

    @model_validator(mode="before")
    @classmethod
    def reject_secret_session_fields(cls, value: Any) -> Any:
        ensure_no_forbidden_quikstrike_matrix_content(value)
        return value


class QuikStrikeMatrixViewType(StrEnum):
    OPEN_INTEREST_MATRIX = "open_interest_matrix"
    OI_CHANGE_MATRIX = "oi_change_matrix"
    VOLUME_MATRIX = "volume_matrix"


class QuikStrikeMatrixValueType(StrEnum):
    OPEN_INTEREST = "open_interest"
    OI_CHANGE = "oi_change"
    VOLUME = "volume"


class QuikStrikeMatrixOptionType(StrEnum):
    CALL = "call"
    PUT = "put"
    COMBINED = "combined"


class QuikStrikeMatrixExtractionStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"


class QuikStrikeMatrixConversionStatus(StrEnum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class QuikStrikeMatrixMappingStatus(StrEnum):
    VALID = "valid"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class QuikStrikeMatrixCellState(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    BLANK = "blank"
    INVALID = "invalid"


class QuikStrikeMatrixArtifactType(StrEnum):
    RAW_NORMALIZED_ROWS_JSON = "raw_normalized_rows_json"
    RAW_NORMALIZED_ROWS_PARQUET = "raw_normalized_rows_parquet"
    RAW_METADATA = "raw_metadata"
    PROCESSED_XAU_VOL_OI_CSV = "processed_xau_vol_oi_csv"
    PROCESSED_XAU_VOL_OI_PARQUET = "processed_xau_vol_oi_parquet"
    CONVERSION_METADATA = "conversion_metadata"
    REPORT_JSON = "report_json"
    REPORT_MARKDOWN = "report_markdown"


class QuikStrikeMatrixArtifactFormat(StrEnum):
    JSON = "json"
    CSV = "csv"
    PARQUET = "parquet"
    MARKDOWN = "markdown"


class QuikStrikeMatrixMetadata(QuikStrikeMatrixBaseModel):
    capture_timestamp: datetime | None = None
    product: str
    option_product_code: str
    futures_symbol: str | None = None
    source_menu: str = "OPEN INTEREST Matrix"
    selected_view_type: QuikStrikeMatrixViewType
    selected_view_label: str | None = None
    table_title: str | None = None
    raw_visible_text: str
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator(
        "product",
        "option_product_code",
        "futures_symbol",
        "source_menu",
        "selected_view_label",
        "table_title",
        "raw_visible_text",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).split())
        if not normalized:
            raise ValueError("QuikStrike Matrix text fields must not be blank")
        return normalized

    @field_validator("warnings", "limitations")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)

    @model_validator(mode="after")
    def validate_supported_gold_surface(self) -> "QuikStrikeMatrixMetadata":
        product_scope = f"{self.product} {self.option_product_code}".lower()
        if "gold" not in product_scope and "og|gc" not in product_scope:
            raise ValueError("QuikStrike Matrix metadata must describe Gold (OG|GC)")
        if "open interest" not in self.source_menu.lower():
            raise ValueError("QuikStrike Matrix metadata must describe OPEN INTEREST")
        return self


class QuikStrikeMatrixTableSnapshot(QuikStrikeMatrixBaseModel):
    view_type: QuikStrikeMatrixViewType
    html_table: str | None = None
    caption: str | None = None
    header_rows: list[list[str]] = Field(default_factory=list)
    body_rows: list[list[str]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("html_table", "caption")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).split())
        return normalized or None

    @field_validator("warnings", "limitations")
    @classmethod
    def normalize_table_lists(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)

    @model_validator(mode="after")
    def validate_table_source_present(self) -> "QuikStrikeMatrixTableSnapshot":
        if self.html_table is None and not (self.header_rows and self.body_rows):
            raise ValueError("matrix table snapshot requires html_table or row arrays")
        if self.html_table and _contains_forbidden_markup(self.html_table):
            raise ValueError(
                "matrix table snapshot must not contain scripts, forms, or hidden inputs"
            )
        return self


class QuikStrikeMatrixHeaderCell(QuikStrikeMatrixBaseModel):
    text: str
    column_index: int = Field(ge=0)
    row_index: int = Field(ge=0)
    colspan: int = Field(default=1, ge=1)
    rowspan: int = Field(default=1, ge=1)
    expiration: str | None = None
    dte: float | None = Field(default=None, ge=0)
    futures_symbol: str | None = None
    future_reference_price: float | None = Field(default=None, gt=0)
    option_type: QuikStrikeMatrixOptionType | None = None
    warnings: list[str] = Field(default_factory=list)

    @field_validator("text", "expiration", "futures_symbol")
    @classmethod
    def normalize_header_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).split())
        if not normalized and value is not None:
            return ""
        return normalized

    @field_validator("warnings")
    @classmethod
    def normalize_warnings(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)


class QuikStrikeMatrixBodyCell(QuikStrikeMatrixBaseModel):
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    strike: float | None = None
    row_label: str
    column_label: str
    raw_value: str | None = None
    numeric_value: float | None = None
    cell_state: QuikStrikeMatrixCellState
    option_type: QuikStrikeMatrixOptionType | None = None
    expiration: str | None = None
    dte: float | None = Field(default=None, ge=0)
    futures_symbol: str | None = None
    future_reference_price: float | None = Field(default=None, gt=0)

    @field_validator("row_label", "column_label", "raw_value", "expiration", "futures_symbol")
    @classmethod
    def normalize_body_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).split())
        return normalized or ""

    @model_validator(mode="after")
    def validate_cell_state_value(self) -> "QuikStrikeMatrixBodyCell":
        if self.cell_state == QuikStrikeMatrixCellState.AVAILABLE and self.numeric_value is None:
            raise ValueError("available matrix cells require numeric_value")
        if (
            self.cell_state != QuikStrikeMatrixCellState.AVAILABLE
            and self.numeric_value is not None
        ):
            raise ValueError("unavailable matrix cells must not include numeric_value")
        return self


class QuikStrikeMatrixMappingValidation(QuikStrikeMatrixBaseModel):
    status: QuikStrikeMatrixMappingStatus
    table_present: bool
    strike_rows_found: int = Field(ge=0)
    expiration_columns_found: int = Field(ge=0)
    option_side_mapping: str = "unknown"
    numeric_cell_count: int = Field(ge=0)
    unavailable_cell_count: int = Field(ge=0)
    duplicate_row_count: int = Field(ge=0)
    blocked_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("option_side_mapping")
    @classmethod
    def normalize_side_mapping(cls, value: str) -> str:
        normalized = " ".join(value.split())
        return normalized or "unknown"

    @field_validator("blocked_reasons", "warnings", "limitations")
    @classmethod
    def normalize_lists(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)

    @model_validator(mode="after")
    def validate_blocked_reasons(self) -> "QuikStrikeMatrixMappingValidation":
        if self.status == QuikStrikeMatrixMappingStatus.BLOCKED and not self.blocked_reasons:
            raise ValueError("blocked matrix mapping requires at least one blocked reason")
        return self


class QuikStrikeMatrixNormalizedRow(QuikStrikeMatrixBaseModel):
    row_id: str
    extraction_id: str
    capture_timestamp: datetime
    product: str
    option_product_code: str
    futures_symbol: str | None = None
    source_menu: str
    view_type: QuikStrikeMatrixViewType
    strike: float | None = None
    expiration: str | None = None
    dte: float | None = Field(default=None, ge=0)
    future_reference_price: float | None = Field(default=None, gt=0)
    option_type: QuikStrikeMatrixOptionType | None = None
    value: float | None = None
    value_type: QuikStrikeMatrixValueType
    cell_state: QuikStrikeMatrixCellState
    table_row_label: str
    table_column_label: str
    extraction_warnings: list[str] = Field(default_factory=list)
    extraction_limitations: list[str] = Field(default_factory=list)

    @field_validator("row_id", "extraction_id")
    @classmethod
    def validate_ids(cls, value: str) -> str:
        return validate_quikstrike_matrix_safe_id(value.replace(":", "_"))

    @field_validator(
        "product",
        "option_product_code",
        "futures_symbol",
        "source_menu",
        "expiration",
        "table_row_label",
        "table_column_label",
    )
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).split())
        if not normalized:
            raise ValueError("QuikStrike Matrix normalized row text fields must not be blank")
        return normalized

    @field_validator("extraction_warnings", "extraction_limitations")
    @classmethod
    def normalize_row_lists(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)

    @model_validator(mode="after")
    def validate_row_value_type_and_state(self) -> "QuikStrikeMatrixNormalizedRow":
        if self.value_type != value_type_for_matrix_view(self.view_type):
            raise ValueError("matrix normalized row value_type must match selected view")
        if self.cell_state == QuikStrikeMatrixCellState.AVAILABLE and self.value is None:
            raise ValueError("available matrix rows require value")
        if self.cell_state != QuikStrikeMatrixCellState.AVAILABLE and self.value is not None:
            raise ValueError("unavailable matrix rows must not include value")
        return self


class QuikStrikeMatrixArtifact(QuikStrikeMatrixBaseModel):
    artifact_type: QuikStrikeMatrixArtifactType
    path: str
    format: QuikStrikeMatrixArtifactFormat
    rows: int | None = Field(default=None, ge=0)
    created_at: datetime
    limitations: list[str] = Field(default_factory=list)

    @field_validator("path")
    @classmethod
    def validate_artifact_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip()
        allowed_prefixes = (
            "data/raw/quikstrike_matrix/",
            "data/processed/quikstrike_matrix/",
            "data/reports/quikstrike_matrix/",
        )
        if not normalized.startswith(allowed_prefixes):
            raise ValueError("QuikStrike Matrix artifact paths must stay under ignored local roots")
        if ".." in normalized.split("/"):
            raise ValueError("QuikStrike Matrix artifact paths must not include parent traversal")
        return normalized

    @field_validator("limitations")
    @classmethod
    def normalize_artifact_limitations(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)


class QuikStrikeMatrixExtractionRequest(QuikStrikeMatrixBaseModel):
    requested_views: list[QuikStrikeMatrixViewType]
    metadata_by_view: dict[QuikStrikeMatrixViewType, QuikStrikeMatrixMetadata]
    tables_by_view: dict[QuikStrikeMatrixViewType, QuikStrikeMatrixTableSnapshot]
    run_label: str | None = None
    persist_report: bool = True
    research_only_acknowledged: bool

    @field_validator("requested_views")
    @classmethod
    def normalize_requested_views(
        cls, values: list[QuikStrikeMatrixViewType]
    ) -> list[QuikStrikeMatrixViewType]:
        deduped = list(dict.fromkeys(values))
        if not deduped:
            raise ValueError("at least one QuikStrike Matrix view is required")
        return deduped

    @field_validator("run_label")
    @classmethod
    def validate_run_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_quikstrike_matrix_safe_id(value)

    @model_validator(mode="after")
    def validate_request_consistency(self) -> "QuikStrikeMatrixExtractionRequest":
        if not self.research_only_acknowledged:
            raise ValueError("research_only_acknowledged must be true")
        for view in self.requested_views:
            if view not in self.metadata_by_view:
                raise ValueError(f"missing metadata for requested view: {view}")
            if view not in self.tables_by_view:
                raise ValueError(f"missing table snapshot for requested view: {view}")
            if self.metadata_by_view[view].selected_view_type != view:
                raise ValueError(f"metadata view mismatch for requested view: {view}")
            if self.tables_by_view[view].view_type != view:
                raise ValueError(f"table snapshot view mismatch for requested view: {view}")
        return self


class QuikStrikeMatrixExtractionResult(QuikStrikeMatrixBaseModel):
    extraction_id: str
    status: QuikStrikeMatrixExtractionStatus
    created_at: datetime
    completed_at: datetime | None = None
    requested_views: list[QuikStrikeMatrixViewType] = Field(default_factory=list)
    completed_views: list[QuikStrikeMatrixViewType] = Field(default_factory=list)
    partial_views: list[QuikStrikeMatrixViewType] = Field(default_factory=list)
    missing_views: list[QuikStrikeMatrixViewType] = Field(default_factory=list)
    row_count: int = Field(ge=0)
    strike_count: int = Field(ge=0)
    expiration_count: int = Field(ge=0)
    unavailable_cell_count: int = Field(ge=0)
    mapping: QuikStrikeMatrixMappingValidation
    conversion_eligible: bool
    artifacts: list[QuikStrikeMatrixArtifact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    research_only_warnings: list[str] = Field(
        default_factory=lambda: [QUIKSTRIKE_MATRIX_RESEARCH_ONLY_WARNING]
    )

    @field_validator("extraction_id")
    @classmethod
    def validate_extraction_id(cls, value: str) -> str:
        return validate_quikstrike_matrix_safe_id(value)

    @field_validator("warnings", "limitations", "research_only_warnings")
    @classmethod
    def normalize_result_lists(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)

    @model_validator(mode="after")
    def validate_conversion_eligibility(self) -> "QuikStrikeMatrixExtractionResult":
        if (
            self.conversion_eligible
            and self.mapping.status == QuikStrikeMatrixMappingStatus.BLOCKED
        ):
            raise ValueError("conversion_eligible requires non-blocked matrix mapping")
        return self


class QuikStrikeMatrixXauVolOiRow(QuikStrikeMatrixBaseModel):
    timestamp: datetime
    expiry: str
    strike: float
    option_type: QuikStrikeMatrixOptionType
    open_interest: float | None = None
    oi_change: float | None = None
    volume: float | None = None
    source: str = "quikstrike_matrix_local"
    source_menu: str
    source_view: str
    source_extraction_id: str
    table_row_label: str
    table_column_label: str
    futures_symbol: str | None = None
    dte: float | None = Field(default=None, ge=0)
    underlying_futures_price: float | None = None
    limitations: list[str] = Field(default_factory=list)

    @field_validator(
        "expiry",
        "source",
        "source_menu",
        "source_view",
        "source_extraction_id",
        "table_row_label",
        "table_column_label",
        "futures_symbol",
    )
    @classmethod
    def normalize_source_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).split())
        if not normalized:
            raise ValueError("QuikStrike Matrix XAU source fields must not be blank")
        return normalized

    @field_validator("source_extraction_id")
    @classmethod
    def validate_source_extraction_id(cls, value: str) -> str:
        return validate_quikstrike_matrix_safe_id(value)

    @field_validator("limitations")
    @classmethod
    def normalize_xau_row_limitations(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)


class QuikStrikeMatrixConversionResult(QuikStrikeMatrixBaseModel):
    conversion_id: str
    extraction_id: str
    status: QuikStrikeMatrixConversionStatus
    row_count: int = Field(ge=0)
    output_artifacts: list[QuikStrikeMatrixArtifact] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("conversion_id", "extraction_id")
    @classmethod
    def validate_result_ids(cls, value: str) -> str:
        return validate_quikstrike_matrix_safe_id(value)

    @field_validator("blocked_reasons", "warnings", "limitations")
    @classmethod
    def normalize_conversion_lists(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)

    @model_validator(mode="after")
    def validate_blocked_reasons(self) -> "QuikStrikeMatrixConversionResult":
        if self.status == QuikStrikeMatrixConversionStatus.BLOCKED and not self.blocked_reasons:
            raise ValueError("blocked conversion requires at least one blocked reason")
        if self.status == QuikStrikeMatrixConversionStatus.COMPLETED and not self.output_artifacts:
            raise ValueError("completed conversion requires output artifacts")
        return self


class QuikStrikeMatrixExtractionReport(QuikStrikeMatrixBaseModel):
    extraction_id: str
    status: QuikStrikeMatrixExtractionStatus
    created_at: datetime
    completed_at: datetime | None = None
    request_summary: dict[str, Any] = Field(default_factory=dict)
    view_summaries: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = Field(ge=0)
    strike_count: int = Field(ge=0)
    expiration_count: int = Field(ge=0)
    unavailable_cell_count: int = Field(ge=0)
    mapping: QuikStrikeMatrixMappingValidation
    conversion_result: QuikStrikeMatrixConversionResult | None = None
    artifacts: list[QuikStrikeMatrixArtifact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    research_only_warnings: list[str] = Field(
        default_factory=lambda: [QUIKSTRIKE_MATRIX_RESEARCH_ONLY_WARNING]
    )

    @field_validator("extraction_id")
    @classmethod
    def validate_report_extraction_id(cls, value: str) -> str:
        return validate_quikstrike_matrix_safe_id(value)

    @field_validator("warnings", "limitations", "research_only_warnings")
    @classmethod
    def normalize_report_lists(cls, values: list[str]) -> list[str]:
        return _dedupe_nonblank_strings(values)


class QuikStrikeMatrixExtractionSummary(QuikStrikeMatrixBaseModel):
    extraction_id: str
    status: QuikStrikeMatrixExtractionStatus
    created_at: datetime
    completed_at: datetime | None = None
    requested_view_count: int = Field(ge=0)
    completed_view_count: int = Field(ge=0)
    missing_view_count: int = Field(ge=0)
    row_count: int = Field(ge=0)
    strike_count: int = Field(ge=0)
    expiration_count: int = Field(ge=0)
    unavailable_cell_count: int = Field(ge=0)
    conversion_eligible: bool
    conversion_status: QuikStrikeMatrixConversionStatus | None = None
    artifact_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    limitation_count: int = Field(ge=0)

    @field_validator("extraction_id")
    @classmethod
    def validate_summary_extraction_id(cls, value: str) -> str:
        return validate_quikstrike_matrix_safe_id(value)


class QuikStrikeMatrixExtractionListResponse(QuikStrikeMatrixBaseModel):
    extractions: list[QuikStrikeMatrixExtractionSummary] = Field(default_factory=list)


class QuikStrikeMatrixRowsResponse(QuikStrikeMatrixBaseModel):
    extraction_id: str
    rows: list[QuikStrikeMatrixNormalizedRow] = Field(default_factory=list)

    @field_validator("extraction_id")
    @classmethod
    def validate_rows_extraction_id(cls, value: str) -> str:
        return validate_quikstrike_matrix_safe_id(value)


class QuikStrikeMatrixConversionRowsResponse(QuikStrikeMatrixBaseModel):
    extraction_id: str
    conversion_result: QuikStrikeMatrixConversionResult | None = None
    rows: list[QuikStrikeMatrixXauVolOiRow] = Field(default_factory=list)

    @field_validator("extraction_id")
    @classmethod
    def validate_conversion_rows_extraction_id(cls, value: str) -> str:
        return validate_quikstrike_matrix_safe_id(value)


def value_type_for_matrix_view(
    view_type: QuikStrikeMatrixViewType | str,
) -> QuikStrikeMatrixValueType:
    normalized = QuikStrikeMatrixViewType(view_type)
    if normalized == QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX:
        return QuikStrikeMatrixValueType.OPEN_INTEREST
    if normalized == QuikStrikeMatrixViewType.OI_CHANGE_MATRIX:
        return QuikStrikeMatrixValueType.OI_CHANGE
    return QuikStrikeMatrixValueType.VOLUME


def validate_quikstrike_matrix_safe_id(value: str) -> str:
    normalized = value.strip()
    if not normalized or not SAFE_QUIKSTRIKE_MATRIX_ID_PATTERN.fullmatch(normalized):
        raise ValueError("QuikStrike Matrix ids must be filesystem-safe")
    return normalized


def ensure_no_forbidden_quikstrike_matrix_content(value: Any, prefix: str = "") -> None:
    matches = _forbidden_quikstrike_matrix_paths(value, prefix)
    if matches:
        fields = ", ".join(sorted(set(matches)))
        raise ValueError(
            "QuikStrike Matrix payloads must not include secret/session fields: "
            f"{fields}"
        )


def _forbidden_quikstrike_matrix_paths(value: Any, prefix: str = "") -> list[str]:
    matches: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            normalized_key = _normalize_guardrail_key(str(key))
            if normalized_key in FORBIDDEN_QUIKSTRIKE_MATRIX_FIELDS:
                matches.append(path)
            matches.extend(_forbidden_quikstrike_matrix_paths(item, path))
        return matches
    if isinstance(value, list):
        for index, item in enumerate(value):
            path = f"{prefix}.{index}" if prefix else str(index)
            matches.extend(_forbidden_quikstrike_matrix_paths(item, path))
        return matches
    if isinstance(value, str):
        for pattern in FORBIDDEN_QUIKSTRIKE_MATRIX_VALUE_PATTERNS:
            if pattern.search(value):
                matches.append(prefix or "<value>")
                break
    return matches


def _contains_forbidden_markup(value: str) -> bool:
    lowered = value.lower()
    forbidden_fragments = (
        "<script",
        "<form",
        "<input",
        "__viewstate",
        "__eventvalidation",
        "cookie",
        "authorization",
    )
    return any(fragment in lowered for fragment in forbidden_fragments)


def _dedupe_nonblank_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value).split())
        if normalized and normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)
    return deduped
