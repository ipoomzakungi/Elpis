from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import mean, median
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
    if len(filled) < minimum_sample_size:
        warnings.append("Results are provisional because fewer than 30 plans filled.")
    net_values = [item.net_points for item in filled if item.net_points is not None]
    gross_values = [item.gross_points for item in filled if item.gross_points is not None]
    mae_values = [item.mae_points for item in outcomes if item.mae_points is not None]
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
        unavailable_count=status_counts[XauWalkforwardTradeStatus.UNAVAILABLE],
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
        median_mfe_points=_median([item.mfe_points for item in outcomes]),
        median_mae_points=_median([item.mae_points for item in outcomes]),
        mae_p90_points=_adverse_percentile(mae_values, 0.90),
        mae_p95_points=_adverse_percentile(mae_values, 0.95),
        gross_expectancy_points=_avg(gross_values),
        net_expectancy_points=_avg(net_values),
        profit_factor_points=_profit_factor(net_values),
        maximum_cumulative_drawdown_points=_maximum_drawdown(net_values),
        maximum_consecutive_losses=_maximum_consecutive_losses(net_values),
        avg_time_to_exit_minutes=_avg([item.time_to_exit_minutes for item in outcomes]),
        grouped_stats=_grouped_stats(plans, outcomes),
        warnings=warnings,
        limitations=[
            "Research-only points statistics; no lot size, capital, or real PnL.",
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
        groups[("baseline_config", outcome.baseline_config)].append(outcome)
        groups[("entry_type", outcome.entry_type.value)].append(outcome)
        groups[("cycle_label", outcome.cycle_label)].append(outcome)
        groups[("cost_points", str(outcome.cost_points))].append(outcome)
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
            "net_expectancy_points": _avg([item.net_points for item in items]),
            "fill_count": sum(_is_filled(item) for item in items),
            "small_sample_warning": sum(_is_filled(item) for item in items) < 20,
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


def _median(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return median(present) if present else None


def _adverse_percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    adverse = sorted(abs(value) for value in values)
    index = min(round((len(adverse) - 1) * percentile), len(adverse) - 1)
    return adverse[index]


def _profit_factor(values: list[float]) -> float | None:
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if losses == 0:
        return None
    return gains / losses


def _maximum_drawdown(values: list[float]) -> float | None:
    if not values:
        return None
    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return drawdown


def _maximum_consecutive_losses(values: list[float]) -> int:
    maximum = 0
    current = 0
    for value in values:
        if value < 0:
            current += 1
            maximum = max(maximum, current)
        else:
            current = 0
    return maximum
