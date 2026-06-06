from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RESEARCH_ONLY_NO_SIGNAL_REASON = (
    "Feature 021 is research-only; signal generation is disabled."
)


class XauSdOiCandidateBaseModel(BaseModel):
    """Strict base model for XAU SD/OI research candidate schemas."""

    model_config = ConfigDict(extra="forbid")


class XauSdOiCandidateSide(StrEnum):
    LONG_REVERSION_CANDIDATE = "long_reversion_candidate"
    SHORT_REVERSION_CANDIDATE = "short_reversion_candidate"
    NO_TRADE = "no_trade"
    BREAKOUT_RISK = "breakout_risk"


class XauSdOiStretchZone(StrEnum):
    UPPER_2SD_TO_3SD = "upper_2sd_to_3sd"
    LOWER_2SD_TO_3SD = "lower_2sd_to_3sd"
    OUTSIDE_3SD = "outside_3sd"
    INSIDE_NORMAL_RANGE = "inside_normal_range"
    UNAVAILABLE = "unavailable"


class XauSdOiConfirmationState(StrEnum):
    UNAVAILABLE = "unavailable"
    NEUTRAL = "neutral"
    REJECTION = "rejection"
    CLOSE_BACK_INSIDE = "close_back_inside"
    ACCEPTANCE = "acceptance"


class XauSdOiIvState(StrEnum):
    UNAVAILABLE = "unavailable"
    STABLE = "stable"
    COMPRESSING = "compressing"
    EXPANDING = "expanding"


class XauSdOiFlowState(StrEnum):
    UNAVAILABLE = "unavailable"
    NEUTRAL = "neutral"
    NOT_BREAKOUT_CONFIRMED = "not_breakout_confirmed"
    FLOW_THROUGH_WALL = "flow_through_wall"


class XauSdOiWallState(StrEnum):
    UNAVAILABLE = "unavailable"
    NO_MAPPED_WALL = "no_mapped_wall"
    NEAREST_WALL_PRESENT = "nearest_wall_present"


class XauSdOiReadinessState(StrEnum):
    CANDIDATE_READY = "candidate_ready"
    MONITOR_ONLY = "monitor_only"
    BREAKOUT_RISK = "breakout_risk"
    BLOCKED_MISSING_CONTEXT = "blocked_missing_context"


class XauSdOiCandidateReason(XauSdOiCandidateBaseModel):
    reason_code: str
    message: str
    severity: str = "info"

    @field_validator("reason_code", "message", "severity")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("candidate reason text fields must not be blank")
        return normalized


class XauSdOiCandidateTarget(XauSdOiCandidateBaseModel):
    label: str
    level: float | None
    source: str

    @field_validator("label", "source")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("candidate target text fields must not be blank")
        return normalized


class XauSdOiCandidateInvalidation(XauSdOiCandidateBaseModel):
    label: str
    level: float | None
    source: str

    @field_validator("label", "source")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("candidate invalidation text fields must not be blank")
        return normalized


class XauSdOiCandidate(XauSdOiCandidateBaseModel):
    candidate_id: str
    map_id: str
    wall_id: str | None = None
    session_date: date
    timestamp: datetime
    side: XauSdOiCandidateSide
    stretch_zone: XauSdOiStretchZone
    traded_price: float | None
    gc_price: float | None = None
    basis: float | None = None
    nearest_wall_level: float | None = None
    nearest_wall_distance: float | None = None
    nearest_wall_oi_change: float | None = None
    nearest_wall_volume: float | None = None
    expected_range_source: str | None = None
    lower_1sd: float | None = None
    upper_1sd: float | None = None
    lower_2sd: float | None = None
    upper_2sd: float | None = None
    lower_3sd: float | None = None
    upper_3sd: float | None = None
    lower_3_5sd: float | None = None
    upper_3_5sd: float | None = None
    target_1: float | None = None
    target_2: float | None = None
    target_3: float | None = None
    stop_reference: float | None = None
    confirmation_state: XauSdOiConfirmationState
    iv_state: XauSdOiIvState
    flow_state: XauSdOiFlowState
    oi_wall_state: XauSdOiWallState
    readiness_state: XauSdOiReadinessState
    reasons: list[XauSdOiCandidateReason] = Field(default_factory=list)
    targets: list[XauSdOiCandidateTarget] = Field(default_factory=list)
    invalidations: list[XauSdOiCandidateInvalidation] = Field(default_factory=list)
    no_signal_reasons: list[str] = Field(
        default_factory=lambda: [RESEARCH_ONLY_NO_SIGNAL_REASON]
    )
    limitations: list[str] = Field(default_factory=list)
    signal_allowed: bool = False
    research_only: bool = True

    @field_validator("candidate_id", "map_id")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("candidate id fields must not be blank")
        return normalized

    @field_validator("expected_range_source")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator("no_signal_reasons", "limitations")
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = " ".join(value.split())
            if normalized and normalized not in seen:
                output.append(normalized)
                seen.add(normalized)
        return output

    @model_validator(mode="after")
    def validate_research_only_state(self) -> XauSdOiCandidate:
        if self.signal_allowed:
            raise ValueError("XAU SD/OI research candidates cannot enable signals")
        if not self.research_only:
            raise ValueError("XAU SD/OI candidates must remain research_only")
        if not self.no_signal_reasons:
            raise ValueError("research candidates require at least one no-signal reason")
        return self


class XauSdOiCandidateSet(XauSdOiCandidateBaseModel):
    map_id: str
    session_date: date
    timestamp: datetime
    candidate_count: int = Field(ge=0)
    candidates: list[XauSdOiCandidate] = Field(default_factory=list)
    no_signal_reasons: list[str] = Field(
        default_factory=lambda: [RESEARCH_ONLY_NO_SIGNAL_REASON]
    )
    limitations: list[str] = Field(default_factory=list)
    signal_allowed: bool = False
    research_only: bool = True

    @field_validator("map_id")
    @classmethod
    def normalize_map_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("candidate set map_id must not be blank")
        return normalized

    @field_validator("no_signal_reasons", "limitations")
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = " ".join(value.split())
            if normalized and normalized not in seen:
                output.append(normalized)
                seen.add(normalized)
        return output

    @model_validator(mode="after")
    def validate_candidate_set(self) -> XauSdOiCandidateSet:
        if self.candidate_count != len(self.candidates):
            raise ValueError("candidate_count must match number of candidates")
        if self.signal_allowed:
            raise ValueError("XAU SD/OI candidate sets cannot enable signals")
        if not self.research_only:
            raise ValueError("XAU SD/OI candidate sets must remain research_only")
        if not self.no_signal_reasons:
            raise ValueError("candidate sets require at least one no-signal reason")
        return self
