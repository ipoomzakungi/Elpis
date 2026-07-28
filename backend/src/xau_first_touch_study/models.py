from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class TimeAnchor(StrEnum):
    T0_DTE_080 = "T0_DTE_080"
    T1_CME_SETTLEMENT = "T1_CME_SETTLEMENT"
    T2_BANGKOK_0700 = "T2_BANGKOK_0700"


class MappingMode(StrEnum):
    DISTANCE_REANCHORED = "distance_reanchored"
    SAME_TIME_REFERENCE_BASIS = "same_time_reference_basis"


class CountingMode(StrEnum):
    AGGREGATED = "aggregated_first_touch_per_tier"
    SIDE_SPECIFIC = "side_specific_first_touch"


class EventSide(StrEnum):
    LOWER_LONG = "lower_long"
    UPPER_SHORT = "upper_short"


class FirstPassageStatus(StrEnum):
    TP_FIRST = "tp_first"
    SL_FIRST = "sl_first"
    SESSION_END_UNRESOLVED = "session_end_unresolved"
    SAME_BAR_AMBIGUOUS = "same_bar_ambiguous"
    UNAVAILABLE = "unavailable"


class ShadowState(StrEnum):
    DATA_BLOCKED = "DATA_BLOCKED"
    PLAN_READY = "PLAN_READY"
    WAITING_FOR_FIRST_TOUCH = "WAITING_FOR_FIRST_TOUCH"
    FIRST_TOUCH_1SD_CONTROL = "FIRST_TOUCH_1SD_CONTROL"
    FIRST_TOUCH_2SD_ARMED = "FIRST_TOUCH_2SD_ARMED"
    FIRST_TOUCH_3SD_ARMED = "FIRST_TOUCH_3SD_ARMED"
    SHADOW_POSITION_OPEN = "SHADOW_POSITION_OPEN"
    TP_HIT = "TP_HIT"
    SL_HIT = "SL_HIT"
    AMBIGUOUS = "AMBIGUOUS"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    TIER_LOCKED = "TIER_LOCKED"


@dataclass(frozen=True)
class SourceSnapshot:
    snapshot_id: str
    session_date: date
    observed_at: datetime
    series: str
    kind: str
    source_dte: float
    future_reference: float
    atm_iv: float | None
    iv_change: float | None
    future_change: float | None
    activity_total: float
    ranges: dict[int, tuple[float, float]]
    strike_rows: list[dict[str, Any]] = field(default_factory=list)
    expiry: date | None = None
    calendar_dte: float | None = None
    trading_session_dte: float | None = None


@dataclass(frozen=True)
class SnapshotSelection:
    anchor: TimeAnchor
    snapshot: SourceSnapshot
    activation_at: datetime
    selection_reason: str
    target_at: datetime | None
    dte_error: float
    strict_dte_eligible: bool


@dataclass(frozen=True)
class MappedPlan:
    plan_id: str
    session_date: date
    anchor: TimeAnchor
    mapping_mode: MappingMode
    selection: SnapshotSelection
    planning_xau_timestamp: datetime
    planning_xau_price: float
    source_xau_timestamp: datetime
    source_xau_price: float
    source_gap_seconds: float
    mapping_quality: str
    closed_bar_status: str
    basis_points: float | None
    mapped_levels: dict[int, tuple[float, float]]
    one_sd_points: float
    oi_hard_feature_allowed: bool
    research_only: bool = True
    signal_allowed: bool = False
    order_submission_allowed: bool = False


@dataclass(frozen=True)
class FirstTouchEvent:
    event_id: str
    plan_id: str
    session_date: date
    anchor: TimeAnchor
    mapping_mode: MappingMode
    counting_mode: CountingMode
    tier: int
    side: EventSide
    boundary: float
    touch_timestamp: datetime
    touch_bar_index: int
    source_series: str
    source_dte: float
    selected_snapshot_at: datetime
    repeated_touch_count: int
    one_sd_points: float
    context: dict[str, Any] = field(default_factory=dict)
    first_touch: bool = True
    tiers_are_nested: bool = True
    research_only: bool = True
    signal_allowed: bool = False
    order_submission_allowed: bool = False


@dataclass(frozen=True)
class EventOutcome:
    event_id: str
    session_date: date
    tier: int
    side: EventSide
    anchor: TimeAnchor
    mapping_mode: MappingMode
    label: str
    status: str
    success: bool | None
    tp_points: float | None
    sl_points: float | None
    cost_points: float
    gross_points: float | None
    net_points: float | None
    mfe_points: float | None
    mae_points: float | None
    maximum_adverse_before_reversal: float | None
    resolved_at: datetime | None
    minutes_to_resolution: float | None
    same_bar_ambiguous: bool
    include_in_expectancy: bool
    research_only: bool = True
    signal_allowed: bool = False
    order_submission_allowed: bool = False


def as_record(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: as_record(getattr(value, key)) for key in value.__dataclass_fields__}
    if isinstance(value, dict):
        return {str(key): as_record(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_record(item) for item in value]
    return value
