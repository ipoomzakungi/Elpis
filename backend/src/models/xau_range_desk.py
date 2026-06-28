from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from src.models.xau import XauBaseModel, XauWallType

RANGE_DESK_NO_SIGNAL_REASON = (
    "Feature 024A Range Desk is research-only planning context; signal generation is disabled."
)


class XauRangeDeskReadiness(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class XauRangeDeskLevelKind(StrEnum):
    LOWER_3SD = "lower_3sd"
    LOWER_2SD = "lower_2sd"
    LOWER_1SD = "lower_1sd"
    MEAN = "mean"
    UPPER_1SD = "upper_1sd"
    UPPER_2SD = "upper_2sd"
    UPPER_3SD = "upper_3sd"
    SESSION_OPEN = "session_open"
    OI_WALL = "oi_wall"


class XauRangeDeskZoneKind(StrEnum):
    NO_TRADE_INSIDE_1SD = "no_trade_inside_1sd"
    UPPER_STRETCH_2SD_TO_3SD = "upper_stretch_2sd_to_3sd"
    LOWER_STRETCH_2SD_TO_3SD = "lower_stretch_2sd_to_3sd"


class XauRangeDeskLevelInput(XauBaseModel):
    label: XauRangeDeskLevelKind
    futures_level: float = Field(..., gt=0)
    source: str = Field(default="manual_research_input", min_length=1)

    @field_validator("source")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("source must not be blank")
        return normalized


class XauRangeDeskOiWallInput(XauBaseModel):
    wall_id: str
    futures_level: float = Field(..., gt=0)
    wall_type: XauWallType = XauWallType.UNKNOWN
    open_interest: float | None = Field(default=None, ge=0)
    oi_change: float | None = None
    volume: float | None = Field(default=None, ge=0)
    source: str = Field(default="manual_research_input", min_length=1)

    @field_validator("wall_id", "source")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("wall text fields must not be blank")
        return normalized


class XauRangeDeskPlanRequest(XauBaseModel):
    session_date: date | None = None
    traded_instrument: str = "XAUUSD"
    futures_symbol: str = "GC"
    future_reference_price: float = Field(..., gt=0)
    traded_reference_price: float = Field(..., gt=0)
    session_open_price: float | None = Field(default=None, gt=0)
    levels: list[XauRangeDeskLevelInput] = Field(default_factory=list)
    oi_walls: list[XauRangeDeskOiWallInput] = Field(default_factory=list)
    research_only_acknowledged: bool = True

    @field_validator("traded_instrument", "futures_symbol")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("instrument text fields must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_research_only(self) -> XauRangeDeskPlanRequest:
        if not self.research_only_acknowledged:
            raise ValueError("Range Desk planning is research-only and must be acknowledged")
        labels = [level.label for level in self.levels]
        if len(labels) != len(set(labels)):
            raise ValueError("range desk level labels must be unique")
        return self


class XauRangeDeskBasisSnapshot(XauBaseModel):
    future_reference_price: float = Field(..., gt=0)
    traded_reference_price: float = Field(..., gt=0)
    diff_points: float
    traded_offset: float
    formula: str


class XauRangeDeskMappedLevel(XauBaseModel):
    label: XauRangeDeskLevelKind
    futures_level: float = Field(..., gt=0)
    mapped_traded_level: float = Field(..., gt=0)
    distance_from_traded_reference: float
    source: str


class XauRangeDeskMappedWall(XauBaseModel):
    wall_id: str
    wall_type: XauWallType
    futures_level: float = Field(..., gt=0)
    mapped_traded_level: float = Field(..., gt=0)
    distance_from_traded_reference: float
    open_interest: float | None = Field(default=None, ge=0)
    oi_change: float | None = None
    volume: float | None = Field(default=None, ge=0)
    source: str


class XauRangeDeskZone(XauBaseModel):
    zone: XauRangeDeskZoneKind
    lower_traded_level: float | None = None
    upper_traded_level: float | None = None
    meaning: str

    @field_validator("meaning")
    @classmethod
    def normalize_meaning(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("zone meaning must not be blank")
        return normalized


class XauRangeDeskTargetPlan(XauBaseModel):
    side: str
    target_1: float | None = None
    target_2: float | None = None
    target_3: float | None = None
    invalidation_reference: float | None = None
    planning_note: str

    @field_validator("side", "planning_note")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("target plan text fields must not be blank")
        return normalized


class XauRangeDeskPlan(XauBaseModel):
    session_date: date | None = None
    traded_instrument: str
    futures_symbol: str
    readiness: XauRangeDeskReadiness
    basis_snapshot: XauRangeDeskBasisSnapshot
    block_size_points: float | None = Field(default=None, gt=0)
    futures_levels: list[XauRangeDeskMappedLevel] = Field(default_factory=list)
    traded_levels: list[XauRangeDeskMappedLevel] = Field(default_factory=list)
    mapped_oi_walls: list[XauRangeDeskMappedWall] = Field(default_factory=list)
    zones: list[XauRangeDeskZone] = Field(default_factory=list)
    target_plans: list[XauRangeDeskTargetPlan] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    no_signal_reasons: list[str] = Field(
        default_factory=lambda: [RANGE_DESK_NO_SIGNAL_REASON]
    )
    research_only: bool = True
    signal_allowed: bool = False

    @field_validator(
        "missing_inputs",
        "limitations",
        "no_signal_reasons",
    )
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        return _dedupe(values)

    @model_validator(mode="after")
    def validate_research_only_state(self) -> XauRangeDeskPlan:
        if self.signal_allowed:
            raise ValueError("Range Desk plans cannot enable signals")
        if not self.research_only:
            raise ValueError("Range Desk plans must remain research_only")
        if not self.no_signal_reasons:
            raise ValueError("Range Desk plans require no_signal_reasons")
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
    "RANGE_DESK_NO_SIGNAL_REASON",
    "XauRangeDeskBasisSnapshot",
    "XauRangeDeskLevelInput",
    "XauRangeDeskLevelKind",
    "XauRangeDeskMappedLevel",
    "XauRangeDeskMappedWall",
    "XauRangeDeskOiWallInput",
    "XauRangeDeskPlan",
    "XauRangeDeskPlanRequest",
    "XauRangeDeskReadiness",
    "XauRangeDeskTargetPlan",
    "XauRangeDeskZone",
    "XauRangeDeskZoneKind",
]
