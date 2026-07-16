from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time
from statistics import mean
from typing import Any


def build_event_independence_audit(
    raw_events: list[dict[str, Any]],
    episode_events: list[dict[str, Any]],
    strategy_results: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    event_index = {row["episode_id"]: row for row in episode_events}
    revised, blocked = enforce_non_overlapping_positions(strategy_results["outcomes"], event_index)
    current = _summaries(strategy_results["outcomes"])
    non_overlapping = _summaries(revised)
    base_revised = [
        row
        for row in revised
        if row["spread_points"] == 1.0 and row["slippage_points_per_side"] == 0.0
    ]
    audit = {
        "raw_event_count": len(raw_events),
        "checkpoint_event_count": len(raw_events),
        "continuous_excursion_count": len({row["episode_id"] for row in episode_events}),
        "non_overlapping_tradable_opportunity_count": len(
            {row["episode_id"] for row in base_revised}
        ),
        "concurrent_position_block_count": blocked,
        "duplicated_event_count": len(raw_events) - len({row["event_id"] for row in raw_events}),
        "repeated_rolling_signal_count": sum(
            row["planning_mode"] == "rolling_30m" and not row.get("is_episode_anchor", False)
            for row in raw_events
        ),
        "current_accounting": current,
        "non_overlapping_one_position_accounting": non_overlapping,
        "concurrency_rule": "one active position per experiment, side, series, and configuration",
        "cost_scenarios_multiply_sample": False,
        "research_only": True,
        "signal_allowed": False,
    }
    revised_results = {
        "outcomes": revised,
        "summaries": non_overlapping,
        "blocked_concurrent_rows": blocked,
        "research_only": True,
        "signal_allowed": False,
    }
    return audit, revised_results


def enforce_non_overlapping_positions(
    outcomes: list[dict[str, Any]],
    event_index: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in outcomes:
        event = event_index.get(row["episode_id"], {})
        key = (
            row["experiment_id"],
            row["planning_mode"],
            row["target_sd"],
            row["spread_points"],
            row["slippage_points_per_side"],
            row["side"],
            event.get("selected_series"),
        )
        grouped[key].append({**row, "selected_series": event.get("selected_series")})
    kept = []
    blocked = 0
    for rows in grouped.values():
        active_until: datetime | None = None
        active_session: str | None = None
        for row in sorted(rows, key=lambda item: item["entry_timestamp"]):
            entry = datetime.fromisoformat(row["entry_timestamp"])
            if active_session != row["session_date"]:
                active_until = None
                active_session = row["session_date"]
            if active_until is not None and entry <= active_until:
                blocked += 1
                continue
            kept.append(row)
            active_until = _exit_or_session_end(row, entry)
    kept.sort(
        key=lambda row: (
            row["session_date"],
            row["entry_timestamp"],
            row["experiment_id"],
        )
    )
    return kept, blocked


def candidate_summaries(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    definitions = (
        ("C1", "MR0", "fixed_morning", 0.5),
        ("C2", "MR0", "rolling_30m", 0.25),
        ("C3", "MR2", "fixed_morning", 0.5),
        ("BO0_MONITOR", "BO0", "fixed_morning", 0.5),
    )
    base = [
        row
        for row in outcomes
        if row["spread_points"] == 1.0 and row["slippage_points_per_side"] == 0.0
    ]
    results = []
    for candidate, experiment, mode, target in definitions:
        rows = [
            row
            for row in base
            if row["experiment_id"] == experiment
            and row["planning_mode"] == mode
            and row["target_sd"] == target
        ]
        values = [float(row["net_points"]) for row in rows if row["net_points"] is not None]
        results.append(
            {
                "candidate_id": candidate,
                "experiment_id": experiment,
                "planning_mode": mode,
                "target_sd": target,
                "non_overlapping_opportunity_count": len({row["episode_id"] for row in rows}),
                "priced_opportunity_count": len(
                    {row["episode_id"] for row in rows if row["net_points"] is not None}
                ),
                "independent_session_count": len({row["session_date"] for row in rows}),
                "priced_independent_session_count": len(
                    {row["session_date"] for row in rows if row["net_points"] is not None}
                ),
                "same_bar_ambiguous_count": sum(row["same_bar_ambiguous"] for row in rows),
                "net_expectancy_points": mean(values) if values else None,
                "by_entry_zone": _entry_zone_summaries(rows),
                "by_side": _side_summaries(rows),
            }
        )
    return results


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
    result = []
    for key, items in sorted(grouped.items()):
        values = [float(row["net_points"]) for row in items if row["net_points"] is not None]
        result.append(
            {
                "experiment_id": key[0],
                "planning_mode": key[1],
                "target_sd": key[2],
                "spread_points": key[3],
                "slippage_points_per_side": key[4],
                "unique_episode_count": len({row["episode_id"] for row in items}),
                "independent_session_count": len({row["session_date"] for row in items}),
                "net_expectancy_points": mean(values) if values else None,
            }
        )
    return result


def _exit_or_session_end(row: dict[str, Any], entry: datetime) -> datetime:
    if row.get("exit_timestamp"):
        return datetime.fromisoformat(row["exit_timestamp"])
    return datetime.combine(entry.date(), time(23, 59, 59), tzinfo=entry.tzinfo)


def _entry_zone_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        zone = "1.5SD" if "1_5sd" in row["event_type"] else "1SD"
        if row["net_points"] is not None:
            grouped[zone].append(float(row["net_points"]))
    return [
        {"entry_zone": key, "count": len(values), "expectancy_points": mean(values)}
        for key, values in sorted(grouped.items())
    ]


def _side_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row["net_points"] is not None:
            grouped[row["side"]].append(float(row["net_points"]))
    return [
        {"side": key, "count": len(values), "expectancy_points": mean(values)}
        for key, values in sorted(grouped.items())
    ]
