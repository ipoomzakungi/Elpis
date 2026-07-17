from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import mean
from typing import Any

from src.models.xau_market_context import XauPriceBar

SPREADS = (0.3, 0.5, 1.0, 1.5)
SLIPPAGES = (0.0, 0.2, 0.5)


def simulate_frozen_candidate(
    candidate: dict[str, Any],
    events: list[dict[str, Any]],
    bars: list[XauPriceBar],
    *,
    spread_points: float,
    slippage_points_per_side: float,
) -> list[dict[str, Any]]:
    if candidate.get("experiment_id") != "MR0" or candidate.get("candidate_id") not in {
        "C1",
        "C2",
    }:
        raise ValueError("Only frozen C1/C2 candidates may create validation outcomes")
    target_sd = float(candidate["target_sd"])
    selected = [
        event
        for event in events
        if event["planning_mode"] == candidate["planning_mode"]
        and event["event_type"]
        in {
            "lower_1sd_touch",
            "lower_1_5sd_touch",
            "upper_1sd_touch",
            "upper_1_5sd_touch",
        }
    ]
    total_cost = spread_points + 2 * slippage_points_per_side
    outcomes = []
    for event in selected:
        outcome = _simulate(event, bars, target_sd=target_sd)
        gross = outcome.get("gross_points")
        outcomes.append(
            {
                **outcome,
                "experiment_id": candidate["experiment_id"],
                "candidate_id": candidate["candidate_id"],
                "candidate_hash": candidate["candidate_hash"],
                "target_sd": target_sd,
                "spread_points": spread_points,
                "slippage_points_per_side": slippage_points_per_side,
                "total_cost_points": total_cost,
                "net_points": gross - total_cost if gross is not None else None,
                "original_m1_status": outcome["status"],
                "resolved_status": outcome["status"],
                "resolution_source": None,
                "resolution_confidence": None,
                "research_only": True,
                "signal_allowed": False,
                "order_submission_allowed": False,
            }
        )
    return outcomes


def run_preregistered_strategies(
    events: list[dict[str, Any]],
    bars: list[XauPriceBar],
) -> dict[str, Any]:
    trial_rows = []
    base_outcomes: dict[tuple[str, str], dict[str, Any]] = {}
    for experiment_id in ("MR0", "MR1", "MR2", "MR3", "BO0", "BO1", "PIN0"):
        selected = [event for event in events if _eligible(experiment_id, event)]
        targets = (0.25, 0.5) if experiment_id.startswith("MR") else (0.5,)
        for target_sd in targets:
            for event in selected:
                outcome = _simulate(event, bars, target_sd=target_sd)
                base_outcomes[(experiment_id, f"{event['episode_id']}:{target_sd}")] = outcome
                for spread in SPREADS:
                    for slippage in SLIPPAGES:
                        total_cost = spread + 2 * slippage
                        gross = outcome.get("gross_points")
                        trial_rows.append(
                            {
                                **outcome,
                                "experiment_id": experiment_id,
                                "target_sd": target_sd,
                                "spread_points": spread,
                                "slippage_points_per_side": slippage,
                                "total_cost_points": total_cost,
                                "net_points": gross - total_cost if gross is not None else None,
                                "research_only": True,
                                "signal_allowed": False,
                            }
                        )
    summaries = _summaries(trial_rows)
    return {
        "outcomes": trial_rows,
        "summaries": summaries,
        "incremental_value": _incremental_value(trial_rows),
        "trial_count": len(summaries),
        "configuration_row_count": len(trial_rows),
        "cost_scenarios_multiply_sample": False,
        "same_bar_policy": "ambiguous_on_entry_bar; stop_first_after_entry_bar",
        "research_only": True,
        "signal_allowed": False,
    }


def _eligible(experiment_id: str, event: dict[str, Any]) -> bool:
    event_type = event["event_type"]
    is_mr = event_type in {
        "lower_1sd_touch",
        "lower_1_5sd_touch",
        "upper_1sd_touch",
        "upper_1_5sd_touch",
    }
    if experiment_id == "MR0":
        return is_mr
    if experiment_id == "MR1":
        return is_mr and event.get("iv_state") in {"stable", "compressing"}
    oi_near = (
        event.get("oi_rank") is not None
        and event["oi_rank"] <= 5
        and event.get("oi_distance_sd") is not None
        and event["oi_distance_sd"] <= 0.25
    )
    if experiment_id == "MR2":
        return is_mr and oi_near
    if experiment_id == "MR3":
        volume_acceleration = event.get("volume_change_percentile")
        return (
            is_mr
            and oi_near
            and event.get("iv_state") in {"stable", "compressing"}
            and volume_acceleration is not None
            and volume_acceleration < 0.75
        )
    is_breakout = event_type.startswith("close_beyond_")
    if experiment_id == "BO0":
        return is_breakout
    if experiment_id == "BO1":
        gap = (
            event.get("oi_low_activity_gap_above")
            if event["side"] == "long_breakout"
            else event.get("oi_low_activity_gap_below")
        )
        return (
            is_breakout
            and event.get("iv_state") == "expanding"
            and (event.get("volume_change_percentile") or 0) >= 0.75
            and gap is True
        )
    return (
        experiment_id == "PIN0"
        and event_type == "pin_candidate"
        and event.get("dte") is not None
        and event["dte"] <= 1.0
        and oi_near
    )


def _simulate(
    event: dict[str, Any],
    bars: list[XauPriceBar],
    *,
    target_sd: float,
) -> dict[str, Any]:
    timestamp = datetime.fromisoformat(event["event_timestamp"])
    window = [
        bar
        for bar in bars
        if bar.timestamp >= timestamp and bar.timestamp.date() == timestamp.date()
    ]
    direction = _direction(event)
    entry = float(event["entry_price"])
    one_sd = float(event["one_sd_points"])
    target, stop = _levels(event, direction, entry, one_sd, target_sd)
    status = "time_exit"
    exit_price = window[-1].close if window else None
    exited_at = window[-1].timestamp if window else None
    ambiguous = False
    for index, bar in enumerate(window):
        target_hit = bar.high >= target if direction > 0 else bar.low <= target
        stop_hit = bar.low <= stop if direction > 0 else bar.high >= stop
        if index == 0 and (target_hit or stop_hit):
            status = "same_bar_ambiguous"
            exit_price = None
            exited_at = None
            ambiguous = True
            break
        if target_hit and stop_hit:
            status = "stop_hit"
            exit_price = stop
            exited_at = bar.timestamp
            break
        if stop_hit:
            status = "stop_hit"
            exit_price = stop
            exited_at = bar.timestamp
            break
        if target_hit:
            status = "target_hit"
            exit_price = target
            exited_at = bar.timestamp
            break
    gross = direction * (exit_price - entry) if exit_price is not None else None
    return {
        "episode_id": event["episode_id"],
        "event_id": event["event_id"],
        "session_date": event["session_date"],
        "planning_mode": event["planning_mode"],
        "side": event["side"],
        "event_type": event["event_type"],
        "entry_timestamp": event["event_timestamp"],
        "entry_price": entry,
        "target_price": target,
        "stop_price": stop,
        "status": status,
        "exit_timestamp": exited_at.isoformat() if exited_at else None,
        "exit_price": exit_price,
        "gross_points": gross,
        "same_bar_ambiguous": ambiguous,
    }


def _levels(
    event: dict[str, Any], direction: int, entry: float, one_sd: float, target_sd: float
) -> tuple[float, float]:
    if event["event_type"] == "pin_candidate" and event.get("oi_nearest_wall") is not None:
        target = float(event["oi_nearest_wall"])
        direction = 1 if target >= entry else -1
        return target, entry - direction * 0.5 * one_sd
    if event["side"].endswith("breakout"):
        next_wall = (
            event.get("oi_next_wall_above") if direction > 0 else event.get("oi_next_wall_below")
        )
        target = (
            float(next_wall)
            if next_wall is not None and direction * (float(next_wall) - entry) > 0
            else entry + direction * target_sd * one_sd
        )
        return target, entry - direction * 0.5 * one_sd
    target = entry + direction * target_sd * one_sd
    stop_distance = one_sd if "1sd_touch" in event["event_type"] else one_sd
    return target, entry - direction * stop_distance


def _direction(event: dict[str, Any]) -> int:
    if event["side"] == "pin":
        wall = event.get("oi_nearest_wall")
        return 1 if wall is not None and wall >= event["entry_price"] else -1
    return 1 if event["side"] in {"long_reversion", "long_breakout"} else -1


def _summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                row["experiment_id"],
                row["planning_mode"],
                row["target_sd"],
                row["spread_points"],
                row["slippage_points_per_side"],
            )
        ].append(row)
    summaries = []
    for key, items in sorted(grouped.items()):
        net = [float(item["net_points"]) for item in items if item["net_points"] is not None]
        summaries.append(
            {
                "experiment_id": key[0],
                "planning_mode": key[1],
                "target_sd": key[2],
                "spread_points": key[3],
                "slippage_points_per_side": key[4],
                "unique_episode_count": len({item["episode_id"] for item in items}),
                "independent_session_count": len({item["session_date"] for item in items}),
                "target_hit_count": sum(item["status"] == "target_hit" for item in items),
                "stop_hit_count": sum(item["status"] == "stop_hit" for item in items),
                "time_exit_count": sum(item["status"] == "time_exit" for item in items),
                "same_bar_ambiguous_count": sum(item["same_bar_ambiguous"] for item in items),
                "net_expectancy_points": mean(net) if net else None,
            }
        )
    return summaries


def _incremental_value(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline_rows = [
        row
        for row in rows
        if row["spread_points"] == 1.0 and row["slippage_points_per_side"] == 0.0
    ]
    by_experiment: dict[str, dict[tuple[str, float], dict[str, Any]]] = defaultdict(dict)
    for row in baseline_rows:
        by_experiment[row["experiment_id"]][(row["episode_id"], row["target_sd"])] = row
    comparisons = []
    for experiment, control in (
        ("MR1", "MR0"),
        ("MR2", "MR0"),
        ("MR3", "MR0"),
        ("BO1", "BO0"),
    ):
        execution_differences = []
        retained = []
        for key, row in by_experiment[experiment].items():
            baseline = by_experiment[control].get(key)
            if (
                baseline is not None
                and row.get("net_points") is not None
                and baseline.get("net_points") is not None
            ):
                execution_differences.append(
                    float(row["net_points"]) - float(baseline["net_points"])
                )
                retained.append(float(baseline["net_points"]))
        selected_keys = set(by_experiment[experiment])
        rejected = [
            float(row["net_points"])
            for key, row in by_experiment[control].items()
            if key not in selected_keys and row.get("net_points") is not None
        ]
        retained_expectancy = mean(retained) if retained else None
        rejected_expectancy = mean(rejected) if rejected else None
        comparisons.append(
            {
                "experiment_id": experiment,
                "matched_control": control,
                "matched_episode_count": len(retained),
                "rejected_control_episode_count": len(rejected),
                "retained_expectancy_points": retained_expectancy,
                "rejected_expectancy_points": rejected_expectancy,
                "mean_incremental_net_points": (
                    retained_expectancy - rejected_expectancy
                    if retained_expectancy is not None and rejected_expectancy is not None
                    else None
                ),
                "same_episode_execution_difference_points": (
                    mean(execution_differences) if execution_differences else None
                ),
            }
        )
    return comparisons
