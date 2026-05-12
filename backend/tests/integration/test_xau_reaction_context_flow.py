from datetime import UTC, datetime

import pytest

from src.models.xau_reaction import (
    XauAcceptanceInput,
    XauFreshnessState,
    XauInitialMoveDirection,
    XauIntradayFreshnessInput,
    XauIvEdgeState,
    XauOpenRegimeInput,
    XauOpenSide,
    XauReactionLabel,
    XauReactionReportRequest,
    XauRewardRiskState,
    XauVolRegimeInput,
    XauVrpRegime,
)
from src.xau_reaction.orchestration import (
    XauReactionReportOrchestrator,
    classify_source_report_reactions,
)
from tests.helpers.test_xau_reaction_data import sample_feature006_xau_report


def test_orchestration_computes_context_states_and_feeds_classifier():
    source_report = sample_feature006_xau_report()
    request = _full_context_request()
    orchestrator = XauReactionReportOrchestrator()

    context_bundle = orchestrator.build_context(request=request, source_report=source_report)
    rows = orchestrator.classify_source_report(
        request=request,
        source_report=source_report,
    )

    assert context_bundle.freshness_state.state == XauFreshnessState.VALID
    assert context_bundle.vol_regime_state.vrp == pytest.approx(0.04)
    assert context_bundle.vol_regime_state.vrp_regime == XauVrpRegime.IV_PREMIUM
    assert context_bundle.vol_regime_state.iv_edge_state == XauIvEdgeState.INSIDE
    assert context_bundle.open_regime_state.open_side == XauOpenSide.ABOVE_OPEN
    assert context_bundle.acceptance_states["wall_2400_call"].confirmed_breakout is True

    assert len(rows) == 1
    row = rows[0]
    assert row.reaction_label == XauReactionLabel.BREAKOUT_CANDIDATE
    assert row.wall_id == "wall_2400_call"
    assert row.zone_id == "zone_2400"
    assert row.freshness_state.state == XauFreshnessState.VALID
    assert row.acceptance_state is not None
    assert row.acceptance_state.confirmed_breakout is True

    risk_plans = orchestrator.plan_source_report_risk(
        request=request,
        source_report=source_report,
    )
    assert len(risk_plans) == 1
    assert risk_plans[0].reaction_id == row.reaction_id
    assert risk_plans[0].rr_state == XauRewardRiskState.BELOW_MINIMUM


def test_orchestration_missing_context_inputs_return_safe_no_trade_rows():
    source_report = sample_feature006_xau_report()
    request = XauReactionReportRequest(
        source_report_id=source_report.report_id,
        current_price=2405.0,
        current_timestamp=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
        research_only_acknowledged=True,
    )

    rows = classify_source_report_reactions(request=request, source_report=source_report)

    assert len(rows) == 1
    row = rows[0]
    assert row.reaction_label == XauReactionLabel.NO_TRADE
    assert row.acceptance_state is None
    reasons = " ".join(row.no_trade_reasons).lower()
    assert "freshness" in reasons
    assert "volatility" in reasons
    assert "opening" in reasons


def test_orchestration_reaction_outputs_avoid_directional_or_ordering_language():
    source_report = sample_feature006_xau_report()
    rows = classify_source_report_reactions(
        request=_full_context_request(),
        source_report=source_report,
    )

    assert rows
    for row in rows:
        payload_text = row.model_dump_json().lower()
        assert "buy" not in payload_text
        assert "sell" not in payload_text
        assert "execution" not in payload_text
        assert "research" in payload_text


def _full_context_request() -> XauReactionReportRequest:
    return XauReactionReportRequest(
        source_report_id="xau_vol_oi_synthetic_20260512",
        current_price=2405.0,
        current_timestamp=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
        freshness_input=XauIntradayFreshnessInput(
            intraday_timestamp=datetime(2026, 5, 12, 9, 55, tzinfo=UTC),
            current_timestamp=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
            total_intraday_contracts=12500.0,
            min_contract_threshold=1000.0,
            max_allowed_age_minutes=30,
            session_flag="regular",
        ),
        vol_regime_input=XauVolRegimeInput(
            implied_volatility=0.16,
            realized_volatility=0.12,
            price=2405.0,
            iv_lower=2378.0,
            iv_upper=2428.0,
            rv_lower=2388.0,
            rv_upper=2420.0,
        ),
        open_regime_input=XauOpenRegimeInput(
            session_open=2398.0,
            current_price=2405.0,
            initial_move_direction=XauInitialMoveDirection.UP,
            crossed_open_after_initial_move=False,
            acceptance_beyond_open=False,
        ),
        acceptance_inputs=[
            XauAcceptanceInput(
                wall_id="wall_2400_call",
                zone_id="zone_2400",
                wall_level=2393.0,
                high=2408.0,
                low=2392.0,
                close=2405.0,
                next_bar_open=2406.0,
                buffer_points=2.0,
            )
        ],
        max_total_risk_per_idea=0.01,
        max_recovery_legs=1,
        minimum_rr=1.0,
        wall_buffer_points=2.0,
        research_only_acknowledged=True,
    )
