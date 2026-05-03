from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator

from src.models.backtest import StrictModel


class DataSourceProviderType(StrEnum):
    BINANCE_PUBLIC = "binance_public"
    YAHOO_FINANCE = "yahoo_finance"
    LOCAL_FILE = "local_file"
    KAIKO_OPTIONAL = "kaiko_optional"
    TARDIS_OPTIONAL = "tardis_optional"
    COINGLASS_OPTIONAL = "coinglass_optional"
    CRYPTOQUANT_OPTIONAL = "cryptoquant_optional"
    CME_QUIKSTRIKE_LOCAL_OR_OPTIONAL = "cme_quikstrike_local_or_optional"
    FORBIDDEN_PRIVATE_TRADING = "forbidden_private_trading"


class DataSourceReadinessStatus(StrEnum):
    READY = "ready"
    CONFIGURED = "configured"
    MISSING = "missing"
    UNAVAILABLE_OPTIONAL = "unavailable_optional"
    UNSUPPORTED = "unsupported"
    BLOCKED = "blocked"
    FORBIDDEN = "forbidden"


class DataSourceTier(StrEnum):
    TIER_0_PUBLIC_LOCAL = "tier_0_public_local"
    TIER_1_OPTIONAL_PAID_RESEARCH = "tier_1_optional_paid_research"
    TIER_2_FORBIDDEN_V0 = "tier_2_forbidden_v0"


class DataSourceWorkflowType(StrEnum):
    CRYPTO_MULTI_ASSET = "crypto_multi_asset"
    PROXY_OHLCV = "proxy_ohlcv"
    XAU_VOL_OI = "xau_vol_oi"
    OPTIONAL_VENDOR = "optional_vendor"
    FIRST_EVIDENCE_RUN = "first_evidence_run"


class FirstEvidenceRunStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"


class DataSourceBootstrapProvider(StrEnum):
    BINANCE_PUBLIC = "binance_public"
    YAHOO_FINANCE = "yahoo_finance"


class MissingDataSeverity(StrEnum):
    BLOCKING = "blocking"
    OPTIONAL = "optional"
    INFORMATIONAL = "informational"


ALLOWED_BOOTSTRAP_BINANCE_SYMBOLS = {
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
}
ALLOWED_BOOTSTRAP_YAHOO_SYMBOLS = {"SPY", "QQQ", "GLD", "GC=F", "BTC-USD"}
ALLOWED_BOOTSTRAP_BINANCE_TIMEFRAMES = {"15m", "1h", "1d"}
ALLOWED_BOOTSTRAP_YAHOO_TIMEFRAMES = {"1d"}


class DataSourceCapability(StrictModel):
    provider_type: DataSourceProviderType
    display_name: str
    tier: DataSourceTier
    supports: list[str] = Field(default_factory=list)
    unsupported: list[str] = Field(default_factory=list)
    requires_key: bool = False
    requires_local_file: bool = False
    is_optional: bool = False
    limitations: list[str] = Field(default_factory=list)
    forbidden_reason: str | None = None

    @field_validator("supports", "unsupported", "limitations")
    @classmethod
    def normalize_string_list(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            item = value.strip()
            if item and item not in normalized:
                normalized.append(item)
        return normalized


class DataSourceMissingDataAction(StrictModel):
    action_id: str
    workflow_type: DataSourceWorkflowType
    provider_type: DataSourceProviderType
    asset: str | None = None
    severity: MissingDataSeverity = MissingDataSeverity.BLOCKING
    title: str
    instructions: list[str]
    required_columns: list[str] = Field(default_factory=list)
    optional_columns: list[str] = Field(default_factory=list)
    blocking: bool = True

    @field_validator("action_id")
    @classmethod
    def normalize_action_id(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("action_id is required")
        return normalized

    @field_validator("asset")
    @classmethod
    def normalize_asset(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @field_validator("instructions", "required_columns", "optional_columns")
    @classmethod
    def normalize_action_lists(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            item = value.strip()
            if item and item not in normalized:
                normalized.append(item)
        return normalized


class DataSourceProviderStatus(StrictModel):
    provider_type: DataSourceProviderType
    status: DataSourceReadinessStatus
    configured: bool
    env_var_name: str | None = None
    secret_value_returned: bool = False
    capabilities: DataSourceCapability
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    missing_actions: list[DataSourceMissingDataAction] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_secret_guard(self) -> "DataSourceProviderStatus":
        if self.secret_value_returned:
            raise ValueError("secret values must never be returned")
        return self


class DataSourceReadiness(StrictModel):
    generated_at: datetime
    provider_statuses: list[DataSourceProviderStatus]
    capability_matrix: list[DataSourceCapability]
    public_sources_available: bool
    optional_sources_missing: list[DataSourceProviderType] = Field(default_factory=list)
    forbidden_sources_detected: list[DataSourceProviderType] = Field(default_factory=list)
    missing_data_actions: list[DataSourceMissingDataAction] = Field(default_factory=list)
    research_only_warnings: list[str] = Field(default_factory=list)


class DataSourceLocalFileCapabilityDetection(StrictModel):
    available_columns: list[str]
    detected_capabilities: list[str] = Field(default_factory=list)
    missing_ohlcv_columns: list[str] = Field(default_factory=list)
    missing_xau_options_oi_columns: list[str] = Field(default_factory=list)
    supports_ohlcv: bool = False
    supports_xau_options_oi: bool = False


class DataSourceCapabilityListResponse(StrictModel):
    capabilities: list[DataSourceCapability]


class DataSourceMissingDataResponse(StrictModel):
    actions: list[DataSourceMissingDataAction]


class DataSourcePreflightRequest(StrictModel):
    crypto_assets: list[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    optional_crypto_assets: list[str] = Field(default_factory=list)
    crypto_timeframe: str = "15m"
    proxy_assets: list[str] = Field(default_factory=lambda: ["SPY", "QQQ", "GLD", "GC=F"])
    proxy_timeframe: str = "1d"
    processed_feature_root: Path | None = None
    xau_options_oi_file_path: Path | None = None
    require_optional_vendors: list[DataSourceProviderType] = Field(default_factory=list)
    requested_capabilities: list[str] = Field(default_factory=list)
    research_only_acknowledged: bool

    @field_validator("crypto_assets", "optional_crypto_assets", "proxy_assets")
    @classmethod
    def normalize_assets(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            symbol = value.strip().upper()
            if not symbol:
                raise ValueError("asset symbols must not be blank")
            if symbol not in normalized:
                normalized.append(symbol)
        return normalized

    @field_validator("crypto_timeframe", "proxy_timeframe")
    @classmethod
    def normalize_timeframe(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("timeframe is required")
        return normalized

    @field_validator("requested_capabilities")
    @classmethod
    def normalize_requested_capabilities(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            capability = value.strip().lower().replace("-", "_").replace(" ", "_")
            if capability and capability not in normalized:
                normalized.append(capability)
        return normalized

    @model_validator(mode="after")
    def validate_preflight_request(self) -> "DataSourcePreflightRequest":
        if not self.research_only_acknowledged:
            raise ValueError("research_only_acknowledged must be true")
        _validate_local_path(self.processed_feature_root, "processed_feature_root")
        _validate_local_path(self.xau_options_oi_file_path, "xau_options_oi_file_path")
        return self


class DataSourcePreflightAssetResult(StrictModel):
    asset: str | None = None
    provider_type: DataSourceProviderType
    status: DataSourceReadinessStatus
    feature_path: str | None = None
    row_count: int | None = Field(default=None, ge=0)
    missing_data_actions: list[DataSourceMissingDataAction] = Field(default_factory=list)
    unsupported_capabilities: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class DataSourcePreflightResult(StrictModel):
    status: FirstEvidenceRunStatus
    readiness: DataSourceReadiness
    crypto_results: list[DataSourcePreflightAssetResult] = Field(default_factory=list)
    proxy_results: list[DataSourcePreflightAssetResult] = Field(default_factory=list)
    xau_result: DataSourcePreflightAssetResult | None = None
    optional_vendor_results: list[DataSourceProviderStatus] = Field(default_factory=list)
    unsupported_capabilities: list[str] = Field(default_factory=list)
    missing_data_actions: list[DataSourceMissingDataAction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class FirstEvidenceRunRequest(StrictModel):
    name: str | None = None
    preflight: DataSourcePreflightRequest
    use_existing_research_report_ids: list[str] = Field(default_factory=list)
    use_existing_xau_report_id: str | None = None
    run_when_partial: bool = True
    research_only_acknowledged: bool

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("use_existing_research_report_ids")
    @classmethod
    def normalize_research_report_ids(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            report_id = _normalize_safe_report_id(value, "use_existing_research_report_ids")
            if report_id is not None and report_id not in normalized:
                normalized.append(report_id)
        return normalized

    @field_validator("use_existing_xau_report_id")
    @classmethod
    def normalize_existing_xau_report_id(cls, value: str | None) -> str | None:
        return _normalize_safe_report_id(value, "use_existing_xau_report_id")

    @model_validator(mode="after")
    def validate_first_run_request(self) -> "FirstEvidenceRunRequest":
        if not self.research_only_acknowledged:
            raise ValueError("research_only_acknowledged must be true")
        return self


class FirstEvidenceRunResult(StrictModel):
    first_run_id: str
    status: FirstEvidenceRunStatus
    execution_run_id: str | None = None
    evidence_report_path: str | None = None
    decision: str | None = None
    linked_research_report_ids: list[str] = Field(default_factory=list)
    linked_xau_report_ids: list[str] = Field(default_factory=list)
    preflight_result: DataSourcePreflightResult
    evidence_summary: dict[str, Any] | None = None
    missing_data_actions: list[DataSourceMissingDataAction] = Field(default_factory=list)
    research_only_warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    created_at: datetime


class DataSourceBootstrapRequest(StrictModel):
    binance_symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    optional_binance_symbols: list[str] = Field(default_factory=list)
    binance_timeframes: list[str] = Field(default_factory=lambda: ["15m"])
    yahoo_symbols: list[str] = Field(
        default_factory=lambda: ["SPY", "QQQ", "GLD", "GC=F", "BTC-USD"]
    )
    yahoo_timeframes: list[str] = Field(default_factory=lambda: ["1d"])
    days: int = Field(default=30, ge=1, le=365)
    start_time: datetime | None = None
    end_time: datetime | None = None
    include_binance: bool = True
    include_yahoo: bool = True
    include_binance_open_interest: bool = True
    include_binance_funding: bool = True
    run_preflight_after: bool = True
    include_xau_local_instructions: bool = True
    research_only_acknowledged: bool

    @field_validator("binance_symbols", "optional_binance_symbols", "yahoo_symbols")
    @classmethod
    def normalize_bootstrap_symbols(cls, values: list[str], info) -> list[str]:
        normalized: list[str] = []
        allowed = (
            ALLOWED_BOOTSTRAP_YAHOO_SYMBOLS
            if info.field_name == "yahoo_symbols"
            else ALLOWED_BOOTSTRAP_BINANCE_SYMBOLS
        )
        for value in values:
            symbol = value.strip().upper()
            if not symbol:
                raise ValueError("bootstrap symbols must not be blank")
            if symbol not in allowed:
                raise ValueError(f"unsupported public bootstrap symbol: {symbol}")
            if symbol not in normalized:
                normalized.append(symbol)
        return normalized

    @field_validator("binance_timeframes", "yahoo_timeframes")
    @classmethod
    def normalize_bootstrap_timeframes(cls, values: list[str], info) -> list[str]:
        normalized: list[str] = []
        allowed = (
            ALLOWED_BOOTSTRAP_YAHOO_TIMEFRAMES
            if info.field_name == "yahoo_timeframes"
            else ALLOWED_BOOTSTRAP_BINANCE_TIMEFRAMES
        )
        for value in values:
            timeframe = value.strip().lower()
            if not timeframe:
                raise ValueError("bootstrap timeframes must not be blank")
            if timeframe not in allowed:
                raise ValueError(f"unsupported public bootstrap timeframe: {timeframe}")
            if timeframe not in normalized:
                normalized.append(timeframe)
        return normalized

    @model_validator(mode="after")
    def validate_bootstrap_request(self) -> "DataSourceBootstrapRequest":
        if not self.research_only_acknowledged:
            raise ValueError("research_only_acknowledged must be true")
        if self.start_time is not None and self.end_time is not None:
            if self.start_time >= self.end_time:
                raise ValueError("start_time must be before end_time")
        return self


class DataSourceBootstrapPlanItem(StrictModel):
    provider: DataSourceBootstrapProvider
    symbol: str
    timeframe: str
    data_types: list[str]
    unsupported_capabilities: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class DataSourceBootstrapArtifact(StrictModel):
    provider_type: DataSourceProviderType
    data_type: str
    path: Path
    row_count: int = Field(ge=0)
    start_timestamp: datetime | None = None
    end_timestamp: datetime | None = None
    limitations: list[str] = Field(default_factory=list)


class DataSourceBootstrapAssetSummary(StrictModel):
    provider_type: DataSourceProviderType
    symbol: str
    timeframe: str
    status: FirstEvidenceRunStatus
    raw_artifacts: list[DataSourceBootstrapArtifact] = Field(default_factory=list)
    processed_feature_path: Path | None = None
    row_count: int = Field(default=0, ge=0)
    start_timestamp: datetime | None = None
    end_timestamp: datetime | None = None
    unsupported_capabilities: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class DataSourceBootstrapRunResult(StrictModel):
    bootstrap_run_id: str
    status: FirstEvidenceRunStatus
    created_at: datetime
    raw_root: Path
    processed_root: Path
    asset_summaries: list[DataSourceBootstrapAssetSummary] = Field(default_factory=list)
    preflight_result: DataSourcePreflightResult | None = None
    missing_data_actions: list[DataSourceMissingDataAction] = Field(default_factory=list)
    research_only_warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class DataSourceBootstrapRunListResponse(StrictModel):
    runs: list[DataSourceBootstrapRunResult] = Field(default_factory=list)


def _validate_local_path(path: Path | None, field_name: str) -> None:
    if path is None:
        return
    if ".." in path.parts:
        raise ValueError(f"{field_name} must not contain parent traversal")

    if path.is_absolute():
        # Absolute paths are allowed for local smoke work, but still must not
        # include traversal segments after normalization.
        resolved = path.resolve()
        if ".." in resolved.parts:
            raise ValueError(f"{field_name} must be a safe local path")


def _normalize_safe_report_id(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if any(part in {"", ".", ".."} for part in Path(normalized).parts):
        raise ValueError(f"{field_name} must contain safe report id values")
    return normalized
