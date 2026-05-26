from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from pipeline_utils import parse_timestamp_value, read_yaml, resolve_path, to_jsonable, write_json

BASE_PARAMETER_ORDER = [
    "entryStrictness",
    "tradeMode",
    "allowLongs",
    "allowShorts",
    "entrySd",
    "stopSd",
    "noTradeSd",
    "mrMinScoreLong",
    "mrMinScoreShort",
    "breakoutMinScore",
    "cooldownBars",
    "donFastLen",
    "donSlowLen",
    "minFeeMultipleForTP",
    "brkTp1R",
    "brkRunnerR",
    "mrMaxBars",
    "brkMaxBars",
    "gridSdLen",
    "exitAtrLen",
    "atrStopMult",
    "brkTp1Qty",
    "mrTp1Qty",
    "mrUseTp2",
    "moveStopToBreakevenAfterTp1",
    "softMajorityPct",
    "majorityPct",
    "regimeDiLen",
    "regimeAdxSmooth",
    "regimeAdxLevel",
    "regimeAtrLen",
    "atrBaseLen",
    "regimeAtrRatioLevel",
    "maxAdxForMeanReversion",
    "softMaxAdxForMR",
    "sweepLookback",
    "maLen",
    "rsiLen",
    "macdFastLen",
    "macdSlowLen",
    "macdSignalLen",
]

INTEGER_PARAMETERS = {
    "cooldownBars",
    "donFastLen",
    "donSlowLen",
    "mrMaxBars",
    "brkMaxBars",
    "gridSdLen",
    "exitAtrLen",
    "regimeDiLen",
    "regimeAdxSmooth",
    "regimeAtrLen",
    "atrBaseLen",
    "sweepLookback",
    "maLen",
    "rsiLen",
    "macdFastLen",
    "macdSlowLen",
    "macdSignalLen",
}

PARAMETER_STEPS = {
    "entrySd": 0.05,
    "stopSd": 0.05,
    "noTradeSd": 0.05,
    "mrMinScoreLong": 0.5,
    "mrMinScoreShort": 0.5,
    "breakoutMinScore": 0.5,
    "minFeeMultipleForTP": 0.25,
    "brkTp1R": 0.25,
    "brkRunnerR": 0.25,
    "atrStopMult": 0.25,
    "brkTp1Qty": 5.0,
    "mrTp1Qty": 5.0,
    "softMajorityPct": 0.01,
    "majorityPct": 0.01,
    "regimeAdxLevel": 0.5,
    "regimeAtrRatioLevel": 0.05,
    "maxAdxForMeanReversion": 0.5,
    "softMaxAdxForMR": 0.5,
}

_WORKER_SPLITS: dict[str, list[dict[str, Any]]] | None = None
_WORKER_CONFIG: dict[str, Any] | None = None


@dataclass
class Position:
    side: str
    trade_type: str
    entry_index: int
    signal_index: int
    entry_time: datetime
    entry_price: float
    qty: float
    remaining_qty: float
    stop: float
    tp1: float | None
    runner_target: float | None
    tp2: float | None
    tp1_qty_pct: float
    entry_fee: float
    funding_cost: float
    realized_pnl: float = 0.0
    exit_fees: float = 0.0
    tp1_hit: bool = False


def load_frame(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".parquet":
        df = pl.read_parquet(path)
    elif path.suffix.lower() == ".csv":
        df = pl.read_csv(path, try_parse_dates=False)
    else:
        raise ValueError(f"Unsupported input format: {path.suffix}")

    aliases = {column.lower(): column for column in df.columns}
    if "datetime" not in aliases and "timestamp" in aliases:
        df = df.rename({aliases["timestamp"]: "datetime"})
    required = {"datetime", "open", "high", "low", "close"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Input data missing columns: {missing}")

    if not isinstance(df.schema["datetime"], pl.Datetime):
        df = df.with_columns(
            pl.col("datetime")
            .map_elements(parse_timestamp_value, return_dtype=pl.Datetime("us", "UTC"))
            .alias("datetime")
        )
    return df.sort("datetime").to_dicts()


def optimize(
    config_path: Path,
    iterations_override: int | None = None,
    max_workers_override: int | None = None,
) -> dict[str, Any]:
    config = read_yaml(config_path)
    reports_dir = resolve_path(config["data"].get("reports_dir", "data/reports/tradingview_optimizer"))
    reports_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(int(config.get("search", {}).get("seed", 42)))
    iterations = iterations_override or int(config.get("search", {}).get("iterations", 250))
    max_workers = resolve_max_workers(max_workers_override, config)
    top_n = int(config.get("search", {}).get("top_n", 20))

    all_candidates: list[dict[str, Any]] = []
    for data_spec in data_specs(config):
        data_path = resolve_path(data_spec["input_path"])
        timeframe = str(data_spec.get("timeframe") or config["data"].get("timeframe") or data_path.stem)
        rows = load_frame(data_path)
        splits = split_rows(rows, config["walk_forward"])
        candidates = run_search(
            config=config,
            splits=splits,
            rng=rng,
            iterations=iterations,
            max_workers=max_workers,
            timeframe=timeframe,
            data_path=data_path,
        )
        ranked_for_timeframe = sorted(candidates, key=lambda item: item["score"], reverse=True)
        timeframe_dir = reports_dir / timeframe
        write_csv(timeframe_dir / "all_results.csv", ranked_for_timeframe)
        write_csv(timeframe_dir / "top_results.csv", ranked_for_timeframe[:top_n])
        write_json(timeframe_dir / "best_presets.json", build_presets(ranked_for_timeframe[:top_n], config))
        write_pine_markdown(timeframe_dir / "pine_input_preset.md", ranked_for_timeframe[:top_n], config)
        all_candidates.extend(candidates)

    ranked = sorted(all_candidates, key=lambda item: item["score"], reverse=True)
    top = ranked[:top_n]
    write_csv(reports_dir / "all_results.csv", ranked)
    write_csv(reports_dir / "top_results.csv", top)
    write_json(reports_dir / "best_presets.json", build_presets(top, config))
    write_pine_markdown(reports_dir / "pine_input_preset.md", top, config)
    return {
        "reports_dir": reports_dir,
        "evaluated": len(all_candidates),
        "accepted": sum(1 for item in all_candidates if item["accepted"]),
        "best": top[0] if top else None,
    }


def data_specs(config: dict[str, Any]) -> list[dict[str, Any]]:
    data = config["data"]
    inputs = data.get("inputs")
    if inputs:
        specs = []
        for item in inputs:
            if not isinstance(item, dict) or "input_path" not in item:
                raise ValueError("Each data input must be a mapping with input_path")
            specs.append(item)
        return specs
    return [
        {
            "input_path": data["input_path"],
            "timeframe": data.get("timeframe"),
        }
    ]


def run_search(
    config: dict[str, Any],
    splits: dict[str, list[dict[str, Any]]],
    rng: random.Random,
    iterations: int,
    max_workers: int,
    timeframe: str,
    data_path: Path,
) -> list[dict[str, Any]]:
    fixed = config.get("fixed") or {}
    parameter_space = config["parameters"]
    tasks: list[tuple[str, dict[str, Any]]] = []
    for index in range(iterations):
        params = {**fixed, **sample_params(parameter_space, rng)}
        params = coerce_sampled_params(params)
        tasks.append((f"{timeframe}_{index + 1}", params))

    if max_workers <= 1 or iterations <= 1:
        candidates = [evaluate_candidate(config_id, params, splits, config) for config_id, params in tasks]
    else:
        worker_count = min(max_workers, iterations)
        chunk_size = max(1, len(tasks) // max(worker_count * 4, 1))
        with ProcessPoolExecutor(
            max_workers=worker_count,
            initializer=init_worker,
            initargs=(splits, config),
        ) as executor:
            candidates = list(executor.map(evaluate_candidate_worker, tasks, chunksize=chunk_size))

    for result in candidates:
        result["timeframe"] = timeframe
        result["data_path"] = data_path
    return candidates


def resolve_max_workers(max_workers_override: int | None, config: dict[str, Any]) -> int:
    configured = max_workers_override
    if configured is None:
        configured = int(config.get("search", {}).get("max_workers", 1))
    if configured == 0:
        return max((os.cpu_count() or 2) - 1, 1)
    return max(int(configured), 1)


def init_worker(splits: dict[str, list[dict[str, Any]]], config: dict[str, Any]) -> None:
    global _WORKER_SPLITS, _WORKER_CONFIG
    _WORKER_SPLITS = splits
    _WORKER_CONFIG = config


def evaluate_candidate_worker(task: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    if _WORKER_SPLITS is None or _WORKER_CONFIG is None:
        raise RuntimeError("Worker was not initialized")
    config_id, params = task
    return evaluate_candidate(config_id, params, _WORKER_SPLITS, _WORKER_CONFIG)


def parameter_order(config: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    configured = set(config.get("parameters", {}).keys())
    for key in BASE_PARAMETER_ORDER:
        if key in configured:
            keys.append(key)
    for key in config.get("parameters", {}).keys():
        if key not in keys:
            keys.append(key)
    return keys


def split_rows(rows: list[dict[str, Any]], split_config: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    train_start = parse_timestamp_value(split_config["train_start"])
    train_end = parse_timestamp_value(split_config["train_end"])
    validation_start = parse_timestamp_value(split_config["validation_start"])
    validation_end = parse_timestamp_value(split_config["validation_end"])
    test_start = parse_timestamp_value(split_config["test_start"])
    splits = {
        "train": [
            row for row in rows if train_start <= as_utc(row["datetime"]) < train_end
        ],
        "validation": [
            row for row in rows if validation_start <= as_utc(row["datetime"]) < validation_end
        ],
        "test": [row for row in rows if as_utc(row["datetime"]) >= test_start],
    }
    empty = [name for name, split in splits.items() if not split]
    if empty:
        raise ValueError(f"Empty walk-forward splits: {empty}")
    return splits


def sample_params(parameter_space: dict[str, list[Any]], rng: random.Random) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key, value in parameter_space.items():
        if not isinstance(value, list):
            params[key] = value
            continue
        if len(value) != 2:
            params[key] = rng.choice(value)
            continue
        low, high = value
        if isinstance(low, bool) or isinstance(high, bool) or not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
            params[key] = rng.choice(value)
        elif key in INTEGER_PARAMETERS:
            params[key] = rng.randint(int(low), int(high))
        else:
            raw = rng.uniform(float(low), float(high))
            step = PARAMETER_STEPS.get(key, 0.05)
            params[key] = round(round(raw / step) * step, 4)
    return params


def coerce_sampled_params(params: dict[str, Any]) -> dict[str, Any]:
    coerced = dict(params)
    coerced["stopSd"] = max(float(coerced["stopSd"]), float(coerced["entrySd"]) + 0.25)
    if "donFastLen" in coerced and "donSlowLen" in coerced:
        coerced["donSlowLen"] = max(int(coerced["donSlowLen"]), int(coerced["donFastLen"]) + 2)
    if "macdFastLen" in coerced and "macdSlowLen" in coerced:
        coerced["macdSlowLen"] = max(int(coerced["macdSlowLen"]), int(coerced["macdFastLen"]) + 2)
    if coerced.get("allowLongs") is False and coerced.get("allowShorts") is False:
        coerced["allowLongs"] = True
    return coerced


def apply_effective_pine_preset(params: dict[str, Any]) -> dict[str, Any]:
    effective = dict(params)
    strictness = (
        str(effective.get("entryStrictness", "balanced_quality"))
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )
    is_recovery = strictness in {"research_frequency", "recovery", "strict_recovery"}
    is_balanced_quality = strictness in {"balanced_quality", "strict_balanced_quality"}
    is_conservative = strictness in {"conservative", "strict_conservative"}

    if is_recovery:
        effective["donFastLen"] = min(int(effective["donFastLen"]), 12)
        effective["donSlowLen"] = min(int(effective["donSlowLen"]), 34)
        effective["entrySd"] = min(float(effective["entrySd"]), 0.75)
        effective["stopSd"] = max(float(effective["stopSd"]), 2.40)
        effective["noTradeSd"] = min(float(effective["noTradeSd"]), 0.20)
        effective["maxAdxForMeanReversion"] = max(float(effective.get("maxAdxForMeanReversion", 34.0)), 45.0)
        effective["softMaxAdxForMR"] = max(float(effective.get("softMaxAdxForMR", 36.0)), 42.0)
        effective["mrMinScoreLong"] = min(float(effective["mrMinScoreLong"]), 2.5)
        effective["mrMinScoreShort"] = min(float(effective["mrMinScoreShort"]), 3.0)
        effective["breakoutMinScore"] = min(float(effective["breakoutMinScore"]), 2.5)
        effective["cooldownBars"] = min(int(effective["cooldownBars"]), 2)
        effective["mrMaxBars"] = min(int(effective["mrMaxBars"]), 5)
        effective["brkMaxBars"] = min(int(effective["brkMaxBars"]), 16)
    elif is_balanced_quality:
        effective["donFastLen"] = min(int(effective["donFastLen"]), 16)
        effective["donSlowLen"] = min(int(effective["donSlowLen"]), 40)
        effective["entrySd"] = max(float(effective["entrySd"]), 1.15)
        effective["stopSd"] = max(float(effective["stopSd"]), 2.50)
        effective["noTradeSd"] = max(float(effective["noTradeSd"]), 0.35)
        effective["maxAdxForMeanReversion"] = min(float(effective.get("maxAdxForMeanReversion", 34.0)), 34.0)
        effective["softMaxAdxForMR"] = min(float(effective.get("softMaxAdxForMR", 36.0)), 36.0)
        effective["mrMinScoreLong"] = max(float(effective["mrMinScoreLong"]), 4.0)
        effective["mrMinScoreShort"] = max(float(effective["mrMinScoreShort"]), 4.5)
        effective["breakoutMinScore"] = max(float(effective["breakoutMinScore"]), 4.0)
        effective["cooldownBars"] = max(int(effective["cooldownBars"]), 6)
        effective["mrMaxBars"] = min(int(effective["mrMaxBars"]), 6)
        effective["brkMaxBars"] = max(int(effective["brkMaxBars"]), 32)
    elif is_conservative:
        effective["donFastLen"] = max(int(effective["donFastLen"]), 20)
        effective["donSlowLen"] = max(int(effective["donSlowLen"]), 55)
        effective["entrySd"] = max(float(effective["entrySd"]), 1.40)
        effective["stopSd"] = max(float(effective["stopSd"]), 2.60)
        effective["noTradeSd"] = max(float(effective["noTradeSd"]), 0.50)
        effective["maxAdxForMeanReversion"] = min(float(effective.get("maxAdxForMeanReversion", 34.0)), 25.0)
        effective["softMaxAdxForMR"] = min(float(effective.get("softMaxAdxForMR", 36.0)), 28.0)
        effective["mrMinScoreLong"] = max(float(effective["mrMinScoreLong"]), 4.5)
        effective["mrMinScoreShort"] = max(float(effective["mrMinScoreShort"]), 5.0)
        effective["breakoutMinScore"] = max(float(effective["breakoutMinScore"]), 5.0)
        effective["cooldownBars"] = max(int(effective["cooldownBars"]), 8)
        effective["mrMaxBars"] = min(int(effective["mrMaxBars"]), 6)
        effective["brkMaxBars"] = min(int(effective["brkMaxBars"]), 16)

    effective["stopSd"] = max(float(effective["stopSd"]), float(effective["entrySd"]) + 0.25)
    return effective


def evaluate_candidate(
    config_id: str | int,
    params: dict[str, Any],
    splits: dict[str, list[dict[str, Any]]],
    config: dict[str, Any],
) -> dict[str, Any]:
    train = run_backtest(splits["train"], params, config)
    validation = run_backtest(splits["validation"], params, config)
    test = run_backtest(splits["test"], params, config)
    scenario_results = evaluate_fee_scenarios(params, splits, config)
    reject_reasons = rejection_reasons(validation, config["reject"])
    robust_reasons = robustness_reasons(scenario_results, config.get("robustness", {}))
    train_stable = train["profit_factor"] is not None and train["profit_factor"] >= 1.0
    test_not_collapsed = test["net_pnl"] >= -abs(validation["net_pnl"]) * 0.75
    score = validation_score(validation, config["reject"], scenario_results)
    all_reasons = reject_reasons + robust_reasons
    if all_reasons:
        score -= 100.0 + len(all_reasons) * 10.0
    if not train_stable:
        score -= 15.0
    if not test_not_collapsed:
        score -= 20.0

    ordered_params = parameter_order(config)
    result = {
        "config_id": config_id,
        **{key: params.get(key) for key in ordered_params},
        **prefix_metrics("train", train),
        **prefix_metrics("validation", validation),
        **prefix_metrics("test", test),
        "accepted": not all_reasons,
        "train_stable": train_stable,
        "test_not_collapsed": test_not_collapsed,
        "reject_reasons": "; ".join(all_reasons),
        "score": score,
    }
    if scenario_results:
        worst_validation = min(scenario_results, key=lambda item: item["validation"]["net_pnl"])
        worst_test = min(scenario_results, key=lambda item: item["test"]["net_pnl"])
        result.update(
            {
                "worst_fee_scenario": worst_validation["name"],
                "worst_fee_validation_net_pnl": worst_validation["validation"]["net_pnl"],
                "worst_fee_validation_profit_factor": worst_validation["validation"]["profit_factor"],
                "worst_fee_validation_trades_per_year": worst_validation["validation"]["trades_per_year"],
                "worst_fee_test_net_pnl": worst_test["test"]["net_pnl"],
                "worst_fee_test_profit_factor": worst_test["test"]["profit_factor"],
            }
        )
        for scenario in scenario_results:
            result.update(prefix_metrics(f"{scenario['name']}_validation", scenario["validation"]))
            result.update(prefix_metrics(f"{scenario['name']}_test", scenario["test"]))
    return result


def evaluate_fee_scenarios(
    params: dict[str, Any],
    splits: dict[str, list[dict[str, Any]]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    scenarios = fee_scenarios(config)
    results = []
    for name, fee_config in scenarios:
        results.append(
            {
                "name": name,
                "validation": run_backtest(splits["validation"], params, config, fee_config=fee_config),
                "test": run_backtest(splits["test"], params, config, fee_config=fee_config),
            }
        )
    return results


def fee_scenarios(config: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    robustness = config.get("robustness", {})
    if not robustness.get("enabled", False):
        return []
    scenarios = []
    for index, scenario in enumerate(robustness.get("fee_scenarios", []), start=1):
        if not isinstance(scenario, dict):
            raise ValueError("fee_scenarios entries must be mappings")
        name = slugify(str(scenario.get("name", f"fee_scenario_{index}")))
        fee_config = {**config["fees"], **scenario}
        scenarios.append((name, fee_config))
    return scenarios


def run_backtest(
    rows: list[dict[str, Any]],
    params: dict[str, Any],
    config: dict[str, Any],
    fee_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    effective = apply_effective_pine_preset(params)
    indicators = build_indicators(rows, effective)
    fee_model = fee_model_from_config(fee_config or config["fees"])
    initial_cash = float(config["execution"].get("initial_cash", 100000))
    fixed_qty = float(config["execution"].get("fixed_qty", 1.0))
    use_spread = bool(config["execution"].get("use_spread", True))
    cash = initial_cash
    peak = initial_cash
    max_drawdown = 0.0
    trades: list[dict[str, Any]] = []
    position: Position | None = None
    last_close_index: int | None = None
    equity_curve_count = 0

    min_bars = max(
        int(effective["donSlowLen"]),
        int(effective["donFastLen"]),
        int(effective.get("gridSdLen", 50)),
        int(effective.get("macdSlowLen", 26)) + int(effective.get("macdSignalLen", 9)),
        120,
    )

    for index, row in enumerate(rows):
        if position is not None:
            closed_trade = update_position(
                position=position,
                index=index,
                row=row,
                indicators=indicators,
                params=effective,
                fee_model=fee_model,
                use_spread=use_spread,
                is_final=index == len(rows) - 1,
            )
            if closed_trade is not None:
                cash += closed_trade["net_pnl"]
                trades.append(closed_trade)
                position = None
                last_close_index = index

        if position is None and index >= min_bars and index < len(rows) - 1:
            if last_close_index is None or index - last_close_index >= int(effective["cooldownBars"]):
                signal = signal_at(index, rows, indicators, effective, fee_model)
                if signal is not None:
                    entry_row = rows[index + 1]
                    entry_price = execution_price(
                        mid=float(entry_row["open"]),
                        spread=float(entry_row.get("spread_close") or 0.0),
                        side=signal["side"],
                        action="entry",
                        fee_model=fee_model,
                        use_spread=use_spread,
                    )
                    position = open_position(
                        signal=signal,
                        entry_index=index + 1,
                        entry_row=entry_row,
                        entry_price=entry_price,
                        qty=fixed_qty,
                        fee_model=fee_model,
                        params=effective,
                    )
                    cash -= position.entry_fee + position.funding_cost

        unrealized = mark_to_market(position, row, fee_model, use_spread) if position else 0.0
        equity = cash + unrealized
        peak = max(peak, equity)
        drawdown = (equity - peak) / peak if peak else 0.0
        max_drawdown = min(max_drawdown, drawdown)
        equity_curve_count += 1

    metrics = summarize_trades(trades, initial_cash, max_drawdown, rows)
    metrics["equity_points"] = equity_curve_count
    return metrics


def signal_at(
    index: int,
    rows: list[dict[str, Any]],
    ind: dict[str, list[Any]],
    params: dict[str, Any],
    fee_model: dict[str, float],
) -> dict[str, Any] | None:
    trade_mode = str(params.get("tradeMode", "auto")).lower()
    allow_breakout = trade_mode in {"auto", "don_only", "breakout", "donchian", "donchian_breakout_only"}
    allow_mr = trade_mode in {"auto", "sd_only", "mr", "mean_reversion", "sd_mean_reversion_only"}
    allow_longs = bool(params.get("allowLongs", True))
    allow_shorts = bool(params.get("allowShorts", True))
    close = float(rows[index]["close"])
    high = float(rows[index]["high"])
    low = float(rows[index]["low"])
    open_ = float(rows[index]["open"])
    grid_mid = ind["grid_mid"][index]
    grid_dev = ind["grid_dev"][index]
    exit_atr = ind["exit_atr"][index]
    don_upper_prev = ind["don_upper_prev"][index]
    don_lower_prev = ind["don_lower_prev"][index]
    don_slow_mid_prev = ind["don_slow_mid_prev"][index]
    if any(value is None for value in [grid_mid, grid_dev, exit_atr, don_upper_prev, don_lower_prev]):
        return None

    round_trip_points = close * fee_model["round_trip_cost_pct"] / 100.0
    required_reward = round_trip_points * float(params["minFeeMultipleForTP"])

    bull_breakout = close > don_upper_prev
    bear_breakout = close < don_lower_prev
    fresh_bull = bull_breakout and not bool(ind["bull_breakout"][index - 1])
    fresh_bear = bear_breakout and not bool(ind["bear_breakout"][index - 1])
    atr_expanding = bool(ind["atr_expanding"][index])
    trend_up = bool(ind["trend_up"][index])
    trend_down = bool(ind["trend_down"][index])
    range_regime = bool(ind["range_regime"][index])
    up_share = ind["up_share"][index] or 0.0
    low_share = ind["low_share"][index] or 0.0
    bull_majority = up_share >= float(params.get("majorityPct", 0.52))
    bear_majority = low_share >= float(params.get("majorityPct", 0.52))
    rsi = ind["rsi"][index]
    macd_hist = ind["macd_hist"][index]
    macd_line = ind["macd_line"][index]
    macd_signal = ind["macd_signal"][index]
    breakout_momentum_long = (rsi is not None and rsi > 55) or (
        macd_line is not None and macd_signal is not None and macd_hist is not None and macd_line > macd_signal and macd_hist > 0
    )
    breakout_momentum_short = (rsi is not None and rsi < 45) or (
        macd_line is not None and macd_signal is not None and macd_hist is not None and macd_line < macd_signal and macd_hist < 0
    )
    slow_bias_long = don_slow_mid_prev is not None and close > don_slow_mid_prev
    slow_bias_short = don_slow_mid_prev is not None and close < don_slow_mid_prev
    breakout_reward = max((ind["don_width_prev"][index] or 0.0) * 0.5, (exit_atr or 0.0) * 3.0)
    breakout_cost_ok = breakout_reward >= required_reward

    breakout_long_score = 0.0
    breakout_long_score += 2.0 if bull_breakout else 0.0
    breakout_long_score += 1.0 if fresh_bull else 0.0
    breakout_long_score += 1.0 if slow_bias_long else 0.0
    breakout_long_score += 1.0 if breakout_momentum_long else 0.0
    breakout_long_score += 1.0 if trend_up else 0.0
    breakout_long_score += 1.0 if bull_majority or up_share >= float(params.get("softMajorityPct", 0.50)) else 0.0
    breakout_long_score += 1.0 if atr_expanding else 0.0
    breakout_long_score -= 1.0 if range_regime else 0.0

    breakout_short_score = 0.0
    breakout_short_score += 2.0 if bear_breakout else 0.0
    breakout_short_score += 1.0 if fresh_bear else 0.0
    breakout_short_score += 1.0 if slow_bias_short else 0.0
    breakout_short_score += 1.0 if breakout_momentum_short else 0.0
    breakout_short_score += 1.0 if trend_down else 0.0
    breakout_short_score += 1.0 if bear_majority or low_share >= float(params.get("softMajorityPct", 0.50)) else 0.0
    breakout_short_score += 1.0 if atr_expanding else 0.0
    breakout_short_score -= 1.0 if range_regime else 0.0

    if allow_breakout and allow_longs and bull_breakout and breakout_cost_ok and breakout_long_score >= float(params["breakoutMinScore"]):
        stop = close - exit_atr * float(params.get("atrStopMult", 2.0))
        return {"side": "long", "type": "breakout", "signal_index": index, "stop": stop}
    if allow_breakout and allow_shorts and bear_breakout and breakout_cost_ok and breakout_short_score >= float(params["breakoutMinScore"]):
        stop = close + exit_atr * float(params.get("atrStopMult", 2.0))
        return {"side": "short", "type": "breakout", "signal_index": index, "stop": stop}

    sigma = (close - grid_mid) / grid_dev if grid_dev else 0.0
    lower_entry = grid_mid - grid_dev * float(params["entrySd"])
    upper_entry = grid_mid + grid_dev * float(params["entrySd"])
    lower_stop = grid_mid - grid_dev * float(params["stopSd"])
    upper_stop = grid_mid + grid_dev * float(params["stopSd"])
    low_trap = bool(ind["low_trap"][index])
    high_trap = bool(ind["high_trap"][index])
    no_fade_long_blocked = bool(ind["no_fade_long_blocked"][index])
    no_fade_short_blocked = bool(ind["no_fade_short_blocked"][index])
    mr_regime_ok = range_regime or bool(ind["soft_range_regime"][index])
    atr_hard = bool(ind["atr_expansion_hard"][index])
    mr_reward = abs(close - grid_mid)
    mr_cost_ok = mr_reward >= required_reward

    mr_long_score = 0.0
    mr_long_score += 2.0 if sigma <= -float(params["entrySd"]) else 0.0
    mr_long_score += 1.0 if sigma <= -(float(params["entrySd"]) + 0.25) else 0.0
    mr_long_score += 1.0 if low <= lower_entry and close > lower_entry else 0.0
    mr_long_score += 1.0 if low_trap else 0.0
    mr_long_score += 1.0 if close > open_ else 0.0
    mr_long_score += 1.0 if index > 0 and close > float(rows[index - 1]["close"]) else 0.0
    mr_long_score += 1.0 if mr_regime_ok else 0.0
    mr_long_score += 1.0 if not bear_majority else 0.0
    mr_long_score += 1.0 if bull_majority or up_share >= float(params.get("softMajorityPct", 0.50)) else 0.0
    mr_long_score += 1.0 if close >= (ind["don_lower"][index] or close) else 0.0
    mr_long_score -= 1.0 if no_fade_long_blocked else 0.0
    mr_long_score -= 1.0 if atr_hard else 0.0

    mr_short_score = 0.0
    mr_short_score += 2.0 if sigma >= float(params["entrySd"]) else 0.0
    mr_short_score += 1.0 if sigma >= float(params["entrySd"]) + 0.25 else 0.0
    mr_short_score += 1.0 if high >= upper_entry and close < upper_entry else 0.0
    mr_short_score += 1.0 if high_trap else 0.0
    mr_short_score += 1.0 if close < open_ else 0.0
    mr_short_score += 1.0 if index > 0 and close < float(rows[index - 1]["close"]) else 0.0
    mr_short_score += 1.0 if mr_regime_ok else 0.0
    mr_short_score += 1.0 if not bull_majority else 0.0
    mr_short_score += 1.0 if bear_majority or low_share >= float(params.get("softMajorityPct", 0.50)) else 0.0
    mr_short_score += 1.0 if close <= (ind["don_upper"][index] or close) else 0.0
    mr_short_score -= 1.0 if no_fade_short_blocked else 0.0
    mr_short_score -= 1.0 if atr_hard else 0.0
    ema = ind["ema"][index]
    mr_short_score -= 1.0 if ema is not None and close > ema else 0.0

    if (
        mr_cost_ok
        and allow_mr
        and allow_longs
        and mr_long_score >= float(params["mrMinScoreLong"])
        and close > lower_stop
        and not no_fade_long_blocked
        and (low <= lower_entry or close <= lower_entry)
    ):
        return {
            "side": "long",
            "type": "mr",
            "signal_index": index,
            "stop": lower_stop,
            "grid_mid": grid_mid,
            "grid_dev": grid_dev,
        }
    if (
        mr_cost_ok
        and allow_mr
        and allow_shorts
        and mr_short_score >= float(params["mrMinScoreShort"])
        and close < upper_stop
        and not no_fade_short_blocked
        and (high >= upper_entry or close >= upper_entry)
    ):
        return {
            "side": "short",
            "type": "mr",
            "signal_index": index,
            "stop": upper_stop,
            "grid_mid": grid_mid,
            "grid_dev": grid_dev,
        }
    return None


def open_position(
    signal: dict[str, Any],
    entry_index: int,
    entry_row: dict[str, Any],
    entry_price: float,
    qty: float,
    fee_model: dict[str, float],
    params: dict[str, Any],
) -> Position:
    stop = float(signal["stop"])
    risk = abs(entry_price - stop)
    round_trip_points = entry_price * fee_model["round_trip_cost_pct"] / 100.0
    required_reward = round_trip_points * float(params["minFeeMultipleForTP"])
    entry_fee = abs(entry_price * qty) * fee_model["entry_fee_pct"] / 100.0
    funding_cost = abs(entry_price * qty) * fee_model["funding_pct"] / 100.0
    side = signal["side"]
    trade_type = signal["type"]

    if trade_type == "breakout":
        tp1_distance = max(risk * float(params["brkTp1R"]), required_reward)
        tp1 = entry_price + tp1_distance if side == "long" else entry_price - tp1_distance
        runner_target = (
            entry_price + risk * float(params["brkRunnerR"])
            if side == "long"
            else entry_price - risk * float(params["brkRunnerR"])
        )
        tp2 = None
        tp1_qty_pct = float(params.get("brkTp1Qty", 30.0))
    else:
        grid_mid = float(signal["grid_mid"])
        grid_dev = float(signal["grid_dev"])
        tp1 = grid_mid
        runner_target = None
        tp2 = (
            grid_mid + grid_dev * float(params["noTradeSd"])
            if side == "long"
            else grid_mid - grid_dev * float(params["noTradeSd"])
        )
        tp1_qty_pct = float(params.get("mrTp1Qty", 75.0)) if bool(params.get("mrUseTp2", True)) else 100.0

    return Position(
        side=side,
        trade_type=trade_type,
        entry_index=entry_index,
        signal_index=int(signal["signal_index"]),
        entry_time=as_utc(entry_row["datetime"]),
        entry_price=entry_price,
        qty=qty,
        remaining_qty=qty,
        stop=stop,
        tp1=tp1,
        runner_target=runner_target,
        tp2=tp2,
        tp1_qty_pct=tp1_qty_pct,
        entry_fee=entry_fee,
        funding_cost=funding_cost,
    )


def update_position(
    position: Position,
    index: int,
    row: dict[str, Any],
    indicators: dict[str, list[Any]],
    params: dict[str, Any],
    fee_model: dict[str, float],
    use_spread: bool,
    is_final: bool,
) -> dict[str, Any] | None:
    side = position.side
    high = float(row["high"])
    low = float(row["low"])
    close = float(row["close"])
    spread = float(row.get("spread_close") or 0.0)
    bars = index - position.entry_index

    if position.trade_type == "mr":
        grid_mid = indicators["grid_mid"][index]
        grid_dev = indicators["grid_dev"][index]
        if grid_mid is not None and position.tp1 is None:
            target_reward = grid_mid - position.entry_price if side == "long" else position.entry_price - grid_mid
            required = position.entry_price * fee_model["round_trip_cost_pct"] / 100.0 * float(params["minFeeMultipleForTP"])
            if target_reward >= required:
                position.tp1 = grid_mid
        if grid_mid is not None and grid_dev is not None:
            no_trade = float(params["noTradeSd"])
            position.tp2 = grid_mid + grid_dev * no_trade if side == "long" else grid_mid - grid_dev * no_trade

    if position.tp1 is not None and not position.tp1_hit:
        tp1_hit = high >= position.tp1 if side == "long" else low <= position.tp1
        stop_hit = low <= position.stop if side == "long" else high >= position.stop
        if stop_hit:
            return close_full(position, row, position.stop, "stop", fee_model, use_spread)
        if tp1_hit:
            exit_qty = position.qty * position.tp1_qty_pct / 100.0
            exit_price = execution_price(position.tp1, spread, side, "exit", fee_model, use_spread)
            realize_partial(position, exit_qty, exit_price, fee_model)
            position.remaining_qty = max(position.remaining_qty - exit_qty, 0.0)
            position.tp1_hit = True
            if bool(params.get("moveStopToBreakevenAfterTp1", True)):
                position.stop = max(position.stop, position.entry_price) if side == "long" else min(position.stop, position.entry_price)
            if position.remaining_qty <= 1e-12:
                return finalize_trade(position, row, position.tp1, "tp1", fee_model, use_spread)

    trail = None
    if position.trade_type == "breakout":
        trail = indicators["don_lower_prev"][index] if side == "long" else indicators["don_upper_prev"][index]
        if trail is not None and position.tp1_hit:
            position.stop = max(position.stop, trail) if side == "long" else min(position.stop, trail)
        target = position.runner_target
        max_bars = int(params["brkMaxBars"])
    else:
        target = position.tp2 if position.tp1_hit else position.tp1
        max_bars = int(params["mrMaxBars"])

    stop_hit = low <= position.stop if side == "long" else high >= position.stop
    target_hit = target is not None and (high >= target if side == "long" else low <= target)
    if stop_hit:
        return close_full(position, row, position.stop, "stop", fee_model, use_spread)
    if target_hit:
        return close_full(position, row, float(target), "runner_target" if position.tp1_hit else "target", fee_model, use_spread)
    if bars >= max_bars:
        return close_full(position, row, close, "time_exit", fee_model, use_spread)
    if is_final:
        return close_full(position, row, close, "end_of_data", fee_model, use_spread)
    return None


def realize_partial(position: Position, qty: float, exit_price: float, fee_model: dict[str, float]) -> None:
    gross = (
        (exit_price - position.entry_price) * qty
        if position.side == "long"
        else (position.entry_price - exit_price) * qty
    )
    fee = abs(exit_price * qty) * fee_model["exit_fee_pct"] / 100.0
    position.realized_pnl += gross - fee
    position.exit_fees += fee


def close_full(
    position: Position,
    row: dict[str, Any],
    raw_exit_price: float,
    reason: str,
    fee_model: dict[str, float],
    use_spread: bool,
) -> dict[str, Any]:
    exit_price = execution_price(
        raw_exit_price,
        float(row.get("spread_close") or 0.0),
        position.side,
        "exit",
        fee_model,
        use_spread,
    )
    realize_partial(position, position.remaining_qty, exit_price, fee_model)
    return finalize_trade(position, row, exit_price, reason, fee_model, use_spread)


def finalize_trade(
    position: Position,
    row: dict[str, Any],
    exit_price: float,
    reason: str,
    fee_model: dict[str, float],
    use_spread: bool,
) -> dict[str, Any]:
    total_fees = position.entry_fee + position.exit_fees + position.funding_cost
    net_pnl = position.realized_pnl - position.entry_fee - position.funding_cost
    gross_pnl = net_pnl + total_fees
    return {
        "side": position.side,
        "type": position.trade_type,
        "entry_time": position.entry_time,
        "exit_time": as_utc(row["datetime"]),
        "entry_price": position.entry_price,
        "exit_price": exit_price,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "fees": total_fees,
        "bars": int((as_utc(row["datetime"]) - position.entry_time).total_seconds() // 900),
        "exit_reason": reason,
    }


def mark_to_market(position: Position, row: dict[str, Any], fee_model: dict[str, float], use_spread: bool) -> float:
    exit_price = execution_price(
        float(row["close"]),
        float(row.get("spread_close") or 0.0),
        position.side,
        "exit",
        fee_model,
        use_spread,
    )
    gross = (
        (exit_price - position.entry_price) * position.remaining_qty
        if position.side == "long"
        else (position.entry_price - exit_price) * position.remaining_qty
    )
    return position.realized_pnl - position.entry_fee - position.funding_cost + gross


def execution_price(
    mid: float,
    spread: float,
    side: str,
    action: str,
    fee_model: dict[str, float],
    use_spread: bool,
) -> float:
    half_spread = spread / 2.0 if use_spread else 0.0
    slip = mid * fee_model["slippage_pct"] / 100.0
    if side == "long":
        return mid + half_spread + slip if action == "entry" else mid - half_spread - slip
    return mid - half_spread - slip if action == "entry" else mid + half_spread + slip


def fee_model_from_config(config: dict[str, Any]) -> dict[str, float]:
    exchange = str(config.get("exchange", "bybit")).lower()
    if exchange == "bybit":
        maker = float(config.get("bybit_maker_fee_pct", 0.020))
        taker = float(config.get("bybit_taker_fee_pct", 0.055))
    elif exchange == "mexc":
        maker = float(config.get("mexc_maker_fee_pct", 0.000))
        taker = float(config.get("mexc_taker_fee_pct", 0.040))
    else:
        maker = float(config.get("custom_maker_fee_pct", 0.020))
        taker = float(config.get("custom_taker_fee_pct", 0.055))
    mode = str(config.get("order_fee_mode", "maker_taker")).lower()
    entry_fee = taker if mode == "taker_taker" else maker
    exit_fee = maker if mode == "maker_maker" else taker
    slippage = float(config.get("slippage_pct_per_side", 0.010))
    funding = float(config.get("expected_funding_pct", 0.0))
    return {
        "entry_fee_pct": entry_fee,
        "exit_fee_pct": exit_fee,
        "slippage_pct": slippage,
        "funding_pct": funding,
        "round_trip_cost_pct": entry_fee + exit_fee + slippage * 2.0 + funding,
    }


def build_indicators(rows: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, list[Any]]:
    close = [float(row["close"]) for row in rows]
    high = [float(row["high"]) for row in rows]
    low = [float(row["low"]) for row in rows]
    open_ = [float(row["open"]) for row in rows]
    volume = [float(row.get("bid_volume") or row.get("ask_volume") or row.get("volume") or 0.0) for row in rows]

    don_fast = int(params["donFastLen"])
    don_slow = int(params["donSlowLen"])
    grid_len = int(params.get("gridSdLen", 50))
    exit_atr_len = int(params.get("exitAtrLen", 14))
    regime_atr_len = int(params.get("regimeAtrLen", 14))
    atr_base_len = int(params.get("atrBaseLen", 14))

    don_upper = rolling_max(high, don_fast)
    don_lower = rolling_min(low, don_fast)
    don_mid = midpoint(don_upper, don_lower)
    don_upper_prev = shift(don_upper, 1)
    don_lower_prev = shift(don_lower, 1)
    don_width_prev = [
        None if u is None or l is None else abs(u - l)
        for u, l in zip(don_upper_prev, don_lower_prev)
    ]
    don_slow_mid_prev = shift(midpoint(rolling_max(high, don_slow), rolling_min(low, don_slow)), 1)
    grid_dev = rolling_stdev(close, grid_len)
    ema = ema_list(close, int(params.get("maLen", 50)))
    rsi = rsi_list(close, int(params.get("rsiLen", 14)))
    macd_line, macd_signal, macd_hist = macd_list(
        close,
        int(params.get("macdFastLen", 12)),
        int(params.get("macdSlowLen", 26)),
        int(params.get("macdSignalLen", 9)),
    )
    exit_atr = atr_list(high, low, close, exit_atr_len)
    regime_atr = atr_list(high, low, close, regime_atr_len)
    regime_atr_base = sma_list(regime_atr, atr_base_len)
    plus_di, minus_di, adx = dmi_list(high, low, close, int(params.get("regimeDiLen", 14)), int(params.get("regimeAdxSmooth", 14)))
    atr_ratio = [
        None if a is None or b in (None, 0) else a / b
        for a, b in zip(regime_atr, regime_atr_base)
    ]

    prior_high = shift(rolling_max(high, int(params.get("sweepLookback", 20))), 1)
    prior_low = shift(rolling_min(low, int(params.get("sweepLookback", 20))), 1)
    high_trap = [ph is not None and h > ph and c < ph for ph, h, c in zip(prior_high, high, close)]
    low_trap = [pl is not None and l < pl and c > pl for pl, l, c in zip(prior_low, low, close)]

    trend_up = []
    trend_down = []
    range_regime = []
    atr_expanding = []
    atr_expansion_hard = []
    soft_range = []
    up_share = []
    low_share = []
    bull_breakout = []
    bear_breakout = []
    for i in range(len(rows)):
        ratio = atr_ratio[i]
        adx_value = adx[i]
        pdi = plus_di[i]
        mdi = minus_di[i]
        dm = don_mid[i]
        ready = None not in (ratio, adx_value, pdi, mdi, dm)
        atr_expanding.append(bool(ready and ratio >= float(params.get("regimeAtrRatioLevel", 1.0))))
        atr_expansion_hard.append(bool(ready and ratio >= float(params.get("regimeAtrRatioLevel", 1.0)) * 1.15))
        trend_up.append(bool(ready and adx_value >= float(params.get("regimeAdxLevel", 20.0)) and pdi > mdi and close[i] > dm))
        trend_down.append(bool(ready and adx_value >= float(params.get("regimeAdxLevel", 20.0)) and mdi > pdi and close[i] < dm))
        range_regime.append(bool(ready and adx_value <= float(params.get("maxAdxForMeanReversion", 34.0)) and not atr_expansion_hard[-1] and don_lower[i] <= close[i] <= don_upper[i]))
        soft_range.append(bool(ready and adx_value <= float(params.get("softMaxAdxForMR", 36.0)) and not trend_up[-1] and not trend_down[-1]))
        statuses = [
            sign(close[i] - ema[i]) if ema[i] is not None else 0,
            sign((rsi[i] or 50) - 50) if rsi[i] is not None else 0,
            sign(macd_hist[i]) if macd_hist[i] is not None else 0,
            sign(close[i] - dm) if dm is not None else 0,
            1 if trend_up[-1] else -1 if trend_down[-1] else 0,
            1 if low_trap[i] else -1 if high_trap[i] else 0,
        ]
        up_share.append(sum(1 for item in statuses if item > 0) / len(statuses))
        low_share.append(sum(1 for item in statuses if item < 0) / len(statuses))
        bull_breakout.append(bool(don_upper_prev[i] is not None and close[i] > don_upper_prev[i]))
        bear_breakout.append(bool(don_lower_prev[i] is not None and close[i] < don_lower_prev[i]))

    no_fade_long_blocked = [bear and trend for bear, trend in zip(bear_breakout, trend_down)]
    no_fade_short_blocked = [bull and trend for bull, trend in zip(bull_breakout, trend_up)]

    return {
        "don_upper": don_upper,
        "don_lower": don_lower,
        "don_mid": don_mid,
        "don_upper_prev": don_upper_prev,
        "don_lower_prev": don_lower_prev,
        "don_width_prev": don_width_prev,
        "don_slow_mid_prev": don_slow_mid_prev,
        "grid_mid": don_mid,
        "grid_dev": grid_dev,
        "ema": ema,
        "rsi": rsi,
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
        "exit_atr": exit_atr,
        "atr_expanding": atr_expanding,
        "atr_expansion_hard": atr_expansion_hard,
        "trend_up": trend_up,
        "trend_down": trend_down,
        "range_regime": range_regime,
        "soft_range_regime": soft_range,
        "high_trap": high_trap,
        "low_trap": low_trap,
        "up_share": up_share,
        "low_share": low_share,
        "bull_breakout": bull_breakout,
        "bear_breakout": bear_breakout,
        "no_fade_long_blocked": no_fade_long_blocked,
        "no_fade_short_blocked": no_fade_short_blocked,
    }


def summarize_trades(
    trades: list[dict[str, Any]],
    initial_cash: float,
    max_drawdown: float,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    years = max((as_utc(rows[-1]["datetime"]) - as_utc(rows[0]["datetime"])).total_seconds() / (365.25 * 24 * 3600), 1e-9)
    wins = [trade for trade in trades if trade["net_pnl"] > 0]
    losses = [trade for trade in trades if trade["net_pnl"] < 0]
    gross_profit = sum(trade["gross_pnl"] for trade in trades if trade["gross_pnl"] > 0)
    gross_loss = abs(sum(trade["gross_pnl"] for trade in trades if trade["gross_pnl"] < 0))
    net_pnl = sum(trade["net_pnl"] for trade in trades)
    total_fees = sum(trade["fees"] for trade in trades)
    average_win = sum(trade["net_pnl"] for trade in wins) / len(wins) if wins else None
    average_loss_abs = abs(sum(trade["net_pnl"] for trade in losses) / len(losses)) if losses else None
    avg_win_loss = (
        average_win / average_loss_abs
        if average_win is not None and average_loss_abs not in (None, 0)
        else None
    )
    long_trades = [trade for trade in trades if trade["side"] == "long"]
    short_trades = [trade for trade in trades if trade["side"] == "short"]
    return {
        "total_trades": len(trades),
        "trades_per_year": len(trades) / years,
        "net_pnl": net_pnl,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "win_rate": len(wins) / len(trades) if trades else None,
        "avg_win": average_win,
        "avg_loss": -average_loss_abs if average_loss_abs is not None else None,
        "avg_win_loss": avg_win_loss,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown * 100.0,
        "commission_drag": total_fees,
        "commission_to_gross_profit": total_fees / gross_profit if gross_profit else None,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "long_trades": len(long_trades),
        "short_trades": len(short_trades),
        "mr_trades": sum(1 for trade in trades if trade["type"] == "mr"),
        "breakout_trades": sum(1 for trade in trades if trade["type"] == "breakout"),
    }


def rejection_reasons(metrics: dict[str, Any], reject: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if metrics["trades_per_year"] < float(reject["min_trades_per_year"]):
        reasons.append("trades/year below minimum")
    max_trades = reject.get("max_trades_per_year")
    if max_trades not in (None, "", 0, "none", "null") and metrics["trades_per_year"] > float(max_trades):
        reasons.append("trades/year above maximum")
    if metrics["profit_factor"] is None or metrics["profit_factor"] < float(reject["min_validation_profit_factor"]):
        reasons.append("validation profit factor below minimum")
    if metrics["avg_win_loss"] is None or metrics["avg_win_loss"] < float(reject["min_avg_win_loss"]):
        reasons.append("avg win/loss below minimum")
    if (
        metrics["commission_to_gross_profit"] is None
        or metrics["commission_to_gross_profit"] > float(reject["max_commission_to_gross_profit"])
    ):
        reasons.append("commission drag too high")
    return reasons


def robustness_reasons(scenario_results: list[dict[str, Any]], robustness: dict[str, Any]) -> list[str]:
    if not robustness.get("enabled", False):
        return []
    reasons: list[str] = []
    require_validation_positive = bool(robustness.get("require_validation_net_pnl_positive", True))
    require_test_positive = bool(robustness.get("require_test_net_pnl_positive", False))
    min_validation_pf = robustness.get("min_validation_profit_factor", 1.0)
    for scenario in scenario_results:
        validation = scenario["validation"]
        test = scenario["test"]
        name = scenario["name"]
        if require_validation_positive and validation["net_pnl"] <= 0:
            reasons.append(f"{name} validation net P&L not positive")
        if min_validation_pf is not None and (validation["profit_factor"] is None or validation["profit_factor"] < float(min_validation_pf)):
            reasons.append(f"{name} validation profit factor below robust minimum")
        if require_test_positive and test["net_pnl"] <= 0:
            reasons.append(f"{name} test net P&L not positive")
    return reasons


def validation_score(
    metrics: dict[str, Any],
    reject: dict[str, Any],
    scenario_results: list[dict[str, Any]] | None = None,
) -> float:
    pf = min(metrics["profit_factor"] or 0.0, 3.0)
    min_trades = float(reject.get("min_trades_per_year", 0.0))
    trades_score = min(metrics["trades_per_year"] / min_trades, 2.0) if min_trades else 0.0
    if min_trades and metrics["trades_per_year"] < min_trades:
        trades_score -= (min_trades - metrics["trades_per_year"]) / max(min_trades, 1.0) * 10.0
    win_loss = min(metrics["avg_win_loss"] or 0.0, 3.0)
    drawdown_penalty = abs(metrics["max_drawdown_pct"]) * 0.2
    commission_drag = metrics["commission_to_gross_profit"] or 0.0
    score = metrics["net_pnl"] * 0.02 + pf * 20.0 + win_loss * 8.0 + trades_score * 2.0 - drawdown_penalty - commission_drag * 8.0
    if scenario_results:
        worst_validation = min(scenario_results, key=lambda item: item["validation"]["net_pnl"])["validation"]
        worst_pf = min((item["validation"]["profit_factor"] or 0.0) for item in scenario_results)
        score += worst_validation["net_pnl"] * 0.025 + min(worst_pf, 3.0) * 12.0
        if worst_validation["net_pnl"] <= 0:
            score -= 50.0 + abs(worst_validation["net_pnl"]) * 0.01
    return score


def prefix_metrics(prefix: str, metrics: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "total_trades",
        "trades_per_year",
        "net_pnl",
        "profit_factor",
        "win_rate",
        "avg_win",
        "avg_loss",
        "avg_win_loss",
        "max_drawdown_pct",
        "commission_drag",
        "commission_to_gross_profit",
        "long_trades",
        "short_trades",
        "mr_trades",
        "breakout_trades",
    ]
    return {f"{prefix}_{key}": metrics.get(key) for key in keys}


def build_presets(top: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    ordered_params = parameter_order(config)
    return {
        "source": "TradingView strategy Python approximation",
        "created_at": datetime.now(timezone.utc),
        "fixed_inputs": {
            "entryStrictness": (config.get("fixed") or {}).get("entryStrictness", "sampled"),
            "fee_exchange": config.get("fees", {}).get("exchange"),
            "order_fee_mode": config.get("fees", {}).get("order_fee_mode"),
            "slippage_pct_per_side": config.get("fees", {}).get("slippage_pct_per_side"),
            "expected_funding_pct": config.get("fees", {}).get("expected_funding_pct"),
        },
        "notes": [
            "Use these as candidate Pine inputs, not as proof of profitability.",
            "Results approximate the Pine logic and should be rechecked in TradingView.",
            "The Python runner applies the Pine entry strictness preset before evaluating signals.",
        ],
        "presets": [
            {
                "rank": index + 1,
                "score": row["score"],
                "accepted": row["accepted"],
                "timeframe": row.get("timeframe"),
                "data_path": row.get("data_path"),
                "parameters": {key: row.get(key) for key in ordered_params},
                "validation": {key.removeprefix("validation_"): value for key, value in row.items() if key.startswith("validation_")},
                "test": {key.removeprefix("test_"): value for key, value in row.items() if key.startswith("test_")},
            }
            for index, row in enumerate(top)
        ],
    }


def write_pine_markdown(path: Path, top: list[dict[str, Any]], config: dict[str, Any]) -> None:
    fixed = config.get("fixed") or {}
    fees = config.get("fees", {})
    ordered_params = parameter_order(config)
    lines = [
        "# Pine Input Presets",
        "",
        "Data: see each preset timeframe/path below.",
        "",
        "These presets come from a Python approximation of the Pine strategy. Re-test in TradingView before using them for any research conclusion.",
        "",
        "Keep these fixed Pine inputs aligned before pasting a preset:",
        "",
        "```text",
        f"entryStrictness = {fixed.get('entryStrictness', 'sampled per preset')}",
        f"exchangeFeeProfile = {fees.get('exchange', 'bybit')}",
        f"orderFeeMode = {fees.get('order_fee_mode', 'maker_taker')}",
        f"slippagePctPerSide = {fees.get('slippage_pct_per_side', 0.0)}",
        f"expectedFundingPct = {fees.get('expected_funding_pct', 0.0)}",
        "```",
        "",
    ]
    if not any(row["accepted"] for row in top):
        lines.extend(
            [
                "> No preset in this run passed all validation filters. Treat the blocks below as diagnostics only.",
                "",
            ]
        )
    for index, row in enumerate(top[:5], start=1):
        lines.append(f"## Preset {index}")
        lines.append("")
        lines.append(f"- Accepted by validation filters: `{row['accepted']}`")
        lines.append(f"- Timeframe: `{row.get('timeframe', 'n/a')}`")
        lines.append(f"- Data: `{Path(row['data_path']).as_posix() if row.get('data_path') else 'n/a'}`")
        lines.append(f"- Validation PF: `{format_float(row['validation_profit_factor'])}`")
        lines.append(f"- Validation trades/year: `{format_float(row['validation_trades_per_year'])}`")
        lines.append(f"- Validation net P&L: `{format_float(row['validation_net_pnl'])}`")
        if "worst_fee_validation_net_pnl" in row:
            lines.append(f"- Worst-fee validation net P&L: `{format_float(row['worst_fee_validation_net_pnl'])}`")
            lines.append(f"- Worst-fee validation PF: `{format_float(row['worst_fee_validation_profit_factor'])}`")
        lines.append("")
        lines.append("```text")
        for key in ordered_params:
            lines.append(f"{key} = {row.get(key)}")
        lines.append("```")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    columns = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows([{key: to_jsonable(value) for key, value in row.items()} for row in rows])


def as_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    parsed = parse_timestamp_value(value)
    if parsed is None:
        raise ValueError(f"Invalid timestamp: {value!r}")
    return parsed


def format_float(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def slugify(value: str) -> str:
    cleaned = "".join(character.lower() if character.isalnum() else "_" for character in value)
    return "_".join(part for part in cleaned.split("_") if part)


def sign(value: float | None) -> int:
    if value is None:
        return 0
    return 1 if value > 0 else -1 if value < 0 else 0


def shift(values: list[Any], periods: int) -> list[Any]:
    return [None] * periods + values[:-periods]


def midpoint(a: list[float | None], b: list[float | None]) -> list[float | None]:
    return [None if x is None or y is None else (x + y) * 0.5 for x, y in zip(a, b)]


def rolling_max(values: list[float], window: int) -> list[float | None]:
    output: list[float | None] = []
    for index in range(len(values)):
        if index + 1 < window:
            output.append(None)
        else:
            output.append(max(values[index + 1 - window : index + 1]))
    return output


def rolling_min(values: list[float], window: int) -> list[float | None]:
    output: list[float | None] = []
    for index in range(len(values)):
        if index + 1 < window:
            output.append(None)
        else:
            output.append(min(values[index + 1 - window : index + 1]))
    return output


def rolling_stdev(values: list[float], window: int) -> list[float | None]:
    output: list[float | None] = []
    for index in range(len(values)):
        if index + 1 < window:
            output.append(None)
            continue
        segment = values[index + 1 - window : index + 1]
        avg = sum(segment) / window
        variance = sum((value - avg) ** 2 for value in segment) / window
        output.append(math.sqrt(variance))
    return output


def sma_list(values: list[float | None], window: int) -> list[float | None]:
    output: list[float | None] = []
    active: list[float] = []
    for value in values:
        active.append(float(value) if value is not None else math.nan)
        if len(active) > window:
            active.pop(0)
        if len(active) == window and all(math.isfinite(item) for item in active):
            output.append(sum(active) / window)
        else:
            output.append(None)
    return output


def ema_list(values: list[float], length: int) -> list[float | None]:
    output: list[float | None] = []
    alpha = 2.0 / (length + 1.0)
    ema_value: float | None = None
    for value in values:
        ema_value = value if ema_value is None else ema_value + alpha * (value - ema_value)
        output.append(ema_value)
    return output


def rsi_list(values: list[float], length: int) -> list[float | None]:
    gains: list[float] = [0.0]
    losses: list[float] = [0.0]
    for prev, curr in zip(values, values[1:]):
        delta = curr - prev
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = rma_list(gains, length)
    avg_loss = rma_list(losses, length)
    output: list[float | None] = []
    for gain, loss in zip(avg_gain, avg_loss):
        if gain is None or loss is None:
            output.append(None)
        elif loss == 0 and gain == 0:
            output.append(50.0)
        elif loss == 0:
            output.append(100.0)
        else:
            rs = gain / loss
            output.append(100.0 - 100.0 / (1.0 + rs))
    return output


def rma_list(values: list[float], length: int) -> list[float | None]:
    output: list[float | None] = []
    rma: float | None = None
    for index, value in enumerate(values):
        if index + 1 < length:
            output.append(None)
        elif index + 1 == length:
            rma = sum(values[:length]) / length
            output.append(rma)
        else:
            assert rma is not None
            rma = (rma * (length - 1) + value) / length
            output.append(rma)
    return output


def macd_list(values: list[float], fast: int, slow: int, signal: int) -> tuple[list[Any], list[Any], list[Any]]:
    fast_ema = ema_list(values, fast)
    slow_ema = ema_list(values, slow)
    line = [None if f is None or s is None else f - s for f, s in zip(fast_ema, slow_ema)]
    signal_line = ema_nullable(line, signal)
    hist = [None if l is None or s is None else l - s for l, s in zip(line, signal_line)]
    return line, signal_line, hist


def ema_nullable(values: list[float | None], length: int) -> list[float | None]:
    output: list[float | None] = []
    alpha = 2.0 / (length + 1.0)
    ema_value: float | None = None
    for value in values:
        if value is None:
            output.append(None)
            continue
        ema_value = value if ema_value is None else ema_value + alpha * (value - ema_value)
        output.append(ema_value)
    return output


def atr_list(high: list[float], low: list[float], close: list[float], length: int) -> list[float | None]:
    tr: list[float] = []
    for index in range(len(close)):
        if index == 0:
            tr.append(high[index] - low[index])
        else:
            tr.append(max(high[index] - low[index], abs(high[index] - close[index - 1]), abs(low[index] - close[index - 1])))
    return rma_list(tr, length)


def dmi_list(high: list[float], low: list[float], close: list[float], di_len: int, adx_len: int) -> tuple[list[Any], list[Any], list[Any]]:
    plus_dm = [0.0]
    minus_dm = [0.0]
    tr = [high[0] - low[0]]
    for index in range(1, len(close)):
        up_move = high[index] - high[index - 1]
        down_move = low[index - 1] - low[index]
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        tr.append(max(high[index] - low[index], abs(high[index] - close[index - 1]), abs(low[index] - close[index - 1])))
    atr = rma_list(tr, di_len)
    plus = rma_list(plus_dm, di_len)
    minus = rma_list(minus_dm, di_len)
    plus_di = [None if a in (None, 0) or p is None else 100.0 * p / a for p, a in zip(plus, atr)]
    minus_di = [None if a in (None, 0) or m is None else 100.0 * m / a for m, a in zip(minus, atr)]
    dx = [
        None if p is None or m is None or p + m == 0 else 100.0 * abs(p - m) / (p + m)
        for p, m in zip(plus_di, minus_di)
    ]
    adx = rma_nullable(dx, adx_len)
    return plus_di, minus_di, adx


def rma_nullable(values: list[float | None], length: int) -> list[float | None]:
    output: list[float | None] = []
    active: list[float] = []
    rma: float | None = None
    for value in values:
        if value is None:
            output.append(None)
            continue
        active.append(value)
        if rma is None:
            if len(active) < length:
                output.append(None)
            else:
                rma = sum(active[-length:]) / length
                output.append(rma)
        else:
            rma = (rma * (length - 1) + value) / length
            output.append(rma)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize TradingView Pine strategy parameters locally.")
    parser.add_argument("--config", default="configs/tradingview_optimizer_config.yaml")
    parser.add_argument("--iterations", type=int, default=None)
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Parallel worker processes. Use 0 for CPU count minus one.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = optimize(
        resolve_path(args.config),
        iterations_override=args.iterations,
        max_workers_override=args.workers,
    )
    best = result["best"]
    if best is None:
        print("optimizer completed with no candidates")
        return
    print(
        "TradingView optimizer complete: "
        f"evaluated={result['evaluated']}, accepted={result['accepted']}, "
        f"best_config_id={best['config_id']}, "
        f"timeframe={best.get('timeframe', 'n/a')}, "
        f"validation_pf={format_float(best['validation_profit_factor'])}, "
        f"validation_trades_year={format_float(best['validation_trades_per_year'])}"
    )
    if result["accepted"] == 0:
        print("warning: no configs passed all validation filters; preset output is diagnostic only")
    print(f"reports: {result['reports_dir']}")


if __name__ == "__main__":
    main()
