import re
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from src.models.backtest import StrictModel, _normalize_guardrail_key

SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
SAFE_DERIBIT_UNDERLYING_PATTERN = re.compile(r"^[A-Z0-9_-]{2,20}$")
MIN_REASONABLE_CFTC_YEAR = 1986
MAX_REASONABLE_CFTC_YEAR = 2100

FORBIDDEN_FREE_DERIVATIVES_FIELDS = {
    "account",
    "accountid",
    "apikey",
    "apisecret",
    "broker",
    "credential",
    "credentials",
    "execution",
    "live",
    "livetrading",
    "order",
    "orderid",
    "ordertype",
    "paidkey",
    "paidvendorkey",
    "private",
    "privatekey",
    "secret",
    "secretkey",
    "shadowtrading",
    "wallet",
    "walletaddress",
}


class FreeDerivativesBaseModel(StrictModel):
    """Strict base model for research-only free derivatives schemas."""

    @model_validator(mode="before")
    @classmethod
    def reject_credential_fields(cls, value: Any) -> Any:
        ensure_no_forbidden_request_fields(value)
        return value


class FreeDerivativesSource(StrEnum):
    CFTC_COT = "cftc_cot"
    GVZ = "gvz"
    DERIBIT_PUBLIC_OPTIONS = "deribit_public_options"


class FreeDerivativesRunStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"


class FreeDerivativesSourceStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    FAILED = "failed"


class FreeDerivativesArtifactType(StrEnum):
    RAW_CFTC = "raw_cftc"
    PROCESSED_CFTC = "processed_cftc"
    RAW_GVZ = "raw_gvz"
    PROCESSED_GVZ = "processed_gvz"
    RAW_DERIBIT_INSTRUMENTS = "raw_deribit_instruments"
    RAW_DERIBIT_SUMMARY = "raw_deribit_summary"
    PROCESSED_DERIBIT_OPTIONS = "processed_deribit_options"
    PROCESSED_DERIBIT_WALLS = "processed_deribit_walls"
    RUN_METADATA = "run_metadata"
    RUN_JSON = "run_json"
    RUN_MARKDOWN = "run_markdown"


class FreeDerivativesArtifactFormat(StrEnum):
    JSON = "json"
    CSV = "csv"
    PARQUET = "parquet"
    MARKDOWN = "markdown"
    ZIP = "zip"


class FreeDerivativesReportFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    BOTH = "both"


class CftcCotReportCategory(StrEnum):
    FUTURES_ONLY = "futures_only"
    FUTURES_AND_OPTIONS_COMBINED = "futures_and_options_combined"


class DeribitOptionType(StrEnum):
    CALL = "call"
    PUT = "put"
    UNKNOWN = "unknown"


class CftcCotRequest(FreeDerivativesBaseModel):
    years: list[int] = Field(default_factory=list)
    categories: list[CftcCotReportCategory] = Field(
        default_factory=lambda: [
            CftcCotReportCategory.FUTURES_ONLY,
            CftcCotReportCategory.FUTURES_AND_OPTIONS_COMBINED,
        ]
    )
    source_urls: list[str] = Field(default_factory=list)
    local_fixture_paths: list[Path] = Field(default_factory=list)
    market_filters: list[str] = Field(default_factory=lambda: ["gold", "comex"])

    @field_validator("years")
    @classmethod
    def validate_years(cls, values: list[int]) -> list[int]:
        normalized: list[int] = []
        for value in values:
            if value < MIN_REASONABLE_CFTC_YEAR or value > MAX_REASONABLE_CFTC_YEAR:
                raise ValueError("CFTC years must be reasonable four-digit years")
            if value not in normalized:
                normalized.append(value)
        return normalized

    @field_validator("categories")
    @classmethod
    def validate_categories(
        cls,
        values: list[CftcCotReportCategory],
    ) -> list[CftcCotReportCategory]:
        normalized: list[CftcCotReportCategory] = []
        for value in values:
            if value not in normalized:
                normalized.append(value)
        if not normalized:
            raise ValueError("at least one CFTC report category is required")
        return normalized

    @field_validator("source_urls")
    @classmethod
    def validate_source_urls(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            url = validate_public_source_url(value, field_name="source_urls")
            if url not in normalized:
                normalized.append(url)
        return normalized

    @field_validator("local_fixture_paths")
    @classmethod
    def validate_local_fixture_paths(cls, values: list[Path]) -> list[Path]:
        return [
            validate_safe_local_path(path, field_name="local_fixture_paths")
            for path in values
        ]

    @field_validator("market_filters")
    @classmethod
    def validate_market_filters(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            item = value.strip().lower()
            if item and item not in normalized:
                normalized.append(item)
        if not normalized:
            raise ValueError("at least one CFTC market filter is required")
        return normalized


class GvzRequest(FreeDerivativesBaseModel):
    series_id: str = "GVZCLS"
    start_date: date | None = None
    end_date: date | None = None
    source_url: str | None = None
    local_fixture_path: Path | None = None

    @field_validator("series_id")
    @classmethod
    def normalize_series_id(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("series_id is required")
        return normalized

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_public_source_url(value, field_name="source_url")

    @field_validator("local_fixture_path")
    @classmethod
    def validate_local_fixture_path(cls, value: Path | None) -> Path | None:
        return validate_safe_local_path(value, field_name="local_fixture_path")

    @model_validator(mode="after")
    def validate_date_window(self) -> "GvzRequest":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


class DeribitOptionsRequest(FreeDerivativesBaseModel):
    underlyings: list[str] = Field(default_factory=lambda: ["BTC", "ETH"])
    include_expired: bool = False
    snapshot_timestamp: datetime | None = None
    fixture_instruments_path: Path | None = None
    fixture_summary_path: Path | None = None

    @field_validator("underlyings")
    @classmethod
    def normalize_underlyings(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            underlying = value.strip().upper()
            if not SAFE_DERIBIT_UNDERLYING_PATTERN.fullmatch(underlying):
                raise ValueError("Deribit underlyings must be safe uppercase symbols")
            if underlying not in normalized:
                normalized.append(underlying)
        if not normalized:
            raise ValueError("at least one Deribit underlying is required")
        return normalized

    @field_validator("fixture_instruments_path", "fixture_summary_path")
    @classmethod
    def validate_fixture_paths(cls, value: Path | None, info) -> Path | None:
        return validate_safe_local_path(value, field_name=info.field_name)


class FreeDerivativesBootstrapRequest(FreeDerivativesBaseModel):
    include_cftc: bool = True
    include_gvz: bool = True
    include_deribit: bool = True
    cftc: CftcCotRequest = Field(default_factory=CftcCotRequest)
    gvz: GvzRequest = Field(default_factory=GvzRequest)
    deribit: DeribitOptionsRequest = Field(default_factory=DeribitOptionsRequest)
    run_label: str | None = None
    report_format: FreeDerivativesReportFormat = FreeDerivativesReportFormat.BOTH
    research_only_acknowledged: bool

    @field_validator("run_label")
    @classmethod
    def normalize_run_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return validate_filesystem_safe_id(normalized, label="run_label")

    @model_validator(mode="after")
    def validate_bootstrap_request(self) -> "FreeDerivativesBootstrapRequest":
        if not self.research_only_acknowledged:
            raise ValueError("research_only_acknowledged must be true")
        if not (self.include_cftc or self.include_gvz or self.include_deribit):
            raise ValueError("at least one free derivatives source must be enabled")
        return self


class FreeDerivativesArtifact(FreeDerivativesBaseModel):
    artifact_type: FreeDerivativesArtifactType
    source: FreeDerivativesSource
    path: str
    format: FreeDerivativesArtifactFormat
    rows: int | None = Field(default=None, ge=0)
    created_at: datetime
    limitations: list[str] = Field(default_factory=list)


class FreeDerivativesSourceResult(FreeDerivativesBaseModel):
    source: FreeDerivativesSource
    status: FreeDerivativesSourceStatus
    requested_items: list[str] = Field(default_factory=list)
    completed_items: list[str] = Field(default_factory=list)
    skipped_items: list[str] = Field(default_factory=list)
    failed_items: list[str] = Field(default_factory=list)
    row_count: int = Field(default=0, ge=0)
    instrument_count: int = Field(default=0, ge=0)
    coverage_start: date | None = None
    coverage_end: date | None = None
    snapshot_timestamp: datetime | None = None
    artifacts: list[FreeDerivativesArtifact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    missing_data_actions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_visible_non_completed_context(self) -> "FreeDerivativesSourceResult":
        if self.status in {
            FreeDerivativesSourceStatus.SKIPPED,
            FreeDerivativesSourceStatus.FAILED,
        } and not (self.warnings or self.missing_data_actions):
            raise ValueError("skipped and failed source results need visible context")
        return self


class FreeDerivativesBootstrapRun(FreeDerivativesBaseModel):
    run_id: str
    status: FreeDerivativesRunStatus
    created_at: datetime
    completed_at: datetime | None = None
    request: FreeDerivativesBootstrapRequest
    source_results: list[FreeDerivativesSourceResult] = Field(default_factory=list)
    artifacts: list[FreeDerivativesArtifact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    missing_data_actions: list[str] = Field(default_factory=list)
    research_only_warnings: list[str] = Field(default_factory=list)

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        return validate_filesystem_safe_id(value, label="run_id")


class FreeDerivativesBootstrapRunSummary(FreeDerivativesBaseModel):
    run_id: str
    status: FreeDerivativesRunStatus
    created_at: datetime
    completed_at: datetime | None = None
    completed_source_count: int = Field(default=0, ge=0)
    partial_source_count: int = Field(default=0, ge=0)
    failed_source_count: int = Field(default=0, ge=0)
    artifact_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    limitation_count: int = Field(default=0, ge=0)

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        return validate_filesystem_safe_id(value, label="run_id")


class FreeDerivativesBootstrapRunListResponse(FreeDerivativesBaseModel):
    runs: list[FreeDerivativesBootstrapRunSummary] = Field(default_factory=list)


def create_free_derivatives_run_id(
    run_label: str | None = None,
    created_at: datetime | None = None,
) -> str:
    timestamp = (created_at or datetime.now(UTC)).strftime("%Y%m%d_%H%M%S")
    if run_label:
        return f"free_derivatives_{validate_filesystem_safe_id(run_label, label='run_label')}"
    return f"free_derivatives_{timestamp}"


def validate_filesystem_safe_id(value: str, *, label: str = "id") -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must not be blank")
    if not SAFE_ID_PATTERN.fullmatch(normalized):
        raise ValueError(f"{label} must be filesystem-safe")
    return normalized


def validate_safe_local_path(
    path: str | Path | None,
    *,
    field_name: str,
) -> Path | None:
    if path is None:
        return None
    local_path = Path(path)
    if any(part in {"", ".", ".."} for part in local_path.parts):
        raise ValueError(f"{field_name} must not contain parent traversal")
    return local_path


def validate_public_source_url(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    parsed = urlparse(normalized)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be a public HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError(f"{field_name} must not include credentials")
    return normalized


def ensure_no_forbidden_request_fields(value: Any, prefix: str = "") -> None:
    matches = _forbidden_request_paths(value, prefix=prefix)
    if matches:
        fields = ", ".join(sorted(set(matches)))
        raise ValueError(f"credential or execution fields are not allowed: {fields}")


def _forbidden_request_paths(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        matches: list[str] = []
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            normalized_key = _normalize_guardrail_key(str(key))
            if normalized_key in FORBIDDEN_FREE_DERIVATIVES_FIELDS:
                matches.append(path)
            matches.extend(_forbidden_request_paths(item, prefix=path))
        return matches
    if isinstance(value, list):
        matches = []
        for index, item in enumerate(value):
            path = f"{prefix}.{index}" if prefix else str(index)
            matches.extend(_forbidden_request_paths(item, prefix=path))
        return matches
    return []

