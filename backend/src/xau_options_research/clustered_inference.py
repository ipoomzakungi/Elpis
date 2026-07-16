from __future__ import annotations

import random
from collections import defaultdict
from statistics import mean
from typing import Any


def build_clustered_inference_audit(
    outcomes: list[dict[str, Any]],
    *,
    seed: int = 32,
    iterations: int = 1000,
) -> dict[str, Any]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in outcomes:
        grouped[
            (
                row["experiment_id"],
                row["planning_mode"],
                row["target_sd"],
                row["spread_points"],
                row["slippage_points_per_side"],
            )
        ].append(row)
    trials = []
    for number, (key, rows) in enumerate(sorted(grouped.items()), start=1):
        session_means = _session_means(rows)
        ci = session_block_bootstrap_ci(
            session_means,
            seed=f"{seed}:bootstrap:{key}",
            iterations=iterations,
        )
        p_value = clustered_sign_permutation_p_value(
            session_means,
            seed=f"{seed}:permutation:{key}",
            iterations=iterations,
        )
        trials.append(
            {
                "trial_number": number,
                "experiment_id": key[0],
                "planning_mode": key[1],
                "target_sd": key[2],
                "spread_points": key[3],
                "slippage_points_per_side": key[4],
                "independent_session_count": len(session_means),
                "independent_non_overlapping_opportunity_count": len(
                    {row["episode_id"] for row in rows}
                ),
                "session_level_mean_points": (
                    mean(session_means.values()) if session_means else None
                ),
                "session_clustered_ci95": ci,
                "clustered_permutation_p_value": p_value,
                "resampling_unit": "session",
                "episode_level_p_value": None,
                "episode_level_p_value_status": "invalid_for_inference",
            }
        )
    _apply_bh(trials)
    violations = []
    for row in trials:
        ci = row["session_clustered_ci95"]
        inconsistent = bool(
            row["bh_q_value"] is not None
            and row["bh_q_value"] < 0.01
            and ci is not None
            and ci[0] < 0 < ci[1]
        )
        row["inference_consistency_status"] = "failed" if inconsistent else "passed"
        if inconsistent:
            violations.append(row["trial_number"])
    return {
        "trials": trials,
        "trial_count": len(trials),
        "resampling_unit": "session",
        "permutation_iterations": iterations,
        "bootstrap_iterations": iterations,
        "inference_consistency_violation_count": len(violations),
        "inference_consistency_violation_trials": violations,
        "research_only": True,
        "signal_allowed": False,
    }


def session_block_bootstrap_ci(
    session_means: dict[str, float],
    *,
    seed: str | int,
    iterations: int,
) -> list[float] | None:
    sessions = sorted(session_means)
    if not sessions:
        return None
    rng = random.Random(seed)
    samples = []
    for _ in range(iterations):
        selected = [rng.choice(sessions) for _ in sessions]
        samples.append(mean(session_means[session] for session in selected))
    samples.sort()
    return [
        samples[int(0.025 * (len(samples) - 1))],
        samples[int(0.975 * (len(samples) - 1))],
    ]


def clustered_sign_permutation_p_value(
    session_means: dict[str, float],
    *,
    seed: str | int,
    iterations: int,
) -> float | None:
    values = list(session_means.values())
    if not values:
        return None
    observed = abs(mean(values))
    rng = random.Random(seed)
    exceed = 0
    for _ in range(iterations):
        permuted = [value * rng.choice((-1, 1)) for value in values]
        exceed += abs(mean(permuted)) >= observed
    return (exceed + 1) / (iterations + 1)


def consistency_status(q_value: float | None, ci: list[float] | None) -> str:
    if q_value is not None and q_value < 0.01 and ci and ci[0] < 0 < ci[1]:
        return "failed"
    return "passed"


def _session_means(rows: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.get("net_points") is not None:
            grouped[row["session_date"]].append(float(row["net_points"]))
    return {session: mean(values) for session, values in grouped.items() if values}


def _apply_bh(trials: list[dict[str, Any]]) -> None:
    valid = sorted(
        (
            (index, float(row["clustered_permutation_p_value"]))
            for index, row in enumerate(trials)
            if row["clustered_permutation_p_value"] is not None
        ),
        key=lambda item: item[1],
    )
    running = 1.0
    for rank, (index, value) in reversed(list(enumerate(valid, start=1))):
        running = min(running, value * len(valid) / rank)
        trials[index]["bh_q_value"] = min(running, 1.0)
    for row in trials:
        row.setdefault("bh_q_value", None)
