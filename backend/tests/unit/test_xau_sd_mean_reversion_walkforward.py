from __future__ import annotations

from datetime import date, datetime

from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import (
    XauPlanReadiness,
    XauSdEntryLevel,
    XauSdMeanReversionPlan,
    XauSlMode,
    XauTpMode,
    XauTradeSide,
    XauVolRegimeLabel,
    XauWalkforwardTradeStatus,
    XauWindowAlignmentStatus,
)
from src.xau_vol2vol_history_walkforward.walkforward_simulator import simulate_plan


def test_walkforward_no_fill_when_price_never_touches_entry() -> None:
    outcome = simulate_plan(_plan(), [_bar(low=4080, high=4090)])

    assert outcome.status == XauWalkforwardTradeStatus.NO_FILL


def test_walkforward_target_hit_after_entry_and_target_touched() -> None:
    outcome = simulate_plan(_plan(), [_bar(low=4069, high=4085)])

    assert outcome.status == XauWalkforwardTradeStatus.TARGET_HIT
    assert outcome.triggered_at is not None
    assert outcome.mfe_points == 15


def test_walkforward_stop_hit_after_entry_and_stop_touched() -> None:
    outcome = simulate_plan(_plan(), [_bar(low=4055, high=4072)])

    assert outcome.status == XauWalkforwardTradeStatus.STOP_HIT
    assert outcome.mae_points == -15


def test_same_bar_target_and_stop_is_ambiguous_by_default() -> None:
    outcome = simulate_plan(_plan(), [_bar(low=4055, high=4085)])

    assert outcome.status == XauWalkforwardTradeStatus.AMBIGUOUS
    assert outcome.ambiguity_notes


def test_earlier_bars_do_not_trigger_later_plan() -> None:
    early = _bar(
        low=4055,
        high=4085,
        timestamp=datetime.fromisoformat("2026-06-26T10:01:00+07:00"),
    )

    outcome = simulate_plan(_plan(), [early])

    assert outcome.status == XauWalkforwardTradeStatus.UNAVAILABLE
    assert outcome.window_alignment_status == XauWindowAlignmentStatus.NO_BARS_IN_WINDOW
    assert outcome.triggered_at is None


def test_triggered_at_is_on_or_after_window_start() -> None:
    early = _bar(
        low=4055,
        high=4085,
        timestamp=datetime.fromisoformat("2026-06-26T10:01:00+07:00"),
    )
    valid = _bar(
        low=4069,
        high=4085,
        timestamp=datetime.fromisoformat("2026-07-08T10:01:00+07:00"),
    )

    outcome = simulate_plan(_plan(), [early, valid])

    assert outcome.status == XauWalkforwardTradeStatus.TARGET_HIT
    assert outcome.simulation_window_start is not None
    assert outcome.triggered_at is not None
    assert outcome.triggered_at >= outcome.simulation_window_start
    assert outcome.first_bar_used == valid.timestamp


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


def _bar(
    *,
    low: float,
    high: float,
    timestamp: datetime | None = None,
) -> XauPriceBar:
    return XauPriceBar(
        timestamp=timestamp or datetime.fromisoformat("2026-07-08T10:01:00+07:00"),
        open=(low + high) / 2,
        high=high,
        low=low,
        close=(low + high) / 2,
        volume=1,
    )
