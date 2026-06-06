from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.models.xau import XauDailyStructuralMap
from src.models.xau_daily_structural_map import XauDailyStructuralMapReportMetadata
from src.models.xau_sd_oi_candidate import (
    RESEARCH_ONLY_NO_SIGNAL_REASON,
    XauSdOiCandidateSet,
    XauSdOiConfirmationState,
    XauSdOiFlowState,
    XauSdOiIvState,
)

DAILY_WORKBENCH_NO_SIGNAL_REASON = (
    "Feature 022 is a research-only daily workbench; signal generation is disabled."
)


class XauDailyWorkbenchBaseModel(BaseModel):
    """Strict base model for XAU daily research workbench schemas."""

    model_config = ConfigDict(extra="forbid")


class XauDailyWorkbenchCmeSource(StrEnum):
    LOCAL_BUNDLE = "local_bundle"
    API_ONLY = "api_only"
    LATEST_EXISTING = "latest_existing"
    FIXTURE = "fixture"


class XauDailyWorkbenchPriceProvider(StrEnum):
    STATIC_FIXTURE = "static_fixture"
    YAHOO_RESEARCH_FALLBACK = "yahoo_research_fallback"


class XauDailyWorkbenchReadiness(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class XauDailyWorkbenchProviderType(StrEnum):
    CME_DATA_SOURCE = "cme_data_source"
    FUTURES_PRICE = "futures_price"
    TRADED_PRICE = "traded_price"
    SESSION_OPEN = "session_open"
    BASIS = "basis"
    CANDIDATE_STORE = "candidate_store"


class XauDailyWorkbenchProviderState(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"
    ERROR = "error"


class XauDailyWorkbenchSourceQuality(StrEnum):
    OFFICIAL = "official"
    LOCAL_BUNDLE = "local_bundle"
    LATEST_EXISTING = "latest_existing"
    RESEARCH_FALLBACK = "research_fallback"
    MANUAL_OVERRIDE = "manual_override"
    FIXTURE = "fixture"


class XauDailyWorkbenchMissingInputSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class XauDailyWorkbenchProviderStatus(XauDailyWorkbenchBaseModel):
    provider_name: str
    provider_type: XauDailyWorkbenchProviderType
    status: XauDailyWorkbenchProviderState
    source_quality: XauDailyWorkbenchSourceQuality
    message: str
    limitations: list[str] = Field(default_factory=list)

    @field_validator("provider_name", "message")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("provider status text fields must not be blank")
        return normalized

    @field_validator("limitations")
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        return _dedupe(values)


class XauDailyWorkbenchMissingInput(XauDailyWorkbenchBaseModel):
    input_name: str
    severity: XauDailyWorkbenchMissingInputSeverity = (
        XauDailyWorkbenchMissingInputSeverity.BLOCKING
    )
    message: str

    @field_validator("input_name", "message")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("missing input text fields must not be blank")
        return normalized


class XauDailyWorkbenchBasisSnapshot(XauDailyWorkbenchBaseModel):
    timestamp: datetime
    gc_reference_price: float | None = Field(default=None, gt=0)
    traded_reference_price: float | None = Field(default=None, gt=0)
    traded_instrument: str
    basis: float | None = None
    formula: str
    source: XauDailyWorkbenchSourceQuality
    alignment_status: str = "unknown"
    limitations: list[str] = Field(default_factory=list)

    @field_validator("traded_instrument", "formula", "alignment_status")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("basis snapshot text fields must not be blank")
        return normalized

    @field_validator("limitations")
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        return _dedupe(values)


class XauDailyWorkbenchRunRequest(XauDailyWorkbenchBaseModel):
    session_date: date | None = None
    expiration_code: str | None = None
    traded_instrument: str = "XAUUSD"
    cme_source: XauDailyWorkbenchCmeSource = XauDailyWorkbenchCmeSource.LATEST_EXISTING
    input_dir: Path | None = None
    gc_reference_price: float | None = Field(default=None, gt=0)
    traded_reference_price: float | None = Field(default=None, gt=0)
    session_open_price: float | None = Field(default=None, gt=0)
    session_open_source: str | None = "manual_research_input"
    manual_basis: float | None = None
    confirmation_state: XauSdOiConfirmationState = XauSdOiConfirmationState.UNAVAILABLE
    iv_state: XauSdOiIvState = XauSdOiIvState.UNAVAILABLE
    flow_state: XauSdOiFlowState = XauSdOiFlowState.UNAVAILABLE
    price_provider: XauDailyWorkbenchPriceProvider | None = (
        XauDailyWorkbenchPriceProvider.STATIC_FIXTURE
    )
    output_root: Path | None = None
    map_id: str | None = None
    run_candidates: bool = True
    overwrite_allowed: bool = False
    research_only_acknowledged: bool = True

    @field_validator(
        "expiration_code",
        "traded_instrument",
        "session_open_source",
        "map_id",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        normalized = " ".join(str(value).split())
        return normalized or None

    @model_validator(mode="after")
    def validate_research_only_request(self) -> XauDailyWorkbenchRunRequest:
        if not self.traded_instrument:
            raise ValueError("traded_instrument must not be blank")
        if not self.research_only_acknowledged:
            raise ValueError("XAU daily workbench is research-only and must be acknowledged")
        return self


class XauDailyWorkbenchCandidateMetadata(XauDailyWorkbenchBaseModel):
    candidate_set_id: str
    map_id: str
    created_at: datetime
    candidate_count: int = Field(ge=0)
    readiness: XauDailyWorkbenchReadiness
    no_signal_reasons: list[str] = Field(default_factory=list)
    missing_inputs: list[XauDailyWorkbenchMissingInput] = Field(default_factory=list)
    research_only: bool = True
    signal_allowed: bool = False

    @field_validator("candidate_set_id", "map_id")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("candidate metadata ids must not be blank")
        return normalized

    @field_validator("no_signal_reasons")
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        return _dedupe(values)

    @model_validator(mode="after")
    def validate_no_signal_state(self) -> XauDailyWorkbenchCandidateMetadata:
        if self.signal_allowed:
            raise ValueError("XAU workbench candidate metadata cannot enable signals")
        if not self.research_only:
            raise ValueError("XAU workbench candidate metadata must remain research_only")
        if not self.no_signal_reasons:
            raise ValueError("candidate metadata requires at least one no_signal_reason")
        return self


class XauDailyWorkbenchRunResult(XauDailyWorkbenchBaseModel):
    run_id: str
    created_at: datetime
    cme_source: XauDailyWorkbenchCmeSource
    traded_instrument: str
    session_date: date | None = None
    expiration_code: str | None = None
    map_id: str | None = None
    candidate_set_id: str | None = None
    readiness: XauDailyWorkbenchReadiness
    map_artifact_paths: dict[str, str] = Field(default_factory=dict)
    candidate_artifact_paths: dict[str, str] = Field(default_factory=dict)
    missing_inputs: list[XauDailyWorkbenchMissingInput] = Field(default_factory=list)
    provider_statuses: list[XauDailyWorkbenchProviderStatus] = Field(default_factory=list)
    no_signal_reasons: list[str] = Field(
        default_factory=lambda: [DAILY_WORKBENCH_NO_SIGNAL_REASON]
    )
    limitations: list[str] = Field(default_factory=list)
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    basis_snapshot: XauDailyWorkbenchBasisSnapshot | None = None
    map_metadata: XauDailyStructuralMapReportMetadata | None = None
    daily_map: XauDailyStructuralMap | None = None
    candidate_set: XauSdOiCandidateSet | None = None
    candidate_metadata: XauDailyWorkbenchCandidateMetadata | None = None
    research_only: bool = True
    signal_allowed: bool = False

    @field_validator("run_id")
    @classmethod
    def normalize_run_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("run_id must not be blank")
        return normalized

    @field_validator("traded_instrument")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("traded_instrument must not be blank")
        return normalized

    @field_validator("no_signal_reasons", "limitations")
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        return _dedupe(values)

    @field_validator("artifact_paths", "map_artifact_paths", "candidate_artifact_paths")
    @classmethod
    def normalize_artifact_paths(cls, values: dict[str, str]) -> dict[str, str]:
        return {str(key): str(value).replace("\\", "/") for key, value in values.items()}

    @model_validator(mode="after")
    def validate_research_only_state(self) -> XauDailyWorkbenchRunResult:
        if self.signal_allowed:
            raise ValueError("XAU daily workbench results cannot enable signals")
        if not self.research_only:
            raise ValueError("XAU daily workbench results must remain research_only")
        if not self.no_signal_reasons:
            raise ValueError("workbench results require no_signal_reasons")
        if self.candidate_set is not None and self.candidate_set.signal_allowed:
            raise ValueError("workbench cannot return signal-enabled candidates")
        return self


class XauDailyWorkbenchLatestResponse(XauDailyWorkbenchBaseModel):
    readiness: XauDailyWorkbenchReadiness
    missing_inputs: list[XauDailyWorkbenchMissingInput] = Field(default_factory=list)
    no_signal_reasons: list[str] = Field(
        default_factory=lambda: [DAILY_WORKBENCH_NO_SIGNAL_REASON]
    )
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    latest_run: XauDailyWorkbenchRunResult | None = None
    available_runs: list[str] = Field(default_factory=list)
    message: str
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_no_signal_state(self) -> XauDailyWorkbenchLatestResponse:
        if self.signal_allowed:
            raise ValueError("XAU daily workbench latest response cannot enable signals")
        if not self.research_only:
            raise ValueError("XAU daily workbench latest response must remain research_only")
        return self


class XauDailyWorkbenchLatestState(XauDailyWorkbenchLatestResponse):
    """Named latest-state model for the workbench contract."""


class XauDailyWorkbenchMapResponse(XauDailyWorkbenchBaseModel):
    map_id: str
    readiness: XauDailyWorkbenchReadiness
    missing_inputs: list[XauDailyWorkbenchMissingInput] = Field(default_factory=list)
    no_signal_reasons: list[str] = Field(
        default_factory=lambda: [DAILY_WORKBENCH_NO_SIGNAL_REASON]
    )
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    map_metadata: XauDailyStructuralMapReportMetadata
    daily_map: XauDailyStructuralMap
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_no_signal_state(self) -> XauDailyWorkbenchMapResponse:
        if self.signal_allowed or self.daily_map.signal_allowed:
            raise ValueError("XAU daily workbench map response cannot enable signals")
        if not self.research_only:
            raise ValueError("XAU daily workbench map response must remain research_only")
        return self


class XauDailyWorkbenchCandidateResponse(XauDailyWorkbenchBaseModel):
    map_id: str
    candidate_set_id: str
    readiness: XauDailyWorkbenchReadiness
    missing_inputs: list[XauDailyWorkbenchMissingInput] = Field(default_factory=list)
    no_signal_reasons: list[str] = Field(
        default_factory=lambda: [DAILY_WORKBENCH_NO_SIGNAL_REASON]
    )
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    candidate_metadata: XauDailyWorkbenchCandidateMetadata
    candidate_set: XauSdOiCandidateSet
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_no_signal_state(self) -> XauDailyWorkbenchCandidateResponse:
        if self.signal_allowed or self.candidate_set.signal_allowed:
            raise ValueError("XAU daily workbench candidate response cannot enable signals")
        if not self.research_only:
            raise ValueError("XAU daily workbench candidate response must remain research_only")
        return self


def research_only_no_signal_reasons(*extra: str) -> list[str]:
    return _dedupe(
        [
            DAILY_WORKBENCH_NO_SIGNAL_REASON,
            RESEARCH_ONLY_NO_SIGNAL_REASON,
            *extra,
        ]
    )


def missing_input(
    input_name: str,
    message: str,
    *,
    severity: XauDailyWorkbenchMissingInputSeverity = (
        XauDailyWorkbenchMissingInputSeverity.BLOCKING
    ),
) -> XauDailyWorkbenchMissingInput:
    return XauDailyWorkbenchMissingInput(
        input_name=input_name,
        severity=severity,
        message=message,
    )


def provider_status(
    *,
    provider_name: str,
    provider_type: XauDailyWorkbenchProviderType,
    status: XauDailyWorkbenchProviderState,
    source_quality: XauDailyWorkbenchSourceQuality,
    message: str,
    limitations: list[str] | None = None,
) -> XauDailyWorkbenchProviderStatus:
    return XauDailyWorkbenchProviderStatus(
        provider_name=provider_name,
        provider_type=provider_type,
        status=status,
        source_quality=source_quality,
        message=message,
        limitations=limitations or [],
    )


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value).split())
        if normalized and normalized not in seen:
            output.append(normalized)
            seen.add(normalized)
    return output


__all__ = [
    "DAILY_WORKBENCH_NO_SIGNAL_REASON",
    "XauDailyWorkbenchBasisSnapshot",
    "XauDailyWorkbenchCandidateMetadata",
    "XauDailyWorkbenchCandidateResponse",
    "XauDailyWorkbenchCmeSource",
    "XauDailyWorkbenchLatestResponse",
    "XauDailyWorkbenchLatestState",
    "XauDailyWorkbenchMapResponse",
    "XauDailyWorkbenchMissingInput",
    "XauDailyWorkbenchMissingInputSeverity",
    "XauDailyWorkbenchPriceProvider",
    "XauDailyWorkbenchProviderState",
    "XauDailyWorkbenchProviderStatus",
    "XauDailyWorkbenchProviderType",
    "XauDailyWorkbenchReadiness",
    "XauDailyWorkbenchRunRequest",
    "XauDailyWorkbenchRunResult",
    "XauDailyWorkbenchSourceQuality",
    "missing_input",
    "provider_status",
    "research_only_no_signal_reasons",
]
