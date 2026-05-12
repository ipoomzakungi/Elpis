from src.models.xau_reaction import (
    XauAcceptanceDirection,
    XauAcceptanceResult,
    XauConfidenceLabel,
    XauEventRiskState,
    XauFreshnessResult,
    XauFreshnessState,
    XauIvEdgeState,
    XauReactionLabel,
    XauVolRegimeResult,
)
from src.xau_reaction.classifier import classify_reaction_rows
from tests.helpers.test_xau_reaction_data import (
    sample_feature006_xau_report,
    sample_xau_freshness_result,
    sample_xau_open_regime_result,
    sample_xau_vol_regime_result,
)


def test_classifier_returns_reversal_candidate_from_high_score_rejection_evidence():
    row = _classify_one(
        acceptance_state=_acceptance(
            wick_rejection=True,
            direction=XauAcceptanceDirection.ABOVE,
            notes=["Synthetic wick rejection at wall."],
        ),
        sigma_position=1.35,
        next_wall_reference="wall_2420_call",
    )

    assert row.reaction_label == XauReactionLabel.REVERSAL_CANDIDATE
    assert row.confidence_label in {XauConfidenceLabel.HIGH, XauConfidenceLabel.MEDIUM}
    assert row.wall_id == "wall_2400_call"
    assert row.zone_id == "zone_2400"
    assert row.invalidation_level is not None
    assert row.target_level_1 is not None
    assert row.next_wall_reference == "wall_2420_call"
    assert any("rejection" in note.lower() for note in row.explanation_notes)


def test_classifier_treats_failed_breakout_as_reversal_rejection_evidence():
    row = _classify_one(
        acceptance_state=_acceptance(
            accepted_beyond_wall=True,
            failed_breakout=True,
            direction=XauAcceptanceDirection.ABOVE,
            notes=["Synthetic failed breakout at wall."],
        ),
        sigma_position=1.4,
    )

    assert row.reaction_label == XauReactionLabel.REVERSAL_CANDIDATE
    assert any("failed breakout" in note.lower() for note in row.explanation_notes)


def test_classifier_returns_breakout_candidate_from_confirmed_wall_acceptance():
    row = _classify_one(
        acceptance_state=_acceptance(
            accepted_beyond_wall=True,
            confirmed_breakout=True,
            direction=XauAcceptanceDirection.ABOVE,
            notes=["Synthetic confirmed breakout context."],
        ),
        sigma_position=0.8,
        next_wall_reference="wall_2425_call",
    )

    assert row.reaction_label == XauReactionLabel.BREAKOUT_CANDIDATE
    assert row.invalidation_level is not None
    assert row.target_level_1 is not None
    assert row.next_wall_reference == "wall_2425_call"


def test_classifier_returns_squeeze_risk_before_breakout_when_iv_edge_stress_exists():
    row = _classify_one(
        acceptance_state=_acceptance(
            accepted_beyond_wall=True,
            confirmed_breakout=True,
            direction=XauAcceptanceDirection.ABOVE,
        ),
        vol_regime_state=_vol_regime(iv_edge_state=XauIvEdgeState.BEYOND_EDGE),
        flow_expansion=False,
    )

    assert row.reaction_label == XauReactionLabel.SQUEEZE_RISK
    assert any("iv edge" in note.lower() for note in row.explanation_notes)


def test_classifier_returns_squeeze_risk_when_flow_expansion_confirms_accepted_break():
    row = _classify_one(
        acceptance_state=_acceptance(
            accepted_beyond_wall=True,
            confirmed_breakout=True,
            direction=XauAcceptanceDirection.ABOVE,
        ),
        flow_expansion=True,
    )

    assert row.reaction_label == XauReactionLabel.SQUEEZE_RISK
    assert any("flow expansion" in note.lower() for note in row.explanation_notes)


def test_classifier_returns_vacuum_to_next_wall_for_accepted_low_oi_gap():
    row = _classify_one(
        acceptance_state=_acceptance(
            accepted_beyond_wall=True,
            confirmed_breakout=True,
            direction=XauAcceptanceDirection.ABOVE,
        ),
        low_oi_gap=True,
        next_wall_distance=45.0,
        next_wall_reference="wall_2440_call",
    )

    assert row.reaction_label == XauReactionLabel.VACUUM_TO_NEXT_WALL
    assert row.next_wall_reference == "wall_2440_call"
    assert any("low-oi gap" in note.lower() for note in row.explanation_notes)


def test_classifier_returns_pin_magnet_for_near_expiry_high_oi_inside_one_sd():
    row = _classify_one(
        acceptance_state=_acceptance(direction=XauAcceptanceDirection.UNKNOWN),
        current_price=2394.0,
        inside_1sd=True,
        near_expiry=True,
        near_spot=True,
        sigma_position=0.2,
    )

    assert row.reaction_label == XauReactionLabel.PIN_MAGNET
    assert row.target_level_1 == 2393.0
    assert any("near-expiry" in note.lower() for note in row.explanation_notes)


def test_classifier_blocks_stale_prior_day_unknown_and_thin_freshness_states():
    for freshness_state in [
        XauFreshnessState.STALE,
        XauFreshnessState.PRIOR_DAY,
        XauFreshnessState.UNKNOWN,
        XauFreshnessState.THIN,
    ]:
        row = _classify_one(
            freshness_state=XauFreshnessResult(
                state=freshness_state,
                age_minutes=120.0,
                confidence_label=XauConfidenceLabel.BLOCKED,
                no_trade_reason=f"Synthetic {freshness_state.value} state.",
                notes=[f"Synthetic {freshness_state.value} state."],
            ),
            acceptance_state=_acceptance(
                accepted_beyond_wall=True,
                confirmed_breakout=True,
                direction=XauAcceptanceDirection.ABOVE,
            ),
        )

        assert row.reaction_label == XauReactionLabel.NO_TRADE
        assert row.confidence_label == XauConfidenceLabel.BLOCKED
        assert row.no_trade_reasons


def test_classifier_blocks_missing_source_basis_conflicts_and_event_risk():
    report = sample_feature006_xau_report()

    missing_context_rows = classify_reaction_rows(
        source_report_id=report.report_id,
        walls=[],
        zones=report.zones,
        context=_context(),
    )
    assert len(missing_context_rows) == 1
    assert missing_context_rows[0].reaction_label == XauReactionLabel.NO_TRADE
    assert "source context" in " ".join(missing_context_rows[0].no_trade_reasons).lower()

    basis_row = _classify_one(basis_available=False)
    conflict_row = _classify_one(conflicting_evidence=True)
    event_row = _classify_one(event_risk_state=XauEventRiskState.BLOCKED)

    assert basis_row.reaction_label == XauReactionLabel.NO_TRADE
    assert conflict_row.reaction_label == XauReactionLabel.NO_TRADE
    assert event_row.reaction_label == XauReactionLabel.NO_TRADE


def test_classifier_output_avoids_buy_sell_or_execution_wording():
    rows = [
        _classify_one(
            acceptance_state=_acceptance(
                wick_rejection=True,
                direction=XauAcceptanceDirection.ABOVE,
            ),
            sigma_position=1.4,
        ),
        _classify_one(
            acceptance_state=_acceptance(
                accepted_beyond_wall=True,
                confirmed_breakout=True,
                direction=XauAcceptanceDirection.ABOVE,
            ),
        ),
        _classify_one(freshness_state=_freshness(XauFreshnessState.STALE)),
    ]

    for row in rows:
        payload_text = row.model_dump_json().lower()
        assert "buy" not in payload_text
        assert "sell" not in payload_text
        assert "execution" not in payload_text
        assert "research" in payload_text


def test_classifier_uses_deterministic_priority_for_squeeze_before_vacuum_and_breakout():
    row = _classify_one(
        acceptance_state=_acceptance(
            accepted_beyond_wall=True,
            confirmed_breakout=True,
            direction=XauAcceptanceDirection.ABOVE,
        ),
        vol_regime_state=_vol_regime(iv_edge_state=XauIvEdgeState.BEYOND_EDGE),
        low_oi_gap=True,
        next_wall_distance=80.0,
        flow_expansion=True,
    )

    assert row.reaction_label == XauReactionLabel.SQUEEZE_RISK


def test_classifier_uses_pin_priority_when_acceptance_is_unclear():
    row = _classify_one(
        acceptance_state=_acceptance(direction=XauAcceptanceDirection.UNKNOWN),
        inside_1sd=True,
        near_expiry=True,
        near_spot=True,
        sigma_position=0.5,
    )

    assert row.reaction_label == XauReactionLabel.PIN_MAGNET


def test_classifier_falls_back_to_no_trade_when_evidence_is_incomplete():
    row = _classify_one(
        acceptance_state=_acceptance(direction=XauAcceptanceDirection.UNKNOWN),
        sigma_position=0.2,
        inside_1sd=False,
        near_expiry=False,
        near_spot=False,
    )

    assert row.reaction_label == XauReactionLabel.NO_TRADE
    assert row.no_trade_reasons == [
        "No deterministic reaction candidate met the required evidence gates."
    ]


def _classify_one(**context_overrides):
    report = sample_feature006_xau_report()
    rows = classify_reaction_rows(
        source_report_id=report.report_id,
        walls=report.walls,
        zones=report.zones,
        context=_context(**context_overrides),
    )
    assert len(rows) == 1
    return rows[0]


def _context(**overrides):
    context = {
        "freshness_state": sample_xau_freshness_result(),
        "vol_regime_state": sample_xau_vol_regime_result(),
        "open_regime_state": sample_xau_open_regime_result(),
        "acceptance_states": {"wall_2400_call": _acceptance()},
        "event_risk_state": XauEventRiskState.CLEAR,
        "current_price": 2405.0,
        "sigma_position": 1.25,
        "inside_1sd": False,
        "near_expiry": False,
        "near_spot": False,
        "basis_available": True,
        "conflicting_evidence": False,
        "flow_expansion": False,
        "low_oi_gap": False,
        "next_wall_distance": 27.0,
        "next_wall_reference": "wall_2420_call",
        "wall_buffer_points": 2.0,
    }
    if "acceptance_state" in overrides:
        context["acceptance_states"] = {"wall_2400_call": overrides.pop("acceptance_state")}
    context.update(overrides)
    return context


def _freshness(state: XauFreshnessState) -> XauFreshnessResult:
    return XauFreshnessResult(
        state=state,
        age_minutes=120.0 if state != XauFreshnessState.VALID else 5.0,
        confidence_label=XauConfidenceLabel.HIGH
        if state == XauFreshnessState.VALID
        else XauConfidenceLabel.BLOCKED,
        no_trade_reason=None if state == XauFreshnessState.VALID else f"{state.value} state.",
        notes=[f"Synthetic {state.value} freshness state."],
    )


def _vol_regime(iv_edge_state: XauIvEdgeState) -> XauVolRegimeResult:
    base = sample_xau_vol_regime_result()
    return base.model_copy(update={"iv_edge_state": iv_edge_state})


def _acceptance(
    *,
    accepted_beyond_wall: bool = False,
    wick_rejection: bool = False,
    failed_breakout: bool = False,
    confirmed_breakout: bool = False,
    direction: XauAcceptanceDirection = XauAcceptanceDirection.UNKNOWN,
    notes: list[str] | None = None,
) -> XauAcceptanceResult:
    return XauAcceptanceResult(
        wall_id="wall_2400_call",
        zone_id="zone_2400",
        accepted_beyond_wall=accepted_beyond_wall,
        wick_rejection=wick_rejection,
        failed_breakout=failed_breakout,
        confirmed_breakout=confirmed_breakout,
        direction=direction,
        confidence_label=XauConfidenceLabel.HIGH
        if confirmed_breakout or wick_rejection or failed_breakout
        else XauConfidenceLabel.MEDIUM,
        notes=notes or ["Synthetic neutral acceptance context."],
    )
