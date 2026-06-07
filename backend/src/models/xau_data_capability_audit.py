from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import Field, field_validator, model_validator

from src.models.xau import XauBaseModel

DATA_CAPABILITY_AUDIT_NO_SIGNAL_REASON = (
    "Feature 024B is a research-only data capability audit; signal generation is disabled."
)


class XauDataCapabilityAuditReadiness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class XauDataCapabilityStatus(StrEnum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    BLOCKED = "blocked"


class XauDataCapabilityName(StrEnum):
    HAS_OI = "has_oi"
    HAS_OI_CHANGE = "has_oi_change"
    HAS_INTRADAY_VOLUME = "has_intraday_volume"
    HAS_VOL = "has_vol"
    HAS_VOL_CHG = "has_vol_chg"
    HAS_FUTURE_CHG = "has_future_chg"
    HAS_DTE = "has_dte"
    HAS_FUTURE_REFERENCE = "has_future_reference"
    HAS_NATIVE_SD = "has_native_sd"
    HAS_DELTA = "has_delta"
    HAS_GAMMA = "has_gamma"
    HAS_DELTA_RANGES = "has_delta_ranges"
    HAS_SD_RANGES = "has_sd_ranges"
    HAS_GEX_POSSIBLE = "has_gex_possible"


class XauDataCapabilitySourceType(StrEnum):
    VOL2VOL = "vol2vol"
    MATRIX = "matrix"
    FUSION = "fusion"
    XAU_VOL_OI = "xau_vol_oi"


class XauDataCapabilityAuditRequest(XauBaseModel):
    reports_dir: Path | None = None
    vol2vol_report_ids: list[str] | None = None
    matrix_report_ids: list[str] | None = None
    fusion_report_ids: list[str] | None = None
    xau_vol_oi_report_ids: list[str] | None = None
    max_reports_per_source: int = Field(default=1, ge=1, le=20)
    research_only_acknowledged: bool = True

    @field_validator(
        "vol2vol_report_ids",
        "matrix_report_ids",
        "fusion_report_ids",
        "xau_vol_oi_report_ids",
    )
    @classmethod
    def normalize_id_list(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        output: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = " ".join(str(value).split())
            if normalized and normalized not in seen:
                output.append(normalized)
                seen.add(normalized)
        return output

    @model_validator(mode="after")
    def validate_research_only(self) -> XauDataCapabilityAuditRequest:
        if not self.research_only_acknowledged:
            raise ValueError("XAU data capability audit is research-only and must be acknowledged")
        return self


class XauDataCapabilitySourceSummary(XauBaseModel):
    source_type: XauDataCapabilitySourceType
    report_id: str
    status: str
    row_count: int = Field(ge=0)
    artifact_paths: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("report_id", "status")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(str(value).split())
        if not normalized:
            raise ValueError("source summary text fields must not be blank")
        return normalized

    @field_validator("artifact_paths", "limitations")
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        return _dedupe(values)


class XauDataCapabilityEvidence(XauBaseModel):
    source_type: XauDataCapabilitySourceType
    report_id: str
    field_names: list[str] = Field(default_factory=list)
    row_count: int = Field(ge=0)
    non_null_count: int = Field(ge=0)
    sample_values: list[str] = Field(default_factory=list)

    @field_validator("report_id")
    @classmethod
    def normalize_report_id(cls, value: str) -> str:
        normalized = " ".join(str(value).split())
        if not normalized:
            raise ValueError("evidence report_id must not be blank")
        return normalized

    @field_validator("field_names", "sample_values")
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        return _dedupe(values)


class XauDataCapabilityResult(XauBaseModel):
    capability: XauDataCapabilityName
    status: XauDataCapabilityStatus
    source_count: int = Field(ge=0)
    row_count: int = Field(ge=0)
    non_null_count: int = Field(ge=0)
    evidence: list[XauDataCapabilityEvidence] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("limitations")
    @classmethod
    def normalize_limitations(cls, values: list[str]) -> list[str]:
        return _dedupe(values)


class XauDataCapabilityAuditResult(XauBaseModel):
    audit_id: str
    created_at: datetime
    readiness: XauDataCapabilityAuditReadiness
    source_reports: list[XauDataCapabilitySourceSummary] = Field(default_factory=list)
    capabilities: list[XauDataCapabilityResult] = Field(default_factory=list)
    missing_capabilities: list[XauDataCapabilityName] = Field(default_factory=list)
    blocked_capabilities: list[XauDataCapabilityName] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    no_signal_reasons: list[str] = Field(
        default_factory=lambda: [DATA_CAPABILITY_AUDIT_NO_SIGNAL_REASON]
    )
    research_only: bool = True
    signal_allowed: bool = False

    @field_validator("audit_id")
    @classmethod
    def normalize_audit_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("audit_id must not be blank")
        return normalized

    @field_validator("limitations", "no_signal_reasons")
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        return _dedupe(values)

    @model_validator(mode="after")
    def validate_research_only_state(self) -> XauDataCapabilityAuditResult:
        if self.signal_allowed:
            raise ValueError("XAU data capability audits cannot enable signals")
        if not self.research_only:
            raise ValueError("XAU data capability audits must remain research_only")
        if not self.no_signal_reasons:
            raise ValueError("XAU data capability audits require no_signal_reasons")
        return self


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
    "DATA_CAPABILITY_AUDIT_NO_SIGNAL_REASON",
    "XauDataCapabilityAuditReadiness",
    "XauDataCapabilityAuditRequest",
    "XauDataCapabilityAuditResult",
    "XauDataCapabilityEvidence",
    "XauDataCapabilityName",
    "XauDataCapabilityResult",
    "XauDataCapabilitySourceSummary",
    "XauDataCapabilitySourceType",
    "XauDataCapabilityStatus",
]
