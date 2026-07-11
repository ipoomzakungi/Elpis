from __future__ import annotations

from datetime import date, datetime, time

from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import (
    XauMappingMode,
    XauVol2VolRangeDeskSnapshot,
    XauVol2VolStrikeSnapshot,
)
from src.xau_vol2vol_history_walkforward.planning import select_planning_cycles
from src.xau_vol2vol_history_walkforward.sd_zone_audit import (
    build_preregistered_exit_backtest,
    build_sd_zone_audit,
    build_session_coverage_rows,
)


def test_source_alignment_compares_snapshot_with_xau_source_bar() -> None:
    selections, _ = _select(
        mapping_mode=XauMappingMode.SAME_TIME_BASIS,
        snapshots=[_snapshot("06:55:30", series="near", dte=0.8)],
        bars=[_bar("06:55:00", 100), _bar("07:00:00", 105), _bar("08:00:00", 110)],
    )

    selection = selections[0]
    assert selection.source_alignment_seconds == 30
    assert selection.xau_price_age_at_planning_seconds == 0
    assert selection.selected_xau_price_time == _time("06:55:00")


def test_same_time_basis_rejects_stale_source_pair() -> None:
    selections, issues = _select(
        mapping_mode=XauMappingMode.SAME_TIME_BASIS,
        snapshots=[_snapshot("06:59:00", series="near", dte=0.8)],
        bars=[_bar("06:50:00", 100), _bar("07:00:00", 105), _bar("08:00:00", 110)],
        tolerance=300,
    )

    assert selections == []
    assert issues["source_alignment_rejected_count"] == 1


def test_distance_reanchored_uses_planning_price_and_is_distinct() -> None:
    snapshots = [_snapshot("06:55:30", series="near", dte=0.8)]
    bars = [_bar("06:55:00", 100), _bar("07:00:00", 105), _bar("08:00:00", 110)]
    same, _ = _select(
        mapping_mode=XauMappingMode.SAME_TIME_BASIS,
        snapshots=snapshots,
        bars=bars,
    )
    reanchored, _ = _select(
        mapping_mode=XauMappingMode.DISTANCE_REANCHORED,
        snapshots=snapshots,
        bars=bars,
    )

    assert same[0].range_snapshot.cfd_open == 100
    assert reanchored[0].range_snapshot.cfd_open == 105
    assert same[0].range_snapshot.diff != reanchored[0].range_snapshot.diff


def test_series_selection_is_deterministic_and_covers_window() -> None:
    selections, _ = _select(
        mapping_mode=XauMappingMode.DISTANCE_REANCHORED,
        snapshots=[
            _snapshot("06:55:00", series="near", dte=0.8),
            _snapshot("06:59:00", series="far", dte=1.2),
        ],
        bars=[_bar("06:54:00", 100), _bar("07:00:00", 105), _bar("08:00:00", 110)],
    )

    assert selections[0].range_snapshot.series == "near"
    assert selections[0].series_selection_reason == (
        "nearest_positive_dte_covering_monitoring_window"
    )
    assert len(selections[0].candidate_series) == 2


def test_zone_entry_and_literal_two_sd_are_separate() -> None:
    selections, _ = _select(
        mapping_mode=XauMappingMode.DISTANCE_REANCHORED,
        snapshots=[_snapshot("06:55:00", series="near", dte=0.8)],
        bars=[_bar("06:54:00", 100), _bar("07:00:00", 105), _bar("08:00:00", 116)],
    )
    _, opportunities, _ = build_sd_zone_audit(
        selections,
        [_bar("08:00:00", 116)],
        planning_mode="fixed_morning",
    )
    short = {
        item["entry_definition"]: item
        for item in opportunities
        if item["side"] == "short_reversion"
    }

    assert short["zone_2_entry"]["entry_sd"] == 1.0
    assert short["zone_2_entry"]["touched"] is True
    assert short["literal_2sd"]["entry_sd"] == 2.0
    assert short["literal_2sd"]["touched"] is False
    diagnostics, _, summary = build_sd_zone_audit(
        selections,
        [_bar("08:00:00", 116)],
        planning_mode="fixed_morning",
    )
    assert diagnostics[0]["mapped_center_round_trip_error"] == 0
    assert diagnostics[0]["research_only"] is True
    assert diagnostics[0]["signal_allowed"] is False
    assert summary["true_basis_validation"] == "unavailable"


def test_strikes_from_an_unselected_series_are_not_mixed() -> None:
    snapshots = [
        _snapshot("06:55:00", series="near", dte=0.8),
        _snapshot("06:59:00", series="far", dte=1.2),
    ]
    strike_rows = [
        _strike("near", 110),
        _strike("far", 130),
    ]
    selections, _ = select_planning_cycles(
        range_snapshots=snapshots,
        strike_rows=strike_rows,
        bars=[_bar("06:54:00", 100), _bar("07:00:00", 105), _bar("08:00:00", 110)],
        session_date_from=date(2026, 7, 7),
        session_date_to=date(2026, 7, 7),
        planning_times=(time(7, 0),),
        timezone="Asia/Bangkok",
        planning_mode="fixed_morning",
        day_end_time=time(8, 0),
    )

    assert selections[0].range_snapshot.series == "near"
    assert {item.series for item in selections[0].strike_rows} == {"near"}


def test_rolling_plan_expires_before_next_checkpoint() -> None:
    snapshots = [
        _snapshot("06:55:00", series="near", dte=0.8),
        _snapshot("07:25:00", series="near", dte=0.78),
    ]
    bars = [
        _bar("06:54:00", 100),
        _bar("07:00:00", 105),
        _bar("07:01:00", 106),
        _bar("07:29:00", 107),
        _bar("07:30:00", 108),
        _bar("07:31:00", 109),
    ]
    selections, _ = select_planning_cycles(
        range_snapshots=snapshots,
        strike_rows=[],
        bars=bars,
        session_date_from=date(2026, 7, 7),
        session_date_to=date(2026, 7, 7),
        planning_times=(time(7, 0), time(7, 30)),
        timezone="Asia/Bangkok",
        planning_mode="rolling_30m",
        day_end_time=time(7, 31),
        mapping_mode=XauMappingMode.DISTANCE_REANCHORED,
    )

    assert selections[0].simulation_window_end.time() == time(7, 29, 59, 999999)
    assert selections[1].simulation_window_start.time() == time(7, 31)


def test_stale_rolling_snapshot_is_rejected() -> None:
    selections, issues = select_planning_cycles(
        range_snapshots=[_snapshot("06:55:00", series="near", dte=0.8)],
        strike_rows=[],
        bars=[_bar("06:54:00", 100), _bar("07:30:00", 105), _bar("07:31:00", 106)],
        session_date_from=date(2026, 7, 7),
        session_date_to=date(2026, 7, 7),
        planning_times=(time(7, 30),),
        timezone="Asia/Bangkok",
        planning_mode="rolling_30m",
        day_end_time=time(7, 31),
        snapshot_freshness_tolerance_seconds=1800,
    )

    assert selections == []
    assert issues["stale_snapshot_rejected_count"] == 1


def test_observed_timestamp_maps_source_session_to_bangkok_trading_date() -> None:
    snapshot = _snapshot("07:00:00", series="near", dte=0.8).model_copy(
        update={
            "session_date": date(2026, 5, 31),
            "observed_at": datetime.fromisoformat("2026-06-01T06:55:00+07:00"),
        }
    )
    bars = [
        XauPriceBar(
            timestamp=datetime.fromisoformat("2026-06-01T07:00:00+07:00"),
            open=105,
            high=106,
            low=104,
            close=105,
            volume=1,
        ),
        XauPriceBar(
            timestamp=datetime.fromisoformat("2026-06-01T08:00:00+07:00"),
            open=110,
            high=111,
            low=109,
            close=110,
            volume=1,
        ),
    ]
    selections, _ = select_planning_cycles(
        range_snapshots=[snapshot],
        strike_rows=[],
        bars=bars,
        session_date_from=date(2026, 6, 1),
        session_date_to=date(2026, 6, 1),
        planning_times=(time(7, 0),),
        timezone="Asia/Bangkok",
        planning_mode="fixed_morning",
        day_end_time=time(8, 0),
        join_by_observed_trading_date=True,
    )

    assert selections[0].session_date == date(2026, 6, 1)
    assert selections[0].source_session_date == date(2026, 5, 31)


def test_coverage_reports_each_source_session_once() -> None:
    snapshot = _snapshot("06:55:00", series="near", dte=0.8)
    bars = [_bar("07:00:00", 105), _bar("08:00:00", 110)]
    result_sets = [
        {
            "planning_mode": "fixed_morning",
            "diagnostics": [{"source_session_date": "2026-07-07"}],
        },
        {
            "planning_mode": "rolling_30m",
            "diagnostics": [{"source_session_date": "2026-07-07"}],
        },
    ]

    rows, _ = build_session_coverage_rows(
        [snapshot, snapshot.model_copy()],
        bars,
        result_sets,
        timezone="Asia/Bangkok",
        bar_interval_minutes=60,
    )

    assert len(rows) == 1
    assert rows[0]["source_session_date"] == "2026-07-07"
    assert rows[0]["fixed_morning_testable"] is True


def test_preregistered_exit_uses_conservative_stop_first() -> None:
    selections, _ = _select(
        mapping_mode=XauMappingMode.DISTANCE_REANCHORED,
        snapshots=[_snapshot("06:55:00", series="near", dte=0.8)],
        bars=[_bar("06:54:00", 100), _bar("07:00:00", 105), _bar("08:00:00", 118)],
    )
    touch_bar = XauPriceBar(
        timestamp=_time("08:00:00"),
        open=118,
        high=126,
        low=110,
        close=118,
        volume=1,
    )
    diagnostics, opportunities, summary = build_sd_zone_audit(
        selections,
        [touch_bar],
        planning_mode="fixed_morning",
    )
    result_sets = [
        {
            "planning_mode": "fixed_morning",
            "mapping_mode": "distance_reanchored",
            "diagnostics": diagnostics,
            "opportunities": opportunities,
            "summary": summary,
        }
    ]

    backtest = build_preregistered_exit_backtest(result_sets, [touch_bar])
    experiment = backtest["experiments"][0]
    strategy_a = [
        item
        for item in experiment["outcomes"]
        if item["strategy_id"] == "A" and item["cost_points"] == 0
    ]

    assert strategy_a[0]["status"] == "stop_hit"
    assert experiment["unique_market_opportunity_count"] == 2
    assert backtest["signal_allowed"] is False


def _select(
    *,
    mapping_mode: XauMappingMode,
    snapshots: list[XauVol2VolRangeDeskSnapshot],
    bars: list[XauPriceBar],
    tolerance: int = 300,
):
    return select_planning_cycles(
        range_snapshots=snapshots,
        strike_rows=[],
        bars=bars,
        session_date_from=date(2026, 7, 7),
        session_date_to=date(2026, 7, 7),
        planning_times=(time(7, 0),),
        timezone="Asia/Bangkok",
        planning_mode="fixed_morning",
        day_end_time=time(8, 0),
        mapping_mode=mapping_mode,
        source_alignment_tolerance_seconds=tolerance,
    )


def _snapshot(hhmmss: str, *, series: str, dte: float) -> XauVol2VolRangeDeskSnapshot:
    return XauVol2VolRangeDeskSnapshot(
        session_date=date(2026, 7, 7),
        observed_at=datetime.fromisoformat(f"2026-07-07T{hhmmss}+07:00"),
        series=series,
        dte=dte,
        future_open=120,
        future_buy_1sd=110,
        future_buy_2sd=100,
        future_buy_3sd=90,
        future_sell_1sd=130,
        future_sell_2sd=140,
        future_sell_3sd=150,
        sd_step_1=10,
        sd_step_2=20,
        sd_step_3=30,
    )


def _bar(hhmmss: str, close: float) -> XauPriceBar:
    return XauPriceBar(
        timestamp=_time(hhmmss),
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1,
    )


def _strike(series: str, strike: float) -> XauVol2VolStrikeSnapshot:
    return XauVol2VolStrikeSnapshot(
        session_date=date(2026, 7, 7),
        observed_at=_time("06:50:00"),
        series=series,
        snapshot_kind="open_interest",
        strike=strike,
        total=1,
        source="fixture",
    )


def _time(hhmmss: str) -> datetime:
    return datetime.fromisoformat(f"2026-07-07T{hhmmss}+07:00")
