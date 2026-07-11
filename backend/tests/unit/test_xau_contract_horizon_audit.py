from __future__ import annotations

from datetime import date, datetime, timedelta

from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import (
    XauMappingMode,
    XauSourceClass,
    XauVol2VolRangeDeskSnapshot,
)
from src.xau_vol2vol_history_walkforward.contract_horizon_audit import (
    build_contract_alignment_audit,
    build_holding_horizon_comparison,
)
from src.xau_vol2vol_history_walkforward.planning import XauPlanningSelection


def test_alignment_audit_labels_yahoo_as_proxy_and_flags_mismatch() -> None:
    selection = _selection()
    spot = [_bar("2026-07-07T06:55:00+07:00", 100, symbol="XAUUSD")]
    proxy = [_bar("2026-07-07T06:55:00+07:00", 141, symbol="GC=F")]

    result = build_contract_alignment_audit(
        [selection],
        spot,
        proxy,
        mismatch_threshold_points=20,
    )

    row = result["observations"][0]
    assert row["futures_proxy_source_class"] == "continuous_futures_proxy"
    assert row["contract_alignment_status"] == "mismatch"
    assert row["vol2vol_spot_basis"] == 20
    assert row["yahoo_spot_proxy_basis"] == 41
    assert row["difference_between_basis_methods"] == -21
    assert row["true_basis_validation"] == "unavailable"


def test_alignment_audit_rejects_pairs_over_300_seconds() -> None:
    selection = _selection()
    stale = _bar("2026-07-07T06:49:00+07:00", 100)

    result = build_contract_alignment_audit(
        [selection],
        [stale],
        [stale.model_copy(update={"symbol": "GC=F"})],
        source_gap_limit_seconds=300,
    )

    assert result["accepted_observation_count"] == 0
    assert result["observations"][0]["source_pair_accepted"] is False


def test_horizons_are_separate_and_costs_do_not_multiply_opportunities() -> None:
    result_set = _result_set()
    bars = [
        _bar("2026-07-07T08:00:00+07:00", 110, high=111, low=109),
        _bar("2026-07-07T23:55:00+07:00", 109, high=111, low=108),
        _bar("2026-07-08T06:55:00+07:00", 105, high=106, low=104),
    ]

    result = build_holding_horizon_comparison(
        [result_set],
        bars,
        source_class=XauSourceClass.CONTINUOUS_FUTURES_PROXY,
        costs=(0.0, 1.0),
    )

    intraday, next_plan = result["experiments"]
    assert intraday["unique_market_opportunity_count"] == 1
    assert intraday["configuration_outcome_count"] == 2
    assert intraday["cost_scenario_row_count"] == 4
    assert {row["status"] for row in intraday["outcomes"]} == {"time_exit_profit"}
    assert {row["status"] for row in next_plan["outcomes"]} == {"target_hit"}
    assert next_plan["overlapping_morning_position_count"] == 0
    assert result["research_only"] is True
    assert result["signal_allowed"] is False


def _selection() -> XauPlanningSelection:
    planning_at = datetime.fromisoformat("2026-07-07T07:00:00+07:00")
    snapshot = XauVol2VolRangeDeskSnapshot(
        session_date=date(2026, 7, 7),
        observed_at=datetime.fromisoformat("2026-07-07T06:55:00+07:00"),
        series="G2N6",
        dte=0.8,
        future_open=120,
        future_buy_1sd=110,
        future_buy_2sd=100,
        future_buy_3sd=90,
        future_sell_1sd=130,
        future_sell_2sd=140,
        future_sell_3sd=150,
        cfd_open=100,
        diff=20,
    )
    return XauPlanningSelection(
        session_date=date(2026, 7, 7),
        source_session_date=date(2026, 7, 7),
        cycle_label="fixed_morning_0700",
        planning_at=planning_at,
        simulation_window_start=planning_at + timedelta(minutes=1),
        simulation_window_end=planning_at.replace(hour=23, minute=59, second=59),
        range_snapshot=snapshot,
        mapping_mode=XauMappingMode.DISTANCE_REANCHORED,
    )


def _result_set() -> dict:
    planning_at = "2026-07-07T07:00:00+07:00"
    diagnostic = {
        "session_date": "2026-07-07",
        "planning_at": planning_at,
        "selected_series": "G2N6",
        "xau_reference": 100,
        "lower_1sd": 90,
        "lower_1_5sd": 85,
        "lower_2sd": 80,
        "lower_2_5sd": 75,
        "upper_1sd": 110,
        "upper_1_5sd": 115,
        "upper_2sd": 120,
        "upper_2_5sd": 125,
    }
    return {
        "planning_mode": "fixed_morning",
        "mapping_mode": "distance_reanchored",
        "diagnostics": [diagnostic],
        "opportunities": [],
    }


def _bar(timestamp: str, close: float, *, symbol="XAUUSD", high=None, low=None):
    return XauPriceBar(
        timestamp=datetime.fromisoformat(timestamp),
        open=close,
        high=high if high is not None else close,
        low=low if low is not None else close,
        close=close,
        volume=1,
        symbol=symbol,
        timeframe="5m",
    )
