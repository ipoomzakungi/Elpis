from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from src.models.xau_walk_forward_research import (
    XauOhlcvBar,
    XauResearchOrderOutcome,
    XauResearchOrderOutcomeStatus,
    XauResearchOrderPlan,
    XauResearchOrderSide,
)


def simulate_research_order_outcomes(
    plans: list[XauResearchOrderPlan],
    bars: list[XauOhlcvBar],
    *,
    conservative_ordering: bool = True,
) -> list[XauResearchOrderOutcome]:
    return [
        simulate_research_order_outcome(
            plan,
            bars,
            conservative_ordering=conservative_ordering,
        )
        for plan in plans
    ]


def simulate_research_order_outcome(
    plan: XauResearchOrderPlan,
    bars: list[XauOhlcvBar],
    *,
    conservative_ordering: bool = True,
) -> XauResearchOrderOutcome:
    if not bars:
        return XauResearchOrderOutcome(
            plan_id=plan.plan_id,
            status=XauResearchOrderOutcomeStatus.UNAVAILABLE,
            limitations=["No OHLCV bars were supplied for outcome simulation."],
        )

    triggered = False
    trigger_time = None
    mfe = 0.0
    mae = 0.0
    for bar in sorted(bars, key=lambda item: item.timestamp):
        if not triggered and _crosses_entry(plan, bar):
            triggered = True
            trigger_time = bar.timestamp
        if not triggered:
            continue

        mfe = max(mfe, _favorable_move(plan, bar))
        mae = min(mae, _adverse_move(plan, bar))
        target_hit = _target_hit(plan, bar)
        stop_hit = _stop_hit(plan, bar)
        if target_hit and stop_hit:
            if conservative_ordering:
                return _exit_outcome(
                    plan,
                    XauResearchOrderOutcomeStatus.STOP_HIT,
                    trigger_time,
                    bar.timestamp,
                    plan.stop_level,
                    mfe,
                    mae,
                    ["Target and stop were inside the same candle; conservative result used."],
                )
            return _exit_outcome(
                plan,
                XauResearchOrderOutcomeStatus.AMBIGUOUS,
                trigger_time,
                bar.timestamp,
                plan.stop_level,
                mfe,
                mae,
                ["Target and stop were inside the same candle."],
            )
        if target_hit:
            return _exit_outcome(
                plan,
                XauResearchOrderOutcomeStatus.TARGET_HIT,
                trigger_time,
                bar.timestamp,
                plan.target_level,
                mfe,
                mae,
                [],
            )
        if stop_hit:
            return _exit_outcome(
                plan,
                XauResearchOrderOutcomeStatus.STOP_HIT,
                trigger_time,
                bar.timestamp,
                plan.stop_level,
                mfe,
                mae,
                [],
            )

    if triggered:
        return XauResearchOrderOutcome(
            plan_id=plan.plan_id,
            status=XauResearchOrderOutcomeStatus.EXPIRED,
            trigger_time=trigger_time,
            entry_fill_level=plan.entry_level,
            mfe_points=mfe,
            mae_points=mae,
            limitations=[
                "Plan triggered but did not hit target or stop before supplied bars ended."
            ],
        )
    return XauResearchOrderOutcome(
        plan_id=plan.plan_id,
        status=XauResearchOrderOutcomeStatus.EXPIRED,
        limitations=["Plan did not trigger before supplied bars ended."],
    )


def load_ohlcv_bars(path: Path) -> list[XauOhlcvBar]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [
            XauOhlcvBar(
                timestamp=datetime.fromisoformat(row["timestamp"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]) if row.get("volume") else None,
            )
            for row in reader
        ]


def _crosses_entry(plan: XauResearchOrderPlan, bar: XauOhlcvBar) -> bool:
    return bar.low <= plan.entry_level <= bar.high


def _target_hit(plan: XauResearchOrderPlan, bar: XauOhlcvBar) -> bool:
    if plan.side == XauResearchOrderSide.LONG_REVERSION:
        return bar.high >= plan.target_level
    return bar.low <= plan.target_level


def _stop_hit(plan: XauResearchOrderPlan, bar: XauOhlcvBar) -> bool:
    if plan.side == XauResearchOrderSide.LONG_REVERSION:
        return bar.low <= plan.stop_level
    return bar.high >= plan.stop_level


def _favorable_move(plan: XauResearchOrderPlan, bar: XauOhlcvBar) -> float:
    if plan.side == XauResearchOrderSide.LONG_REVERSION:
        return bar.high - plan.entry_level
    return plan.entry_level - bar.low


def _adverse_move(plan: XauResearchOrderPlan, bar: XauOhlcvBar) -> float:
    if plan.side == XauResearchOrderSide.LONG_REVERSION:
        return bar.low - plan.entry_level
    return plan.entry_level - bar.high


def _realized_points(plan: XauResearchOrderPlan, exit_level: float) -> float:
    if plan.side == XauResearchOrderSide.LONG_REVERSION:
        return exit_level - plan.entry_level
    return plan.entry_level - exit_level


def _exit_outcome(
    plan: XauResearchOrderPlan,
    status: XauResearchOrderOutcomeStatus,
    trigger_time,
    exit_time,
    exit_level: float,
    mfe: float,
    mae: float,
    limitations: list[str],
) -> XauResearchOrderOutcome:
    return XauResearchOrderOutcome(
        plan_id=plan.plan_id,
        status=status,
        trigger_time=trigger_time,
        exit_time=exit_time,
        entry_fill_level=plan.entry_level,
        exit_level=exit_level,
        mfe_points=mfe,
        mae_points=mae,
        realized_points=_realized_points(plan, exit_level),
        limitations=limitations,
    )


__all__ = [
    "load_ohlcv_bars",
    "simulate_research_order_outcome",
    "simulate_research_order_outcomes",
]
