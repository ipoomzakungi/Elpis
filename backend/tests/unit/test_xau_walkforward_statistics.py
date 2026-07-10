from __future__ import annotations

from datetime import date, datetime

from src.models.xau_vol2vol_history_walkforward import (
    XauPlanReadiness,
    XauSdEntryLevel,
    XauSdMeanReversionPlan,
    XauSlMode,
    XauTpMode,
    XauTradeSide,
    XauVolRegimeLabel,
    XauWalkforwardTradeOutcome,
    XauWalkforwardTradeStatus,
)
from src.xau_vol2vol_history_walkforward.statistics import build_walkforward_stats


def test_stats_grouped_by_side_entry_sd_and_tp_mode() -> None:
    plan = _plan()
    outcomes = [
        _outcome(XauWalkforwardTradeStatus.TARGET_HIT, mfe=20, mae=-4),
        _outcome(XauWalkforwardTradeStatus.STOP_HIT, mfe=3, mae=-12),
        _outcome(XauWalkforwardTradeStatus.NO_FILL, mfe=None, mae=None),
        _outcome(XauWalkforwardTradeStatus.UNAVAILABLE, mfe=None, mae=None),
    ]

    stats = build_walkforward_stats(run_id="run", plans=[plan], outcomes=outcomes)

    assert stats.fill_rate == 2 / 4
    assert stats.target_hit_rate_after_fill == 0.5
    assert stats.stop_hit_rate_after_fill == 0.5
    assert stats.worst_mae_points == -12
    groups = {(item["group_by"], item["group"]) for item in stats.grouped_stats}
    assert ("side", "long_reversion") in groups
    assert ("entry_sd", "two_sd") in groups
    assert ("tp_mode", "half_sd") in groups


def test_mark_only_time_exit_does_not_enter_expectancy() -> None:
    marked = _outcome(XauWalkforwardTradeStatus.TIME_EXIT_PROFIT, mfe=8, mae=-2)
    marked = marked.model_copy(
        update={"net_points": 6, "gross_points": 6, "include_in_expectancy": False}
    )

    stats = build_walkforward_stats(run_id="run", plans=[_plan()], outcomes=[marked])

    assert stats.triggered_count == 1
    assert stats.time_exit_profit_count == 1
    assert stats.net_expectancy_points is None


def _plan() -> XauSdMeanReversionPlan:
    return XauSdMeanReversionPlan(
        plan_id="fixture",
        session_date=date(2026, 7, 8),
        cycle_label="manual",
        observed_at=datetime.fromisoformat("2026-07-08T10:00:00+07:00"),
        side=XauTradeSide.LONG_REVERSION,
        entry_sd=XauSdEntryLevel.TWO_SD,
        entry_level=4070,
        tp_mode=XauTpMode.HALF_SD,
        target_level=4080,
        sl_mode=XauSlMode.NEXT_HALF_SD,
        stop_level=4060,
        open_price=4096,
        sd_step_points=20,
        vol_regime_label=XauVolRegimeLabel.NORMAL,
        readiness=XauPlanReadiness.READY,
    )


def _outcome(
    status: XauWalkforwardTradeStatus,
    *,
    mfe: float | None,
    mae: float | None,
) -> XauWalkforwardTradeOutcome:
    return XauWalkforwardTradeOutcome(
        plan_id="fixture",
        session_date=date(2026, 7, 8),
        side=XauTradeSide.LONG_REVERSION,
        entry_sd=XauSdEntryLevel.TWO_SD,
        tp_mode=XauTpMode.HALF_SD,
        sl_mode=XauSlMode.NEXT_HALF_SD,
        status=status,
        entry_level=4070,
        target_level=4080,
        stop_level=4060,
        mfe_points=mfe,
        mae_points=mae,
        max_drawdown_points=abs(mae) if mae is not None else None,
        bars_evaluated=1,
    )
