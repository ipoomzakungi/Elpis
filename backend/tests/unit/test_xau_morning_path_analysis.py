from __future__ import annotations

from datetime import date, datetime, time

from test_xau_vol2vol_planning import _bar, _snapshot

from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import (
    XauSdEntryLevel,
    XauWalkforwardTradeOutcome,
    XauWalkforwardTradeStatus,
)
from src.xau_vol2vol_history_walkforward.baselines import build_predefined_baseline_plans
from src.xau_vol2vol_history_walkforward.morning_path_analysis import (
    build_daily_sd_paths,
    build_opportunity_map,
)
from src.xau_vol2vol_history_walkforward.planning import select_planning_cycles


def test_morning_path_observes_touches_at_0800_and_1830() -> None:
    selection = _selection()
    bars = [
        _price_bar("08:00", low=4074, high=4090),
        _price_bar("18:30", low=4090, high=4116),
    ]

    paths = build_daily_sd_paths([selection], bars)

    assert len(paths) == 1
    assert paths[0].first_lower_2sd_touch_time == bars[0].timestamp
    assert paths[0].first_upper_2sd_touch_time == bars[1].timestamp


def test_five_configurations_and_cost_copies_are_one_opportunity() -> None:
    selection = _selection()
    plans = [
        plan
        for plan in build_predefined_baseline_plans(
            [selection], ["B1", "B2", "B3", "B5", "B6"]
        )
        if plan.side.value == "short_reversion"
        and plan.entry_sd == XauSdEntryLevel.TWO_SD
    ]
    path = build_daily_sd_paths(
        [selection],
        [_price_bar("18:30", low=4090, high=4116)],
    )[0]
    outcomes = [
        _outcome(plan, cost, XauWalkforwardTradeStatus.TARGET_HIT)
        for plan in plans
        for cost in (0.0, 0.5, 1.0, 1.5)
    ]

    opportunities, summary = build_opportunity_map([path], plans, outcomes)

    assert len(opportunities) == 1
    assert opportunities[0].configuration_fill_count == 5
    assert opportunities[0].cost_scenario_filled_row_count == 20
    assert summary["unique_market_opportunity_count"] == 1
    assert summary["configuration_fill_count"] == 5
    assert summary["cost_scenario_filled_row_count"] == 20
    assert summary["evidence_status"] == "insufficient_sample"


def test_two_sd_and_three_sd_touches_are_distinct_opportunities() -> None:
    selection = _selection()
    plans = [
        plan
        for plan in build_predefined_baseline_plans([selection], ["B1", "B4"])
        if plan.side.value == "short_reversion"
    ]
    path = build_daily_sd_paths(
        [selection],
        [_price_bar("18:30", low=4090, high=4126)],
    )[0]

    opportunities, summary = build_opportunity_map([path], plans, [])

    assert len(opportunities) == 2
    assert {item.entry_sd for item in opportunities} == {
        XauSdEntryLevel.TWO_SD,
        XauSdEntryLevel.THREE_SD,
    }
    assert summary["unique_2sd_opportunity_count"] == 1
    assert summary["unique_3sd_opportunity_count"] == 1


def _selection():
    selections, _ = select_planning_cycles(
        range_snapshots=[_snapshot("06:55")],
        strike_rows=[],
        bars=[_bar("06:59", 4095), _bar("08:00", 4095)],
        session_date_from=date(2026, 7, 7),
        session_date_to=date(2026, 7, 7),
        planning_times=(time(7, 0),),
        timezone="Asia/Bangkok",
        planning_mode="fixed_morning",
    )
    return selections[0]


def _price_bar(hhmm: str, *, low: float, high: float) -> XauPriceBar:
    return XauPriceBar(
        timestamp=datetime.fromisoformat(f"2026-07-07T{hhmm}:00+07:00"),
        open=(low + high) / 2,
        high=high,
        low=low,
        close=(low + high) / 2,
        volume=1,
    )


def _outcome(plan, cost: float, status: XauWalkforwardTradeStatus):
    return XauWalkforwardTradeOutcome(
        plan_id=plan.plan_id,
        session_date=plan.session_date,
        side=plan.side,
        entry_sd=plan.entry_sd,
        tp_mode=plan.tp_mode,
        sl_mode=plan.sl_mode,
        status=status,
        baseline_config=plan.baseline_config,
        entry_type=plan.entry_type,
        cycle_label=plan.cycle_label,
        cost_points=cost,
        bars_evaluated=1,
    )
