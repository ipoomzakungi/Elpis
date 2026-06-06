from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TypeVar

from src.models.xau import XauDailyStructuralMap, XauDailyStructuralMapWall
from src.models.xau_sd_oi_candidate import (
    RESEARCH_ONLY_NO_SIGNAL_REASON,
    XauSdOiCandidate,
    XauSdOiCandidateInvalidation,
    XauSdOiCandidateReason,
    XauSdOiCandidateSet,
    XauSdOiCandidateSide,
    XauSdOiCandidateTarget,
    XauSdOiConfirmationState,
    XauSdOiFlowState,
    XauSdOiIvState,
    XauSdOiReadinessState,
    XauSdOiStretchZone,
    XauSdOiWallState,
)

DERIVED_3_5SD_LIMITATION = (
    "3.5SD references were derived from 1SD band geometry because native 3.5SD "
    "bands were unavailable."
)
BASIS_MISSING_REASON_CODE = "basis_missing"
EXPECTED_RANGE_MISSING_REASON_CODE = "expected_range_missing"
TRADED_PRICE_MISSING_REASON_CODE = "traded_price_missing"
SESSION_OPEN_MISSING_REASON_CODE = "session_open_missing"

_EnumT = TypeVar("_EnumT", bound=StrEnum)


def build_xau_sd_oi_candidate_set(
    daily_map: XauDailyStructuralMap,
    *,
    timestamp: datetime,
    traded_price: float | None,
    gc_price: float | None = None,
    confirmation_state: XauSdOiConfirmationState | str = (
        XauSdOiConfirmationState.UNAVAILABLE
    ),
    iv_state: XauSdOiIvState | str = XauSdOiIvState.UNAVAILABLE,
    flow_state: XauSdOiFlowState | str = XauSdOiFlowState.UNAVAILABLE,
) -> XauSdOiCandidateSet:
    """Build one research-only SD/OI candidate for a structural map timestamp."""

    confirmation = _coerce_enum(XauSdOiConfirmationState, confirmation_state)
    iv = _coerce_enum(XauSdOiIvState, iv_state)
    flow = _coerce_enum(XauSdOiFlowState, flow_state)
    lower_3_5sd, upper_3_5sd, derived_3_5sd_limitation = _derive_3_5sd(daily_map)
    limitations = _dedupe(
        [
            *daily_map.limitations,
            *([derived_3_5sd_limitation] if derived_3_5sd_limitation else []),
        ]
    )
    stretch_zone = _stretch_zone(daily_map, traded_price)
    nearest_wall = _nearest_mapped_wall(daily_map, traded_price)
    oi_wall_state = (
        XauSdOiWallState.NEAREST_WALL_PRESENT
        if nearest_wall is not None
        else XauSdOiWallState.NO_MAPPED_WALL
    )

    missing_reasons = _missing_context_reasons(daily_map, traded_price)
    if missing_reasons:
        candidate = _candidate(
            daily_map=daily_map,
            timestamp=timestamp,
            traded_price=traded_price,
            gc_price=gc_price,
            lower_3_5sd=lower_3_5sd,
            upper_3_5sd=upper_3_5sd,
            nearest_wall=nearest_wall,
            side=XauSdOiCandidateSide.NO_TRADE,
            stretch_zone=stretch_zone,
            confirmation_state=confirmation,
            iv_state=iv,
            flow_state=flow,
            oi_wall_state=oi_wall_state,
            readiness_state=XauSdOiReadinessState.BLOCKED_MISSING_CONTEXT,
            reasons=missing_reasons,
            limitations=limitations,
        )
        return _candidate_set(daily_map, timestamp, candidate, limitations=limitations)

    if _breakout_risk(daily_map, traded_price, confirmation, iv, flow):
        reasons = [
            _reason(
                "breakout_risk",
                "Price or IV/flow/acceptance context indicates breakout risk.",
                severity="warning",
            )
        ]
        candidate = _candidate(
            daily_map=daily_map,
            timestamp=timestamp,
            traded_price=traded_price,
            gc_price=gc_price,
            lower_3_5sd=lower_3_5sd,
            upper_3_5sd=upper_3_5sd,
            nearest_wall=nearest_wall,
            side=XauSdOiCandidateSide.BREAKOUT_RISK,
            stretch_zone=stretch_zone,
            confirmation_state=confirmation,
            iv_state=iv,
            flow_state=flow,
            oi_wall_state=oi_wall_state,
            readiness_state=XauSdOiReadinessState.BREAKOUT_RISK,
            reasons=reasons,
            limitations=limitations,
        )
        return _candidate_set(daily_map, timestamp, candidate, limitations=limitations)

    if stretch_zone == XauSdOiStretchZone.UPPER_2SD_TO_3SD and _reversion_confirmed(
        confirmation, iv, flow
    ):
        upper_1sd = _adjusted_band(daily_map, daily_map.upper_1sd)
        range_midpoint = _range_midpoint(daily_map)
        targets = [
            _target("target_1_upper_1sd", upper_1sd, "expected_range_upper_1sd"),
            _target(
                "target_2_session_open",
                daily_map.session_open_price,
                "session_open",
            ),
            _target("target_3_range_midpoint", range_midpoint, "expected_range_midpoint"),
        ]
        invalidations = [
            _invalidation(
                "upper_3_5sd_stop_reference",
                upper_3_5sd,
                "derived_3_5sd_reference",
            )
        ]
        candidate = _candidate(
            daily_map=daily_map,
            timestamp=timestamp,
            traded_price=traded_price,
            gc_price=gc_price,
            lower_3_5sd=lower_3_5sd,
            upper_3_5sd=upper_3_5sd,
            nearest_wall=nearest_wall,
            side=XauSdOiCandidateSide.SHORT_REVERSION_CANDIDATE,
            stretch_zone=stretch_zone,
            confirmation_state=confirmation,
            iv_state=iv,
            flow_state=flow,
            oi_wall_state=oi_wall_state,
            readiness_state=XauSdOiReadinessState.CANDIDATE_READY,
            reasons=[
                _reason(
                    "upper_2sd_to_3sd_rejection",
                    "Upper 2SD-3SD stretch has rejection context without breakout confirmation.",
                )
            ],
            targets=targets,
            invalidations=invalidations,
            target_1=upper_1sd,
            target_2=daily_map.session_open_price,
            target_3=range_midpoint,
            stop_reference=upper_3_5sd,
            limitations=limitations,
        )
        return _candidate_set(daily_map, timestamp, candidate, limitations=limitations)

    if stretch_zone == XauSdOiStretchZone.LOWER_2SD_TO_3SD and _reversion_confirmed(
        confirmation, iv, flow
    ):
        lower_1sd = _adjusted_band(daily_map, daily_map.lower_1sd)
        range_midpoint = _range_midpoint(daily_map)
        targets = [
            _target("target_1_lower_1sd", lower_1sd, "expected_range_lower_1sd"),
            _target(
                "target_2_session_open",
                daily_map.session_open_price,
                "session_open",
            ),
            _target("target_3_range_midpoint", range_midpoint, "expected_range_midpoint"),
        ]
        invalidations = [
            _invalidation(
                "lower_3_5sd_stop_reference",
                lower_3_5sd,
                "derived_3_5sd_reference",
            )
        ]
        candidate = _candidate(
            daily_map=daily_map,
            timestamp=timestamp,
            traded_price=traded_price,
            gc_price=gc_price,
            lower_3_5sd=lower_3_5sd,
            upper_3_5sd=upper_3_5sd,
            nearest_wall=nearest_wall,
            side=XauSdOiCandidateSide.LONG_REVERSION_CANDIDATE,
            stretch_zone=stretch_zone,
            confirmation_state=confirmation,
            iv_state=iv,
            flow_state=flow,
            oi_wall_state=oi_wall_state,
            readiness_state=XauSdOiReadinessState.CANDIDATE_READY,
            reasons=[
                _reason(
                    "lower_2sd_to_3sd_rejection",
                    "Lower 2SD-3SD stretch has rejection context without breakout confirmation.",
                )
            ],
            targets=targets,
            invalidations=invalidations,
            target_1=lower_1sd,
            target_2=daily_map.session_open_price,
            target_3=range_midpoint,
            stop_reference=lower_3_5sd,
            limitations=limitations,
        )
        return _candidate_set(daily_map, timestamp, candidate, limitations=limitations)

    reasons = [
        _reason(
            "inside_normal_range_monitor"
            if stretch_zone == XauSdOiStretchZone.INSIDE_NORMAL_RANGE
            else "reversion_confirmation_absent",
            "Context is monitor-only; no research candidate is promoted.",
        )
    ]
    candidate = _candidate(
        daily_map=daily_map,
        timestamp=timestamp,
        traded_price=traded_price,
        gc_price=gc_price,
        lower_3_5sd=lower_3_5sd,
        upper_3_5sd=upper_3_5sd,
        nearest_wall=nearest_wall,
        side=XauSdOiCandidateSide.NO_TRADE,
        stretch_zone=stretch_zone,
        confirmation_state=confirmation,
        iv_state=iv,
        flow_state=flow,
        oi_wall_state=oi_wall_state,
        readiness_state=XauSdOiReadinessState.MONITOR_ONLY,
        reasons=reasons,
        limitations=limitations,
    )
    return _candidate_set(daily_map, timestamp, candidate, limitations=limitations)


def _candidate(
    *,
    daily_map: XauDailyStructuralMap,
    timestamp: datetime,
    traded_price: float | None,
    gc_price: float | None,
    lower_3_5sd: float | None,
    upper_3_5sd: float | None,
    nearest_wall: XauDailyStructuralMapWall | None,
    side: XauSdOiCandidateSide,
    stretch_zone: XauSdOiStretchZone,
    confirmation_state: XauSdOiConfirmationState,
    iv_state: XauSdOiIvState,
    flow_state: XauSdOiFlowState,
    oi_wall_state: XauSdOiWallState,
    readiness_state: XauSdOiReadinessState,
    reasons: list[XauSdOiCandidateReason],
    limitations: list[str],
    targets: list[XauSdOiCandidateTarget] | None = None,
    invalidations: list[XauSdOiCandidateInvalidation] | None = None,
    target_1: float | None = None,
    target_2: float | None = None,
    target_3: float | None = None,
    stop_reference: float | None = None,
) -> XauSdOiCandidate:
    return XauSdOiCandidate(
        candidate_id=_candidate_id(daily_map.map_id, timestamp, side),
        map_id=daily_map.map_id,
        wall_id=nearest_wall.wall_id if nearest_wall else None,
        session_date=daily_map.session_date,
        timestamp=timestamp,
        side=side,
        stretch_zone=stretch_zone,
        traded_price=traded_price,
        gc_price=gc_price or daily_map.reference_futures_price,
        basis=daily_map.basis,
        nearest_wall_level=nearest_wall.spot_equivalent_level if nearest_wall else None,
        nearest_wall_distance=(
            nearest_wall.spot_equivalent_level - traded_price
            if nearest_wall and traded_price is not None
            else None
        ),
        nearest_wall_oi_change=nearest_wall.oi_change if nearest_wall else None,
        nearest_wall_volume=nearest_wall.volume if nearest_wall else None,
        expected_range_source=(
            daily_map.expected_range_source.value if daily_map.expected_range_source else None
        ),
        lower_1sd=_adjusted_band(daily_map, daily_map.lower_1sd),
        upper_1sd=_adjusted_band(daily_map, daily_map.upper_1sd),
        lower_2sd=_adjusted_band(daily_map, daily_map.lower_2sd),
        upper_2sd=_adjusted_band(daily_map, daily_map.upper_2sd),
        lower_3sd=_adjusted_band(daily_map, daily_map.lower_3sd),
        upper_3sd=_adjusted_band(daily_map, daily_map.upper_3sd),
        lower_3_5sd=lower_3_5sd,
        upper_3_5sd=upper_3_5sd,
        target_1=target_1,
        target_2=target_2,
        target_3=target_3,
        stop_reference=stop_reference,
        confirmation_state=confirmation_state,
        iv_state=iv_state,
        flow_state=flow_state,
        oi_wall_state=oi_wall_state,
        readiness_state=readiness_state,
        reasons=reasons,
        targets=targets or [],
        invalidations=invalidations or [],
        no_signal_reasons=[RESEARCH_ONLY_NO_SIGNAL_REASON],
        limitations=limitations,
        signal_allowed=False,
        research_only=True,
    )


def _candidate_set(
    daily_map: XauDailyStructuralMap,
    timestamp: datetime,
    candidate: XauSdOiCandidate,
    *,
    limitations: list[str],
) -> XauSdOiCandidateSet:
    return XauSdOiCandidateSet(
        map_id=daily_map.map_id,
        session_date=daily_map.session_date,
        timestamp=timestamp,
        candidate_count=1,
        candidates=[candidate],
        no_signal_reasons=[RESEARCH_ONLY_NO_SIGNAL_REASON],
        limitations=limitations,
        signal_allowed=False,
        research_only=True,
    )


def _missing_context_reasons(
    daily_map: XauDailyStructuralMap,
    traded_price: float | None,
) -> list[XauSdOiCandidateReason]:
    reasons: list[XauSdOiCandidateReason] = []
    if not daily_map.basis_mapping_available or daily_map.basis is None:
        reasons.append(
            _reason(
                BASIS_MISSING_REASON_CODE,
                "Basis mapping is unavailable; candidate classification is blocked.",
                severity="warning",
            )
        )
    if not _expected_range_complete(daily_map):
        reasons.append(
            _reason(
                EXPECTED_RANGE_MISSING_REASON_CODE,
                "Expected-range context is incomplete; candidate classification is blocked.",
                severity="warning",
            )
        )
    if traded_price is None:
        reasons.append(
            _reason(
                TRADED_PRICE_MISSING_REASON_CODE,
                "Observed traded price is unavailable; candidate classification is blocked.",
                severity="warning",
            )
        )
    if not daily_map.session_open_available or daily_map.session_open_price is None:
        reasons.append(
            _reason(
                SESSION_OPEN_MISSING_REASON_CODE,
                "Session open is unavailable; candidate classification is blocked.",
                severity="warning",
            )
        )
    return reasons


def _expected_range_complete(daily_map: XauDailyStructuralMap) -> bool:
    if daily_map.expected_range_source is None:
        return False
    required = (
        daily_map.lower_1sd,
        daily_map.upper_1sd,
        daily_map.lower_2sd,
        daily_map.upper_2sd,
        daily_map.lower_3sd,
        daily_map.upper_3sd,
    )
    return all(value is not None for value in required)


def _stretch_zone(
    daily_map: XauDailyStructuralMap,
    traded_price: float | None,
) -> XauSdOiStretchZone:
    if (
        traded_price is None
        or not _basis_available(daily_map)
        or not _expected_range_complete(daily_map)
    ):
        return XauSdOiStretchZone.UNAVAILABLE
    lower_2sd = _adjusted_band(daily_map, daily_map.lower_2sd)
    upper_2sd = _adjusted_band(daily_map, daily_map.upper_2sd)
    lower_3sd = _adjusted_band(daily_map, daily_map.lower_3sd)
    upper_3sd = _adjusted_band(daily_map, daily_map.upper_3sd)
    if (
        lower_2sd is None
        or upper_2sd is None
        or lower_3sd is None
        or upper_3sd is None
    ):
        return XauSdOiStretchZone.UNAVAILABLE
    if traded_price > upper_3sd or traded_price < lower_3sd:
        return XauSdOiStretchZone.OUTSIDE_3SD
    if upper_2sd <= traded_price <= upper_3sd:
        return XauSdOiStretchZone.UPPER_2SD_TO_3SD
    if lower_3sd <= traded_price <= lower_2sd:
        return XauSdOiStretchZone.LOWER_2SD_TO_3SD
    if lower_2sd <= traded_price <= upper_2sd:
        return XauSdOiStretchZone.INSIDE_NORMAL_RANGE
    return XauSdOiStretchZone.UNAVAILABLE


def _breakout_risk(
    daily_map: XauDailyStructuralMap,
    traded_price: float | None,
    confirmation_state: XauSdOiConfirmationState,
    iv_state: XauSdOiIvState,
    flow_state: XauSdOiFlowState,
) -> bool:
    if (
        traded_price is not None
        and _basis_available(daily_map)
        and _expected_range_complete(daily_map)
    ):
        lower_3sd = _adjusted_band(daily_map, daily_map.lower_3sd)
        upper_3sd = _adjusted_band(daily_map, daily_map.upper_3sd)
        if lower_3sd is not None and upper_3sd is not None and (
            traded_price > upper_3sd or traded_price < lower_3sd
        ):
            return True
    return (
        iv_state == XauSdOiIvState.EXPANDING
        and flow_state == XauSdOiFlowState.FLOW_THROUGH_WALL
        and confirmation_state == XauSdOiConfirmationState.ACCEPTANCE
    )


def _reversion_confirmed(
    confirmation_state: XauSdOiConfirmationState,
    iv_state: XauSdOiIvState,
    flow_state: XauSdOiFlowState,
) -> bool:
    return (
        confirmation_state
        in {
            XauSdOiConfirmationState.REJECTION,
            XauSdOiConfirmationState.CLOSE_BACK_INSIDE,
        }
        and iv_state != XauSdOiIvState.EXPANDING
        and flow_state != XauSdOiFlowState.FLOW_THROUGH_WALL
    )


def _derive_3_5sd(
    daily_map: XauDailyStructuralMap,
) -> tuple[float | None, float | None, str | None]:
    lower_1sd = _adjusted_band(daily_map, daily_map.lower_1sd)
    upper_1sd = _adjusted_band(daily_map, daily_map.upper_1sd)
    if lower_1sd is None or upper_1sd is None:
        return None, None, None
    center = (lower_1sd + upper_1sd) / 2.0
    one_sd = (upper_1sd - lower_1sd) / 2.0
    if one_sd <= 0:
        return None, None, None
    return center - (3.5 * one_sd), center + (3.5 * one_sd), DERIVED_3_5SD_LIMITATION


def _nearest_mapped_wall(
    daily_map: XauDailyStructuralMap,
    traded_price: float | None,
) -> XauDailyStructuralMapWall | None:
    if traded_price is None:
        return None
    mapped_walls = [wall for wall in daily_map.walls if wall.spot_equivalent_level is not None]
    if not mapped_walls:
        return None
    return min(mapped_walls, key=lambda wall: abs(wall.spot_equivalent_level - traded_price))


def _range_midpoint(daily_map: XauDailyStructuralMap) -> float | None:
    lower_1sd = _adjusted_band(daily_map, daily_map.lower_1sd)
    upper_1sd = _adjusted_band(daily_map, daily_map.upper_1sd)
    if lower_1sd is None or upper_1sd is None:
        return None
    return (lower_1sd + upper_1sd) / 2.0


def _basis_available(daily_map: XauDailyStructuralMap) -> bool:
    return daily_map.basis_mapping_available and daily_map.basis is not None


def _adjusted_band(
    daily_map: XauDailyStructuralMap,
    level: float | None,
) -> float | None:
    if level is None:
        return None
    if not _basis_available(daily_map):
        return None
    return level - daily_map.basis


def _reason(
    reason_code: str,
    message: str,
    *,
    severity: str = "info",
) -> XauSdOiCandidateReason:
    return XauSdOiCandidateReason(
        reason_code=reason_code,
        message=message,
        severity=severity,
    )


def _target(label: str, level: float | None, source: str) -> XauSdOiCandidateTarget:
    return XauSdOiCandidateTarget(label=label, level=level, source=source)


def _invalidation(
    label: str,
    level: float | None,
    source: str,
) -> XauSdOiCandidateInvalidation:
    return XauSdOiCandidateInvalidation(label=label, level=level, source=source)


def _candidate_id(
    map_id: str,
    timestamp: datetime,
    side: XauSdOiCandidateSide,
) -> str:
    return f"{map_id}_{timestamp.strftime('%Y%m%dT%H%M%S')}_{side.value}"


def _coerce_enum(enum_type: type[_EnumT], value: _EnumT | str) -> _EnumT:
    if isinstance(value, enum_type):
        return value
    return enum_type(str(value))


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
    "BASIS_MISSING_REASON_CODE",
    "DERIVED_3_5SD_LIMITATION",
    "EXPECTED_RANGE_MISSING_REASON_CODE",
    "SESSION_OPEN_MISSING_REASON_CODE",
    "TRADED_PRICE_MISSING_REASON_CODE",
    "build_xau_sd_oi_candidate_set",
]
