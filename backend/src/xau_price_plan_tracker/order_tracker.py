from __future__ import annotations

from datetime import datetime

from src.models.xau_price_plan_tracker import (
    XauDukasPriceBar,
    XauResearchTrackedOrder,
    XauTrackedOrderStatus,
)
from src.models.xau_walk_forward_research import (
    XauResearchOrderPlan,
    XauResearchOrderSide,
)


def track_research_order(
    plan: XauResearchOrderPlan,
    bars: list[XauDukasPriceBar],
    *,
    planning_time: datetime,
    run_until: datetime | None = None,
    recovery_plan: XauResearchOrderPlan | None = None,
    conservative_stop_first: bool = True,
) -> XauResearchTrackedOrder:
    relevant_bars = [
        bar
        for bar in sorted(bars, key=lambda item: item.timestamp)
        if bar.timestamp >= planning_time and (run_until is None or bar.timestamp <= run_until)
    ]
    recovery_entry = recovery_plan.entry_level if recovery_plan else None
    recovery_target = recovery_plan.target_level if recovery_plan else None
    if not relevant_bars:
        return _tracked_order(
            plan,
            planning_time=planning_time,
            status=XauTrackedOrderStatus.UNAVAILABLE,
            recovery_entry_level=recovery_entry,
            recovery_target_level=recovery_target,
            limitations=["No XAU bars were available after the planning time."],
        )

    triggered = False
    trigger_time = None
    mfe = 0.0
    mae = 0.0
    current_price = relevant_bars[-1].close
    for index, bar in enumerate(relevant_bars):
        if not triggered and _entry_hit(plan, bar):
            triggered = True
            trigger_time = bar.timestamp
        if not triggered:
            continue

        mfe = max(mfe, _favorable_move(plan, bar))
        mae = max(mae, _adverse_move(plan, bar))
        target_hit = _target_hit(plan, bar)
        stop_hit = _stop_hit(plan, bar)
        if target_hit and stop_hit:
            if conservative_stop_first:
                return _exit_order(
                    plan,
                    planning_time=planning_time,
                    status=XauTrackedOrderStatus.STOP_HIT,
                    trigger_time=trigger_time,
                    exit_time=bar.timestamp,
                    current_price=current_price,
                    mfe=mfe,
                    mae=mae,
                    bars_covered_count=len(relevant_bars),
                    recovery_entry_level=recovery_entry,
                    recovery_target_level=recovery_target,
                    limitations=[
                        "Target and stop were inside the same candle; "
                        "conservative stop-first result used."
                    ],
                )
            return _exit_order(
                plan,
                planning_time=planning_time,
                status=XauTrackedOrderStatus.AMBIGUOUS,
                trigger_time=trigger_time,
                exit_time=bar.timestamp,
                current_price=current_price,
                mfe=mfe,
                mae=mae,
                bars_covered_count=len(relevant_bars),
                recovery_entry_level=recovery_entry,
                recovery_target_level=recovery_target,
                limitations=["Target and stop were inside the same candle."],
            )
        if target_hit:
            return _exit_order(
                plan,
                planning_time=planning_time,
                status=XauTrackedOrderStatus.TARGET_HIT,
                trigger_time=trigger_time,
                exit_time=bar.timestamp,
                current_price=current_price,
                mfe=mfe,
                mae=mae,
                bars_covered_count=len(relevant_bars),
                recovery_entry_level=recovery_entry,
                recovery_target_level=recovery_target,
            )
        if stop_hit:
            recovery_status = _recovery_status(
                plan,
                recovery_plan,
                relevant_bars[index + 1 :],
            )
            return _exit_order(
                plan,
                planning_time=planning_time,
                status=recovery_status or XauTrackedOrderStatus.STOP_HIT,
                trigger_time=trigger_time,
                exit_time=bar.timestamp,
                current_price=current_price,
                mfe=mfe,
                mae=mae,
                bars_covered_count=len(relevant_bars),
                recovery_entry_level=recovery_entry,
                recovery_target_level=recovery_target,
            )

    if triggered:
        return _tracked_order(
            plan,
            planning_time=planning_time,
            status=XauTrackedOrderStatus.OPEN,
            trigger_time=trigger_time,
            current_price=current_price,
            current_pnl_points=_current_pnl(plan, current_price),
            max_favorable_excursion_points=mfe,
            max_adverse_excursion_points=mae,
            drawdown_points=mae,
            bars_covered_count=len(relevant_bars),
            recovery_entry_level=recovery_entry,
            recovery_target_level=recovery_target,
        )
    status = (
        XauTrackedOrderStatus.EXPIRED
        if run_until is not None and relevant_bars[-1].timestamp >= run_until
        else XauTrackedOrderStatus.PLANNED
    )
    return _tracked_order(
        plan,
        planning_time=planning_time,
        status=status,
        current_price=current_price,
        current_pnl_points=None,
        bars_covered_count=len(relevant_bars),
        recovery_entry_level=recovery_entry,
        recovery_target_level=recovery_target,
        limitations=["Plan did not trigger during supplied bars."]
        if status == XauTrackedOrderStatus.EXPIRED
        else [],
    )


def _recovery_status(
    initial_plan: XauResearchOrderPlan,
    recovery_plan: XauResearchOrderPlan | None,
    bars: list[XauDukasPriceBar],
) -> XauTrackedOrderStatus | None:
    if recovery_plan is None:
        return None
    triggered = False
    for bar in bars:
        if not triggered and _entry_hit(recovery_plan, bar):
            triggered = True
        if not triggered:
            continue
        if _target_hit(recovery_plan, bar):
            return XauTrackedOrderStatus.RECOVERY_TARGET_HIT
        if _stop_hit(recovery_plan, bar):
            return XauTrackedOrderStatus.STOP_HIT
    if triggered:
        return XauTrackedOrderStatus.RECOVERY_TRIGGERED
    return None


def _entry_hit(plan: XauResearchOrderPlan, bar: XauDukasPriceBar) -> bool:
    if plan.side == XauResearchOrderSide.LONG_REVERSION:
        return bar.low <= plan.entry_level
    return bar.high >= plan.entry_level


def _target_hit(plan: XauResearchOrderPlan, bar: XauDukasPriceBar) -> bool:
    if plan.side == XauResearchOrderSide.LONG_REVERSION:
        return bar.high >= plan.target_level
    return bar.low <= plan.target_level


def _stop_hit(plan: XauResearchOrderPlan, bar: XauDukasPriceBar) -> bool:
    if plan.side == XauResearchOrderSide.LONG_REVERSION:
        return bar.low <= plan.stop_level
    return bar.high >= plan.stop_level


def _favorable_move(plan: XauResearchOrderPlan, bar: XauDukasPriceBar) -> float:
    if plan.side == XauResearchOrderSide.LONG_REVERSION:
        return max(0.0, bar.high - plan.entry_level)
    return max(0.0, plan.entry_level - bar.low)


def _adverse_move(plan: XauResearchOrderPlan, bar: XauDukasPriceBar) -> float:
    if plan.side == XauResearchOrderSide.LONG_REVERSION:
        return max(0.0, plan.entry_level - bar.low)
    return max(0.0, bar.high - plan.entry_level)


def _current_pnl(plan: XauResearchOrderPlan, current_price: float) -> float:
    if plan.side == XauResearchOrderSide.LONG_REVERSION:
        return current_price - plan.entry_level
    return plan.entry_level - current_price


def _exit_order(
    plan: XauResearchOrderPlan,
    *,
    planning_time: datetime,
    status: XauTrackedOrderStatus,
    trigger_time: datetime | None,
    exit_time: datetime,
    current_price: float,
    mfe: float,
    mae: float,
    bars_covered_count: int,
    recovery_entry_level: float | None,
    recovery_target_level: float | None,
    limitations: list[str] | None = None,
) -> XauResearchTrackedOrder:
    return _tracked_order(
        plan,
        planning_time=planning_time,
        status=status,
        trigger_time=trigger_time,
        exit_time=exit_time,
        current_price=current_price,
        current_pnl_points=_current_pnl(plan, current_price),
        max_favorable_excursion_points=mfe,
        max_adverse_excursion_points=mae,
        drawdown_points=mae,
        bars_covered_count=bars_covered_count,
        recovery_entry_level=recovery_entry_level,
        recovery_target_level=recovery_target_level,
        limitations=limitations or [],
    )


def _tracked_order(
    plan: XauResearchOrderPlan,
    *,
    planning_time: datetime,
    status: XauTrackedOrderStatus,
    recovery_entry_level: float | None = None,
    recovery_target_level: float | None = None,
    trigger_time: datetime | None = None,
    exit_time: datetime | None = None,
    current_price: float | None = None,
    current_pnl_points: float | None = None,
    max_favorable_excursion_points: float | None = None,
    max_adverse_excursion_points: float | None = None,
    drawdown_points: float | None = None,
    bars_covered_count: int = 0,
    limitations: list[str] | None = None,
) -> XauResearchTrackedOrder:
    return XauResearchTrackedOrder(
        order_id=plan.plan_id,
        planning_time=planning_time,
        side=plan.side,
        entry_level=plan.entry_level,
        target_level=plan.target_level,
        stop_level=plan.stop_level,
        recovery_entry_level=recovery_entry_level,
        recovery_target_level=recovery_target_level,
        status=status,
        trigger_time=trigger_time,
        exit_time=exit_time,
        current_price=current_price,
        current_pnl_points=current_pnl_points,
        max_favorable_excursion_points=max_favorable_excursion_points,
        max_adverse_excursion_points=max_adverse_excursion_points,
        drawdown_points=drawdown_points,
        bars_covered_count=bars_covered_count,
        limitations=limitations or [],
        research_only=True,
        signal_allowed=False,
    )


__all__ = ["track_research_order"]
