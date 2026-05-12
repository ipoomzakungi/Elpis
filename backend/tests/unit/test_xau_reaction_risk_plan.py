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
    XauRewardRiskState,
    XauRvExtensionState,
    XauVolRegimeResult,
    XauVrpRegime,
)
from src.xau_reaction.risk_plan import plan_bounded_research_risk


def test_risk_planner_creates_bounded_annotation_for_candidate_reaction():
    reaction = _reaction(
        reaction_label=XauReactionLabel.REVERSAL_CANDIDATE,
        invalidation_level=2390.0,
        target_level_1=2410.0,
        target_level_2=2420.0,
    )

    plans = plan_bounded_research_risk(
        reactions=[reaction],
        risk_config=_risk_config(reference_price=2400.0, minimum_rr=1.0),
    )

    assert len(plans) == 1
    plan = plans[0]
    assert plan.plan_id == f"risk_{reaction.reaction_id}"
    assert plan.reaction_id == reaction.reaction_id
    assert plan.reaction_label == XauReactionLabel.REVERSAL_CANDIDATE
    assert plan.entry_condition_text is not None
    assert "research annotation" in plan.entry_condition_text.lower()
    assert "candidate" in plan.entry_condition_text.lower()
    assert plan.invalidation_level == 2390.0
    assert plan.stop_buffer_points == 2.0
    assert plan.target_1 == 2410.0
    assert plan.target_2 == 2420.0
    assert plan.max_total_risk_per_idea == 0.01
    assert plan.max_recovery_legs == 1
    assert plan.minimum_rr == 1.0
    assert plan.rr_state == XauRewardRiskState.MEETS_MINIMUM
    assert plan.cancel_conditions
    assert any("invalidation" in note.lower() for note in plan.risk_notes)


def test_risk_planner_omits_no_trade_entry_and_target_plan():
    reaction = _reaction(
        reaction_label=XauReactionLabel.NO_TRADE,
        no_trade_reasons=["Synthetic stale context blocks candidate review."],
        confidence_label=XauConfidenceLabel.BLOCKED,
        invalidation_level=None,
        target_level_1=None,
        target_level_2=None,
    )

    plans = plan_bounded_research_risk(
        reactions=[reaction],
        risk_config=_risk_config(reference_price=2400.0),
    )

    assert plans == []


def test_risk_planner_caps_recovery_legs_and_marks_below_minimum_rr():
    reaction = _reaction(
        reaction_label=XauReactionLabel.BREAKOUT_CANDIDATE,
        invalidation_level=2390.0,
        target_level_1=2402.0,
        target_level_2=2404.0,
    )

    plans = plan_bounded_research_risk(
        reactions=[reaction],
        risk_config=_risk_config(
            reference_price=2400.0,
            max_total_risk_per_idea=0.005,
            max_recovery_legs=5,
            absolute_max_recovery_legs=2,
            minimum_rr=1.5,
        ),
    )

    assert len(plans) == 1
    plan = plans[0]
    assert plan.max_recovery_legs == 2
    assert plan.max_total_risk_per_idea == 0.005
    assert plan.rr_state == XauRewardRiskState.BELOW_MINIMUM
    notes = " ".join(plan.risk_notes).lower()
    assert "0.50%" in notes
    assert "bounded" in notes
    assert "below" in notes


def test_risk_planner_marks_rr_unavailable_when_reference_or_levels_are_missing():
    reaction = _reaction(
        reaction_label=XauReactionLabel.PIN_MAGNET,
        invalidation_level=None,
        target_level_1=2393.0,
        target_level_2=None,
    )

    plans = plan_bounded_research_risk(
        reactions=[reaction],
        risk_config=_risk_config(reference_price=None, minimum_rr=1.5),
    )

    assert len(plans) == 1
    assert plans[0].rr_state == XauRewardRiskState.UNAVAILABLE
    assert any("unavailable" in note.lower() for note in plans[0].risk_notes)


def test_risk_planner_cancel_conditions_reflect_context_risks():
    reaction = _reaction(
        reaction_label=XauReactionLabel.SQUEEZE_RISK,
        freshness_state=_freshness(XauFreshnessState.STALE),
        vol_regime_state=_vol_regime(iv_edge_state=XauIvEdgeState.BEYOND_EDGE),
        open_regime_state=_open_regime(XauOpenFlipState.CROSSED_WITHOUT_ACCEPTANCE),
        acceptance_state=_acceptance(failed_breakout=True),
        event_risk_state=XauEventRiskState.BLOCKED,
    )

    plan = plan_bounded_research_risk(
        reactions=[reaction],
        risk_config=_risk_config(reference_price=2400.0),
    )[0]
    cancel_text = " ".join(plan.cancel_conditions).lower()

    assert "freshness" in cancel_text
    assert "acceptance" in cancel_text
    assert "volatility" in cancel_text
    assert "open-regime" in cancel_text
    assert "event-risk" in cancel_text


def test_risk_plan_text_avoids_forbidden_wording():
    reaction = _reaction(
        reaction_label=XauReactionLabel.VACUUM_TO_NEXT_WALL,
        invalidation_level=2390.0,
        target_level_1=2410.0,
        target_level_2=2420.0,
    )

    plans = plan_bounded_research_risk(
        reactions=[reaction],
        risk_config=_risk_config(reference_price=2400.0),
    )

    forbidden_terms = [
        "buy",
        "sell",
        "execute",
        "execution",
        "live",
        "guaranteed",
        "profitable",
        "safe",
        "signal",
        "martingale",
        "unlimited",
        "averaging",
    ]
    for plan in plans:
        payload_text = plan.model_dump_json().lower()
        for forbidden in forbidden_terms:
            assert forbidden not in payload_text
        assert "research annotation" in payload_text
        assert "candidate" in payload_text
        assert "cancel condition" in payload_text


def _risk_config(
    *,
    reference_price: float | None,
    max_total_risk_per_idea: float | None = 0.01,
    max_recovery_legs: int = 1,
    absolute_max_recovery_legs: int = 2,
    minimum_rr: float | None = 1.0,
) -> dict[str, object]:
    return {
        "reference_price": reference_price,
        "max_total_risk_per_idea": max_total_risk_per_idea,
        "max_recovery_legs": max_recovery_legs,
        "absolute_max_recovery_legs": absolute_max_recovery_legs,
        "minimum_rr": minimum_rr,
        "stop_buffer_points": 2.0,
    }


def _reaction(
    *,
    reaction_label: XauReactionLabel,
    reaction_id: str = "reaction_xau_vol_oi_synthetic_20260512_wall_2400_call",
    confidence_label: XauConfidenceLabel = XauConfidenceLabel.MEDIUM,
    invalidation_level: float | None = 2390.0,
    target_level_1: float | None = 2410.0,
    target_level_2: float | None = 2420.0,
    no_trade_reasons: list[str] | None = None,
    freshness_state: XauFreshnessResult | None = None,
    vol_regime_state: XauVolRegimeResult | None = None,
    open_regime_state: XauOpenRegimeResult | None = None,
    acceptance_state: XauAcceptanceResult | None = None,
    event_risk_state: XauEventRiskState = XauEventRiskState.CLEAR,
) -> XauReactionRow:
    return XauReactionRow(
        reaction_id=reaction_id,
        source_report_id="xau_vol_oi_synthetic_20260512",
        wall_id="wall_2400_call",
        zone_id="zone_2400",
        reaction_label=reaction_label,
        confidence_label=confidence_label,
        explanation_notes=["Synthetic reaction row for risk planner tests."],
        no_trade_reasons=no_trade_reasons or [],
        invalidation_level=invalidation_level,
        target_level_1=target_level_1,
        target_level_2=target_level_2,
        next_wall_reference="wall_2420_call",
        freshness_state=freshness_state or _freshness(XauFreshnessState.VALID),
        vol_regime_state=vol_regime_state or _vol_regime(),
        open_regime_state=open_regime_state or _open_regime(),
        acceptance_state=acceptance_state or _acceptance(),
        event_risk_state=event_risk_state,
        research_only_warning="XAU reaction outputs are research annotations only.",
    )


def _freshness(state: XauFreshnessState) -> XauFreshnessResult:
    return XauFreshnessResult(
        state=state,
        age_minutes=5.0 if state == XauFreshnessState.VALID else 120.0,
        confidence_label=XauConfidenceLabel.HIGH
        if state == XauFreshnessState.VALID
        else XauConfidenceLabel.BLOCKED,
        no_trade_reason=None if state == XauFreshnessState.VALID else f"{state.value} context.",
        notes=[f"Synthetic {state.value} freshness context."],
    )


def _vol_regime(
    *,
    iv_edge_state: XauIvEdgeState = XauIvEdgeState.INSIDE,
) -> XauVolRegimeResult:
    return XauVolRegimeResult(
        realized_volatility=0.12,
        vrp=0.04,
        vrp_regime=XauVrpRegime.IV_PREMIUM,
        iv_edge_state=iv_edge_state,
        rv_extension_state=XauRvExtensionState.INSIDE,
        confidence_label=XauConfidenceLabel.MEDIUM,
        notes=["Synthetic volatility context."],
    )


def _open_regime(
    flip_state: XauOpenFlipState = XauOpenFlipState.NO_FLIP,
) -> XauOpenRegimeResult:
    return XauOpenRegimeResult(
        open_side=XauOpenSide.ABOVE_OPEN,
        open_distance_points=7.0,
        open_flip_state=flip_state,
        open_as_support_or_resistance=XauOpenSupportResistance.SUPPORT_TEST,
        confidence_label=XauConfidenceLabel.HIGH,
        notes=["Synthetic open context."],
    )


def _acceptance(*, failed_breakout: bool = False) -> XauAcceptanceResult:
    return XauAcceptanceResult(
        wall_id="wall_2400_call",
        zone_id="zone_2400",
        accepted_beyond_wall=not failed_breakout,
        wick_rejection=False,
        failed_breakout=failed_breakout,
        confirmed_breakout=not failed_breakout,
        direction=XauAcceptanceDirection.ABOVE,
        confidence_label=XauConfidenceLabel.HIGH,
        notes=["Synthetic acceptance context."],
    )
