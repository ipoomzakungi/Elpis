from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, field_validator, model_validator

from src.models.backtest import StrictModel


class ResearchExecutionWorkflowStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    FAILED = "failed"


class ResearchEvidenceDecision(StrEnum):
    CONTINUE = "continue"
    REFINE = "refine"
    REJECT = "reject"
    DATA_BLOCKED = "data_blocked"
    INCONCLUSIVE = "inconclusive"


class ResearchExecutionWorkflowType(StrEnum):
    CRYPTO_MULTI_ASSET = "crypto_multi_asset"
    PROXY_OHLCV = "proxy_ohlcv"
    XAU_VOL_OI = "xau_vol_oi"
    EVIDENCE_SUMMARY = "evidence_summary"


DEFAULT_CRYPTO_CAPABILITIES = [
    "ohlcv",
    "regime",
    "open_interest",
    "funding",
    "volume_confirmation",
]
DEFAULT_PROXY_CAPABILITIES = ["ohlcv"]
DEFAULT_XAU_CAPABILITIES = ["gold_options_oi"]

CAPABILITY_ALIASES = {
    "oi": "open_interest",
    "openinterest": "open_interest",
    "funding_rate": "funding",
    "implied_volatility": "iv",
    "volatility": "iv",
    "gold_options_open_interest": "gold_options_oi",
    "gold_options": "gold_options_oi",
    "futures_open_interest": "futures_oi",
    "xauusd_execution": "xauusd_spot_execution",
}


def normalize_capability(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    compact = "".join(character for character in normalized if character.isalnum())
    return CAPABILITY_ALIASES.get(normalized) or CAPABILITY_ALIASES.get(compact) or normalized


def normalize_capabilities(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        capability = normalize_capability(value)
        if capability and capability not in normalized:
            normalized.append(capability)
    return normalized


class ResearchExecutionWorkflowConfig(StrictModel):
    enabled: bool = True
    workflow_type: ResearchExecutionWorkflowType
    required_capabilities: list[str] = Field(default_factory=list)
    existing_report_id: str | None = None
    notes: str | None = None

    @field_validator("required_capabilities")
    @classmethod
    def normalize_required_capabilities(cls, values: list[str]) -> list[str]:
        return normalize_capabilities(values)


class CryptoResearchWorkflowConfig(ResearchExecutionWorkflowConfig):
    workflow_type: ResearchExecutionWorkflowType = ResearchExecutionWorkflowType.CRYPTO_MULTI_ASSET
    primary_assets: list[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    optional_assets: list[str] = Field(default_factory=list)
    timeframe: str = "15m"
    processed_feature_root: Path | None = None
    required_capabilities: list[str] = Field(
        default_factory=lambda: DEFAULT_CRYPTO_CAPABILITIES.copy(),
        validation_alias=AliasChoices("required_capabilities", "required_feature_groups"),
    )
    existing_research_run_id: str | None = None

    @field_validator("primary_assets", "optional_assets")
    @classmethod
    def normalize_symbols(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            symbol = value.strip().upper()
            if not symbol:
                raise ValueError("asset symbols must not be blank")
            if symbol not in normalized:
                normalized.append(symbol)
        return normalized

    @field_validator("timeframe")
    @classmethod
    def normalize_timeframe(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("timeframe is required")
        return normalized

    def enabled_assets(self) -> list[str]:
        return [*self.primary_assets, *self.optional_assets] if self.enabled else []


class ProxyResearchWorkflowConfig(ResearchExecutionWorkflowConfig):
    workflow_type: ResearchExecutionWorkflowType = ResearchExecutionWorkflowType.PROXY_OHLCV
    assets: list[str] = Field(default_factory=lambda: ["SPY", "QQQ", "GLD", "GC=F"])
    provider: str = "yahoo_finance"
    timeframe: str = "1d"
    processed_feature_root: Path | None = None
    required_capabilities: list[str] = Field(
        default_factory=lambda: DEFAULT_PROXY_CAPABILITIES.copy(),
        validation_alias=AliasChoices("required_capabilities", "required_feature_groups"),
    )
    existing_research_run_id: str | None = None

    @field_validator("assets")
    @classmethod
    def normalize_assets(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            symbol = value.strip().upper()
            if not symbol:
                raise ValueError("proxy asset symbols must not be blank")
            if symbol not in normalized:
                normalized.append(symbol)
        return normalized

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("provider is required")
        if normalized in {"yahoo", "yfinance"}:
            return "yahoo_finance"
        return normalized

    @field_validator("timeframe")
    @classmethod
    def normalize_timeframe(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("timeframe is required")
        return normalized

    def enabled_assets(self) -> list[str]:
        return list(self.assets) if self.enabled else []


class XauVolOiWorkflowConfig(ResearchExecutionWorkflowConfig):
    workflow_type: ResearchExecutionWorkflowType = ResearchExecutionWorkflowType.XAU_VOL_OI
    options_oi_file_path: Path | None = None
    existing_xau_report_id: str | None = None
    spot_reference: dict[str, Any] | None = None
    futures_reference: dict[str, Any] | None = None
    manual_basis: float | None = None
    volatility_snapshot: dict[str, Any] | None = None
    include_2sd_range: bool = False
    required_capabilities: list[str] = Field(
        default_factory=lambda: DEFAULT_XAU_CAPABILITIES.copy()
    )


class ResearchExecutionRunRequest(StrictModel):
    name: str | None = None
    description: str | None = None
    crypto: CryptoResearchWorkflowConfig | None = None
    proxy: ProxyResearchWorkflowConfig | None = None
    xau: XauVolOiWorkflowConfig | None = None
    evidence_options: dict[str, Any] = Field(default_factory=dict)
    reference_report_ids: list[str] = Field(default_factory=list)
    research_only_acknowledged: bool

    @field_validator("name", "description")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_research_execution_request(self) -> "ResearchExecutionRunRequest":
        if not self.research_only_acknowledged:
            raise ValueError("research_only_acknowledged must be true")
        workflows = [self.crypto, self.proxy, self.xau]
        if not any(workflow is not None and workflow.enabled for workflow in workflows):
            raise ValueError("at least one workflow must be enabled")
        return self


class ResearchExecutionPreflightResult(StrictModel):
    workflow_type: ResearchExecutionWorkflowType
    status: ResearchExecutionWorkflowStatus
    asset: str | None = None
    source_identity: str | None = None
    ready: bool
    feature_path: str | None = None
    row_count: int | None = Field(default=None, ge=0)
    date_start: datetime | None = None
    date_end: datetime | None = None
    missing_data_actions: list[str] = Field(default_factory=list)
    unsupported_capabilities: list[str] = Field(default_factory=list)
    capability_snapshot: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("asset")
    @classmethod
    def normalize_asset(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None


class ResearchExecutionWorkflowResult(StrictModel):
    workflow_type: ResearchExecutionWorkflowType
    status: ResearchExecutionWorkflowStatus
    decision: ResearchEvidenceDecision
    decision_reason: str
    report_ids: list[str] = Field(default_factory=list)
    asset_results: list[ResearchExecutionPreflightResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    missing_data_actions: list[str] = Field(default_factory=list)


class ResearchEvidenceDecisionResult(StrictModel):
    decision: ResearchEvidenceDecision
    reason: str
    warnings: list[str] = Field(default_factory=list)


class ResearchEvidenceSummary(StrictModel):
    execution_run_id: str
    status: ResearchExecutionWorkflowStatus
    decision: ResearchEvidenceDecision
    workflow_results: list[ResearchExecutionWorkflowResult] = Field(default_factory=list)
    crypto_summary: dict[str, Any] | None = None
    proxy_summary: dict[str, Any] | None = None
    xau_summary: dict[str, Any] | None = None
    missing_data_checklist: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    research_only_warnings: list[str] = Field(
        default_factory=lambda: [
            "Research decisions are evidence labels only, not trading approvals."
        ]
    )
    created_at: datetime


class ResearchExecutionRun(StrictModel):
    execution_run_id: str
    name: str | None = None
    normalized_config: ResearchExecutionRunRequest
    preflight_results: list[ResearchExecutionPreflightResult] = Field(default_factory=list)
    evidence_summary: ResearchEvidenceSummary | None = None
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ResearchExecutionRunSummary(StrictModel):
    execution_run_id: str
    name: str | None = None
    status: ResearchExecutionWorkflowStatus
    decision: ResearchEvidenceDecision
    completed_workflow_count: int = Field(default=0, ge=0)
    blocked_workflow_count: int = Field(default=0, ge=0)
    partial_workflow_count: int = Field(default=0, ge=0)
    failed_workflow_count: int = Field(default=0, ge=0)
    created_at: datetime
    artifact_root: str


class ResearchExecutionRunListResponse(StrictModel):
    runs: list[ResearchExecutionRunSummary] = Field(default_factory=list)


class ResearchExecutionMissingDataResponse(StrictModel):
    execution_run_id: str
    missing_data_checklist: list[str] = Field(default_factory=list)
