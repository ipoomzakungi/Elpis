from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import mean
from typing import Any

from src.models.xau_vol2vol_history_walkforward import (
    XauSdMeanReversionPlan,
    XauWalkforwardStats,
    XauWalkforwardTradeOutcome,
    XauWalkforwardTradeStatus,
)

_FILLED_STATUSES = {
    XauWalkforwardTradeStatus.TARGET_HIT,
    XauWalkforwardTradeStatus.STOP_HIT,
    XauWalkforwardTradeStatus.EXPIRED,
    XauWalkforwardTradeStatus.AMBIGUOUS,
}


def build_walkforward_stats(
    *,
    run_id: str,
    plans: list[XauSdMeanReversionPlan],
    outcomes: list[XauWalkforwardTradeOutcome],
    session_date_from: date | None = None,
    session_date_to: date | None = None,
    minimum_sample_size: int = 30,
) -> XauWalkforwardStats:
    status_counts = defaultdict(int)
    for outcome in outcomes:
        status_counts[outcome.status] += 1
    filled = [item for item in outcomes if _is_filled(item)]
    warnings: list[str] = []
    if len(outcomes) < minimum_sample_size:
        warnings.append("Small sample is not proof.")
    return XauWalkforwardStats(
        run_id=run_id,
        session_date_from=session_date_from,
        session_date_to=session_date_to,
        plan_count=len(plans),
        triggered_count=len(filled),
        no_fill_count=status_counts[XauWalkforwardTradeStatus.NO_FILL],
        target_hit_count=status_counts[XauWalkforwardTradeStatus.TARGET_HIT],
        stop_hit_count=status_counts[XauWalkforwardTradeStatus.STOP_HIT],
        expired_count=status_counts[XauWalkforwardTradeStatus.EXPIRED],
        ambiguous_count=status_counts[XauWalkforwardTradeStatus.AMBIGUOUS],
        fill_rate=_rate(len(filled), len(outcomes)),
        target_hit_rate_after_fill=_rate(
            status_counts[XauWalkforwardTradeStatus.TARGET_HIT],
            len(filled),
        ),
        stop_hit_rate_after_fill=_rate(
            status_counts[XauWalkforwardTradeStatus.STOP_HIT],
            len(filled),
        ),
        avg_mfe_points=_avg([item.mfe_points for item in outcomes]),
        avg_mae_points=_avg([item.mae_points for item in outcomes]),
        worst_mae_points=_min([item.mae_points for item in outcomes]),
        avg_time_to_exit_minutes=_avg([item.time_to_exit_minutes for item in outcomes]),
        grouped_stats=_grouped_stats(plans, outcomes),
        warnings=warnings,
        limitations=[
            "Research-only points statistics; no spread, slippage, lot size, or PnL.",
            "Vol2Vol/OI structure is context, not a buy/sell signal.",
        ],
    )


def _grouped_stats(
    plans: list[XauSdMeanReversionPlan],
    outcomes: list[XauWalkforwardTradeOutcome],
) -> list[dict[str, Any]]:
    plan_by_id = {plan.plan_id: plan for plan in plans}
    groups: dict[tuple[str, str], list[XauWalkforwardTradeOutcome]] = defaultdict(list)
    for outcome in outcomes:
        plan = plan_by_id.get(outcome.plan_id)
        groups[("side", outcome.side.value)].append(outcome)
        groups[("entry_sd", outcome.entry_sd.value)].append(outcome)
        groups[("tp_mode", outcome.tp_mode.value)].append(outcome)
        groups[("sl_mode", outcome.sl_mode.value)].append(outcome)
        if plan is not None:
            groups[("vol_regime_label", plan.vol_regime_label.value)].append(outcome)
            oi = plan.oi_confluence.confluence_label.value if plan.oi_confluence else "unavailable"
            groups[("oi_confluence_label", oi)].append(outcome)
            wormhole = (
                plan.wormhole_state.wormhole_label.value
                if plan.wormhole_state
                else "unavailable"
            )
            groups[("wormhole_label", wormhole)].append(outcome)
            groups[("cycle_label", plan.cycle_label)].append(outcome)
        groups[("session", outcome.session_date.isoformat())].append(outcome)
    return [
        {
            "group_by": key[0],
            "group": key[1],
            "count": len(items),
            "fill_rate": _rate(
                sum(_is_filled(item) for item in items),
                len(items),
            ),
            "target_hit_rate_after_fill": _target_rate_after_fill(items),
            "avg_mfe_points": _avg([item.mfe_points for item in items]),
            "avg_mae_points": _avg([item.mae_points for item in items]),
        }
        for key, items in sorted(groups.items())
    ]


def _target_rate_after_fill(items: list[XauWalkforwardTradeOutcome]) -> float | None:
    filled = [item for item in items if _is_filled(item)]
    return _rate(
        sum(item.status == XauWalkforwardTradeStatus.TARGET_HIT for item in filled),
        len(filled),
    )


def _is_filled(item: XauWalkforwardTradeOutcome) -> bool:
    return item.status in _FILLED_STATUSES


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _avg(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return mean(present) if present else None


def _min(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return min(present) if present else None
