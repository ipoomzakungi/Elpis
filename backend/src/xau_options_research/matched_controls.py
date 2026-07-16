from __future__ import annotations

import hashlib
import random
from collections import defaultdict
from collections.abc import Callable
from statistics import mean
from typing import Any


def build_matched_negative_control_report(
    outcomes: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    seed: int = 32,
    permutations: int = 1000,
) -> dict[str, Any]:
    event_index = {row["episode_id"]: row for row in events}
    base = [
        row
        for row in outcomes
        if row["experiment_id"] == "MR0"
        and row["spread_points"] == 1.0
        and row["slippage_points_per_side"] == 0.0
    ]
    oi_groups = []
    for mode in ("fixed_morning", "rolling_30m"):
        for target in (0.25, 0.5):
            candidates = [
                row for row in base if row["planning_mode"] == mode and row["target_sd"] == target
            ]
            real = [row for row in candidates if _real_oi(event_index.get(row["episode_id"], {}))]
            if not real:
                continue
            controls = {}
            control_episode_sets = {}
            scorers: dict[str, Callable[[dict[str, Any]], float]] = {
                "prior_session_oi_walls": lambda row: _prior_session_score(
                    row, event_index, events
                ),
                "randomly_shifted_walls": lambda row: _stable_random_score(
                    row["episode_id"], seed + 1
                ),
                "distance_only_without_rank": lambda row: float(
                    event_index.get(row["episode_id"], {}).get("oi_distance_sd") or 999
                ),
                "same_count_random_opportunities": lambda row: _stable_random_score(
                    row["episode_id"], seed + 2
                ),
                "persistent_multi_day_walls": lambda row: (
                    0.0
                    if event_index.get(row["episode_id"], {}).get("oi_wall_persistence") is True
                    else 1.0
                ),
            }
            for name, scorer in scorers.items():
                selected = _matched_select(candidates, real, scorer)
                controls[name] = _selection_stats(selected)
                control_episode_sets[name] = {row["episode_id"] for row in selected}
            distribution = _matched_random_distribution(
                candidates,
                real,
                seed=f"{seed}:{mode}:{target}",
                iterations=permutations,
            )
            real_expectancy = _expectancy(real)
            real_episodes = {row["episode_id"] for row in real}
            distinct_control_count = len(
                {tuple(sorted(values)) for values in control_episode_sets.values()}
            )
            discrimination = (
                "non_discriminating"
                if all(values == real_episodes for values in control_episode_sets.values())
                else "discriminating"
            )
            oi_groups.append(
                {
                    "planning_mode": mode,
                    "target_sd": target,
                    "real_oi": _selection_stats(real),
                    "controls": controls,
                    "random_control_distribution": _distribution_stats(distribution),
                    "real_oi_percentile_rank": (
                        sum(value <= real_expectancy for value in distribution) / len(distribution)
                        if distribution and real_expectancy is not None
                        else None
                    ),
                    "matched_counts_equal": all(
                        value["opportunity_count"] == len(real) for value in controls.values()
                    ),
                    "control_discrimination_status": discrimination,
                    "distinct_control_selection_count": distinct_control_count,
                }
            )
    iv = _iv_control(base, event_index, seed=seed, permutations=permutations)
    fixed_oi = next(
        (
            row
            for row in oi_groups
            if row["planning_mode"] == "fixed_morning" and row["target_sd"] == 0.5
        ),
        None,
    )
    c3_pass = bool(
        fixed_oi
        and fixed_oi["real_oi_percentile_rank"] is not None
        and fixed_oi["real_oi_percentile_rank"] >= 0.9
        and fixed_oi["control_discrimination_status"] == "discriminating"
        and all(
            fixed_oi["real_oi"]["expectancy_points"] > value["expectancy_points"]
            for value in fixed_oi["controls"].values()
            if value["expectancy_points"] is not None
        )
    )
    return {
        "oi_matched_controls": oi_groups,
        "iv_matched_control": iv,
        "permutation_iterations": permutations,
        "permutation_unit": "session-stratified opportunity set",
        "mr2_beats_controls": c3_pass,
        "research_only": True,
        "signal_allowed": False,
    }


def _matched_select(
    candidates: list[dict[str, Any]],
    real: list[dict[str, Any]],
    scorer: Callable[[dict[str, Any]], float],
) -> list[dict[str, Any]]:
    needed: dict[tuple[str, str], int] = defaultdict(int)
    for row in real:
        needed[(row["session_date"], row["side"])] += 1
    selected = []
    used = set()
    for stratum, count in sorted(needed.items()):
        pool = [row for row in candidates if (row["session_date"], row["side"]) == stratum]
        for row in sorted(pool, key=lambda item: (scorer(item), item["episode_id"]))[:count]:
            selected.append(row)
            used.add((row["episode_id"], row["target_sd"]))
    if len(selected) < len(real):
        remaining = [row for row in candidates if (row["episode_id"], row["target_sd"]) not in used]
        selected.extend(
            sorted(remaining, key=lambda item: (scorer(item), item["episode_id"]))[
                : len(real) - len(selected)
            ]
        )
    return selected[: len(real)]


def _matched_random_distribution(
    candidates: list[dict[str, Any]],
    real: list[dict[str, Any]],
    *,
    seed: str,
    iterations: int,
) -> list[float]:
    rng = random.Random(seed)
    needed: dict[tuple[str, str], int] = defaultdict(int)
    for row in real:
        needed[(row["session_date"], row["side"])] += 1
    values = []
    for _ in range(iterations):
        selected = []
        for stratum, count in needed.items():
            pool = [row for row in candidates if (row["session_date"], row["side"]) == stratum]
            if pool:
                selected.extend(rng.sample(pool, min(count, len(pool))))
        expectancy = _expectancy(selected)
        if expectancy is not None:
            values.append(expectancy)
    return values


def _iv_control(
    base: list[dict[str, Any]],
    event_index: dict[str, dict[str, Any]],
    *,
    seed: int,
    permutations: int,
) -> dict[str, Any]:
    actual = [
        row
        for row in base
        if event_index.get(row["episode_id"], {}).get("iv_state") in {"stable", "compressing"}
    ]
    actual_expectancy = _expectancy(actual)
    sessions = sorted({row["session_date"] for row in base})
    state_by_session = {
        session: next(
            (
                event_index.get(row["episode_id"], {}).get("iv_state")
                for row in base
                if row["session_date"] == session
            ),
            None,
        )
        for session in sessions
    }
    rng = random.Random(seed + 99)
    distribution = []
    for _ in range(permutations):
        shuffled = sessions[:]
        rng.shuffle(shuffled)
        mapping = {
            session: state_by_session[source]
            for session, source in zip(sessions, shuffled, strict=True)
        }
        selected = [
            row for row in base if mapping[row["session_date"]] in {"stable", "compressing"}
        ]
        value = _expectancy(selected)
        if value is not None:
            distribution.append(value)
    return {
        "actual_iv_state": _selection_stats(actual),
        "session_shuffled_distribution": _distribution_stats(distribution),
        "actual_percentile_rank": (
            sum(value <= actual_expectancy for value in distribution) / len(distribution)
            if distribution and actual_expectancy is not None
            else None
        ),
    }


def _real_oi(event: dict[str, Any]) -> bool:
    return bool(
        event.get("oi_rank") is not None
        and event["oi_rank"] <= 5
        and event.get("oi_distance_sd") is not None
        and event["oi_distance_sd"] <= 0.25
    )


def _prior_session_score(
    row: dict[str, Any],
    event_index: dict[str, dict[str, Any]],
    events: list[dict[str, Any]],
) -> float:
    sessions = sorted({event["session_date"] for event in events})
    try:
        index = sessions.index(row["session_date"])
    except ValueError:
        return 999.0
    if index == 0:
        return 999.0
    prior = next(
        (
            event
            for event in events
            if event["session_date"] == sessions[index - 1]
            and event.get("oi_nearest_wall") is not None
        ),
        None,
    )
    current = event_index.get(row["episode_id"], {})
    if prior is None or not current:
        return 999.0
    return abs(float(prior["oi_nearest_wall"]) - float(current["entry_price"])) / float(
        current["one_sd_points"]
    )


def _stable_random_score(value: str, seed: int) -> float:
    digest = hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()
    return int(digest[:16], 16) / 16**16


def _selection_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "opportunity_count": len(rows),
        "independent_session_count": len({row["session_date"] for row in rows}),
        "expectancy_points": _expectancy(rows),
    }


def _expectancy(rows: list[dict[str, Any]]) -> float | None:
    values = [float(row["net_points"]) for row in rows if row.get("net_points") is not None]
    return mean(values) if values else None


def _distribution_stats(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "count": len(values),
        "mean_expectancy_points": mean(values) if values else None,
        "ci95": (
            [
                ordered[int(0.025 * (len(ordered) - 1))],
                ordered[int(0.975 * (len(ordered) - 1))],
            ]
            if ordered
            else None
        ),
    }
