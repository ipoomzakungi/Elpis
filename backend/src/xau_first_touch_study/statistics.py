from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Callable
from statistics import mean, median
from typing import Any

from src.xau_first_touch_study.models import EventOutcome, FirstPassageStatus


def summarize_outcomes(
    outcomes: list[EventOutcome],
    *,
    bootstrap_seed: int = 34,
    bootstrap_iterations: int = 2_000,
) -> dict[str, Any]:
    included = [
        item for item in outcomes if item.include_in_expectancy and item.net_points is not None
    ]
    resolved = [
        item
        for item in outcomes
        if item.status
        in {
            FirstPassageStatus.TP_FIRST.value,
            FirstPassageStatus.SL_FIRST.value,
            "eventual_reversal",
            "not_observed_before_session_end",
        }
    ]
    successes = sum(item.success is True for item in resolved)
    net = [item.net_points for item in included if item.net_points is not None]
    ordered = sorted(included, key=lambda item: (item.session_date, item.event_id))
    return {
        "event_count": len(outcomes),
        "independent_session_count": len({item.session_date for item in outcomes}),
        "included_expectancy_count": len(included),
        "success_count": successes,
        "failure_count": sum(item.success is False for item in resolved),
        "success_rate": successes / len(resolved) if resolved else None,
        "event_success_rate": successes / len(outcomes) if outcomes else None,
        "wilson_interval_95": wilson_interval(successes, len(resolved)),
        "tp_first_count": sum(
            item.status == FirstPassageStatus.TP_FIRST.value for item in outcomes
        ),
        "sl_first_count": sum(
            item.status == FirstPassageStatus.SL_FIRST.value for item in outcomes
        ),
        "unresolved_count": sum(
            item.status == FirstPassageStatus.SESSION_END_UNRESOLVED.value for item in outcomes
        ),
        "ambiguous_count": sum(item.same_bar_ambiguous for item in outcomes),
        "net_expectancy_points": mean(net) if net else None,
        "median_net_points": median(net) if net else None,
        "avg_mfe_points": _avg(item.mfe_points for item in outcomes),
        "avg_mae_points": _avg(item.mae_points for item in outcomes),
        "avg_minutes_to_resolution": _avg(item.minutes_to_resolution for item in outcomes),
        "avg_minutes_to_tp": _avg(
            item.minutes_to_resolution
            for item in outcomes
            if item.status == FirstPassageStatus.TP_FIRST.value
        ),
        "avg_minutes_to_sl": _avg(
            item.minutes_to_resolution
            for item in outcomes
            if item.status == FirstPassageStatus.SL_FIRST.value
        ),
        "maximum_drawdown_points": maximum_drawdown(net),
        "maximum_consecutive_losses": maximum_consecutive_losses(
            [item.net_points for item in ordered if item.net_points is not None]
        ),
        "session_clustered_expectancy_ci95": clustered_bootstrap_expectancy(
            included,
            seed=bootstrap_seed,
            iterations=bootstrap_iterations,
        ),
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def grouped_summaries(
    outcomes: list[EventOutcome],
    key: Callable[[EventOutcome], str],
    *,
    bootstrap_seed: int = 34,
    bootstrap_iterations: int = 2_000,
) -> list[dict[str, Any]]:
    groups: dict[str, list[EventOutcome]] = defaultdict(list)
    for item in outcomes:
        groups[key(item)].append(item)
    return [
        {
            "group": group,
            **summarize_outcomes(
                rows,
                bootstrap_seed=bootstrap_seed,
                bootstrap_iterations=bootstrap_iterations,
            ),
        }
        for group, rows in sorted(groups.items())
    ]


def chronological_split(
    outcomes: list[EventOutcome],
    *,
    development_fraction: float = 0.7,
    bootstrap_seed: int = 34,
    bootstrap_iterations: int = 2_000,
) -> dict[str, Any]:
    dates = sorted({item.session_date for item in outcomes})
    if len(dates) <= 1:
        development_dates = set(dates)
        holdout_dates: set[Any] = set()
    else:
        index = min(max(int(len(dates) * development_fraction), 1), len(dates) - 1)
        development_dates = set(dates[:index])
        holdout_dates = set(dates[index:])
    development = [item for item in outcomes if item.session_date in development_dates]
    holdout = [item for item in outcomes if item.session_date in holdout_dates]
    return {
        "development_session_dates": [item.isoformat() for item in sorted(development_dates)],
        "holdout_session_dates": [item.isoformat() for item in sorted(holdout_dates)],
        "development": summarize_outcomes(
            development,
            bootstrap_seed=bootstrap_seed,
            bootstrap_iterations=bootstrap_iterations,
        ),
        "holdout": summarize_outcomes(
            holdout,
            bootstrap_seed=bootstrap_seed,
            bootstrap_iterations=bootstrap_iterations,
        ),
    }


def external_prior_comparison(
    local_by_tier: dict[int, list[EventOutcome]],
    external: dict[str, Any],
) -> list[dict[str, Any]]:
    results = []
    for tier in (1, 2, 3):
        local = local_by_tier.get(tier, [])
        summary = summarize_outcomes(local, bootstrap_iterations=500)
        prior = external["tiers"][str(tier)]
        local_success = summary["success_count"]
        local_failure = summary["failure_count"]
        alpha_prior = prior["reversals"] + 1
        beta_prior = prior["touches"] - prior["reversals"] + 1
        alpha_post = alpha_prior + local_success
        beta_post = beta_prior + local_failure
        results.append(
            {
                "tier": tier,
                "external_touch_count": prior["touches"],
                "external_reversal_count": prior["reversals"],
                "external_reported_rate": prior["reported_rate"],
                "local_event_count": summary["event_count"],
                "local_rate": summary["success_rate"],
                "local_minus_external_rate": (
                    summary["success_rate"] - prior["reported_rate"]
                    if summary["success_rate"] is not None
                    else None
                ),
                "external_beta_prior": {
                    "alpha": alpha_prior,
                    "beta": beta_prior,
                    "mean": alpha_prior / (alpha_prior + beta_prior),
                },
                "labeled_posterior_with_local": {
                    "alpha": alpha_post,
                    "beta": beta_post,
                    "mean": alpha_post / (alpha_post + beta_post),
                },
                "warning": "External counts are a labeled prior, not local evidence.",
            }
        )
    return results


def benjamini_hochberg(p_values: list[tuple[str, float]]) -> list[dict[str, Any]]:
    if not p_values:
        return []
    ordered = sorted(p_values, key=lambda item: item[1])
    count = len(ordered)
    adjusted = [0.0] * count
    running = 1.0
    for index in range(count - 1, -1, -1):
        rank = index + 1
        running = min(running, ordered[index][1] * count / rank)
        adjusted[index] = min(running, 1.0)
    return [
        {"trial_id": trial_id, "p_value": value, "q_value": adjusted[index]}
        for index, (trial_id, value) in enumerate(ordered)
    ]


def binomial_upper_tail(successes: int, total: int, null_probability: float) -> float:
    if total <= 0:
        return 1.0
    return min(
        sum(
            math.comb(total, value)
            * null_probability**value
            * (1 - null_probability) ** (total - value)
            for value in range(successes, total + 1)
        ),
        1.0,
    )


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total <= 0:
        return None
    p = successes / total
    denominator = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def clustered_bootstrap_expectancy(
    outcomes: list[EventOutcome],
    *,
    seed: int,
    iterations: int,
) -> list[float] | None:
    by_date: dict[Any, list[float]] = defaultdict(list)
    for item in outcomes:
        if item.net_points is not None:
            by_date[item.session_date].append(item.net_points)
    dates = sorted(by_date)
    if not dates:
        return None
    rng = random.Random(seed)
    samples = []
    for _ in range(iterations):
        sampled_dates = [rng.choice(dates) for _ in dates]
        values = [value for day in sampled_dates for value in by_date[day]]
        if values:
            samples.append(mean(values))
    samples.sort()
    return [
        samples[int((len(samples) - 1) * 0.025)],
        samples[int((len(samples) - 1) * 0.975)],
    ]


def maximum_drawdown(values: list[float]) -> float | None:
    if not values:
        return None
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = min(drawdown, equity - peak)
    return drawdown


def maximum_consecutive_losses(values: list[float]) -> int:
    maximum = 0
    current = 0
    for value in values:
        current = current + 1 if value < 0 else 0
        maximum = max(maximum, current)
    return maximum


def _avg(values: Any) -> float | None:
    present = [value for value in values if value is not None]
    return mean(present) if present else None
