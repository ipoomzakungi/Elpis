from collections.abc import Mapping, Sequence
from typing import Any

from src.models.xau_reaction import (
    XauEventRiskState,
    XauFreshnessState,
    XauIvEdgeState,
    XauOpenFlipState,
    XauReactionLabel,
    XauReactionRow,
    XauRewardRiskState,
    XauRiskPlan,
    XauVrpRegime,
)


def plan_bounded_research_risk(
    *,
    reactions: Sequence[XauReactionRow],
    risk_config: Mapping[str, Any] | None = None,
) -> list[XauRiskPlan]:
    """Create bounded research annotations for non-NO_TRADE reaction rows."""

    config = risk_config or {}
    return [
        _plan_for_reaction(reaction, config=config)
        for reaction in reactions
        if reaction.reaction_label != XauReactionLabel.NO_TRADE
    ]


def create_risk_plan_id(*, reaction_id: str) -> str:
    """Create a stable risk-plan id linked to a reaction row."""

    return f"risk_{reaction_id}"


def _plan_for_reaction(
    reaction: XauReactionRow,
    *,
    config: Mapping[str, Any],
) -> XauRiskPlan:
    rr_state = _reward_risk_state(reaction, config=config)
    max_recovery_legs = _bounded_recovery_legs(config)
    return XauRiskPlan(
        plan_id=create_risk_plan_id(reaction_id=reaction.reaction_id),
        reaction_id=reaction.reaction_id,
        reaction_label=reaction.reaction_label,
        entry_condition_text=_entry_condition_text(reaction),
        invalidation_level=reaction.invalidation_level,
        stop_buffer_points=_stop_buffer_points(config),
        target_1=reaction.target_level_1,
        target_2=reaction.target_level_2,
        max_total_risk_per_idea=_optional_float(config.get("max_total_risk_per_idea")),
        max_recovery_legs=max_recovery_legs,
        minimum_rr=_optional_float(config.get("minimum_rr")),
        rr_state=rr_state,
        cancel_conditions=_cancel_conditions(reaction),
        risk_notes=_risk_notes(
            reaction=reaction,
            config=config,
            max_recovery_legs=max_recovery_legs,
            rr_state=rr_state,
        ),
    )


def _entry_condition_text(reaction: XauReactionRow) -> str:
    label = reaction.reaction_label.value.lower().replace("_", " ")
    return (
        f"Research annotation: observe the {label} only while invalidation "
        "and cancel conditions remain intact."
    )


def _bounded_recovery_legs(config: Mapping[str, Any]) -> int:
    requested = _optional_int(config.get("max_recovery_legs"))
    absolute = _optional_int(config.get("absolute_max_recovery_legs"))
    if requested is None:
        requested = 0
    if absolute is None:
        absolute = requested
    return max(0, min(requested, absolute))


def _stop_buffer_points(config: Mapping[str, Any]) -> float:
    value = _optional_float(config.get("stop_buffer_points"))
    if value is None:
        value = _optional_float(config.get("wall_buffer_points"))
    return max(0.0, value or 0.0)


def _reward_risk_state(
    reaction: XauReactionRow,
    *,
    config: Mapping[str, Any],
) -> XauRewardRiskState:
    minimum_rr = _optional_float(config.get("minimum_rr"))
    if minimum_rr is None:
        return XauRewardRiskState.UNAVAILABLE

    reference_price = _optional_float(config.get("reference_price"))
    invalidation = reaction.invalidation_level
    target = reaction.target_level_1
    if reference_price is None or invalidation is None or target is None:
        return XauRewardRiskState.UNAVAILABLE

    risk_points = abs(reference_price - invalidation)
    reward_points = abs(target - reference_price)
    if risk_points <= 0 or reward_points <= 0:
        return XauRewardRiskState.UNAVAILABLE
    if reward_points / risk_points >= minimum_rr:
        return XauRewardRiskState.MEETS_MINIMUM
    return XauRewardRiskState.BELOW_MINIMUM


def _cancel_conditions(reaction: XauReactionRow) -> list[str]:
    conditions = [
        "Cancel condition: invalidation reference is reached or context changes.",
        "Cancel condition: freshness becomes stale, prior-day, unknown, or thin.",
    ]
    if reaction.freshness_state.state != XauFreshnessState.VALID:
        conditions.append("Cancel condition: freshness currently weakens the candidate.")

    conditions.extend(_acceptance_cancel_conditions(reaction))

    if reaction.vol_regime_state.iv_edge_state in {
        XauIvEdgeState.AT_EDGE,
        XauIvEdgeState.BEYOND_EDGE,
    }:
        conditions.append("Cancel condition: volatility stress changes the candidate context.")
    if reaction.vol_regime_state.vrp_regime == XauVrpRegime.UNKNOWN:
        conditions.append("Cancel condition: volatility context becomes unavailable.")

    if reaction.open_regime_state.open_flip_state in {
        XauOpenFlipState.CROSSED_WITHOUT_ACCEPTANCE,
        XauOpenFlipState.UNKNOWN,
    }:
        conditions.append("Cancel condition: open-regime context conflicts with the candidate.")

    if reaction.event_risk_state in {XauEventRiskState.ELEVATED, XauEventRiskState.BLOCKED}:
        conditions.append("Cancel condition: event-risk state blocks or distorts observation.")
    else:
        conditions.append("Cancel condition: event-risk state changes to blocked.")

    return conditions


def _acceptance_cancel_conditions(reaction: XauReactionRow) -> list[str]:
    acceptance = reaction.acceptance_state
    if acceptance is None:
        return ["Cancel condition: candle acceptance observation is unavailable."]
    if acceptance.failed_breakout:
        return ["Cancel condition: candle acceptance fails to hold beyond the wall."]
    if _is_continuation_label(reaction.reaction_label) and acceptance.wick_rejection:
        return ["Cancel condition: candle rejection conflicts with the candidate."]
    if (
        reaction.reaction_label == XauReactionLabel.REVERSAL_CANDIDATE
        and acceptance.confirmed_breakout
    ):
        return ["Cancel condition: candle acceptance conflicts with rejection context."]
    return ["Cancel condition: candle state changes away from the observed candidate."]


def _is_continuation_label(reaction_label: XauReactionLabel) -> bool:
    return reaction_label in {
        XauReactionLabel.BREAKOUT_CANDIDATE,
        XauReactionLabel.SQUEEZE_RISK,
        XauReactionLabel.VACUUM_TO_NEXT_WALL,
    }


def _risk_notes(
    *,
    reaction: XauReactionRow,
    config: Mapping[str, Any],
    max_recovery_legs: int,
    rr_state: XauRewardRiskState,
) -> list[str]:
    notes = [
        "Research annotation only; candidate review requires independent review.",
        "Use the invalidation reference before continuing candidate review.",
        f"Recovery legs are bounded at {max_recovery_legs}; additional legs are excluded.",
    ]

    max_total_risk = _optional_float(config.get("max_total_risk_per_idea"))
    if max_total_risk is None:
        notes.append("Max total risk cap is unavailable; candidate remains observation only.")
    else:
        notes.append(f"Max total risk per idea capped at {max_total_risk:.2%}.")

    notes.append(_rr_note(rr_state))
    if reaction.target_level_1 is None:
        notes.append("Target 1 reference is unavailable.")
    if reaction.target_level_2 is None:
        notes.append("Target 2 reference is unavailable.")
    return notes


def _rr_note(rr_state: XauRewardRiskState) -> str:
    if rr_state == XauRewardRiskState.MEETS_MINIMUM:
        return "Reward/risk observation meets configured minimum."
    if rr_state == XauRewardRiskState.BELOW_MINIMUM:
        return "Reward/risk observation is below configured minimum."
    return "Reward/risk observation is unavailable from supplied levels."


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
