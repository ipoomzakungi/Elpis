from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo

from src.models.xau_market_context import XauPriceBar
from src.xau_vol2vol_history_walkforward.planning import XauPlanningSelection

ENTRY_DEFINITIONS = {
    "zone_2_entry": 1.0,
    "zone_2_mid": 1.5,
    "literal_2sd": 2.0,
    "literal_3sd": 3.0,
}

EXIT_STRATEGIES = {
    "A": {"entry_definition": "zone_2_entry", "target_sd": 0.25, "stop_sd": 2.0},
    "B": {"entry_definition": "zone_2_entry", "target_sd": 0.5, "stop_sd": 2.0},
    "C": {"entry_definition": "zone_2_mid", "target_sd": 0.25, "stop_sd": 2.5},
    "D": {"entry_definition": "zone_2_mid", "target_sd": 0.5, "stop_sd": 2.5},
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


def build_session_coverage_rows(
    range_snapshots,
    bars: list[XauPriceBar],
    result_sets: list[dict[str, Any]],
    *,
    timezone: str,
    bar_interval_minutes: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    zone = ZoneInfo(timezone)
    fixed_sources = {
        item["source_session_date"]
        for result in result_sets
        if result["planning_mode"] == "fixed_morning"
        for item in result["diagnostics"]
    }
    rolling_sources = {
        item["source_session_date"]
        for result in result_sets
        if result["planning_mode"] == "rolling_30m"
        for item in result["diagnostics"]
    }
    by_source = defaultdict(list)
    for snapshot in range_snapshots:
        by_source[snapshot.session_date].append(snapshot)
    rows = []
    exclusions: dict[str, int] = defaultdict(int)
    for source_date, snapshots in sorted(by_source.items()):
        observed = sorted(item.observed_at.astimezone(zone) for item in snapshots)
        trading_date = observed[0].date()
        date_bars = sorted(
            [bar for bar in bars if bar.timestamp.astimezone(zone).date() == trading_date],
            key=lambda item: item.timestamp,
        )
        planning_at = datetime.combine(
            trading_date,
            datetime.min.time().replace(hour=7),
            tzinfo=zone,
        )
        pre_morning = [item for item in observed if item <= planning_at]
        pre_morning_snapshots = [
            item
            for item in snapshots
            if item.observed_at.astimezone(zone) <= planning_at
        ]
        complete_pre_morning = [
            item for item in pre_morning_snapshots if _has_complete_sd_snapshot(item)
        ]
        complete_anytime = [item for item in snapshots if _has_complete_sd_snapshot(item)]
        full_day = _has_complete_day_window(
            date_bars,
            planning_at=planning_at,
            interval_minutes=bar_interval_minutes,
        )
        source_text = source_date.isoformat()
        reasons = []
        if not date_bars:
            reasons.append("no_xau_bars_on_bangkok_trading_date")
        elif not full_day:
            reasons.append("incomplete_xau_0700_to_2359_window")
        if not pre_morning:
            reasons.append("no_pre_0700_vol2vol_snapshot")
        elif not complete_pre_morning:
            reasons.append("no_complete_sd_ladder_before_0700")
        if source_text not in fixed_sources:
            if date_bars and full_day and complete_pre_morning:
                reasons.append("fixed_morning_planning_integrity_gate_failed")
        if source_text not in rolling_sources:
            if date_bars and complete_anytime:
                reasons.append("rolling_30m_planning_integrity_gate_failed")
        for reason in set(reasons):
            exclusions[reason] += 1
        rows.append(
            {
                "source_session_date": source_text,
                "first_vol2vol_observed_at": observed[0].isoformat(),
                "last_vol2vol_observed_at": observed[-1].isoformat(),
                "bangkok_trading_date": trading_date.isoformat(),
                "xau_bar_start": (
                    date_bars[0].timestamp.astimezone(zone).isoformat()
                    if date_bars
                    else None
                ),
                "xau_bar_end": (
                    date_bars[-1].timestamp.astimezone(zone).isoformat()
                    if date_bars
                    else None
                ),
                "xau_bar_count": len(date_bars),
                "pre_0700_snapshot_available": bool(pre_morning),
                "complete_full_day_candle_window": full_day,
                "fixed_morning_testable": source_text in fixed_sources,
                "rolling_30m_testable": source_text in rolling_sources,
                "exclusion_reasons": reasons,
                "research_only": True,
                "signal_allowed": False,
            }
        )
    return rows, dict(sorted(exclusions.items()))


def build_preregistered_exit_backtest(
    result_sets: list[dict[str, Any]],
    bars: list[XauPriceBar],
    *,
    costs: tuple[float, ...] = (0.0, 0.3, 0.5, 1.0),
) -> dict[str, Any]:
    experiments = []
    for result in result_sets:
        diagnostics = {
            (item["session_date"], item["planning_at"]): item
            for item in result["diagnostics"]
        }
        touched = [
            item
            for item in result["opportunities"]
            if item["touched"]
            and item["entry_definition"] in {"zone_2_entry", "zone_2_mid"}
        ]
        opportunities = _first_filled_opportunities(touched)
        outcomes = []
        for opportunity in opportunities:
            diagnostic = diagnostics[
                (opportunity["session_date"], opportunity["planning_at"])
            ]
            for strategy_id, strategy in EXIT_STRATEGIES.items():
                if strategy["entry_definition"] != opportunity["entry_definition"]:
                    continue
                for cost in costs:
                    outcomes.append(
                        _simulate_exit_strategy(
                            opportunity,
                            diagnostic,
                            bars,
                            strategy_id=strategy_id,
                            target_sd=float(strategy["target_sd"]),
                            stop_sd=float(strategy["stop_sd"]),
                            cost_points=cost,
                        )
                    )
        experiments.append(
            {
                "planning_mode": result["planning_mode"],
                "mapping_mode": result["mapping_mode"],
                "unique_market_opportunity_count": len(opportunities),
                "configuration_outcome_count": len(outcomes) // max(len(costs), 1),
                "cost_scenario_row_count": len(outcomes),
                "outcomes": outcomes,
                "summary_by_strategy_and_cost": _exit_summary(outcomes),
                "same_bar_policy": "conservative_stop_first",
                "rolling_pending_order_policy": "cancel_replace_unfilled_keep_filled",
                "research_only": True,
                "signal_allowed": False,
            }
        )
    return {
        "strategies": EXIT_STRATEGIES,
        "cost_points": list(costs),
        "experiments": experiments,
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
        "source_session_date": selection.source_session_date.isoformat(),
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
        "atm_vol": selection.range_snapshot.vol_now,
        "atm_vol_change": selection.range_snapshot.vol_chg,
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


def _first_filled_opportunities(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    first: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in sorted(items, key=lambda value: value["first_touch_time"]):
        key = (item["session_date"], item["side"], item["entry_definition"])
        first.setdefault(key, item)
    return list(first.values())


def _simulate_exit_strategy(
    opportunity: dict[str, Any],
    diagnostic: dict[str, Any],
    bars: list[XauPriceBar],
    *,
    strategy_id: str,
    target_sd: float,
    stop_sd: float,
    cost_points: float,
) -> dict[str, Any]:
    touched_at = datetime.fromisoformat(opportunity["first_touch_time"])
    session_date = datetime.fromisoformat(opportunity["planning_at"]).date()
    side = opportunity["side"]
    entry = float(opportunity["entry_level"])
    center = float(diagnostic["xau_reference"])
    one_sd = (
        center - float(diagnostic["lower_1sd"])
        if side == "long_reversion"
        else float(diagnostic["upper_1sd"]) - center
    )
    target = (
        entry + target_sd * one_sd
        if side == "long_reversion"
        else entry - target_sd * one_sd
    )
    stop_suffix = "2sd" if stop_sd == 2.0 else "2_5sd"
    stop_key = (
        f"lower_{stop_suffix}"
        if side == "long_reversion"
        else f"upper_{stop_suffix}"
    )
    stop = float(diagnostic[stop_key])
    window = [
        bar
        for bar in bars
        if bar.timestamp.astimezone(touched_at.tzinfo).date() == session_date
        and bar.timestamp >= touched_at
    ]
    status = "unavailable"
    exit_price = None
    exited_at = None
    mfe = None
    mae = None
    for bar in window:
        favorable, adverse = _excursions([bar], entry, side)
        mfe = favorable if mfe is None else max(mfe, favorable)
        mae = adverse if mae is None else min(mae, adverse)
        target_hit = bar.high >= target if side == "long_reversion" else bar.low <= target
        stop_hit = bar.low <= stop if side == "long_reversion" else bar.high >= stop
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
    if status == "unavailable" and window:
        exit_price = window[-1].close
        exited_at = window[-1].timestamp
        gross_at_end = _gross(entry, exit_price, side)
        status = "time_exit_profit" if gross_at_end >= 0 else "time_exit_loss"
    gross = _gross(entry, exit_price, side) if exit_price is not None else None
    return {
        "opportunity_id": opportunity["opportunity_id"],
        "session_date": opportunity["session_date"],
        "planning_at": opportunity["planning_at"],
        "planning_mode": opportunity["planning_mode"],
        "mapping_mode": opportunity["mapping_mode"],
        "selected_series": opportunity["selected_series"],
        "strategy_id": strategy_id,
        "entry_definition": opportunity["entry_definition"],
        "side": side,
        "entry_level": entry,
        "target_level": target,
        "stop_level": stop,
        "triggered_at": opportunity["first_touch_time"],
        "exited_at": exited_at.isoformat() if exited_at else None,
        "status": status,
        "gross_points": gross,
        "cost_points": cost_points,
        "net_points": gross - cost_points if gross is not None else None,
        "mfe_points": mfe,
        "mae_points": mae,
        "research_only": True,
        "signal_allowed": False,
    }


def _exit_summary(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, float], list[dict[str, Any]]] = defaultdict(list)
    for outcome in outcomes:
        groups[(outcome["strategy_id"], outcome["cost_points"])].append(outcome)
    return [
        {
            "strategy_id": key[0],
            "cost_points": key[1],
            "configuration_fill_count": len(items),
            "unique_market_opportunity_count": len(
                {item["opportunity_id"] for item in items}
            ),
            "target_hit_count": sum(item["status"] == "target_hit" for item in items),
            "stop_hit_count": sum(item["status"] == "stop_hit" for item in items),
            "time_exit_count": sum(item["status"].startswith("time_exit") for item in items),
            "net_expectancy_points": _average([item["net_points"] for item in items]),
            "average_mfe_points": _average([item["mfe_points"] for item in items]),
            "average_mae_points": _average([item["mae_points"] for item in items]),
            "research_only": True,
            "signal_allowed": False,
        }
        for key, items in sorted(groups.items())
    ]


def _gross(entry: float, exit_price: float, side: str) -> float:
    return exit_price - entry if side == "long_reversion" else entry - exit_price


def _has_complete_day_window(
    bars: list[XauPriceBar],
    *,
    planning_at: datetime,
    interval_minutes: int,
) -> bool:
    if not bars:
        return False
    end = planning_at.replace(hour=23, minute=59, second=59)
    interval = timedelta(minutes=max(interval_minutes, 1))
    window = [
        bar.timestamp.astimezone(planning_at.tzinfo)
        for bar in bars
        if planning_at < bar.timestamp.astimezone(planning_at.tzinfo) <= end
    ]
    expected = max(int((end - planning_at).total_seconds() // interval.total_seconds()), 1)
    return (
        len(window) >= max(expected - 1, 1)
        and min(window) <= planning_at + interval
        and max(window) >= end - interval
    )


def _has_complete_sd_snapshot(snapshot) -> bool:
    return snapshot.future_open is not None and all(
        value is not None
        for value in (
            snapshot.future_buy_1sd,
            snapshot.future_buy_2sd,
            snapshot.future_buy_3sd,
            snapshot.future_sell_1sd,
            snapshot.future_sell_2sd,
            snapshot.future_sell_3sd,
        )
    )
