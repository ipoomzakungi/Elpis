from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from pytest import approx

from src.models.xau_price_plan_tracker import XauDukasPriceBar, XauTrackedOrderStatus
from src.models.xau_walk_forward_research import (
    XauResearchOrderPlan,
    XauResearchOrderSide,
    XauResearchOrderStage,
    XauResearchRiskStatus,
)
from src.xau_price_plan_tracker.order_tracker import track_research_order


def test_long_plan_tracks_target_pnl_and_drawdown() -> None:
    planning_time = _dt("2026-06-08T10:10:00")
    plan = _plan(
        side=XauResearchOrderSide.LONG_REVERSION,
        entry=4420,
        target=4445,
        stop=4407.5,
    )
    bars = [
        _bar("2026-06-08T10:11:00", 4470, 4471, 4425, 4430),
        _bar("2026-06-08T10:12:00", 4430, 4446, 4418, 4440),
    ]

    tracked = track_research_order(
        plan,
        bars,
        planning_time=planning_time,
        near_miss_threshold_points=1.0,
    )

    assert tracked.status == XauTrackedOrderStatus.TARGET_HIT
    assert tracked.current_pnl_points == 20
    assert tracked.max_favorable_excursion_points == 26
    assert tracked.drawdown_points == 2
    assert tracked.strict_triggered is True
    assert tracked.near_miss is False


def test_short_plan_tracks_open_pnl_and_drawdown() -> None:
    planning_time = _dt("2026-06-08T10:10:00")
    plan = _plan(
        side=XauResearchOrderSide.SHORT_REVERSION,
        entry=4520,
        target=4495,
        stop=4532.5,
    )
    bars = [
        _bar("2026-06-08T10:11:00", 4500, 4521, 4498, 4510),
        _bar("2026-06-08T10:12:00", 4510, 4525, 4500, 4505),
    ]

    tracked = track_research_order(
        plan,
        bars,
        planning_time=planning_time,
        near_miss_threshold_points=1.0,
    )

    assert tracked.status == XauTrackedOrderStatus.OPEN
    assert tracked.current_pnl_points == 15
    assert tracked.drawdown_points == 5
    assert tracked.strict_triggered is True
    assert tracked.near_miss is False


def test_ambiguous_bar_uses_conservative_stop_first() -> None:
    planning_time = _dt("2026-06-08T10:10:00")
    plan = _plan(
        side=XauResearchOrderSide.LONG_REVERSION,
        entry=4420,
        target=4445,
        stop=4407.5,
    )

    tracked = track_research_order(
        plan,
        [_bar("2026-06-08T10:11:00", 4420, 4446, 4407, 4410)],
        planning_time=planning_time,
        near_miss_threshold_points=1.0,
    )

    assert tracked.status == XauTrackedOrderStatus.STOP_HIT
    assert tracked.strict_triggered is True
    assert "conservative" in tracked.limitations[0]


def test_plan_does_not_trigger_and_tracks_near_miss() -> None:
    planning_time = _dt("2026-06-08T10:10:00")
    plan = _plan(
        side=XauResearchOrderSide.LONG_REVERSION,
        entry=4251.34,
        target=4276.34,
        stop=4231.34,
    )

    tracked = track_research_order(
        plan,
        [
            _bar("2026-06-08T10:11:00", 4251.7, 4252, 4251.59, 4251.9),
            _bar("2026-06-08T10:12:00", 4251.9, 4252.2, 4251.6, 4252.0),
        ],
        planning_time=planning_time,
        near_miss_threshold_points=0.3,
    )

    assert tracked.status == XauTrackedOrderStatus.PLANNED
    assert tracked.strict_triggered is False
    assert tracked.near_miss is True
    assert tracked.near_miss_distance_points == approx(0.25)
    assert tracked.near_miss_threshold_points == 0.3
    assert tracked.closest_price_to_entry == 4251.59
    assert tracked.closest_time_to_entry == _dt("2026-06-08T10:11:00")


def test_plan_does_not_mark_near_miss_when_threshold_too_small() -> None:
    planning_time = _dt("2026-06-08T10:10:00")
    plan = _plan(
        side=XauResearchOrderSide.LONG_REVERSION,
        entry=4251.34,
        target=4276.34,
        stop=4231.34,
    )

    tracked = track_research_order(
        plan,
        [
            _bar("2026-06-08T10:11:00", 4251.7, 4252, 4251.59, 4251.9),
            _bar("2026-06-08T10:12:00", 4251.9, 4252.2, 4251.6, 4252.0),
        ],
        planning_time=planning_time,
        near_miss_threshold_points=0.1,
    )

    assert tracked.status == XauTrackedOrderStatus.PLANNED
    assert tracked.strict_triggered is False
    assert tracked.near_miss is False
    assert tracked.near_miss_distance_points is None


def _plan(
    *,
    side: XauResearchOrderSide,
    entry: float,
    target: float,
    stop: float,
) -> XauResearchOrderPlan:
    return XauResearchOrderPlan(
        plan_id=f"test_{side.value}",
        snapshot_id="snapshot",
        timestamp=_dt("2026-06-08T10:10:00"),
        side=side,
        stage=XauResearchOrderStage.INITIAL,
        entry_level=entry,
        target_level=target,
        stop_level=stop,
        entry_sd=2,
        target_sd=1,
        stop_sd=2.5,
        tp_points=abs(entry - target),
        sl_points=abs(entry - stop),
        risk_status=XauResearchRiskStatus.ALLOWED,
    )


def _bar(
    timestamp: str,
    open_: float,
    high: float,
    low: float,
    close: float,
) -> XauDukasPriceBar:
    return XauDukasPriceBar(
        timestamp=_dt(timestamp),
        open=open_,
        high=high,
        low=low,
        close=close,
    )


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=ZoneInfo("Asia/Bangkok"))
