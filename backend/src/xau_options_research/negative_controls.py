from __future__ import annotations

import copy
import random
from typing import Any

from src.models.xau_market_context import XauPriceBar
from src.xau_options_research.strategy_simulator import run_preregistered_strategies


def build_negative_controls(
    events: list[dict[str, Any]],
    bars: list[XauPriceBar],
    *,
    seed: int = 32,
) -> dict[str, Any]:
    controls = {
        "randomly_shifted_oi_walls": _shuffle_field(events, "oi_nearest_wall", seed + 1),
        "prior_session_oi": _prior_session_oi(events),
        "shuffled_iv_change_labels": _shuffle_field(events, "iv_state", seed + 2),
        "shuffled_volume_labels": _shuffle_field(events, "volume_change_percentile", seed + 3),
    }
    reports = []
    for name, rows in controls.items():
        result = run_preregistered_strategies(rows, bars)
        reports.append(
            {
                "control": name,
                "baseline_cost_summaries": [
                    row
                    for row in result["summaries"]
                    if row["spread_points"] == 1.0 and row["slippage_points_per_side"] == 0.0
                ],
            }
        )
    return {
        "deterministic_seed": seed,
        "price_only_controls": ["MR0", "BO0"],
        "controls": reports,
        "research_only": True,
        "signal_allowed": False,
    }


def _shuffle_field(events: list[dict[str, Any]], field: str, seed: int) -> list[dict[str, Any]]:
    rows = copy.deepcopy(events)
    sessions = sorted({row["session_date"] for row in rows})
    values = {
        session: next((row.get(field) for row in rows if row["session_date"] == session), None)
        for session in sessions
    }
    shuffled = sessions[:]
    random.Random(seed).shuffle(shuffled)
    mapping = {session: values[source] for session, source in zip(sessions, shuffled, strict=True)}
    for row in rows:
        row[field] = mapping[row["session_date"]]
        if field == "oi_nearest_wall" and row[field] is not None:
            row["oi_distance_sd"] = abs(float(row[field]) - float(row["entry_price"])) / float(
                row["one_sd_points"]
            )
    return rows


def _prior_session_oi(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = copy.deepcopy(events)
    sessions = sorted({row["session_date"] for row in rows})
    prior = {
        current: sessions[index - 1] if index else None for index, current in enumerate(sessions)
    }
    fields = ("oi_nearest_wall", "oi_distance_sd", "oi_rank", "oi_percentile")
    values = {
        session: {
            field: next((row.get(field) for row in rows if row["session_date"] == session), None)
            for field in fields
        }
        for session in sessions
    }
    for row in rows:
        source = prior[row["session_date"]]
        for field in fields:
            row[field] = values[source][field] if source is not None else None
    return rows
