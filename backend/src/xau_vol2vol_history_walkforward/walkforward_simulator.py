from __future__ import annotations

from datetime import datetime, time
from pathlib import Path

from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import (
    XauPlanReadiness,
    XauSdMeanReversionPlan,
    XauTradeSide,
    XauWalkforwardTradeOutcome,
    XauWalkforwardTradeStatus,
    XauWindowAlignmentStatus,
)
from src.xau_market_context.price_loader import load_price_bars


def load_traded_bars(path: Path, *, timezone: str = "Asia/Bangkok") -> list[XauPriceBar]:
    return load_price_bars(path, default_symbol="XAUUSD", default_timezone=timezone)


def simulate_plans(
    plans: list[XauSdMeanReversionPlan],
    bars: list[XauPriceBar],
    *,
    simulation_start: datetime | None = None,
    simulation_end: datetime | None = None,
    planning_time: time = time(0, 0),
    session_end_time: time = time(23, 0),
    entry_touch_policy: str = "touch",
    same_bar_policy: str = "ambiguous",
) -> list[XauWalkforwardTradeOutcome]:
    sorted_bars = sorted(bars, key=lambda item: item.timestamp)
    return [
        simulate_plan(
            plan,
            sorted_bars,
            simulation_start=simulation_start,
            simulation_end=simulation_end,
            planning_time=planning_time,
            session_end_time=session_end_time,
            entry_touch_policy=entry_touch_policy,
            same_bar_policy=same_bar_policy,
        )
        for plan in plans
    ]


def simulate_plan(
    plan: XauSdMeanReversionPlan,
    bars: list[XauPriceBar],
    *,
    simulation_start: datetime | None = None,
    simulation_end: datetime | None = None,
    planning_time: time = time(0, 0),
    session_end_time: time = time(23, 0),
    entry_touch_policy: str = "touch",
    same_bar_policy: str = "ambiguous",
) -> XauWalkforwardTradeOutcome:
    window_start, window_end, alignment = _plan_window(
        plan,
        bars,
        simulation_start=simulation_start,
        simulation_end=simulation_end,
        planning_time=planning_time,
        session_end_time=session_end_time,
    )
    if (
        plan.readiness == XauPlanReadiness.BLOCKED
        or plan.entry_level is None
        or plan.target_level is None
        or plan.stop_level is None
    ):
        return _outcome(
            plan,
            XauWalkforwardTradeStatus.UNAVAILABLE,
            bars_evaluated=0,
            window_start=window_start,
            window_end=window_end,
            alignment_status=alignment,
        )
    window_bars = [
        bar
        for bar in bars
        if window_start is not None
        and window_end is not None
        and window_start <= bar.timestamp <= window_end
    ]
    if not window_bars:
        return _outcome(
            plan,
            XauWalkforwardTradeStatus.UNAVAILABLE,
            bars_evaluated=0,
            window_start=window_start,
            window_end=window_end,
            alignment_status=XauWindowAlignmentStatus.NO_BARS_IN_WINDOW,
        )

    triggered_at: datetime | None = None
    mfe: float | None = None
    mae: float | None = None
    bars_evaluated = 0
    first_bar_used = window_bars[0].timestamp
    last_bar_used = window_bars[-1].timestamp
    for bar in window_bars:
        if triggered_at is None:
            if _entry_touched(plan, bar, entry_touch_policy):
                triggered_at = bar.timestamp
            else:
                continue

        bars_evaluated += 1
        favorable = _favorable_move(plan, bar)
        adverse = _adverse_move(plan, bar)
        mfe = favorable if mfe is None else max(mfe, favorable)
        mae = adverse if mae is None else min(mae, adverse)
        target_hit = _target_hit(plan, bar)
        stop_hit = _stop_hit(plan, bar)
        if target_hit and stop_hit:
            if same_bar_policy == "conservative_stop_first":
                return _exit(
                    plan,
                    XauWalkforwardTradeStatus.STOP_HIT,
                    triggered_at,
                    bar.timestamp,
                    plan.stop_level,
                    mfe,
                    mae,
                    bars_evaluated,
                    window_start=window_start,
                    window_end=window_end,
                    first_bar_used=first_bar_used,
                    last_bar_used=last_bar_used,
                    alignment_status=alignment,
                )
            if same_bar_policy == "optimistic_target_first":
                return _exit(
                    plan,
                    XauWalkforwardTradeStatus.TARGET_HIT,
                    triggered_at,
                    bar.timestamp,
                    plan.target_level,
                    mfe,
                    mae,
                    bars_evaluated,
                    window_start=window_start,
                    window_end=window_end,
                    first_bar_used=first_bar_used,
                    last_bar_used=last_bar_used,
                    alignment_status=alignment,
                )
            return _exit(
                plan,
                XauWalkforwardTradeStatus.AMBIGUOUS,
                triggered_at,
                bar.timestamp,
                None,
                mfe,
                mae,
                bars_evaluated,
                ambiguity_notes=["Target and stop were both inside the same candle."],
                window_start=window_start,
                window_end=window_end,
                first_bar_used=first_bar_used,
                last_bar_used=last_bar_used,
                alignment_status=alignment,
            )
        if target_hit:
            return _exit(
                plan,
                XauWalkforwardTradeStatus.TARGET_HIT,
                triggered_at,
                bar.timestamp,
                plan.target_level,
                mfe,
                mae,
                bars_evaluated,
                window_start=window_start,
                window_end=window_end,
                first_bar_used=first_bar_used,
                last_bar_used=last_bar_used,
                alignment_status=alignment,
            )
        if stop_hit:
            return _exit(
                plan,
                XauWalkforwardTradeStatus.STOP_HIT,
                triggered_at,
                bar.timestamp,
                plan.stop_level,
                mfe,
                mae,
                bars_evaluated,
                window_start=window_start,
                window_end=window_end,
                first_bar_used=first_bar_used,
                last_bar_used=last_bar_used,
                alignment_status=alignment,
            )

    if triggered_at is None:
        return _outcome(
            plan,
            XauWalkforwardTradeStatus.NO_FILL,
            bars_evaluated=len(window_bars),
            window_start=window_start,
            window_end=window_end,
            first_bar_used=first_bar_used,
            last_bar_used=last_bar_used,
            alignment_status=alignment,
        )
    return XauWalkforwardTradeOutcome(
        plan_id=plan.plan_id,
        session_date=plan.session_date,
        side=plan.side,
        entry_sd=plan.entry_sd,
        tp_mode=plan.tp_mode,
        sl_mode=plan.sl_mode,
        status=XauWalkforwardTradeStatus.EXPIRED,
        triggered_at=triggered_at,
        entry_level=plan.entry_level,
        target_level=plan.target_level,
        stop_level=plan.stop_level,
        mfe_points=mfe,
        mae_points=mae,
        max_drawdown_points=abs(mae) if mae is not None else None,
        bars_evaluated=bars_evaluated,
        simulation_window_start=window_start,
        simulation_window_end=window_end,
        plan_observed_at=plan.observed_at,
        first_bar_used=first_bar_used,
        last_bar_used=last_bar_used,
        window_alignment_status=alignment,
    )


def _entry_touched(plan: XauSdMeanReversionPlan, bar: XauPriceBar, policy: str) -> bool:
    if policy == "close_through":
        if plan.side == XauTradeSide.LONG_REVERSION:
            return bar.close <= plan.entry_level
        return bar.close >= plan.entry_level
    return bar.low <= plan.entry_level <= bar.high


def _target_hit(plan: XauSdMeanReversionPlan, bar: XauPriceBar) -> bool:
    if plan.side == XauTradeSide.LONG_REVERSION:
        return bar.high >= plan.target_level
    return bar.low <= plan.target_level


def _stop_hit(plan: XauSdMeanReversionPlan, bar: XauPriceBar) -> bool:
    if plan.side == XauTradeSide.LONG_REVERSION:
        return bar.low <= plan.stop_level
    return bar.high >= plan.stop_level


def _favorable_move(plan: XauSdMeanReversionPlan, bar: XauPriceBar) -> float:
    if plan.side == XauTradeSide.LONG_REVERSION:
        return bar.high - plan.entry_level
    return plan.entry_level - bar.low


def _adverse_move(plan: XauSdMeanReversionPlan, bar: XauPriceBar) -> float:
    if plan.side == XauTradeSide.LONG_REVERSION:
        return bar.low - plan.entry_level
    return plan.entry_level - bar.high


def _exit(
    plan: XauSdMeanReversionPlan,
    status: XauWalkforwardTradeStatus,
    triggered_at: datetime,
    exited_at: datetime,
    exit_level: float | None,
    mfe: float | None,
    mae: float | None,
    bars_evaluated: int,
    window_start: datetime | None,
    window_end: datetime | None,
    first_bar_used: datetime | None,
    last_bar_used: datetime | None,
    alignment_status: XauWindowAlignmentStatus,
    ambiguity_notes: list[str] | None = None,
) -> XauWalkforwardTradeOutcome:
    return XauWalkforwardTradeOutcome(
        plan_id=plan.plan_id,
        session_date=plan.session_date,
        side=plan.side,
        entry_sd=plan.entry_sd,
        tp_mode=plan.tp_mode,
        sl_mode=plan.sl_mode,
        status=status,
        triggered_at=triggered_at,
        exited_at=exited_at,
        entry_level=plan.entry_level,
        target_level=plan.target_level,
        stop_level=plan.stop_level,
        exit_level=exit_level,
        mfe_points=mfe,
        mae_points=mae,
        max_drawdown_points=abs(mae) if mae is not None else None,
        time_to_exit_minutes=(exited_at - triggered_at).total_seconds() / 60,
        bars_evaluated=bars_evaluated,
        simulation_window_start=window_start,
        simulation_window_end=window_end,
        plan_observed_at=plan.observed_at,
        first_bar_used=first_bar_used,
        last_bar_used=last_bar_used,
        window_alignment_status=alignment_status,
        ambiguity_notes=ambiguity_notes or [],
    )


def _outcome(
    plan: XauSdMeanReversionPlan,
    status: XauWalkforwardTradeStatus,
    *,
    bars_evaluated: int,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    first_bar_used: datetime | None = None,
    last_bar_used: datetime | None = None,
    alignment_status: XauWindowAlignmentStatus = XauWindowAlignmentStatus.INVALID,
) -> XauWalkforwardTradeOutcome:
    return XauWalkforwardTradeOutcome(
        plan_id=plan.plan_id,
        session_date=plan.session_date,
        side=plan.side,
        entry_sd=plan.entry_sd,
        tp_mode=plan.tp_mode,
        sl_mode=plan.sl_mode,
        status=status,
        entry_level=plan.entry_level,
        target_level=plan.target_level,
        stop_level=plan.stop_level,
        bars_evaluated=bars_evaluated,
        simulation_window_start=window_start,
        simulation_window_end=window_end,
        plan_observed_at=plan.observed_at,
        first_bar_used=first_bar_used,
        last_bar_used=last_bar_used,
        window_alignment_status=alignment_status,
    )


def _plan_window(
    plan: XauSdMeanReversionPlan,
    bars: list[XauPriceBar],
    *,
    simulation_start: datetime | None,
    simulation_end: datetime | None,
    planning_time: time,
    session_end_time: time,
) -> tuple[datetime | None, datetime | None, XauWindowAlignmentStatus]:
    timezone = plan.observed_at.tzinfo or (bars[0].timestamp.tzinfo if bars else None)
    if timezone is None:
        return None, None, XauWindowAlignmentStatus.INVALID
    session_start = datetime.combine(plan.session_date, planning_time, tzinfo=timezone)
    session_end = datetime.combine(plan.session_date, session_end_time, tzinfo=timezone)
    starts = [plan.observed_at, session_start]
    if simulation_start is not None:
        starts.append(_coerce_timezone(simulation_start, timezone))
    ends = [session_end]
    if simulation_end is not None:
        ends.append(_coerce_timezone(simulation_end, timezone))
    window_start = max(starts)
    window_end = min(ends)
    if window_end < window_start:
        return window_start, window_end, XauWindowAlignmentStatus.INVALID
    return window_start, window_end, XauWindowAlignmentStatus.ALIGNED


def _coerce_timezone(value: datetime, timezone) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone)
    return value.astimezone(timezone)
