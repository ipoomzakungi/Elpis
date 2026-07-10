from __future__ import annotations

import random
from collections import defaultdict
from statistics import mean
from typing import Any

from src.models.xau_vol2vol_history_walkforward import (
    XauWalkforwardTradeOutcome,
    XauWalkforwardTradeStatus,
)

FILLED_STATUSES = {
    XauWalkforwardTradeStatus.TARGET_HIT,
    XauWalkforwardTradeStatus.STOP_HIT,
    XauWalkforwardTradeStatus.EXPIRED,
    XauWalkforwardTradeStatus.AMBIGUOUS,
}


def build_conservative_statistics(
    outcomes: list[XauWalkforwardTradeOutcome],
    *,
    development_fraction: float = 0.7,
    bootstrap_seed: int = 31,
    bootstrap_iterations: int = 500,
) -> dict[str, Any]:
    dates = sorted({item.session_date for item in outcomes})
    split_index = min(max(int(len(dates) * development_fraction), 1), max(len(dates) - 1, 1))
    development_dates = set(dates[:split_index]) if len(dates) > 1 else set(dates)
    holdout_dates = set(dates[split_index:]) if len(dates) > 1 else set()
    development = [item for item in outcomes if item.session_date in development_dates]
    holdout = [item for item in outcomes if item.session_date in holdout_dates]
    config_comparison = _grouped_summary(outcomes)
    development_summary = {
        "session_dates": [item.isoformat() for item in sorted(development_dates)],
        "session_count": len(development_dates),
        "groups": _grouped_summary(development),
        "research_only": True,
        "signal_allowed": False,
    }
    holdout_summary = {
        "session_dates": [item.isoformat() for item in sorted(holdout_dates)],
        "session_count": len(holdout_dates),
        "groups": _grouped_summary(holdout),
        "research_only": True,
        "signal_allowed": False,
    }
    degradation = _degradation(development_summary["groups"], holdout_summary["groups"])
    bootstrap = _clustered_bootstrap(
        outcomes,
        seed=bootstrap_seed,
        iterations=bootstrap_iterations,
    )
    return {
        "development_stats": development_summary,
        "holdout_stats": holdout_summary,
        "config_comparison": {
            "groups": config_comparison,
            "development_to_holdout_degradation": degradation,
            "session_clustered_bootstrap": bootstrap,
            "bootstrap_seed": bootstrap_seed,
            "research_only": True,
            "signal_allowed": False,
        },
    }


def _grouped_summary(outcomes: list[XauWalkforwardTradeOutcome]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, float, str, str], list[XauWalkforwardTradeOutcome]] = defaultdict(
        list
    )
    for item in outcomes:
        groups[
            (
                item.baseline_config,
                item.cost_points,
                item.side.value,
                item.cycle_label,
            )
        ].append(item)
    summaries = []
    for key, items in sorted(groups.items()):
        filled = [item for item in items if item.status in FILLED_STATUSES]
        net = [item.net_points for item in filled if item.net_points is not None]
        gross = [item.gross_points for item in filled if item.gross_points is not None]
        target_hits = sum(item.status == XauWalkforwardTradeStatus.TARGET_HIT for item in filled)
        summaries.append(
            {
                "baseline_config": key[0],
                "cost_points": key[1],
                "side": key[2],
                "cycle_label": key[3],
                "outcome_count": len(items),
                "independent_session_count": len({item.session_date for item in items}),
                "fill_count": len(filled),
                "no_fill_count": sum(
                    item.status == XauWalkforwardTradeStatus.NO_FILL for item in items
                ),
                "target_hit_count": target_hits,
                "stop_hit_count": sum(
                    item.status == XauWalkforwardTradeStatus.STOP_HIT for item in filled
                ),
                "fill_rate": _rate(len(filled), len(items)),
                "win_rate_after_fill": _rate(target_hits, len(filled)),
                "gross_expectancy_points": mean(gross) if gross else None,
                "net_expectancy_points": mean(net) if net else None,
                "profit_factor_points": _profit_factor(net),
                "same_bar_ambiguity_count": sum(item.same_bar_ambiguous for item in items),
                "provisional": len(filled) < 30,
                "small_sample_warning": len(filled) < 20,
            }
        )
    return summaries


def _degradation(
    development: list[dict[str, Any]],
    holdout: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    def key(item: dict[str, Any]) -> tuple[str, float, str, str]:
        return (
            item["baseline_config"],
            item["cost_points"],
            item["side"],
            item["cycle_label"],
        )

    dev_by_key = {key(item): item for item in development}
    holdout_by_key = {key(item): item for item in holdout}
    results = []
    for group_key in sorted(dev_by_key):
        dev = dev_by_key[group_key]
        test = holdout_by_key.get(group_key)
        dev_net = dev.get("net_expectancy_points")
        holdout_net = test.get("net_expectancy_points") if test else None
        results.append(
            {
                "baseline_config": group_key[0],
                "cost_points": group_key[1],
                "side": group_key[2],
                "cycle_label": group_key[3],
                "development_net_expectancy_points": dev_net,
                "holdout_net_expectancy_points": holdout_net,
                "net_expectancy_degradation_points": (
                    holdout_net - dev_net
                    if dev_net is not None and holdout_net is not None
                    else None
                ),
                "holdout_fill_count": test["fill_count"] if test else 0,
                "no_holdout_fills": not test or test["fill_count"] == 0,
            }
        )
    return results


def _clustered_bootstrap(
    outcomes: list[XauWalkforwardTradeOutcome],
    *,
    seed: int,
    iterations: int,
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, float], list[XauWalkforwardTradeOutcome]] = defaultdict(list)
    for item in outcomes:
        groups[(item.baseline_config, item.cost_points)].append(item)
    results = []
    for key, items in sorted(groups.items()):
        by_date: dict[Any, list[XauWalkforwardTradeOutcome]] = defaultdict(list)
        for item in items:
            by_date[item.session_date].append(item)
        dates = sorted(by_date)
        if not dates:
            continue
        rng = random.Random(f"{seed}:{key[0]}:{key[1]}")
        expectancy_samples: list[float] = []
        win_samples: list[float] = []
        for _ in range(iterations):
            sampled = [rng.choice(dates) for _ in dates]
            trades = [trade for day in sampled for trade in by_date[day]]
            filled = [trade for trade in trades if trade.status in FILLED_STATUSES]
            net = [trade.net_points for trade in filled if trade.net_points is not None]
            if net:
                expectancy_samples.append(mean(net))
            if filled:
                wins = sum(
                    trade.status == XauWalkforwardTradeStatus.TARGET_HIT for trade in filled
                )
                win_samples.append(wins / len(filled))
        results.append(
            {
                "baseline_config": key[0],
                "cost_points": key[1],
                "independent_session_count": len(dates),
                "net_expectancy_ci95": _ci(expectancy_samples),
                "win_rate_ci95": _ci(win_samples),
            }
        )
    return results


def _ci(values: list[float]) -> list[float] | None:
    if not values:
        return None
    ordered = sorted(values)
    low = ordered[int((len(ordered) - 1) * 0.025)]
    high = ordered[int((len(ordered) - 1) * 0.975)]
    return [low, high]


def _profit_factor(values: list[float]) -> float | None:
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    return gains / losses if losses else None


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None
