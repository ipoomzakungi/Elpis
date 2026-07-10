from __future__ import annotations

from datetime import date, datetime, time

from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import XauVol2VolRangeDeskSnapshot
from src.xau_vol2vol_history_walkforward.baselines import build_predefined_baseline_plans
from src.xau_vol2vol_history_walkforward.planning import select_planning_cycles


def test_latest_snapshot_at_or_before_planning_time_is_selected() -> None:
    snapshots = [_snapshot("09:55"), _snapshot("10:05")]
    bars = [_bar("09:59", 4095), _bar("10:01", 4095)]

    selections, issues = select_planning_cycles(
        range_snapshots=snapshots,
        strike_rows=[],
        bars=bars,
        session_date_from=date(2026, 7, 7),
        session_date_to=date(2026, 7, 7),
        planning_times=(time(10, 0),),
        timezone="Asia/Bangkok",
    )

    assert len(selections) == 1
    assert selections[0].range_snapshot.observed_at.hour == 9
    assert selections[0].range_snapshot.diff == 5
    assert issues["future_snapshot_used_count"] == 0


def test_monthly_oi_without_sd_cannot_create_plan() -> None:
    snapshot = XauVol2VolRangeDeskSnapshot(
        session_date=date(2026, 7, 7),
        observed_at=datetime.fromisoformat("2026-07-07T09:55:00+07:00"),
        future_open=4100,
    )

    selections, issues = select_planning_cycles(
        range_snapshots=[snapshot],
        strike_rows=[],
        bars=[_bar("09:59", 4095), _bar("10:01", 4095)],
        session_date_from=date(2026, 7, 7),
        session_date_to=date(2026, 7, 7),
        planning_times=(time(10, 0),),
        timezone="Asia/Bangkok",
    )

    assert selections == []
    assert issues["plans_missing_sd_count"] == 1


def test_predefined_plans_persist_cycle_and_basis_metadata() -> None:
    selections, _ = select_planning_cycles(
        range_snapshots=[_snapshot("09:55")],
        strike_rows=[],
        bars=[_bar("09:59", 4095), _bar("10:01", 4095)],
        session_date_from=date(2026, 7, 7),
        session_date_to=date(2026, 7, 7),
        planning_times=(time(10, 0),),
        timezone="Asia/Bangkok",
    )

    plans = build_predefined_baseline_plans(selections, ["B1", "B2"])

    assert len(plans) == 4
    assert {plan.baseline_config for plan in plans} == {"B1", "B2"}
    assert all(plan.selected_vol2vol_snapshot_time for plan in plans)
    assert all(plan.selected_xau_price_time for plan in plans)
    assert all(plan.simulation_window_start.hour == 10 for plan in plans)
    assert all(plan.simulation_window_end.hour == 18 for plan in plans)
    assert all(plan.signal_allowed is False and plan.research_only is True for plan in plans)


def _snapshot(hhmm: str) -> XauVol2VolRangeDeskSnapshot:
    return XauVol2VolRangeDeskSnapshot(
        session_date=date(2026, 7, 7),
        observed_at=datetime.fromisoformat(f"2026-07-07T{hhmm}:00+07:00"),
        future_open=4100,
        future_buy_1sd=4090,
        future_buy_2sd=4080,
        future_buy_3sd=4070,
        future_sell_1sd=4110,
        future_sell_2sd=4120,
        future_sell_3sd=4130,
        sd_step_1=10,
        sd_step_2=10,
        sd_step_3=10,
    )


def _bar(hhmm: str, close: float) -> XauPriceBar:
    return XauPriceBar(
        timestamp=datetime.fromisoformat(f"2026-07-07T{hhmm}:00+07:00"),
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1,
    )
