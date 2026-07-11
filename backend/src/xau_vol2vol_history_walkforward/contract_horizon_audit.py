from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import (
    XauContractAlignmentStatus,
    XauSourceClass,
)
from src.xau_vol2vol_history_walkforward.planning import XauPlanningSelection
from src.xau_vol2vol_history_walkforward.sd_zone_audit import EXIT_STRATEGIES


def build_contract_alignment_audit(
    selections: list[XauPlanningSelection],
    spot_bars: list[XauPriceBar],
    futures_proxy_bars: list[XauPriceBar],
    *,
    source_gap_limit_seconds: int = 300,
    mismatch_threshold_points: float = 20.0,
    roll_jump_threshold_points: float = 20.0,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    prior_difference: float | None = None
    for selection in sorted(selections, key=lambda item: item.planning_at):
        snapshot = selection.range_snapshot
        snapshot_time = snapshot.observed_at
        spot = _latest_at_or_before(spot_bars, snapshot_time)
        proxy = _latest_at_or_before(futures_proxy_bars, snapshot_time)
        spot_gap = _gap_seconds(snapshot_time, spot)
        proxy_gap = _gap_seconds(snapshot_time, proxy)
        accepted = (
            spot is not None
            and proxy is not None
            and spot_gap is not None
            and proxy_gap is not None
            and spot_gap <= source_gap_limit_seconds
            and proxy_gap <= source_gap_limit_seconds
            and snapshot.future_open is not None
        )
        future_reference = float(snapshot.future_open) if snapshot.future_open else None
        method_difference = (
            future_reference - proxy.close if accepted and future_reference is not None else None
        )
        status = XauContractAlignmentStatus.UNAVAILABLE
        if method_difference is not None:
            status = (
                XauContractAlignmentStatus.MISMATCH
                if abs(method_difference) > mismatch_threshold_points
                else XauContractAlignmentStatus.PROXY
            )
        roll_jump = (
            method_difference is not None
            and prior_difference is not None
            and abs(method_difference - prior_difference) > roll_jump_threshold_points
        )
        levels = _basis_levels(snapshot, spot.close, proxy.close) if accepted else {}
        spot_window = [
            bar
            for bar in spot_bars
            if selection.planning_at < bar.timestamp <= selection.simulation_window_end
        ]
        classifications = {
            mode: _touch_classification(mapped, spot_window)
            for mode, mapped in levels.items()
        }
        classification_changed = len(
            {tuple(sorted(value.items())) for value in classifications.values()}
        ) > 1
        row = {
            "session_date": selection.session_date.isoformat(),
            "source_session_date": selection.source_session_date.isoformat(),
            "planning_mode": "fixed_morning",
            "planning_at": selection.planning_at.isoformat(),
            "vol2vol_snapshot_time": snapshot_time.isoformat(),
            "vol2vol_selected_series": snapshot.series,
            "vol2vol_underlying_contract": None,
            "spot_symbol": spot.symbol if spot else "XAUUSD",
            "futures_proxy_symbol": proxy.symbol if proxy else "GC=F",
            "spot_source_class": XauSourceClass.SPOT_BASIS.value,
            "futures_proxy_source_class": (
                XauSourceClass.CONTINUOUS_FUTURES_PROXY.value
            ),
            "contract_alignment_status": status.value,
            "vol2vol_reference": future_reference,
            "dukascopy_spot_reference": spot.close if spot else None,
            "yahoo_futures_proxy_reference": proxy.close if proxy else None,
            "spot_source_gap_seconds": spot_gap,
            "futures_proxy_source_gap_seconds": proxy_gap,
            "source_pair_accepted": accepted,
            "vol2vol_spot_basis": (
                future_reference - spot.close if accepted and future_reference is not None else None
            ),
            "yahoo_spot_proxy_basis": proxy.close - spot.close if accepted else None,
            "difference_between_basis_methods": method_difference,
            "large_reference_difference": status == XauContractAlignmentStatus.MISMATCH,
            "possible_contract_roll_discontinuity": roll_jump,
            "mapped_levels": levels,
            "touch_classification_by_mapping": classifications,
            "touch_classification_changed": classification_changed,
            "true_basis_validation": "unavailable",
            "research_only": True,
            "signal_allowed": False,
        }
        rows.append(row)
        if method_difference is not None:
            prior_difference = method_difference
    accepted_rows = [row for row in rows if row["source_pair_accepted"]]
    return {
        "source_gap_limit_seconds": source_gap_limit_seconds,
        "mismatch_threshold_points": mismatch_threshold_points,
        "roll_jump_threshold_points": roll_jump_threshold_points,
        "observation_count": len(rows),
        "accepted_observation_count": len(accepted_rows),
        "rejected_observation_count": len(rows) - len(accepted_rows),
        "proxy_count": sum(
            row["contract_alignment_status"] == "proxy" for row in rows
        ),
        "mismatch_count": sum(
            row["contract_alignment_status"] == "mismatch" for row in rows
        ),
        "possible_contract_roll_discontinuity_count": sum(
            row["possible_contract_roll_discontinuity"] for row in rows
        ),
        "touch_classification_change_count": sum(
            row["touch_classification_changed"] for row in rows
        ),
        "observations": rows,
        "true_basis_validation": "unavailable",
        "research_only": True,
        "signal_allowed": False,
    }


def build_holding_horizon_comparison(
    result_sets: list[dict[str, Any]],
    bars: list[XauPriceBar],
    *,
    source_class: XauSourceClass,
    costs: tuple[float, ...] = (0.0, 0.3, 0.5, 1.0),
) -> dict[str, Any]:
    experiments: list[dict[str, Any]] = []
    for result in result_sets:
        diagnostics = {
            (item["session_date"], item["planning_at"]): item
            for item in result["diagnostics"]
        }
        for horizon_name in ("intraday_close", "next_plan_close"):
            opportunities, exclusions = _horizon_opportunities(
                result,
                diagnostics,
                bars,
                horizon_name=horizon_name,
            )
            outcomes: list[dict[str, Any]] = []
            for opportunity in opportunities:
                diagnostic = diagnostics[
                    (opportunity["session_date"], opportunity["planning_at"])
                ]
                for strategy_id, strategy in EXIT_STRATEGIES.items():
                    if strategy["entry_definition"] != opportunity["entry_definition"]:
                        continue
                    for cost in costs:
                        outcomes.append(
                            _simulate(
                                opportunity,
                                diagnostic,
                                bars,
                                horizon_name=horizon_name,
                                strategy_id=strategy_id,
                                target_sd=float(strategy["target_sd"]),
                                stop_sd=float(strategy["stop_sd"]),
                                cost_points=cost,
                            )
                        )
            experiments.append(
                {
                    "holding_horizon": horizon_name,
                    "source_class": source_class.value,
                    "mapping_mode": result["mapping_mode"],
                    "planning_mode": result["planning_mode"],
                    "unique_market_opportunity_count": len(opportunities),
                    "configuration_outcome_count": len(outcomes) // max(len(costs), 1),
                    "cost_scenario_row_count": len(outcomes),
                    "horizon_exclusions": exclusions,
                    "outcomes": outcomes,
                    "summary": _summaries(outcomes),
                    "overlapping_morning_position_count": 0,
                    "research_only": True,
                    "signal_allowed": False,
                }
            )
    return {
        "horizons": {
            "intraday_close": "07:00 through 23:59 same day",
            "next_plan_close": "07:00 through immediately before next-day 07:00",
        },
        "experiments": experiments,
        "research_only": True,
        "signal_allowed": False,
    }


def _basis_levels(snapshot, spot: float, proxy: float) -> dict[str, dict[str, float]]:
    fields = {
        "lower_1sd": snapshot.future_buy_1sd,
        "lower_1_5sd": _mid(snapshot.future_buy_1sd, snapshot.future_buy_2sd),
        "lower_2sd": snapshot.future_buy_2sd,
        "upper_1sd": snapshot.future_sell_1sd,
        "upper_1_5sd": _mid(snapshot.future_sell_1sd, snapshot.future_sell_2sd),
        "upper_2sd": snapshot.future_sell_2sd,
    }
    future = float(snapshot.future_open)
    v2v_basis = future - spot
    yahoo_basis = proxy - spot
    return {
        "vol2vol_reference_basis": {
            key: float(value) - v2v_basis for key, value in fields.items()
        },
        "yahoo_continuous_proxy_basis": {
            key: float(value) - yahoo_basis for key, value in fields.items()
        },
        "distance_reanchored": {
            key: spot + (float(value) - future) for key, value in fields.items()
        },
    }


def _horizon_opportunities(result, diagnostics, bars, *, horizon_name):
    exclusions: dict[str, int] = defaultdict(int)
    if result["planning_mode"] != "fixed_morning":
        touched = [
            item
            for item in result["opportunities"]
            if item["touched"]
            and item["entry_definition"] in {"zone_2_entry", "zone_2_mid"}
        ]
        return _first_by_market_key(touched), dict(exclusions)
    opportunities = []
    for diagnostic in diagnostics.values():
        planning_at = datetime.fromisoformat(diagnostic["planning_at"])
        horizon_end = _horizon_end(planning_at, horizon_name)
        if horizon_name == "next_plan_close" and horizon_end.weekday() >= 5:
            exclusions["weekend_crossing"] += 1
            continue
        window = [bar for bar in bars if planning_at < bar.timestamp <= horizon_end]
        if not window or window[-1].timestamp < horizon_end - timedelta(minutes=10):
            exclusions["incomplete_horizon"] += 1
            continue
        for definition, suffix in (("zone_2_entry", "1sd"), ("zone_2_mid", "1_5sd")):
            for side in ("long_reversion", "short_reversion"):
                prefix = "lower" if side == "long_reversion" else "upper"
                level = float(diagnostic[f"{prefix}_{suffix}"])
                touched = _first_touch(window, side, level)
                if touched is None:
                    continue
                opportunities.append(
                    {
                        "opportunity_id": (
                            f"{diagnostic['session_date']}:fixed:{side}:{definition}:{level:.4f}"
                        ),
                        "session_date": diagnostic["session_date"],
                        "planning_at": diagnostic["planning_at"],
                        "planning_mode": result["planning_mode"],
                        "mapping_mode": result["mapping_mode"],
                        "selected_series": diagnostic["selected_series"],
                        "entry_definition": definition,
                        "entry_level": level,
                        "side": side,
                        "first_touch_time": touched.isoformat(),
                    }
                )
    return opportunities, dict(exclusions)


def _simulate(
    opportunity,
    diagnostic,
    bars,
    *,
    horizon_name,
    strategy_id,
    target_sd,
    stop_sd,
    cost_points,
):
    touched_at = datetime.fromisoformat(opportunity["first_touch_time"])
    planning_at = datetime.fromisoformat(opportunity["planning_at"])
    horizon_end = _horizon_end(planning_at, horizon_name)
    side = opportunity["side"]
    entry = float(opportunity["entry_level"])
    center = float(diagnostic["xau_reference"])
    one_sd = (
        center - float(diagnostic["lower_1sd"])
        if side == "long_reversion"
        else float(diagnostic["upper_1sd"]) - center
    )
    target = entry + target_sd * one_sd if side == "long_reversion" else entry - target_sd * one_sd
    suffix = "2sd" if stop_sd == 2.0 else "2_5sd"
    stop = float(diagnostic[f"{'lower' if side == 'long_reversion' else 'upper'}_{suffix}"])
    window = [bar for bar in bars if touched_at <= bar.timestamp <= horizon_end]
    status, exit_price, exited_at = "unavailable", None, None
    mfe, mae = None, None
    for bar in window:
        favorable, adverse = _excursion(bar, entry, side)
        mfe = favorable if mfe is None else max(mfe, favorable)
        mae = adverse if mae is None else min(mae, adverse)
        target_hit = bar.high >= target if side == "long_reversion" else bar.low <= target
        stop_hit = bar.low <= stop if side == "long_reversion" else bar.high >= stop
        if stop_hit or target_hit:
            status = "stop_hit" if stop_hit else "target_hit"
            exit_price = stop if stop_hit else target
            exited_at = bar.timestamp
            break
    if status == "unavailable" and window:
        exit_price = window[-1].close
        exited_at = window[-1].timestamp
        status = "time_exit_profit" if _gross(entry, exit_price, side) >= 0 else "time_exit_loss"
    gross = _gross(entry, exit_price, side) if exit_price is not None else None
    return {
        **{key: opportunity[key] for key in (
            "opportunity_id", "session_date", "planning_at", "planning_mode",
            "mapping_mode", "selected_series", "entry_definition", "side",
        )},
        "holding_horizon": horizon_name,
        "strategy_id": strategy_id,
        "entry_level": entry,
        "target_level": target,
        "stop_level": stop,
        "triggered_at": touched_at.isoformat(),
        "exited_at": exited_at.isoformat() if exited_at else None,
        "duration_minutes": (
            (exited_at - touched_at).total_seconds() / 60 if exited_at else None
        ),
        "status": status,
        "gross_points": gross,
        "cost_points": cost_points,
        "net_points": gross - cost_points if gross is not None else None,
        "mfe_points": mfe,
        "mae_points": mae,
        "research_only": True,
        "signal_allowed": False,
    }


def _summaries(outcomes):
    groups = defaultdict(list)
    for row in outcomes:
        groups[(row["strategy_id"], row["side"], row["cost_points"])].append(row)
    summaries = []
    for (strategy, side, cost), items in sorted(groups.items()):
        ordered = sorted(items, key=lambda row: row["triggered_at"])
        net = [float(row["net_points"]) for row in ordered if row["net_points"] is not None]
        summaries.append({
            "strategy_id": strategy,
            "side": side,
            "cost_points": cost,
            "unique_market_opportunity_count": len({row["opportunity_id"] for row in items}),
            "configuration_fill_count": len(items),
            "target_hit_count": sum(row["status"] == "target_hit" for row in items),
            "stop_hit_count": sum(row["status"] == "stop_hit" for row in items),
            "time_exit_profit_count": sum(row["status"] == "time_exit_profit" for row in items),
            "time_exit_loss_count": sum(row["status"] == "time_exit_loss" for row in items),
            "average_duration_minutes": _average([row["duration_minutes"] for row in items]),
            "average_mfe_points": _average([row["mfe_points"] for row in items]),
            "average_mae_points": _average([row["mae_points"] for row in items]),
            "net_expectancy_points": mean(net) if net else None,
            "maximum_cumulative_drawdown_points": _max_drawdown(net),
            "maximum_consecutive_losses": _max_consecutive_losses(net),
            "research_only": True,
            "signal_allowed": False,
        })
    return summaries


def _latest_at_or_before(bars, timestamp):
    eligible = [bar for bar in bars if bar.timestamp <= timestamp]
    return max(eligible, key=lambda bar: bar.timestamp) if eligible else None


def _gap_seconds(timestamp, bar):
    return abs((timestamp - bar.timestamp).total_seconds()) if bar else None


def _mid(first, second):
    return (float(first) + float(second)) / 2


def _touch_classification(levels, bars):
    if not bars:
        return {"reached_1sd": False, "reached_1_5sd": False, "reached_2sd": False}
    high = max(bar.high for bar in bars)
    low = min(bar.low for bar in bars)
    return {
        "reached_1sd": low <= levels["lower_1sd"] or high >= levels["upper_1sd"],
        "reached_1_5sd": (
            low <= levels["lower_1_5sd"] or high >= levels["upper_1_5sd"]
        ),
        "reached_2sd": low <= levels["lower_2sd"] or high >= levels["upper_2sd"],
    }


def _first_touch(bars, side, level):
    if side == "long_reversion":
        return next((bar.timestamp for bar in bars if bar.low <= level), None)
    return next((bar.timestamp for bar in bars if bar.high >= level), None)


def _first_by_market_key(items):
    first = {}
    for item in sorted(items, key=lambda row: row["first_touch_time"]):
        key = (item["session_date"], item["side"], item["entry_definition"])
        first.setdefault(key, item)
    return list(first.values())


def _horizon_end(planning_at, horizon_name):
    if horizon_name == "next_plan_close":
        return planning_at + timedelta(days=1) - timedelta(microseconds=1)
    return planning_at.replace(hour=23, minute=59, second=59, microsecond=999999)


def _excursion(bar, entry, side):
    if side == "long_reversion":
        return bar.high - entry, bar.low - entry
    return entry - bar.low, entry - bar.high


def _gross(entry, exit_price, side):
    return exit_price - entry if side == "long_reversion" else entry - exit_price


def _average(values):
    present = [float(value) for value in values if value is not None]
    return mean(present) if present else None


def _max_drawdown(net):
    peak = equity = drawdown = 0.0
    for value in net:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _max_consecutive_losses(net):
    current = maximum = 0
    for value in net:
        current = current + 1 if value < 0 else 0
        maximum = max(maximum, current)
    return maximum
