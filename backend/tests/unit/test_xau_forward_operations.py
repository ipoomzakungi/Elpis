from __future__ import annotations

from datetime import date, datetime

from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import (
    XauVol2VolRangeDeskSnapshot,
    XauVol2VolStrikeSnapshot,
)
from src.xau_vol2vol_history_walkforward.forward_operations import (
    ForwardOperationalState,
    evaluate_forward_readiness,
    observe_forward_plan,
)


def test_forward_readiness_builds_research_plan() -> None:
    result = evaluate_forward_readiness(
        session_date=date(2026, 7, 13),
        planning_at=_time("07:00:00"),
        range_rows=[_range("06:55:00")],
        strike_rows=_strikes("06:55:00"),
        bars=[_bar("06:55:00", 100), _bar("07:00:00", 101)],
        planning_mode="fixed_morning",
    )

    assert result.state == ForwardOperationalState.PLAN_READY
    assert result.plan is not None
    assert result.plan["levels"]["lower_1sd"] == 90
    assert len(result.plan["top_oi_walls"]) == 5
    assert result.plan["f0_status"] == "active_research_baseline"
    assert result.plan["f1_status"] == "context_label_only"
    assert result.plan["signal_allowed"] is False


def test_forward_readiness_reports_missing_and_stale_states() -> None:
    missing = evaluate_forward_readiness(
        session_date=date(2026, 7, 13),
        planning_at=_time("07:00:00"),
        range_rows=[_range("07:05:00")],
        strike_rows=[],
        bars=[_bar("07:00:00", 100)],
        planning_mode="fixed_morning",
    )
    stale = evaluate_forward_readiness(
        session_date=date(2026, 7, 13),
        planning_at=_time("07:00:00"),
        range_rows=[_range("06:00:00")],
        strike_rows=[],
        bars=[_bar("06:00:00", 100), _bar("07:00:00", 101)],
        planning_mode="fixed_morning",
    )

    assert missing.state == ForwardOperationalState.NO_PRE_0700_SNAPSHOT
    assert stale.state == ForwardOperationalState.STALE_SOURCE


def test_monitor_records_touch_confirmation_and_final_outcomes() -> None:
    readiness = evaluate_forward_readiness(
        session_date=date(2026, 7, 13),
        planning_at=_time("07:00:00"),
        range_rows=[_range("06:55:00")],
        strike_rows=_strikes("06:55:00"),
        bars=[_bar("06:55:00", 100), _bar("07:00:00", 100)],
        planning_mode="fixed_morning",
    )
    bars = [
        _bar("07:01:00", 100),
        _wide_bar("08:01:00", close=89, high=91, low=88),
        _wide_bar("08:04:00", close=91, high=92, low=89),
        _wide_bar("08:05:00", close=92, high=93, low=91),
        _wide_bar("09:00:00", close=95, high=96, low=94),
    ]

    observed = observe_forward_plan(readiness.plan, bars, finalize=True)

    assert observed["opportunities"]
    assert observed["confirmations"]
    assert observed["outcomes"]
    assert {row["strategy_id"] for row in observed["outcomes"]} >= {"A", "B"}


def _range(hhmmss: str) -> XauVol2VolRangeDeskSnapshot:
    return XauVol2VolRangeDeskSnapshot(
        session_date=date(2026, 7, 13),
        observed_at=_time(hhmmss),
        series="SERIES",
        dte=0.8,
        future_open=120,
        future_buy_1sd=110,
        future_buy_2sd=100,
        future_buy_3sd=90,
        future_sell_1sd=130,
        future_sell_2sd=140,
        future_sell_3sd=150,
    )


def _strikes(hhmmss: str) -> list[XauVol2VolStrikeSnapshot]:
    return [
        XauVol2VolStrikeSnapshot(
            session_date=date(2026, 7, 13),
            observed_at=_time(hhmmss),
            series="SERIES",
            snapshot_kind="open_interest",
            strike=100 + index * 5,
            total=100 - index,
            source="fixture",
        )
        for index in range(6)
    ]


def _bar(hhmmss: str, close: float) -> XauPriceBar:
    return XauPriceBar(
        timestamp=_time(hhmmss),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1,
    )


def _wide_bar(hhmmss: str, *, close: float, high: float, low: float) -> XauPriceBar:
    return XauPriceBar(
        timestamp=_time(hhmmss),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=1,
    )


def _time(hhmmss: str) -> datetime:
    return datetime.fromisoformat(f"2026-07-13T{hhmmss}+07:00")
