from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProviderDataType(StrEnum):
    """Supported research data artifact types."""

    OHLCV = "ohlcv"
    OPEN_INTEREST = "open_interest"
    FUNDING_RATE = "funding_rate"
    FEATURES = "features"


class ProviderDownloadStatus(StrEnum):
    """Provider-aware download status."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class ProviderAssetClass(StrEnum):
    """Curated asset classes exposed by provider metadata."""

    CRYPTO = "crypto"
    EQUITY = "equity"
    ETF = "ETF"
    INDEX = "index"
    FUTURES_PROXY = "futures_proxy"
    MACRO_PROXY = "macro_proxy"
    LOCAL_DATASET = "local_dataset"
    OTHER = "other"


class ProviderCapability(BaseModel):
    """Capability flag for a provider data type."""

    data_type: ProviderDataType = Field(..., description="Research data type")
    supported: bool = Field(..., description="Whether this data type is supported")
    unsupported_reason: str | None = Field(
        default=None,
        description="User-readable reason when the capability is unsupported",
    )

    @model_validator(mode="after")
    def validate_unsupported_reason(self) -> "ProviderCapability":
        if not self.supported and not self.unsupported_reason:
            raise ValueError("unsupported_reason is required when supported is false")
        return self


class ProviderInfo(BaseModel):
    """Provider metadata returned by provider APIs and dashboard clients."""

    provider: str = Field(..., description="Canonical provider identifier")
    display_name: str = Field(..., description="Human-readable provider label")
    supports_ohlcv: bool = Field(..., description="Whether OHLCV is supported")
    supports_open_interest: bool = Field(..., description="Whether open interest is supported")
    supports_funding_rate: bool = Field(..., description="Whether funding rate is supported")
    requires_auth: bool = Field(
        default=False, description="Whether provider credentials are required"
    )
    supported_timeframes: list[str] = Field(..., description="Supported timeframe values")
    default_symbol: str | None = Field(default=None, description="Default provider symbol")
    limitations: list[str] = Field(default_factory=list, description="Known provider limitations")
    capabilities: list[ProviderCapability] = Field(default_factory=list)

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("supported_timeframes")
    @classmethod
    def validate_supported_timeframes(cls, value: list[str]) -> list[str]:
        normalized = [timeframe.strip() for timeframe in value if timeframe.strip()]
        if not normalized:
            raise ValueError("supported_timeframes must contain at least one value")
        return normalized


class ProviderSymbol(BaseModel):
    """A symbol or dataset exposed by a provider."""

    symbol: str = Field(..., description="Provider-facing symbol")
    display_name: str | None = Field(default=None, description="User-facing symbol label")
    asset_class: ProviderAssetClass | str = Field(..., description="Research asset class")
    supports_ohlcv: bool = Field(..., description="Symbol-level OHLCV support")
    supports_open_interest: bool = Field(..., description="Symbol-level open interest support")
    supports_funding_rate: bool = Field(..., description="Symbol-level funding support")
    notes: list[str] = Field(default_factory=list, description="Symbol limitations or notes")

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip()


class UnsupportedCapability(BaseModel):
    """Unsupported data type requested from a known provider."""

    provider: str = Field(..., description="Provider identifier")
    data_type: ProviderDataType = Field(..., description="Unsupported data type")
    reason: str = Field(..., description="User-readable unsupported reason")


class DataArtifact(BaseModel):
    """Locally stored research dataset artifact."""

    data_type: ProviderDataType = Field(..., description="Artifact data type")
    path: str = Field(..., description="Project-relative artifact path")
    rows: int = Field(..., ge=0, description="Rows written to the artifact")
    provider: str = Field(..., description="Source provider")
    symbol: str = Field(..., description="Normalized symbol")
    timeframe: str = Field(..., description="Normalized timeframe")
    first_timestamp: datetime | None = Field(default=None)
    last_timestamp: datetime | None = Field(default=None)


class ProviderDownloadRequest(BaseModel):
    """Provider-aware request to download or validate/import research data."""

    provider: str = Field(..., description="Provider identifier")
    symbol: str | None = Field(default=None, description="Provider symbol")
    timeframe: str = Field(..., description="Requested timeframe")
    days: int | None = Field(default=30, ge=1, le=365, description="History length in days")
    start_time: datetime | None = Field(default=None, description="Inclusive start time")
    end_time: datetime | None = Field(default=None, description="Inclusive end time")
    data_types: list[ProviderDataType] = Field(default_factory=list)
    local_file_path: Path | None = Field(default=None, description="Local CSV or Parquet path")

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    @model_validator(mode="after")
    def validate_date_range(self) -> "ProviderDownloadRequest":
        if self.start_time and self.end_time and self.start_time > self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class ProviderDownloadResult(BaseModel):
    """Outcome of a provider-aware download or local-file validation/import."""

    status: ProviderDownloadStatus = Field(..., description="Download status")
    provider: str = Field(..., description="Provider identifier")
    symbol: str = Field(..., description="Normalized symbol")
    timeframe: str = Field(..., description="Normalized timeframe")
    completed_data_types: list[ProviderDataType] = Field(default_factory=list)
    skipped_data_types: list[UnsupportedCapability] = Field(default_factory=list)
    artifacts: list[DataArtifact] = Field(default_factory=list)
    message: str = Field(..., description="User-readable result summary")
    warnings: list[str] = Field(default_factory=list)


class LocalDatasetValidationReport(BaseModel):
    """Validation result for a local CSV or Parquet research file."""

    file_path: str = Field(..., description="Local source file path")
    is_valid: bool = Field(..., description="Whether the file can be used")
    detected_capabilities: list[ProviderDataType] = Field(default_factory=list)
    required_columns_missing: list[str] = Field(default_factory=list)
    timestamp_column: str | None = Field(default=None)
    timestamp_parseable: bool = Field(default=False)
    duplicate_timestamps: int = Field(default=0, ge=0)
    missing_required_values: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)
