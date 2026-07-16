from __future__ import annotations

import math
import random
from collections import defaultdict
from statistics import mean
from typing import Any


def build_validation_report(
    strategy_results: dict[str, Any],
    valid_sessions: list[str],
    *,
    development_fraction: float = 0.7,
    seed: int = 32,
    bootstrap_iterations: int = 500,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    sessions = sorted(set(valid_sessions))
    split = min(max(int(len(sessions) * development_fraction), 1), max(len(sessions) - 1, 1))
    development = sessions[:split] if len(sessions) > 1 else sessions
    holdout = sessions[split:] if len(sessions) > 1 else []
    base = [
        row
        for row in strategy_results["outcomes"]
        if row["spread_points"] == 1.0 and row["slippage_points_per_side"] == 0.0
    ]
    development_rows = [row for row in base if row["session_date"] in development]
    holdout_rows = [row for row in base if row["session_date"] in holdout]
    dev_summary = _grouped(development_rows)
    holdout_summary = _grouped(holdout_rows)
    degradation = _degradation(dev_summary, holdout_summary)
    trials = _trial_registry(strategy_results["summaries"])
    validation = {
        "development_sessions": development,
        "holdout_sessions": holdout,
        "development_session_count": len(development),
        "holdout_session_count": len(holdout),
        "development_summaries": dev_summary,
        "leave_one_session_out": _leave_one_session_out(development_rows),
        "session_clustered_bootstrap": _bootstrap(
            development_rows,
            seed=seed,
            iterations=bootstrap_iterations,
        ),
        "trial_count": len(trials),
        "effective_independent_experiment_families": 7,
        "resampling_unit": "session",
        "threshold_selection_uses_holdout": False,
        "research_only": True,
        "signal_allowed": False,
    }
    holdout_report = {
        "holdout_sessions": holdout,
        "summaries": holdout_summary,
        "development_to_holdout_degradation": degradation,
        "holdout_used_for_threshold_selection": False,
        "research_only": True,
        "signal_allowed": False,
    }
    trial_report = {
        "trials": trials,
        "trial_count": len(trials),
        "effective_independent_experiment_families": 7,
        "research_only": True,
        "signal_allowed": False,
    }
    return validation, holdout_report, trial_report


def evidence_status(
    *,
    unique_episodes: int,
    holdout_episodes: int,
    sessions_with_events: int,
    integrity_violations: int,
    statistical_support: bool,
) -> str:
    if (
        unique_episodes >= 30
        and holdout_episodes >= 10
        and sessions_with_events >= 10
        and integrity_violations == 0
        and statistical_support
    ):
        return "provisional"
    return "insufficient_sample"


def _grouped(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, float], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["experiment_id"], row["planning_mode"], row["target_sd"])].append(row)
    summaries = []
    for key, items in sorted(grouped.items()):
        values = [float(item["net_points"]) for item in items if item["net_points"] is not None]
        summaries.append(
            {
                "experiment_id": key[0],
                "planning_mode": key[1],
                "target_sd": key[2],
                "unique_episode_count": len({item["episode_id"] for item in items}),
                "independent_session_count": len({item["session_date"] for item in items}),
                "net_expectancy_points": mean(values) if values else None,
                "target_hit_count": sum(item["status"] == "target_hit" for item in items),
                "stop_hit_count": sum(item["status"] == "stop_hit" for item in items),
                "same_bar_ambiguous_count": sum(item["same_bar_ambiguous"] for item in items),
            }
        )
    return summaries


def _leave_one_session_out(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    sessions = sorted({row["session_date"] for row in rows})
    families = sorted({(row["experiment_id"], row["target_sd"]) for row in rows})
    for family in families:
        values = []
        for omitted in sessions:
            sample = [
                float(row["net_points"])
                for row in rows
                if row["experiment_id"] == family[0]
                and row["target_sd"] == family[1]
                and row["session_date"] != omitted
                and row["net_points"] is not None
            ]
            if sample:
                values.append(mean(sample))
        results.append(
            {
                "experiment_id": family[0],
                "target_sd": family[1],
                "minimum_expectancy": min(values) if values else None,
                "maximum_expectancy": max(values) if values else None,
                "omission_count": len(values),
            }
        )
    return results


def _bootstrap(rows: list[dict[str, Any]], *, seed: int, iterations: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, float], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["experiment_id"], row["target_sd"])].append(row)
    results = []
    for key, items in sorted(grouped.items()):
        by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            by_session[item["session_date"]].append(item)
        sessions = sorted(by_session)
        if not sessions:
            continue
        rng = random.Random(f"{seed}:{key}")
        samples = []
        for _ in range(iterations):
            selected = [rng.choice(sessions) for _ in sessions]
            values = [
                float(row["net_points"])
                for session in selected
                for row in by_session[session]
                if row["net_points"] is not None
            ]
            if values:
                samples.append(mean(values))
        samples.sort()
        results.append(
            {
                "experiment_id": key[0],
                "target_sd": key[1],
                "session_count": len(sessions),
                "net_expectancy_ci95": (
                    [
                        samples[int(0.025 * (len(samples) - 1))],
                        samples[int(0.975 * (len(samples) - 1))],
                    ]
                    if samples
                    else None
                ),
            }
        )
    return results


def _degradation(
    development: list[dict[str, Any]], holdout: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple[str, str, float]:
        return (row["experiment_id"], row["planning_mode"], row["target_sd"])

    holdout_index = {key(row): row for row in holdout}
    return [
        {
            "experiment_id": row["experiment_id"],
            "planning_mode": row["planning_mode"],
            "target_sd": row["target_sd"],
            "development_expectancy": row["net_expectancy_points"],
            "holdout_expectancy": holdout_index.get(key(row), {}).get("net_expectancy_points"),
            "degradation_points": _difference(
                row["net_expectancy_points"],
                holdout_index.get(key(row), {}).get("net_expectancy_points"),
            ),
        }
        for row in development
    ]


def _trial_registry(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trials = []
    for number, row in enumerate(summaries, start=1):
        expectancy = row.get("net_expectancy_points")
        count = int(row.get("unique_episode_count") or 0)
        raw_p = (
            math.erfc(abs(float(expectancy)) * math.sqrt(count) / math.sqrt(2))
            if expectancy is not None and count > 1
            else None
        )
        trials.append({"trial_number": number, **row, "raw_p_value": raw_p})
    valid = sorted(
        (
            (index, row["raw_p_value"])
            for index, row in enumerate(trials)
            if row["raw_p_value"] is not None
        ),
        key=lambda item: item[1],
    )
    running = 1.0
    for rank, (index, value) in reversed(list(enumerate(valid, start=1))):
        running = min(running, value * len(valid) / rank)
        trials[index]["bh_q_value"] = min(running, 1.0)
    for row in trials:
        row.setdefault("bh_q_value", None)
    return trials


def _difference(first: float | None, second: float | None) -> float | None:
    return second - first if first is not None and second is not None else None
