from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

from src.models.xau_market_context import XauPriceBar
from src.xau_vol2vol_history_walkforward.planning import XauPlanningSelection

ENTRY_DEFINITIONS = {
    "zone_2_entry": 1.0,
    "zone_2_mid": 1.5,
    "literal_2sd": 2.0,
    "literal_3sd": 3.0,
}


def build_sd_zone_audit(
    selections: list[XauPlanningSelection],
    bars: list[XauPriceBar],
    *,
    planning_mode: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    opportunities: list[dict[str, Any]] = []
    for selection in selections:
        snapshot = selection.range_snapshot
        levels = _mapped_levels(snapshot)
        if levels is None:
            continue
        window = [
            bar
            for bar in bars
            if selection.simulation_window_start
            <= bar.timestamp.astimezone(selection.planning_at.tzinfo)
            <= selection.simulation_window_end
        ]
        if not window:
            continue
        center = float(snapshot.cfd_open)
        diagnostic = _diagnostic(selection, window, levels, center, planning_mode)
        diagnostics.append(diagnostic)
        opportunities.extend(
            _opportunities(selection, window, levels, center, planning_mode)
        )
    return diagnostics, opportunities, _summary(diagnostics, opportunities, planning_mode)


def compare_mapping_modes(
    result_sets: list[dict[str, Any]],
) -> dict[str, Any]:
    by_key: dict[tuple, dict[str, bool]] = defaultdict(dict)
    for result in result_sets:
        mapping_mode = result["mapping_mode"]
        for item in result["opportunities"]:
            key = (
                result["planning_mode"],
                item["session_date"],
                item["planning_at"],
                item["entry_definition"],
                item["side"],
            )
            by_key[key][mapping_mode] = item["touched"]
    changed = [
        {
            "planning_mode": key[0],
            "session_date": key[1],
            "planning_at": key[2],
            "entry_definition": key[3],
            "side": key[4],
            "same_time_basis_touched": values.get("same_time_basis"),
            "distance_reanchored_touched": values.get("distance_reanchored"),
        }
        for key, values in by_key.items()
        if len(values) == 2 and len(set(values.values())) > 1
    ]
    return {
        "touch_classification_change_count": len(changed),
        "touch_classification_changes": changed,
        "true_basis_validation": "unavailable",
        "research_only": True,
        "signal_allowed": False,
    }


def _diagnostic(
    selection: XauPlanningSelection,
    bars: list[XauPriceBar],
    levels: dict[str, float],
    center: float,
    planning_mode: str,
) -> dict[str, Any]:
    high = max(bar.high for bar in bars)
    low = min(bar.low for bar in bars)
    nearest_2sd = min(abs(high - levels["upper_2sd"]), abs(low - levels["lower_2sd"]))
    return {
        "session_date": selection.session_date.isoformat(),
        "planning_mode": planning_mode,
        "planning_at": selection.planning_at.isoformat(),
        "simulation_window_start": selection.simulation_window_start.isoformat(),
        "simulation_window_end": selection.simulation_window_end.isoformat(),
        "selected_series": selection.range_snapshot.series,
        "series_selection_reason": selection.series_selection_reason,
        "candidate_series": selection.candidate_series,
        "dte": selection.range_snapshot.dte,
        "vol2vol_snapshot_time": selection.range_snapshot.observed_at.isoformat(),
        "xau_reference_time": (
            selection.selected_xau_price_time.isoformat()
            if selection.selected_xau_price_time
            else None
        ),
        "source_alignment_seconds": selection.source_alignment_seconds,
        "xau_price_age_at_planning_seconds": (
            selection.xau_price_age_at_planning_seconds
        ),
        "snapshot_age_at_planning_seconds": selection.snapshot_age_at_planning_seconds,
        "future_reference": selection.range_snapshot.future_open,
        "xau_reference": center,
        "mapping_mode": selection.mapping_mode.value,
        "calculated_diff": selection.range_snapshot.diff,
        **levels,
        "day_high": high,
        "day_low": low,
        "maximum_positive_sd": (high - center) / (levels["upper_1sd"] - center),
        "maximum_negative_sd": (low - center) / (center - levels["lower_1sd"]),
        "distance_missed_to_nearest_2sd": nearest_2sd,
        "reached_1sd": low <= levels["lower_1sd"] or high >= levels["upper_1sd"],
        "reached_1_5sd": (
            low <= levels["lower_1_5sd"] or high >= levels["upper_1_5sd"]
        ),
        "reached_2sd": low <= levels["lower_2sd"] or high >= levels["upper_2sd"],
        "reached_2_5sd": (
            low <= levels["lower_2_5sd"] or high >= levels["upper_2_5sd"]
        ),
        "reached_3sd": low <= levels["lower_3sd"] or high >= levels["upper_3sd"],
        "sd_ratio_2_to_1_lower": (center - levels["lower_2sd"])
        / (center - levels["lower_1sd"]),
        "sd_ratio_2_to_1_upper": (levels["upper_2sd"] - center)
        / (levels["upper_1sd"] - center),
        "sd_ratio_3_to_1_lower": (center - levels["lower_3sd"])
        / (center - levels["lower_1sd"]),
        "sd_ratio_3_to_1_upper": (levels["upper_3sd"] - center)
        / (levels["upper_1sd"] - center),
        "mapped_center_round_trip_error": abs(
            float(selection.range_snapshot.future_open)
            - float(selection.range_snapshot.diff)
            - center
        ),
        "expected_move_source": "vol2vol_ranges",
        "true_basis_validation": "unavailable",
        "research_only": True,
        "signal_allowed": False,
    }


def _opportunities(
    selection: XauPlanningSelection,
    bars: list[XauPriceBar],
    levels: dict[str, float],
    center: float,
    planning_mode: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for label, sd_value in ENTRY_DEFINITIONS.items():
        for side in ("long_reversion", "short_reversion"):
            level = _level_for_sd(levels, side, sd_value)
            touched_at = _first_touch(bars, side, level)
            result = {
                "opportunity_id": (
                    f"{selection.session_date}:{selection.cycle_label}:{side}:"
                    f"{label}:{level:.4f}"
                ),
                "session_date": selection.session_date.isoformat(),
                "planning_mode": planning_mode,
                "mapping_mode": selection.mapping_mode.value,
                "planning_at": selection.planning_at.isoformat(),
                "cycle_label": selection.cycle_label,
                "selected_series": selection.range_snapshot.series,
                "entry_definition": label,
                "entry_sd": sd_value,
                "entry_level": level,
                "side": side,
                "touched": touched_at is not None,
                "first_touch_time": touched_at.isoformat() if touched_at else None,
                "research_only": True,
                "signal_allowed": False,
            }
            if touched_at is not None:
                result.update(_post_touch_metrics(bars, touched_at, level, side, levels, center))
            results.append(result)
    return results


def _post_touch_metrics(
    bars: list[XauPriceBar],
    touched_at: datetime,
    entry: float,
    side: str,
    levels: dict[str, float],
    center: float,
) -> dict[str, Any]:
    one_sd = (
        center - levels["lower_1sd"]
        if side == "long_reversion"
        else levels["upper_1sd"] - center
    )
    metrics: dict[str, Any] = {}
    for label, minutes in (("15m", 15), ("30m", 30), ("60m", 60), ("window_end", None)):
        end = touched_at + timedelta(minutes=minutes) if minutes is not None else None
        sample = [
            bar
            for bar in bars
            if bar.timestamp >= touched_at and (end is None or bar.timestamp <= end)
        ]
        favorable, adverse = _excursions(sample, entry, side)
        metrics[f"mfe_{label}_points"] = favorable
        metrics[f"mae_{label}_points"] = adverse
    window_favorable = metrics["mfe_window_end_points"] or 0.0
    metrics["returned_0_25sd"] = window_favorable >= 0.25 * one_sd
    metrics["returned_0_5sd"] = window_favorable >= 0.5 * one_sd
    metrics["returned_1sd"] = window_favorable >= one_sd
    return metrics


def _summary(
    diagnostics: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
    planning_mode: str,
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in opportunities:
        groups[item["entry_definition"]].append(item)
    source_gaps = [
        float(item["source_alignment_seconds"])
        for item in diagnostics
        if item["source_alignment_seconds"] is not None
    ]
    return {
        "planning_mode": planning_mode,
        "mapping_mode": diagnostics[0]["mapping_mode"] if diagnostics else None,
        "testable_session_count": len({item["session_date"] for item in diagnostics}),
        "testable_plan_version_count": len(diagnostics),
        "source_alignment_p50_seconds": _percentile(source_gaps, 0.50),
        "source_alignment_p95_seconds": _percentile(source_gaps, 0.95),
        "source_alignment_max_seconds": max(source_gaps) if source_gaps else None,
        "entry_definitions": {
            key: {
                "candidate_count": len(items),
                "touch_count": sum(item["touched"] for item in items),
                "unique_touched_sessions": len(
                    {item["session_date"] for item in items if item["touched"]}
                ),
                "return_0_25sd_count": sum(
                    bool(item.get("returned_0_25sd")) for item in items
                ),
                "return_0_5sd_count": sum(
                    bool(item.get("returned_0_5sd")) for item in items
                ),
                "return_1sd_count": sum(
                    bool(item.get("returned_1sd")) for item in items
                ),
                "average_mfe_window_end_points": _average(
                    [item.get("mfe_window_end_points") for item in items]
                ),
                "average_mae_window_end_points": _average(
                    [item.get("mae_window_end_points") for item in items]
                ),
                "cost_adjusted_expectancy": "unavailable_without_predeclared_exit_rule",
            }
            for key, items in sorted(groups.items())
        },
        "true_basis_validation": "unavailable",
        "research_only": True,
        "signal_allowed": False,
    }


def _mapped_levels(snapshot) -> dict[str, float] | None:
    required = (
        snapshot.future_open,
        snapshot.cfd_open,
        snapshot.diff,
        snapshot.future_buy_1sd,
        snapshot.future_buy_2sd,
        snapshot.future_buy_3sd,
        snapshot.future_sell_1sd,
        snapshot.future_sell_2sd,
        snapshot.future_sell_3sd,
    )
    if any(value is None for value in required):
        return None
    diff = float(snapshot.diff)
    lower_1 = float(snapshot.future_buy_1sd) - diff
    lower_2 = float(snapshot.future_buy_2sd) - diff
    lower_3 = float(snapshot.future_buy_3sd) - diff
    upper_1 = float(snapshot.future_sell_1sd) - diff
    upper_2 = float(snapshot.future_sell_2sd) - diff
    upper_3 = float(snapshot.future_sell_3sd) - diff
    return {
        "lower_1sd": lower_1,
        "lower_1_5sd": (lower_1 + lower_2) / 2,
        "lower_2sd": lower_2,
        "lower_2_5sd": (lower_2 + lower_3) / 2,
        "lower_3sd": lower_3,
        "upper_1sd": upper_1,
        "upper_1_5sd": (upper_1 + upper_2) / 2,
        "upper_2sd": upper_2,
        "upper_2_5sd": (upper_2 + upper_3) / 2,
        "upper_3sd": upper_3,
    }


def _level_for_sd(levels: dict[str, float], side: str, sd_value: float) -> float:
    prefix = "lower" if side == "long_reversion" else "upper"
    suffix = {1.0: "1sd", 1.5: "1_5sd", 2.0: "2sd", 3.0: "3sd"}[sd_value]
    return levels[f"{prefix}_{suffix}"]


def _first_touch(bars: list[XauPriceBar], side: str, level: float) -> datetime | None:
    if side == "long_reversion":
        return next((bar.timestamp for bar in bars if bar.low <= level), None)
    return next((bar.timestamp for bar in bars if bar.high >= level), None)


def _excursions(bars: list[XauPriceBar], entry: float, side: str) -> tuple[float, float]:
    if not bars:
        return 0.0, 0.0
    if side == "long_reversion":
        return max(bar.high - entry for bar in bars), min(bar.low - entry for bar in bars)
    return max(entry - bar.low for bar in bars), min(entry - bar.high for bar in bars)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def _average(values: list[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return mean(present) if present else None
