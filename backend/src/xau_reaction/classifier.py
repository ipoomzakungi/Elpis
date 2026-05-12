import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from src.models.xau_reaction import (
    XauAcceptanceDirection,
    XauAcceptanceResult,
    XauConfidenceLabel,
    XauEventRiskState,
    XauFreshnessResult,
    XauFreshnessState,
    XauIvEdgeState,
    XauOpenFlipState,
    XauOpenRegimeResult,
    XauOpenSide,
    XauOpenSupportResistance,
    XauReactionLabel,
    XauReactionRow,
    XauRvExtensionState,
    XauVolRegimeResult,
    XauVrpRegime,
)

RESEARCH_ONLY_WARNING = "XAU reaction outputs are research annotations only."
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")


def classify_reaction_rows(
    *,
    source_report_id: str,
    walls: Sequence[Any],
    zones: Sequence[Any],
    context: Mapping[str, Any] | None = None,
) -> list[XauReactionRow]:
    """Classify XAU wall reactions as deterministic research annotations only."""

    classifier_context = context or {}
    freshness_state = _freshness_state(classifier_context)
    vol_regime_state = _vol_regime_state(classifier_context)
    open_regime_state = _open_regime_state(classifier_context)
    event_risk_state = _event_risk_state(classifier_context)

    if not walls:
        return [
            _make_row(
                source_report_id=source_report_id,
                row_key="missing_source_context",
                reaction_label=XauReactionLabel.NO_TRADE,
                confidence_label=XauConfidenceLabel.BLOCKED,
                freshness_state=freshness_state,
                vol_regime_state=vol_regime_state,
                open_regime_state=open_regime_state,
                event_risk_state=event_risk_state,
                explanation_notes=[
                    "Research-only classifier annotation; source wall context is unavailable."
                ],
                no_trade_reasons=["Missing source context: no usable wall rows."],
            )
        ]

    rows: list[XauReactionRow] = []
    for index, wall in enumerate(walls):
        wall_id = _wall_id(wall, index=index)
        zone = find_zone_for_wall(zones, wall_id=wall_id)
        acceptance_state = _acceptance_state(classifier_context, wall_id=wall_id)
        no_trade_reasons = _hard_no_trade_reasons(
            wall=wall,
            context=classifier_context,
            freshness_state=freshness_state,
            vol_regime_state=vol_regime_state,
            open_regime_state=open_regime_state,
            event_risk_state=event_risk_state,
        )

        if no_trade_reasons:
            rows.append(
                _make_row(
                    source_report_id=source_report_id,
                    row_key=wall_id,
                    wall_id=wall_id,
                    zone_id=_zone_id(zone),
                    reaction_label=XauReactionLabel.NO_TRADE,
                    confidence_label=XauConfidenceLabel.BLOCKED,
                    freshness_state=freshness_state,
                    vol_regime_state=vol_regime_state,
                    open_regime_state=open_regime_state,
                    acceptance_state=acceptance_state,
                    event_risk_state=event_risk_state,
                    explanation_notes=[
                        "Research-only classifier annotation; hard context gate blocked "
                        "classification."
                    ],
                    no_trade_reasons=no_trade_reasons,
                )
            )
            continue

        rows.append(
            _classify_wall(
                source_report_id=source_report_id,
                wall=wall,
                wall_id=wall_id,
                zone_id=_zone_id(zone),
                context=classifier_context,
                freshness_state=freshness_state,
                vol_regime_state=vol_regime_state,
                open_regime_state=open_regime_state,
                acceptance_state=acceptance_state,
                event_risk_state=event_risk_state,
            )
        )

    return rows


def create_reaction_row_id(*, source_report_id: str, row_key: str) -> str:
    """Create a deterministic filesystem-safe reaction row id."""

    return _safe_id(f"reaction_{source_report_id}_{row_key}")


def find_zone_for_wall(zones: Sequence[Any], *, wall_id: str) -> Any | None:
    """Return the first source zone linked to the wall, preserving feature 006 traceability."""

    for zone in zones:
        linked_wall_ids = getattr(zone, "linked_wall_ids", None) or []
        if wall_id in linked_wall_ids:
            return zone
    return None


def _classify_wall(
    *,
    source_report_id: str,
    wall: Any,
    wall_id: str,
    zone_id: str | None,
    context: Mapping[str, Any],
    freshness_state: XauFreshnessResult,
    vol_regime_state: XauVolRegimeResult,
    open_regime_state: XauOpenRegimeResult,
    acceptance_state: XauAcceptanceResult | None,
    event_risk_state: XauEventRiskState,
) -> XauReactionRow:
    if _is_pin_magnet(wall=wall, context=context, acceptance_state=acceptance_state):
        return _candidate_row(
            source_report_id=source_report_id,
            wall=wall,
            wall_id=wall_id,
            zone_id=zone_id,
            reaction_label=XauReactionLabel.PIN_MAGNET,
            confidence_label=XauConfidenceLabel.MEDIUM,
            freshness_state=freshness_state,
            vol_regime_state=vol_regime_state,
            open_regime_state=open_regime_state,
            acceptance_state=acceptance_state,
            event_risk_state=event_risk_state,
            context=context,
            explanation_notes=[
                "Research-only classifier annotation; near-expiry high open interest is close "
                "to spot inside the 1SD range.",
                "Acceptance away from the wall is unclear, so the wall remains a magnet context.",
            ],
        )

    if _is_squeeze_risk(
        context=context,
        vol_regime_state=vol_regime_state,
        acceptance_state=acceptance_state,
    ):
        return _candidate_row(
            source_report_id=source_report_id,
            wall=wall,
            wall_id=wall_id,
            zone_id=zone_id,
            reaction_label=XauReactionLabel.SQUEEZE_RISK,
            confidence_label=XauConfidenceLabel.MEDIUM,
            freshness_state=freshness_state,
            vol_regime_state=vol_regime_state,
            open_regime_state=open_regime_state,
            acceptance_state=acceptance_state,
            event_risk_state=event_risk_state,
            context=context,
            explanation_notes=[
                "Research-only classifier annotation; accepted wall break has IV edge stress "
                "or flow expansion evidence.",
                "This is a stress context, not a standalone direction instruction.",
            ],
        )

    if _is_vacuum_to_next_wall(context=context, acceptance_state=acceptance_state):
        return _candidate_row(
            source_report_id=source_report_id,
            wall=wall,
            wall_id=wall_id,
            zone_id=zone_id,
            reaction_label=XauReactionLabel.VACUUM_TO_NEXT_WALL,
            confidence_label=XauConfidenceLabel.MEDIUM,
            freshness_state=freshness_state,
            vol_regime_state=vol_regime_state,
            open_regime_state=open_regime_state,
            acceptance_state=acceptance_state,
            event_risk_state=event_risk_state,
            context=context,
            explanation_notes=[
                "Research-only classifier annotation; accepted move entered a low-OI gap "
                "with a distant next-wall reference."
            ],
        )

    if _is_breakout_candidate(acceptance_state=acceptance_state):
        return _candidate_row(
            source_report_id=source_report_id,
            wall=wall,
            wall_id=wall_id,
            zone_id=zone_id,
            reaction_label=XauReactionLabel.BREAKOUT_CANDIDATE,
            confidence_label=XauConfidenceLabel.MEDIUM,
            freshness_state=freshness_state,
            vol_regime_state=vol_regime_state,
            open_regime_state=open_regime_state,
            acceptance_state=acceptance_state,
            event_risk_state=event_risk_state,
            context=context,
            explanation_notes=[
                "Research-only classifier annotation; close beyond the wall plus next-bar "
                "hold confirmed acceptance."
            ],
        )

    if _is_reversal_candidate(
        wall=wall,
        context=context,
        freshness_state=freshness_state,
        acceptance_state=acceptance_state,
    ):
        explanation_notes = [
            "Research-only classifier annotation; high-score wall showed rejection evidence "
            "near stretched sigma context."
        ]
        if acceptance_state and acceptance_state.failed_breakout:
            explanation_notes.append(
                "Failed breakout evidence supports reversal candidate context."
            )
        elif acceptance_state and acceptance_state.wick_rejection:
            explanation_notes.append("Wick rejection evidence supports reversal candidate context.")
        return _candidate_row(
            source_report_id=source_report_id,
            wall=wall,
            wall_id=wall_id,
            zone_id=zone_id,
            reaction_label=XauReactionLabel.REVERSAL_CANDIDATE,
            confidence_label=_reversal_confidence(wall),
            freshness_state=freshness_state,
            vol_regime_state=vol_regime_state,
            open_regime_state=open_regime_state,
            acceptance_state=acceptance_state,
            event_risk_state=event_risk_state,
            context=context,
            explanation_notes=explanation_notes,
        )

    return _make_row(
        source_report_id=source_report_id,
        row_key=wall_id,
        wall_id=wall_id,
        zone_id=zone_id,
        reaction_label=XauReactionLabel.NO_TRADE,
        confidence_label=XauConfidenceLabel.LOW,
        freshness_state=freshness_state,
        vol_regime_state=vol_regime_state,
        open_regime_state=open_regime_state,
        acceptance_state=acceptance_state,
        event_risk_state=event_risk_state,
        explanation_notes=[
            "Research-only classifier annotation; OI wall evidence did not meet a candidate "
            "gate."
        ],
        no_trade_reasons=["No deterministic reaction candidate met the required evidence gates."],
    )


def _candidate_row(
    *,
    source_report_id: str,
    wall: Any,
    wall_id: str,
    zone_id: str | None,
    reaction_label: XauReactionLabel,
    confidence_label: XauConfidenceLabel,
    freshness_state: XauFreshnessResult,
    vol_regime_state: XauVolRegimeResult,
    open_regime_state: XauOpenRegimeResult,
    acceptance_state: XauAcceptanceResult | None,
    event_risk_state: XauEventRiskState,
    context: Mapping[str, Any],
    explanation_notes: list[str],
) -> XauReactionRow:
    invalidation_level, target_level_1, target_level_2 = _candidate_levels(
        wall=wall,
        reaction_label=reaction_label,
        acceptance_state=acceptance_state,
        context=context,
    )
    return _make_row(
        source_report_id=source_report_id,
        row_key=wall_id,
        wall_id=wall_id,
        zone_id=zone_id,
        reaction_label=reaction_label,
        confidence_label=confidence_label,
        freshness_state=freshness_state,
        vol_regime_state=vol_regime_state,
        open_regime_state=open_regime_state,
        acceptance_state=acceptance_state,
        event_risk_state=event_risk_state,
        explanation_notes=explanation_notes,
        invalidation_level=invalidation_level,
        target_level_1=target_level_1,
        target_level_2=target_level_2,
        next_wall_reference=str(_ctx_value(context, "next_wall_reference", "unavailable")),
    )


def _make_row(
    *,
    source_report_id: str,
    row_key: str,
    reaction_label: XauReactionLabel,
    confidence_label: XauConfidenceLabel,
    freshness_state: XauFreshnessResult,
    vol_regime_state: XauVolRegimeResult,
    open_regime_state: XauOpenRegimeResult,
    wall_id: str | None = None,
    zone_id: str | None = None,
    acceptance_state: XauAcceptanceResult | None = None,
    event_risk_state: XauEventRiskState = XauEventRiskState.UNKNOWN,
    explanation_notes: list[str] | None = None,
    no_trade_reasons: list[str] | None = None,
    invalidation_level: float | None = None,
    target_level_1: float | None = None,
    target_level_2: float | None = None,
    next_wall_reference: str | None = None,
) -> XauReactionRow:
    return XauReactionRow(
        reaction_id=create_reaction_row_id(source_report_id=source_report_id, row_key=row_key),
        source_report_id=source_report_id,
        wall_id=wall_id,
        zone_id=zone_id,
        reaction_label=reaction_label,
        confidence_label=confidence_label,
        explanation_notes=explanation_notes or [],
        no_trade_reasons=no_trade_reasons or [],
        invalidation_level=invalidation_level,
        target_level_1=target_level_1,
        target_level_2=target_level_2,
        next_wall_reference=next_wall_reference,
        freshness_state=freshness_state,
        vol_regime_state=vol_regime_state,
        open_regime_state=open_regime_state,
        acceptance_state=acceptance_state,
        event_risk_state=event_risk_state,
        research_only_warning=RESEARCH_ONLY_WARNING,
    )


def _hard_no_trade_reasons(
    *,
    wall: Any,
    context: Mapping[str, Any],
    freshness_state: XauFreshnessResult,
    vol_regime_state: XauVolRegimeResult,
    open_regime_state: XauOpenRegimeResult,
    event_risk_state: XauEventRiskState,
) -> list[str]:
    reasons: list[str] = []
    if freshness_state.state == XauFreshnessState.STALE:
        reasons.append("Freshness state is STALE.")
    elif freshness_state.state == XauFreshnessState.PRIOR_DAY:
        reasons.append("Freshness state is PRIOR_DAY.")
    elif freshness_state.state == XauFreshnessState.UNKNOWN:
        reasons.append("Freshness state is UNKNOWN.")
    elif freshness_state.state == XauFreshnessState.THIN and _bool_ctx(
        context,
        "thin_is_hard_block",
        default=True,
    ):
        reasons.append("Freshness state is THIN and configured as a hard block.")

    if not _basis_available(wall=wall, context=context):
        reasons.append("Basis mapping is unavailable.")
    if event_risk_state == XauEventRiskState.BLOCKED:
        reasons.append("Event-risk state is BLOCKED.")
    if _bool_ctx(context, "conflicting_evidence", default=False):
        reasons.append("Classifier evidence is conflicting.")
    if vol_regime_state.vrp_regime == XauVrpRegime.UNKNOWN:
        reasons.append("Volatility regime context is unavailable.")
    if open_regime_state.open_side == XauOpenSide.UNKNOWN:
        reasons.append("Opening-price regime context is unavailable.")
    return reasons


def _is_pin_magnet(
    *,
    wall: Any,
    context: Mapping[str, Any],
    acceptance_state: XauAcceptanceResult | None,
) -> bool:
    if not _acceptance_unclear(acceptance_state):
        return False
    return (
        _near_expiry(wall=wall, context=context)
        and _near_spot(wall=wall, context=context)
        and _inside_one_sd(context)
        and _wall_open_interest(wall) >= _float_ctx(context, "pin_min_open_interest", 10000.0)
    )


def _is_squeeze_risk(
    *,
    context: Mapping[str, Any],
    vol_regime_state: XauVolRegimeResult,
    acceptance_state: XauAcceptanceResult | None,
) -> bool:
    if not _accepted_move(acceptance_state):
        return False
    iv_edge_stress = vol_regime_state.iv_edge_state in {
        XauIvEdgeState.AT_EDGE,
        XauIvEdgeState.BEYOND_EDGE,
    }
    return iv_edge_stress or _bool_ctx(context, "flow_expansion", default=False)


def _is_vacuum_to_next_wall(
    *,
    context: Mapping[str, Any],
    acceptance_state: XauAcceptanceResult | None,
) -> bool:
    return (
        _accepted_move(acceptance_state)
        and _bool_ctx(context, "low_oi_gap", default=False)
        and _float_ctx(context, "next_wall_distance", 0.0)
        >= _float_ctx(context, "distant_next_wall_threshold", 20.0)
    )


def _is_breakout_candidate(*, acceptance_state: XauAcceptanceResult | None) -> bool:
    return acceptance_state is not None and acceptance_state.confirmed_breakout


def _is_reversal_candidate(
    *,
    wall: Any,
    context: Mapping[str, Any],
    freshness_state: XauFreshnessResult,
    acceptance_state: XauAcceptanceResult | None,
) -> bool:
    rejection = acceptance_state is not None and (
        acceptance_state.wick_rejection or acceptance_state.failed_breakout
    )
    return (
        freshness_state.state == XauFreshnessState.VALID
        and _wall_score(wall) >= _float_ctx(context, "high_wall_score_threshold", 0.35)
        and rejection
        and abs(_float_ctx(context, "sigma_position", 0.0))
        >= _float_ctx(context, "stretched_sigma_threshold", 1.0)
    )


def _candidate_levels(
    *,
    wall: Any,
    reaction_label: XauReactionLabel,
    acceptance_state: XauAcceptanceResult | None,
    context: Mapping[str, Any],
) -> tuple[float | None, float | None, float | None]:
    wall_level = _wall_level(wall)
    if wall_level is None:
        return None, _target_level_1(context), _target_level_2(context)

    buffer_points = _float_ctx(context, "wall_buffer_points", 2.0)
    current_price = _optional_float(_ctx_value(context, "current_price"))
    next_wall_distance = _optional_float(_ctx_value(context, "next_wall_distance"))

    direction = acceptance_state.direction if acceptance_state else XauAcceptanceDirection.UNKNOWN
    sign = -1.0 if direction == XauAcceptanceDirection.BELOW else 1.0

    if reaction_label == XauReactionLabel.PIN_MAGNET:
        invalidation_sign = 1.0 if current_price is None or current_price >= wall_level else -1.0
        invalidation_level = wall_level + invalidation_sign * buffer_points
        return invalidation_level, wall_level, _target_level_2(context, fallback=current_price)

    if reaction_label in {
        XauReactionLabel.BREAKOUT_CANDIDATE,
        XauReactionLabel.SQUEEZE_RISK,
        XauReactionLabel.VACUUM_TO_NEXT_WALL,
    }:
        invalidation_level = wall_level - sign * buffer_points
        target_1 = _target_level_1(context)
        if target_1 is None and next_wall_distance is not None:
            target_1 = wall_level + sign * max(next_wall_distance / 2.0, buffer_points)
        target_2 = _target_level_2(context)
        if target_2 is None and next_wall_distance is not None:
            target_2 = wall_level + sign * next_wall_distance
        return invalidation_level, target_1 or wall_level, target_2 or target_1 or wall_level

    invalidation_level = wall_level + sign * buffer_points
    target_1 = _target_level_1(context, fallback=current_price)
    target_2 = _target_level_2(context, fallback=target_1)
    return invalidation_level, target_1 or wall_level, target_2 or target_1 or wall_level


def _freshness_state(context: Mapping[str, Any]) -> XauFreshnessResult:
    value = _ctx_value(context, "freshness_state")
    if isinstance(value, XauFreshnessResult):
        return value
    return XauFreshnessResult(
        state=XauFreshnessState.UNKNOWN,
        age_minutes=None,
        confidence_label=XauConfidenceLabel.UNKNOWN,
        no_trade_reason="Freshness context is unavailable.",
        notes=["Freshness context is unavailable."],
    )


def _vol_regime_state(context: Mapping[str, Any]) -> XauVolRegimeResult:
    value = _ctx_value(context, "vol_regime_state")
    if isinstance(value, XauVolRegimeResult):
        return value
    return XauVolRegimeResult(
        realized_volatility=None,
        vrp=None,
        vrp_regime=XauVrpRegime.UNKNOWN,
        iv_edge_state=XauIvEdgeState.UNKNOWN,
        rv_extension_state=XauRvExtensionState.UNKNOWN,
        confidence_label=XauConfidenceLabel.UNKNOWN,
        notes=["Volatility regime context is unavailable."],
    )


def _open_regime_state(context: Mapping[str, Any]) -> XauOpenRegimeResult:
    value = _ctx_value(context, "open_regime_state")
    if isinstance(value, XauOpenRegimeResult):
        return value
    return XauOpenRegimeResult(
        open_side=XauOpenSide.UNKNOWN,
        open_distance_points=None,
        open_flip_state=XauOpenFlipState.UNKNOWN,
        open_as_support_or_resistance=XauOpenSupportResistance.UNKNOWN,
        confidence_label=XauConfidenceLabel.UNKNOWN,
        notes=["Opening-price regime context is unavailable."],
    )


def _acceptance_state(
    context: Mapping[str, Any],
    *,
    wall_id: str,
) -> XauAcceptanceResult | None:
    acceptance_states = _ctx_value(context, "acceptance_states")
    if isinstance(acceptance_states, Mapping):
        value = acceptance_states.get(wall_id)
        return value if isinstance(value, XauAcceptanceResult) else None
    value = _ctx_value(context, "acceptance_state")
    return value if isinstance(value, XauAcceptanceResult) else None


def _event_risk_state(context: Mapping[str, Any]) -> XauEventRiskState:
    value = _ctx_value(context, "event_risk_state", XauEventRiskState.UNKNOWN)
    if isinstance(value, XauEventRiskState):
        return value
    try:
        return XauEventRiskState(str(value))
    except ValueError:
        return XauEventRiskState.UNKNOWN


def _basis_available(*, wall: Any, context: Mapping[str, Any]) -> bool:
    context_value = _ctx_value(context, "basis_available")
    if context_value is not None:
        return bool(context_value)
    return _wall_level(wall) is not None and getattr(wall, "basis", None) is not None


def _acceptance_unclear(acceptance_state: XauAcceptanceResult | None) -> bool:
    if acceptance_state is None:
        return True
    return not (
        acceptance_state.accepted_beyond_wall
        or acceptance_state.confirmed_breakout
        or acceptance_state.wick_rejection
        or acceptance_state.failed_breakout
    )


def _accepted_move(acceptance_state: XauAcceptanceResult | None) -> bool:
    return acceptance_state is not None and (
        acceptance_state.accepted_beyond_wall or acceptance_state.confirmed_breakout
    )


def _inside_one_sd(context: Mapping[str, Any]) -> bool:
    explicit = _ctx_value(context, "inside_1sd")
    if explicit is not None:
        return bool(explicit)
    return abs(_float_ctx(context, "sigma_position", 999.0)) <= 1.0


def _near_spot(*, wall: Any, context: Mapping[str, Any]) -> bool:
    explicit = _ctx_value(context, "near_spot")
    if explicit is not None:
        return bool(explicit)
    current_price = _optional_float(_ctx_value(context, "current_price"))
    wall_level = _wall_level(wall)
    if current_price is None or wall_level is None:
        return False
    return abs(current_price - wall_level) <= _float_ctx(context, "near_spot_threshold", 5.0)


def _near_expiry(*, wall: Any, context: Mapping[str, Any]) -> bool:
    explicit = _ctx_value(context, "near_expiry")
    if explicit is not None:
        return bool(explicit)
    days_to_expiry = _optional_float(getattr(wall, "days_to_expiry", None))
    if days_to_expiry is None:
        expiry = getattr(wall, "expiry", None)
        current_date = _context_date(context)
        if isinstance(expiry, date) and current_date is not None:
            days_to_expiry = float((expiry - current_date).days)
    return days_to_expiry is not None and days_to_expiry <= _float_ctx(
        context,
        "near_expiry_days",
        7.0,
    )


def _context_date(context: Mapping[str, Any]) -> date | None:
    value = _ctx_value(context, "current_timestamp")
    if isinstance(value, datetime):
        return value.date()
    value = _ctx_value(context, "session_date")
    if isinstance(value, date):
        return value
    return None


def _target_level_1(
    context: Mapping[str, Any],
    *,
    fallback: float | None = None,
) -> float | None:
    return _optional_float(_ctx_value(context, "target_level_1")) or fallback


def _target_level_2(
    context: Mapping[str, Any],
    *,
    fallback: float | None = None,
) -> float | None:
    return _optional_float(_ctx_value(context, "target_level_2")) or fallback


def _wall_id(wall: Any, *, index: int) -> str:
    value = getattr(wall, "wall_id", None)
    return _safe_id(str(value)) if value else f"wall_{index}"


def _zone_id(zone: Any | None) -> str | None:
    value = getattr(zone, "zone_id", None) if zone is not None else None
    return str(value) if value else None


def _wall_level(wall: Any) -> float | None:
    return _optional_float(getattr(wall, "spot_equivalent_level", None)) or _optional_float(
        getattr(wall, "level", None)
    )


def _wall_score(wall: Any) -> float:
    return _optional_float(getattr(wall, "wall_score", None)) or 0.0


def _wall_open_interest(wall: Any) -> float:
    return _optional_float(getattr(wall, "open_interest", None)) or 0.0


def _reversal_confidence(wall: Any) -> XauConfidenceLabel:
    return XauConfidenceLabel.HIGH if _wall_score(wall) >= 0.5 else XauConfidenceLabel.MEDIUM


def _ctx_value(context: Mapping[str, Any], key: str, default: Any = None) -> Any:
    return context.get(key, default)


def _bool_ctx(context: Mapping[str, Any], key: str, *, default: bool) -> bool:
    value = _ctx_value(context, key)
    return default if value is None else bool(value)


def _float_ctx(context: Mapping[str, Any], key: str, default: float) -> float:
    value = _optional_float(_ctx_value(context, key))
    return default if value is None else value


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_id(value: str) -> str:
    normalized = _SAFE_ID_RE.sub("_", value.strip())
    normalized = normalized.strip("_")
    return normalized or "unknown"
