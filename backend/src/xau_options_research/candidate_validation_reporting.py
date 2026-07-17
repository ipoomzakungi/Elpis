from __future__ import annotations

from collections import defaultdict
from statistics import mean, median
from typing import Any

from src.xau_options_research.clustered_inference import session_block_bootstrap_ci


def build_validation_summary(
    outcomes: list[dict[str, Any]],
    *,
    calibration: list[dict[str, Any]] | None = None,
    accepted_session_dates: list[str] | None = None,
) -> dict[str, Any]:
    accepted_sessions = set(accepted_session_dates or [])
    if not accepted_session_dates:
        accepted_sessions = {row["session_date"] for row in outcomes}
    candidates = []
    for candidate_id in ("C1", "C2"):
        rows = [row for row in outcomes if row["candidate_id"] == candidate_id]
        priced = [row for row in rows if row.get("net_points") is not None]
        values = [float(row["net_points"]) for row in priced]
        session_means = _session_means(priced)
        calibration_row = next(
            (row for row in calibration or [] if row["candidate_id"] == candidate_id), None
        )
        expectancy = mean(values) if values else None
        candidates.append(
            {
                "candidate_id": candidate_id,
                "validation_session_count": len(accepted_sessions),
                "sessions_with_opportunities": len({row["session_date"] for row in rows}),
                "independent_opportunity_count": len({row["episode_id"] for row in rows}),
                "priced_outcome_count": len(priced),
                "ambiguous_outcome_count": sum(
                    row.get("resolved_status") == "same_bar_ambiguous" for row in rows
                ),
                "target_hit_count": sum(row.get("resolved_status") == "target_hit" for row in rows),
                "stop_hit_count": sum(row.get("resolved_status") == "stop_hit" for row in rows),
                "time_exit_count": sum(row.get("resolved_status") == "time_exit" for row in rows),
                "net_mean_points": expectancy,
                "net_median_points": median(values) if values else None,
                "session_clustered_ci95": session_block_bootstrap_ci(
                    session_means,
                    seed=f"validation-v2:{candidate_id}",
                    iterations=1000,
                ),
                "maximum_cumulative_drawdown_points": _max_drawdown(priced),
                "maximum_consecutive_losses": _max_consecutive_losses(priced),
                "leave_one_session_out": _leave_one_session_out(priced),
                "cost_sensitivity": _cost_sensitivity(priced),
                "entry_zone_results": _group_summary(priced, "entry_zone"),
                "side_results": _group_summary(priced, "side"),
                "cross_results": _cross_summary(priced),
                "calibration_expectancy_points": (
                    calibration_row.get("net_expectancy_points") if calibration_row else None
                ),
                "validation_minus_calibration_points": (
                    expectancy - float(calibration_row["net_expectancy_points"])
                    if expectancy is not None
                    and calibration_row
                    and calibration_row.get("net_expectancy_points") is not None
                    else None
                ),
                "evidence_status": _evidence_status(
                    rows, priced, session_means, accepted_sessions
                ),
            }
        )
    return {
        "validation_session_count": len(accepted_sessions),
        "candidates": candidates,
        "calibration_rows_in_validation": 0,
        "subgroups_are_descriptive_only": True,
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def build_daily_summary(
    session_date: str,
    outcomes: list[dict[str, Any]],
    *,
    c3_eligibility_count: int,
    bo0_monitor_count: int,
) -> dict[str, Any]:
    return {
        "summary_id": f"validation-v2:{session_date}",
        "session_date": session_date,
        "candidate_summaries": build_validation_summary(
            outcomes, accepted_session_dates=[session_date]
        )["candidates"],
        "c3_descriptive_eligibility_count": c3_eligibility_count,
        "c3_outcome_count": 0,
        "bo0_monitor_observation_count": bo0_monitor_count,
        "bo0_candidate_outcome_count": 0,
        "evidence_status": "insufficient_sample",
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _session_means(rows: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[row["session_date"]].append(float(row["net_points"]))
    return {session: mean(values) for session, values in grouped.items()}


def _max_drawdown(rows: list[dict[str, Any]]) -> float:
    equity = 0.0
    peak = 0.0
    maximum = 0.0
    for row in sorted(rows, key=lambda item: item["entry_timestamp"]):
        equity += float(row["net_points"])
        peak = max(peak, equity)
        maximum = max(maximum, peak - equity)
    return maximum


def _max_consecutive_losses(rows: list[dict[str, Any]]) -> int:
    current = 0
    maximum = 0
    for row in sorted(rows, key=lambda item: item["entry_timestamp"]):
        current = current + 1 if float(row["net_points"]) < 0 else 0
        maximum = max(maximum, current)
    return maximum


def _leave_one_session_out(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sessions = sorted({row["session_date"] for row in rows})
    values = []
    for omitted in sessions:
        sample = [
            float(row["net_points"])
            for row in rows
            if row["session_date"] != omitted and row.get("net_points") is not None
        ]
        if sample:
            values.append(mean(sample))
    return {
        "minimum_expectancy_points": min(values) if values else None,
        "maximum_expectancy_points": max(values) if values else None,
        "stable_positive": bool(values) and min(values) > 0,
    }


def _cost_sensitivity(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scenarios = []
    for spread in (0.3, 0.5, 1.0, 1.5):
        values = [
            float(row["gross_points"]) - spread
            for row in rows
            if row.get("gross_points") is not None
        ]
        scenarios.append(
            {
                "spread_points": spread,
                "net_expectancy_points": mean(values) if values else None,
            }
        )
    return scenarios


def _group_summary(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[str(row[field])].append(float(row["net_points"]))
    return [
        {field: key, "count": len(values), "net_mean_points": mean(values)}
        for key, values in sorted(grouped.items())
    ]


def _cross_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        grouped[(row["side"], row["entry_zone"])].append(float(row["net_points"]))
    return [
        {
            "side": key[0],
            "entry_zone": key[1],
            "count": len(values),
            "net_mean_points": mean(values),
        }
        for key, values in sorted(grouped.items())
    ]


def _evidence_status(
    rows: list[dict[str, Any]],
    priced: list[dict[str, Any]],
    session_means: dict[str, float],
    accepted_sessions: set[str],
) -> str:
    fill_sessions = {row["session_date"] for row in priced}
    values = [float(row["net_points"]) for row in priced]
    if (
        len(priced) >= 30
        and len(accepted_sessions) >= 15
        and len(fill_sessions) >= 10
        and values
        and median(values) > 0
        and len(session_means) >= 10
        and _leave_one_session_out(priced)["stable_positive"]
        and sum(row.get("resolved_status") == "same_bar_ambiguous" for row in rows)
        / max(len(rows), 1)
        <= 0.2
    ):
        return "provisional"
    return "insufficient_sample"
