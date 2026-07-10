from __future__ import annotations

from datetime import date

from src.models.xau_vol2vol_history_walkforward import (
    XauSdEntryLevel,
    XauSlMode,
    XauTpMode,
    XauTradeSide,
    XauWalkforwardTradeOutcome,
    XauWalkforwardTradeStatus,
)
from src.xau_vol2vol_history_walkforward.conservative_statistics import (
    build_conservative_statistics,
)


def test_holdout_is_chronological_and_bootstrap_is_deterministic() -> None:
    outcomes = [
        _outcome(date(2026, 7, day), 10 if day % 2 else -10)
        for day in range(1, 11)
    ]

    first = build_conservative_statistics(outcomes, bootstrap_seed=7, bootstrap_iterations=50)
    second = build_conservative_statistics(outcomes, bootstrap_seed=7, bootstrap_iterations=50)

    assert first == second
    assert first["development_stats"]["session_dates"][-1] == "2026-07-07"
    assert first["holdout_stats"]["session_dates"] == [
        "2026-07-08",
        "2026-07-09",
        "2026-07-10",
    ]
    assert first["config_comparison"]["session_clustered_bootstrap"]


def _outcome(session_date: date, net_points: float) -> XauWalkforwardTradeOutcome:
    status = (
        XauWalkforwardTradeStatus.TARGET_HIT
        if net_points > 0
        else XauWalkforwardTradeStatus.STOP_HIT
    )
    return XauWalkforwardTradeOutcome(
        plan_id=f"B1-{session_date}",
        session_date=session_date,
        side=XauTradeSide.LONG_REVERSION,
        entry_sd=XauSdEntryLevel.TWO_SD,
        tp_mode=XauTpMode.HALF_SD,
        sl_mode=XauSlMode.THREE_SD,
        status=status,
        baseline_config="B1",
        cycle_label="10:00",
        cost_points=0,
        gross_points=net_points,
        total_cost_points=0,
        net_points=net_points,
        bars_evaluated=1,
    )
