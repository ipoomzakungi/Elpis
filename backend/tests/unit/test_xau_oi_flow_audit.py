from __future__ import annotations

from datetime import date, datetime

from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import XauVol2VolStrikeSnapshot
from src.xau_vol2vol_history_walkforward.oi_flow_audit import (
    StrikeSnapshotIndex,
    _rejection_confirmation,
    build_conditional_variants,
    build_feature_state,
)


def test_plan_and_touch_states_are_separate_and_never_use_future_rows() -> None:
    index = StrikeSnapshotIndex(
        [
            _row("06:50:00", total=100, change=5),
            _row("07:30:00", total=120, change=20),
            _row("08:30:00", total=140, change=20),
            _row("06:50:00", total=50, kind="intraday_volume", change=2),
            _row("07:30:00", total=70, kind="intraday_volume", change=20),
        ]
    )
    opportunity = _opportunity()
    diagnostic = _diagnostic()

    plan = build_feature_state(
        opportunity,
        diagnostic,
        _time("07:00:00"),
        index,
    )
    touch = build_feature_state(
        opportunity,
        diagnostic,
        _time("08:00:00"),
        index,
    )

    assert plan["oi_snapshot_time"] == _time("06:50:00").isoformat()
    assert touch["oi_snapshot_time"] == _time("07:30:00").isoformat()
    assert plan["oi"]["total"] == 100
    assert touch["oi"]["total"] == 120
    assert plan["future_feature_violation"] is False
    assert touch["future_feature_violation"] is False


def test_delta_uses_previous_same_series_strike_and_preserves_source_change() -> None:
    index = StrikeSnapshotIndex(
        [
            _row("06:30:00", total=80, strike=110, change=3),
            _row("06:45:00", total=999, strike=115, change=900),
            _row("06:50:00", total=100, strike=110, change=7),
            _row("06:49:00", total=500, strike=110, series="OTHER", change=400),
        ]
    )

    state = build_feature_state(
        _opportunity(),
        _diagnostic(),
        _time("07:00:00"),
        index,
    )

    assert state["oi"]["selected_series"] == "SERIES"
    assert state["oi"]["derived_change"] == 20
    assert state["oi"]["source_provided_change"] == 7
    assert state["oi"]["change_discrepancy"] == -13


def test_mapping_modes_map_futures_strikes_to_xauusd() -> None:
    index = StrikeSnapshotIndex([_row("06:50:00", total=100, strike=110)])
    same = build_feature_state(
        _opportunity(mapping_mode="same_time_basis"),
        _diagnostic(),
        _time("07:00:00"),
        index,
    )
    reanchored = build_feature_state(
        _opportunity(mapping_mode="distance_reanchored"),
        _diagnostic(),
        _time("07:00:00"),
        index,
    )

    assert same["oi"]["mapped_xauusd_strike"] == 90
    assert reanchored["oi"]["mapped_xauusd_strike"] == 90


def test_missing_optional_sources_remain_null_and_do_not_remove_opportunity() -> None:
    state = build_feature_state(
        _opportunity(),
        _diagnostic(),
        _time("07:00:00"),
        StrikeSnapshotIndex([]),
    )

    assert state["oi"] is None
    assert state["volume"] is None
    assert state["monthly_oi"] is None
    assert state["quikstrike"] is None
    assert "daily_open_interest" in state["missing_feature_reasons"]
    assert state["research_only"] is True
    assert state["signal_allowed"] is False


def test_f1_uses_plan_state_evidence_and_cost_rows_do_not_multiply_count() -> None:
    feature = {
        **_opportunity(),
        "planning_mode": "fixed_morning",
        "mapping_mode": "same_time_basis",
        "plan_state": {
            "oi": {"top_5": True, "top_10": True, "distance_to_entry_sd": 0.1},
            "volume": {"change_direction": "stable"},
            "monthly_oi": None,
        },
        "touch_state": {"oi": {}, "volume": {}},
        "atm_vol_change": None,
    }
    coverage_state = {
        "monthly_oi": None,
        "quikstrike": None,
        "oi_snapshot_time": _time("06:50:00").isoformat(),
        "volume_snapshot_time": _time("06:50:00").isoformat(),
        "oi_feature_age_seconds": 600,
        "future_feature_violation": False,
    }
    feature["plan_state"].update(coverage_state)
    feature["touch_state"].update(coverage_state)
    outcome = {
        "opportunity_id": feature["opportunity_id"],
        "strategy_id": "A",
        "planning_mode": "fixed_morning",
        "side": "long_reversion",
        "session_date": "2026-07-07",
        "cost_points": 1.0,
        "status": "target_hit",
        "mfe_points": 5,
        "mae_points": -1,
        "net_points": 3,
    }
    backtest = {"experiments": [{"outcomes": [outcome, {**outcome, "cost_points": 0.0}]}]}

    result = build_conditional_variants([feature] * 10, backtest)

    assert result["coverage_gate_passed"] is True
    f1 = next(row for row in result["variants"] if row["variant"] == "F1")
    assert f1["unique_opportunity_count"] == 1


def test_rejection_confirmation_enters_on_next_executable_bar() -> None:
    feature = {
        **_opportunity(),
        "first_touch_time": _time("08:01:00").isoformat(),
    }
    bars = [
        _bar("08:01:00", 89, high=91, low=88),
        _bar("08:02:00", 91, high=92, low=90),
        _bar("08:04:00", 92, high=93, low=91),
        _bar("08:05:00", 93, high=94, low=92),
    ]

    confirmation = _rejection_confirmation(feature, bars)

    assert confirmation is not None
    assert confirmation["confirmation_at"] == _time("08:04:00")
    assert confirmation["entry_at"] == _time("08:05:00")
    assert confirmation["entry_price"] == 93


def _row(
    hhmmss: str,
    *,
    total: float,
    strike: float = 110,
    kind: str = "open_interest",
    series: str = "SERIES",
    change: float | None = None,
) -> XauVol2VolStrikeSnapshot:
    return XauVol2VolStrikeSnapshot(
        session_date=date(2026, 7, 7),
        observed_at=_time(hhmmss),
        series=series,
        snapshot_kind=kind,
        strike=strike,
        call=total * 0.6,
        put=total * 0.4,
        total=total,
        total_change=change,
        vol_settle=20,
        source="fixture",
    )


def _opportunity(mapping_mode: str = "same_time_basis") -> dict:
    return {
        "opportunity_id": "opp-1",
        "session_date": "2026-07-07",
        "planning_at": _time("07:00:00").isoformat(),
        "first_touch_time": _time("08:00:00").isoformat(),
        "selected_series": "SERIES",
        "entry_level": 90,
        "side": "long_reversion",
        "mapping_mode": mapping_mode,
    }


def _diagnostic() -> dict:
    return {
        "source_session_date": "2026-07-07",
        "calculated_diff": 20,
        "future_reference": 120,
        "xau_reference": 100,
        "lower_1sd": 90,
        "lower_2_5sd": 75,
        "upper_1sd": 110,
        "upper_2_5sd": 125,
    }


def _time(hhmmss: str) -> datetime:
    return datetime.fromisoformat(f"2026-07-07T{hhmmss}+07:00")


def _bar(hhmmss: str, close: float, *, high: float, low: float) -> XauPriceBar:
    return XauPriceBar(
        timestamp=_time(hhmmss),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=1,
    )
