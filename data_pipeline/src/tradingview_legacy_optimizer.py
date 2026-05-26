from __future__ import annotations

import argparse
import copy
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline_utils import read_yaml, resolve_path, write_json
from tradingview_optimizer import (
    as_utc,
    atr_list,
    data_specs,
    dmi_list,
    ema_list,
    execution_price,
    fee_model_from_config,
    format_float,
    load_frame,
    macd_list,
    midpoint,
    prefix_metrics,
    rejection_reasons,
    resolve_max_workers,
    rolling_max,
    rolling_min,
    rolling_stdev,
    rsi_list,
    shift,
    sign,
    slugify,
    sma_list,
    split_rows,
    summarize_trades,
    validation_score,
    write_csv,
)


PARAMETER_ORDER = [
    "engineMode",
    "sideMode",
    "donLen",
    "gridSource",
    "gridSdLen",
    "entrySd",
    "stopSd",
    "noTradeSd",
    "useTrendFilter",
    "maxAdxForMeanReversion",
    "useSweepConfirmation",
    "closeAtMiddleMode",
    "useOneTradeOnly",
    "allowFlipOnZoneBreak",
    "fixedGoldStopCapPoints",
    "minBarsBetweenTrades",
    "ladderMode",
    "ladderLevel1Sd",
    "ladderLevel2Sd",
    "ladderLevel3Sd",
    "ladderSoftStopSd",
    "ladderEmergencyStopSd",
    "ladderWeight1",
    "ladderWeight2",
    "ladderWeight3",
    "ladderUseCloseConfirmedStop",
    "ladderStopConfirmBars",
    "ladderUseTrendFilter",
    "ladderMaxAdx",
    "ladderUseSweepConfirmation",
    "ladderUseBasketRiskSizing",
    "ladderBasketRiskPct",
    "ladderMaxNotionalPct",
    "exitAtrLen",
    "atrStopMult",
    "atrTargetMult",
    "maLen",
    "sdLen",
    "envLen",
    "rsiLen",
    "macdFastLen",
    "macdSlowLen",
    "macdSignalLen",
    "regimeDiLen",
    "regimeAdxSmooth",
    "regimeAdxLevel",
    "regimeAtrLen",
    "atrBaseLen",
    "sweepLookback",
]

INTEGER_PARAMETERS = {
    "donLen",
    "gridSdLen",
    "minBarsBetweenTrades",
    "ladderStopConfirmBars",
    "exitAtrLen",
    "maLen",
    "sdLen",
    "envLen",
    "rsiLen",
    "macdFastLen",
    "macdSlowLen",
    "macdSignalLen",
    "regimeDiLen",
    "regimeAdxSmooth",
    "regimeAtrLen",
    "atrBaseLen",
    "sweepLookback",
}

PARAMETER_STEPS = {
    "entrySd": 0.05,
    "stopSd": 0.05,
    "noTradeSd": 0.05,
    "maxAdxForMeanReversion": 0.5,
    "fixedGoldStopCapPoints": 0.5,
    "ladderLevel1Sd": 0.05,
    "ladderLevel2Sd": 0.05,
    "ladderLevel3Sd": 0.05,
    "ladderSoftStopSd": 0.05,
    "ladderEmergencyStopSd": 0.05,
    "ladderWeight1": 1.0,
    "ladderWeight2": 1.0,
    "ladderWeight3": 1.0,
    "ladderMaxAdx": 0.5,
    "ladderBasketRiskPct": 0.05,
    "ladderMaxNotionalPct": 0.5,
    "atrStopMult": 0.25,
    "atrTargetMult": 0.25,
    "regimeAdxLevel": 0.5,
}

FEE_PROFILES: dict[str, dict[str, Any]] = {
    "zero_cost": {
        "fees": {
            "exchange": "custom",
            "order_fee_mode": "maker_maker",
            "custom_maker_fee_pct": 0.0,
            "custom_taker_fee_pct": 0.0,
            "slippage_pct_per_side": 0.0,
            "expected_funding_pct": 0.0,
        },
        "execution": {"use_spread": False},
    },
    "bybit_maker_taker": {
        "fees": {
            "exchange": "bybit",
            "order_fee_mode": "maker_taker",
            "slippage_pct_per_side": 0.010,
            "expected_funding_pct": 0.0,
        },
        "execution": {"use_spread": True},
    },
    "bybit_taker_taker": {
        "fees": {
            "exchange": "bybit",
            "order_fee_mode": "taker_taker",
            "slippage_pct_per_side": 0.010,
            "expected_funding_pct": 0.0,
        },
        "execution": {"use_spread": True},
    },
    "mexc_low_cost": {
        "fees": {
            "exchange": "mexc",
            "order_fee_mode": "maker_taker",
            "slippage_pct_per_side": 0.005,
            "expected_funding_pct": 0.0,
        },
        "execution": {"use_spread": True},
    },
    "worst_case_taker": {
        "fees": {
            "exchange": "custom",
            "order_fee_mode": "taker_taker",
            "custom_maker_fee_pct": 0.055,
            "custom_taker_fee_pct": 0.075,
            "slippage_pct_per_side": 0.030,
            "expected_funding_pct": 0.010,
        },
        "execution": {"use_spread": True},
    },
}

_WORKER_SPLITS: dict[str, list[dict[str, Any]]] | None = None
_WORKER_CONFIG: dict[str, Any] | None = None


@dataclass
class LegacyLeg:
    label: str
    entry_price: float
    qty: float
    entry_fee: float
    entry_time: datetime
    entry_index: int


@dataclass
class LegacyPosition:
    side: str
    trade_type: str
    entry_index: int
    entry_time: datetime
    entry_price: float
    qty: float
    entry_fee: float
    funding_cost: float
    stop: float | None = None
    target: float | None = None
    legs: list[LegacyLeg] = field(default_factory=list)
    realized_pnl: float = 0.0
    exit_fees: float = 0.0
    soft_stop_count: int = 0
    filled_levels: set[str] = field(default_factory=set)


def optimize(
    config_path: Path,
    iterations_override: int | None = None,
    max_workers_override: int | None = None,
) -> dict[str, Any]:
    config = read_yaml(config_path)
    reports_dir = resolve_path(config["data"].get("reports_dir", "data/reports/tradingview_legacy_optimizer"))
    reports_dir.mkdir(parents=True, exist_ok=True)
    iterations = iterations_override or int(config.get("search", {}).get("iterations", 250))
    max_workers = resolve_max_workers(max_workers_override, config)
    top_n = int(config.get("search", {}).get("top_n", 20))
    seed = int(config.get("search", {}).get("seed", 91))
    rng = random.Random(seed)

    all_candidates: list[dict[str, Any]] = []
    for data_spec in data_specs(config):
        data_path = resolve_path(data_spec["input_path"])
        timeframe = str(data_spec.get("timeframe") or config["data"].get("timeframe") or data_path.stem)
        rows = load_frame(data_path)
        splits = split_rows(rows, config["walk_forward"])
        candidates = run_search(config, splits, rng, iterations, max_workers, timeframe, data_path)
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
        "positive_validation": sum(1 for item in all_candidates if item["validation_net_pnl"] > 0),
        "ge500_positive_validation": sum(
            1 for item in all_candidates if item["validation_trades_per_year"] >= 500 and item["validation_net_pnl"] > 0
        ),
        "best": top[0] if top else None,
    }


def run_diagnostics(
    config_path: Path,
    iterations: int,
    workers: int | None,
    fee_profiles: list[str],
    timeframes: set[str] | None,
) -> dict[str, Any]:
    base_config = read_yaml(config_path)
    reports_root = resolve_path("data/reports/tradingview_legacy_diagnostics")
    reports_root.mkdir(parents=True, exist_ok=True)
    max_workers = resolve_max_workers(workers, base_config)
    top_n = int(base_config.get("search", {}).get("top_n", 20))
    seed = int(base_config.get("search", {}).get("seed", 91))
    split_cache = load_split_cache(base_config, timeframes)

    all_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for fee_index, fee_name in enumerate(fee_profiles):
        if fee_name not in FEE_PROFILES:
            raise ValueError(f"Unknown fee profile: {fee_name}")
        case_config = make_fee_config(base_config, fee_name)
        rng = random.Random(seed + fee_index * 10_000)
        case_rows: list[dict[str, Any]] = []

        for timeframe, payload in split_cache.items():
            candidates = run_search(
                config=case_config,
                splits=payload["splits"],
                rng=rng,
                iterations=iterations,
                max_workers=max_workers,
                timeframe=timeframe,
                data_path=payload["data_path"],
            )
            for row in candidates:
                row["diagnostic_case"] = fee_name
                row["fee_profile"] = fee_name
            ranked_tf = sorted(candidates, key=lambda item: item["score"], reverse=True)
            summary_rows.append(summarize_rows(ranked_tf, fee_name, timeframe))
            case_rows.extend(candidates)

        ranked_case = sorted(case_rows, key=lambda item: item["score"], reverse=True)
        case_dir = reports_root / "cases" / fee_name
        write_csv(case_dir / "all_results.csv", ranked_case)
        write_csv(case_dir / "top_results.csv", ranked_case[:top_n])
        write_json(case_dir / "best_presets.json", build_presets(ranked_case[:top_n], case_config))
        write_pine_markdown(case_dir / "pine_input_preset.md", ranked_case[:top_n], case_config)
        summary_rows.append(summarize_rows(ranked_case, fee_name, "all"))
        all_rows.extend(case_rows)

    ranked_all = sorted(all_rows, key=lambda item: item["score"], reverse=True)
    write_csv(reports_root / "all_results.csv", ranked_all)
    write_csv(reports_root / "top_results.csv", ranked_all[:top_n])
    write_csv(reports_root / "summary.csv", summary_rows)
    payload = {
        "reports_dir": reports_root,
        "iterations_per_fee_timeframe": iterations,
        "workers": max_workers,
        "fee_profiles": fee_profiles,
        "timeframes": sorted(split_cache.keys()),
        "total_evaluated": len(all_rows),
        "accepted": sum(1 for row in all_rows if row["accepted"]),
        "positive_validation": sum(1 for row in all_rows if row["validation_net_pnl"] > 0),
        "ge500_positive_validation": sum(
            1 for row in all_rows if row["validation_trades_per_year"] >= 500 and row["validation_net_pnl"] > 0
        ),
        "best": ranked_all[0] if ranked_all else None,
    }
    write_json(reports_root / "summary.json", payload)
    return payload


def load_split_cache(config: dict[str, Any], timeframes: set[str] | None) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    for spec in data_specs(config):
        timeframe = str(spec.get("timeframe") or config["data"].get("timeframe") or Path(spec["input_path"]).stem)
        if timeframes and timeframe not in timeframes:
            continue
        data_path = resolve_path(spec["input_path"])
        rows = load_frame(data_path)
        cache[timeframe] = {"data_path": data_path, "splits": split_rows(rows, config["walk_forward"])}
    if not cache:
        raise ValueError("No matching timeframes selected")
    return cache


def make_fee_config(base_config: dict[str, Any], fee_name: str) -> dict[str, Any]:
    config = copy.deepcopy(base_config)
    profile = FEE_PROFILES[fee_name]
    config["fees"].update(profile["fees"])
    config["execution"].update(profile["execution"])
    config["robustness"] = {"enabled": False}
    return config


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
        tasks.append((f"{timeframe}_{index + 1}", coerce_params(params)))

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


def init_worker(splits: dict[str, list[dict[str, Any]]], config: dict[str, Any]) -> None:
    global _WORKER_SPLITS, _WORKER_CONFIG
    _WORKER_SPLITS = splits
    _WORKER_CONFIG = config


def evaluate_candidate_worker(task: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    if _WORKER_SPLITS is None or _WORKER_CONFIG is None:
        raise RuntimeError("Worker state was not initialized")
    config_id, params = task
    return evaluate_candidate(config_id, params, _WORKER_SPLITS, _WORKER_CONFIG)


def configured_parameter_order(config: dict[str, Any]) -> list[str]:
    configured = set((config.get("fixed") or {}).keys()) | set(config.get("parameters", {}).keys())
    keys = [key for key in PARAMETER_ORDER if key in configured]
    for key in (config.get("fixed") or {}).keys():
        if key not in keys:
            keys.append(key)
    for key in config.get("parameters", {}).keys():
        if key not in keys:
            keys.append(key)
    return keys


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


def coerce_params(params: dict[str, Any]) -> dict[str, Any]:
    coerced = dict(params)
    coerced["engineMode"] = str(coerced.get("engineMode", "ladder")).lower()
    coerced["sideMode"] = str(coerced.get("sideMode", "both")).lower()
    coerced["gridSource"] = str(coerced.get("gridSource", "don")).lower()
    coerced["ladderMode"] = str(coerced.get("ladderMode", "limit")).lower()
    coerced["closeAtMiddleMode"] = str(coerced.get("closeAtMiddleMode", "cross")).lower()
    coerced["stopSd"] = max(float(coerced.get("stopSd", 2.25)), float(coerced.get("entrySd", 1.25)) + 0.25)
    levels = sorted(
        [
            float(coerced.get("ladderLevel1Sd", 2.0)),
            float(coerced.get("ladderLevel2Sd", 2.5)),
            float(coerced.get("ladderLevel3Sd", 3.0)),
        ]
    )
    coerced["ladderLevel1Sd"] = levels[0]
    coerced["ladderLevel2Sd"] = max(levels[1], levels[0] + 0.10)
    coerced["ladderLevel3Sd"] = max(levels[2], coerced["ladderLevel2Sd"] + 0.10)
    coerced["ladderSoftStopSd"] = max(float(coerced.get("ladderSoftStopSd", 3.5)), coerced["ladderLevel3Sd"] + 0.10)
    coerced["ladderEmergencyStopSd"] = max(
        float(coerced.get("ladderEmergencyStopSd", 3.9)),
        coerced["ladderSoftStopSd"] + 0.10,
    )
    if int(coerced.get("macdSlowLen", 26)) <= int(coerced.get("macdFastLen", 12)):
        coerced["macdSlowLen"] = int(coerced["macdFastLen"]) + 2
    total_weight = sum(float(coerced.get(key, 0.0)) for key in ["ladderWeight1", "ladderWeight2", "ladderWeight3"])
    if total_weight <= 0:
        coerced["ladderWeight1"] = 25.0
        coerced["ladderWeight2"] = 35.0
        coerced["ladderWeight3"] = 40.0
    return coerced


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
    reject = config["reject"]
    reject_reasons = rejection_reasons(validation, reject)
    robust_reasons = robustness_reasons(scenario_results, config.get("robustness", {}))
    train_stable = train["profit_factor"] is not None and train["profit_factor"] >= 1.0 and train["net_pnl"] > 0
    test_not_collapsed = test["net_pnl"] >= -abs(validation["net_pnl"]) * 0.75
    score = validation_score(validation, reject, scenario_results)
    all_reasons = reject_reasons + robust_reasons
    if all_reasons:
        score -= 100.0 + len(all_reasons) * 10.0
    if not train_stable:
        score -= 15.0
    if not test_not_collapsed:
        score -= 20.0

    result = {
        "config_id": config_id,
        **{key: params.get(key) for key in configured_parameter_order(config)},
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
    results = []
    for name, fee_config in fee_scenarios(config):
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
        scenarios.append((name, {**config["fees"], **scenario}))
    return scenarios


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


def run_backtest(
    rows: list[dict[str, Any]],
    params: dict[str, Any],
    config: dict[str, Any],
    fee_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = coerce_params(params)
    indicators = build_legacy_indicators(rows, params)
    fee_model = fee_model_from_config(fee_config or config["fees"])
    initial_cash = float(config["execution"].get("initial_cash", 100000))
    point_value = float(config["execution"].get("point_value", 1.0))
    use_spread = bool(config["execution"].get("use_spread", True))
    entry_timing = str(config["execution"].get("entry_timing", "signal_close")).lower()
    cash = initial_cash
    peak = initial_cash
    max_drawdown = 0.0
    trades: list[dict[str, Any]] = []
    position: LegacyPosition | None = None
    last_close_index: int | None = None
    equity_curve_count = 0

    for index, row in enumerate(rows):
        if index < indicators["min_bars_needed"]:
            equity_curve_count += 1
            continue

        if position is not None:
            closed_trade = update_legacy_position(
                position,
                index,
                row,
                indicators,
                params,
                fee_model,
                use_spread,
                is_final=index == len(rows) - 1,
            )
            if closed_trade is not None:
                cash += closed_trade["net_pnl"]
                trades.append(closed_trade)
                position = None
                last_close_index = index

        if position is None and index < len(rows) - 1:
            cooldown = int(params.get("minBarsBetweenTrades", 5))
            if last_close_index is None or index - last_close_index >= cooldown:
                signal = signal_at(index, rows, indicators, params, cash, config)
                if signal is not None:
                    entry_index = index if entry_timing == "signal_close" else index + 1
                    entry_row = rows[entry_index]
                    position = open_legacy_position(
                        signal,
                        entry_index,
                        entry_row,
                        fee_model,
                        use_spread,
                        point_value,
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
    ind: dict[str, Any],
    params: dict[str, Any],
    equity: float,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    engine = str(params.get("engineMode", "ladder")).lower()
    side_mode = str(params.get("sideMode", "both")).lower()
    allow_longs = side_mode in {"both", "long", "long_only"}
    allow_shorts = side_mode in {"both", "short", "short_only"}
    if engine == "grid":
        return grid_signal(index, rows, ind, params, allow_longs, allow_shorts, equity, config)
    if engine == "tactical":
        return tactical_signal(index, rows, ind, params, allow_longs, allow_shorts, equity, config)
    return ladder_signal(index, rows, ind, params, allow_longs, allow_shorts, equity, config)


def grid_signal(
    index: int,
    rows: list[dict[str, Any]],
    ind: dict[str, Any],
    params: dict[str, Any],
    allow_longs: bool,
    allow_shorts: bool,
    equity: float,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    close = float(rows[index]["close"])
    high = float(rows[index]["high"])
    low = float(rows[index]["low"])
    grid_mid = ind["grid_mid"][index]
    grid_dev = ind["grid_dev"][index]
    if grid_mid is None or grid_dev is None or grid_dev <= 0:
        return None
    entry_sd = float(params.get("entrySd", 1.25))
    stop_sd = float(params.get("stopSd", 2.25))
    no_trade_sd = float(params.get("noTradeSd", 0.5))
    lower_no_trade = grid_mid - grid_dev * no_trade_sd
    upper_no_trade = grid_mid + grid_dev * no_trade_sd
    lower_entry = grid_mid - grid_dev * entry_sd
    upper_entry = grid_mid + grid_dev * entry_sd
    lower_stop = grid_mid - grid_dev * stop_sd
    upper_stop = grid_mid + grid_dev * stop_sd
    in_no_trade = lower_no_trade <= close <= upper_no_trade
    lower_break = close < lower_stop
    upper_break = close > upper_stop
    trend_ok = not bool(params.get("useTrendFilter", True)) or ind["adx"][index] is None or ind["adx"][index] <= float(params.get("maxAdxForMeanReversion", 25.0))
    low_trap = bool(ind["low_trap"][index])
    high_trap = bool(ind["high_trap"][index])
    use_sweep = bool(params.get("useSweepConfirmation", True))
    long_raw = (
        allow_longs
        and not in_no_trade
        and (low <= lower_entry or close <= lower_entry)
        and ((low <= lower_entry and close > lower_entry) or (use_sweep and low_trap))
        and trend_ok
        and not lower_break
    )
    short_raw = (
        allow_shorts
        and not in_no_trade
        and (high >= upper_entry or close >= upper_entry)
        and ((high >= upper_entry and close < upper_entry) or (use_sweep and high_trap))
        and trend_ok
        and not upper_break
    )
    if long_raw == short_raw:
        return None
    side = "long" if long_raw else "short"
    qty = order_qty(equity, close, config)
    stop = lower_stop if side == "long" else upper_stop
    stop = apply_fixed_stop_cap(side, close, stop, params)
    return {
        "side": side,
        "type": "grid",
        "entry_price": close,
        "qty": qty,
        "stop": stop,
        "target": grid_mid,
        "signal_index": index,
    }


def ladder_signal(
    index: int,
    rows: list[dict[str, Any]],
    ind: dict[str, Any],
    params: dict[str, Any],
    allow_longs: bool,
    allow_shorts: bool,
    equity: float,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    close = float(rows[index]["close"])
    high = float(rows[index]["high"])
    low = float(rows[index]["low"])
    grid_mid = ind["grid_mid"][index]
    grid_dev = ind["grid_dev"][index]
    if grid_mid is None or grid_dev is None or grid_dev <= 0:
        return None
    trend_ok = not bool(params.get("ladderUseTrendFilter", False)) or ind["adx"][index] is None or ind["adx"][index] <= float(params.get("ladderMaxAdx", 35.0))
    low_trap = bool(ind["low_trap"][index])
    high_trap = bool(ind["high_trap"][index])
    use_sweep = bool(params.get("ladderUseSweepConfirmation", False))
    levels = ladder_levels(grid_mid, grid_dev, params)
    weights = ladder_weights(params)
    side = None
    if allow_longs and close < grid_mid and trend_ok and (not use_sweep or low_trap):
        side = "long"
    if allow_shorts and close > grid_mid and trend_ok and (not use_sweep or high_trap):
        if side is not None:
            return None
        side = "short"
    if side is None:
        return None

    touched: list[tuple[str, float, float]] = []
    mode = str(params.get("ladderMode", "limit")).lower()
    side_levels = levels["long"] if side == "long" else levels["short"]
    if mode == "reject":
        for label, level, weight in zip(["l1", "l2", "l3"], side_levels, weights, strict=False):
            ok = low <= level and close > level if side == "long" else high >= level and close < level
            if ok:
                touched.append((label, close, weight))
    else:
        for label, level, weight in zip(["l1", "l2", "l3"], side_levels, weights, strict=False):
            ok = low <= level if side == "long" else high >= level
            if ok:
                touched.append((label, level, weight))
    if not touched:
        return None

    basket_qty = ladder_basket_qty(side, equity, close, grid_mid, grid_dev, params, config)
    legs = [
        {"label": label, "entry_price": price, "qty": basket_qty * weight}
        for label, price, weight in touched
        if basket_qty * weight > 0
    ]
    if not legs:
        return None
    weighted = sum(leg["entry_price"] * leg["qty"] for leg in legs) / sum(leg["qty"] for leg in legs)
    return {
        "side": side,
        "type": "ladder",
        "entry_price": weighted,
        "qty": sum(leg["qty"] for leg in legs),
        "legs": legs,
        "stop": levels["long_emergency"] if side == "long" else levels["short_emergency"],
        "soft_stop": levels["long_soft"] if side == "long" else levels["short_soft"],
        "target": grid_mid,
        "signal_index": index,
    }


def tactical_signal(
    index: int,
    rows: list[dict[str, Any]],
    ind: dict[str, Any],
    params: dict[str, Any],
    allow_longs: bool,
    allow_shorts: bool,
    equity: float,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    close = float(rows[index]["close"])
    open_ = float(rows[index]["open"])
    high = float(rows[index]["high"])
    low = float(rows[index]["low"])
    don_lower = ind["don_lower"][index]
    don_upper = ind["don_upper"][index]
    atr = ind["exit_atr"][index]
    if don_lower is None or don_upper is None or atr is None:
        return None
    raw_long = allow_longs and low <= don_lower and close > open_ and close > don_lower
    raw_short = allow_shorts and high >= don_upper and close < open_ and close < don_upper
    if bool(params.get("requireBiasFilter", False)):
        raw_long = raw_long and bool(ind["final_buy_bias"][index])
        raw_short = raw_short and bool(ind["final_sell_bias"][index])
    if raw_long == raw_short:
        return None
    side = "long" if raw_long else "short"
    qty = order_qty(equity, close, config)
    stop_distance = atr * float(params.get("atrStopMult", 2.0))
    target_distance = atr * float(params.get("atrTargetMult", 3.0))
    return {
        "side": side,
        "type": "tactical",
        "entry_price": close,
        "qty": qty,
        "stop": close - stop_distance if side == "long" else close + stop_distance,
        "target": close + target_distance if side == "long" else close - target_distance,
        "signal_index": index,
    }


def open_legacy_position(
    signal: dict[str, Any],
    entry_index: int,
    entry_row: dict[str, Any],
    fee_model: dict[str, float],
    use_spread: bool,
    point_value: float,
) -> LegacyPosition:
    side = signal["side"]
    spread = float(entry_row.get("spread_close") or 0.0)
    legs_payload = signal.get("legs") or [{"label": "entry", "entry_price": signal["entry_price"], "qty": signal["qty"]}]
    legs: list[LegacyLeg] = []
    for payload in legs_payload:
        raw_entry = float(payload["entry_price"])
        qty = float(payload["qty"])
        entry_price = execution_price(raw_entry, spread, side, "entry", fee_model, use_spread)
        entry_fee = abs(entry_price * qty * point_value) * fee_model["entry_fee_pct"] / 100.0
        legs.append(
            LegacyLeg(
                label=str(payload["label"]),
                entry_price=entry_price,
                qty=qty,
                entry_fee=entry_fee,
                entry_time=as_utc(entry_row["datetime"]),
                entry_index=entry_index,
            )
        )
    qty = sum(leg.qty for leg in legs)
    entry_price = sum(leg.entry_price * leg.qty for leg in legs) / qty
    entry_fee = sum(leg.entry_fee for leg in legs)
    funding_cost = abs(entry_price * qty * point_value) * fee_model["funding_pct"] / 100.0
    return LegacyPosition(
        side=side,
        trade_type=signal["type"],
        entry_index=entry_index,
        entry_time=as_utc(entry_row["datetime"]),
        entry_price=entry_price,
        qty=qty,
        entry_fee=entry_fee,
        funding_cost=funding_cost,
        stop=signal.get("stop"),
        target=signal.get("target"),
        legs=legs,
        filled_levels={leg.label for leg in legs},
    )


def update_legacy_position(
    position: LegacyPosition,
    index: int,
    row: dict[str, Any],
    ind: dict[str, Any],
    params: dict[str, Any],
    fee_model: dict[str, float],
    use_spread: bool,
    is_final: bool,
) -> dict[str, Any] | None:
    side = position.side
    high = float(row["high"])
    low = float(row["low"])
    close = float(row["close"])
    grid_mid = ind["grid_mid"][index]
    grid_dev = ind["grid_dev"][index]
    stop_first = True

    if position.trade_type == "ladder" and grid_mid is not None and grid_dev is not None:
        maybe_add_ladder_legs(position, index, row, ind, params, fee_model, use_spread)
        levels = ladder_levels(grid_mid, grid_dev, params)
        hard_stop = levels["long_emergency"] if side == "long" else levels["short_emergency"]
        soft_stop = levels["long_soft"] if side == "long" else levels["short_soft"]
        stop_hit = low <= hard_stop if side == "long" else high >= hard_stop
        mid_exit = close >= grid_mid if side == "long" else close <= grid_mid
        soft_bad = close < soft_stop if side == "long" else close > soft_stop
        position.soft_stop_count = position.soft_stop_count + 1 if soft_bad else 0
        soft_hit = bool(params.get("ladderUseCloseConfirmedStop", True)) and position.soft_stop_count >= int(params.get("ladderStopConfirmBars", 1))
        if stop_hit and stop_first:
            return close_legacy_position(position, row, hard_stop, "ladder_emergency_stop", fee_model, use_spread)
        if soft_hit:
            return close_legacy_position(position, row, close, "ladder_soft_stop", fee_model, use_spread)
        if mid_exit:
            return close_legacy_position(position, row, close, "ladder_mid_exit", fee_model, use_spread)
        if stop_hit:
            return close_legacy_position(position, row, hard_stop, "ladder_emergency_stop", fee_model, use_spread)

    elif position.trade_type == "grid" and grid_mid is not None and grid_dev is not None:
        lower_stop = grid_mid - grid_dev * float(params.get("stopSd", 2.25))
        upper_stop = grid_mid + grid_dev * float(params.get("stopSd", 2.25))
        stop = lower_stop if side == "long" else upper_stop
        stop = apply_fixed_stop_cap(side, position.entry_price, stop, params)
        middle_mode = str(params.get("closeAtMiddleMode", "cross")).lower()
        target_hit = (
            close >= grid_mid if side == "long" and middle_mode == "cross"
            else high >= grid_mid if side == "long"
            else close <= grid_mid if middle_mode == "cross"
            else low <= grid_mid
        )
        stop_hit = low <= stop if side == "long" else high >= stop
        if stop_hit and stop_first:
            return close_legacy_position(position, row, stop, "grid_stop", fee_model, use_spread)
        if target_hit:
            raw_exit = close if middle_mode == "cross" else grid_mid
            return close_legacy_position(position, row, raw_exit, "grid_mid_exit", fee_model, use_spread)
        if stop_hit:
            return close_legacy_position(position, row, stop, "grid_stop", fee_model, use_spread)

    elif position.trade_type == "tactical":
        if position.stop is not None and (low <= position.stop if side == "long" else high >= position.stop):
            return close_legacy_position(position, row, float(position.stop), "tactical_stop", fee_model, use_spread)
        if position.target is not None and (high >= position.target if side == "long" else low <= position.target):
            return close_legacy_position(position, row, float(position.target), "tactical_target", fee_model, use_spread)

    if is_final:
        return close_legacy_position(position, row, close, "end_of_data", fee_model, use_spread)
    return None


def maybe_add_ladder_legs(
    position: LegacyPosition,
    index: int,
    row: dict[str, Any],
    ind: dict[str, Any],
    params: dict[str, Any],
    fee_model: dict[str, float],
    use_spread: bool,
) -> None:
    grid_mid = ind["grid_mid"][index]
    grid_dev = ind["grid_dev"][index]
    if grid_mid is None or grid_dev is None:
        return
    levels = ladder_levels(grid_mid, grid_dev, params)
    weights = ladder_weights(params)
    side_levels = levels["long"] if position.side == "long" else levels["short"]
    mode = str(params.get("ladderMode", "limit")).lower()
    high = float(row["high"])
    low = float(row["low"])
    close = float(row["close"])
    spread = float(row.get("spread_close") or 0.0)
    for label, level, weight in zip(["l1", "l2", "l3"], side_levels, weights, strict=False):
        if label in position.filled_levels:
            continue
        if mode == "reject":
            touched = low <= level and close > level if position.side == "long" else high >= level and close < level
            raw_entry = close
        else:
            touched = low <= level if position.side == "long" else high >= level
            raw_entry = level
        if not touched:
            continue
        target_total_qty = position.qty / max(sum(ladder_weights(params)[i] for i, name in enumerate(["l1", "l2", "l3"]) if name in position.filled_levels), 1e-9)
        qty = target_total_qty * weight
        if qty <= 0:
            continue
        entry_price = execution_price(raw_entry, spread, position.side, "entry", fee_model, use_spread)
        entry_fee = abs(entry_price * qty) * fee_model["entry_fee_pct"] / 100.0
        leg = LegacyLeg(label, entry_price, qty, entry_fee, as_utc(row["datetime"]), index)
        position.legs.append(leg)
        position.filled_levels.add(label)
        old_qty = position.qty
        position.qty += qty
        position.entry_price = ((position.entry_price * old_qty) + entry_price * qty) / position.qty
        position.entry_fee += entry_fee


def close_legacy_position(
    position: LegacyPosition,
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
    gross = (
        (exit_price - position.entry_price) * position.qty
        if position.side == "long"
        else (position.entry_price - exit_price) * position.qty
    )
    exit_fee = abs(exit_price * position.qty) * fee_model["exit_fee_pct"] / 100.0
    total_fees = position.entry_fee + exit_fee + position.funding_cost
    net_pnl = gross - total_fees
    return {
        "side": position.side,
        "type": position.trade_type,
        "entry_time": position.entry_time,
        "exit_time": as_utc(row["datetime"]),
        "entry_price": position.entry_price,
        "exit_price": exit_price,
        "gross_pnl": gross,
        "net_pnl": net_pnl,
        "fees": total_fees,
        "bars": int((as_utc(row["datetime"]) - position.entry_time).total_seconds() // 900),
        "exit_reason": reason,
    }


def mark_to_market(position: LegacyPosition, row: dict[str, Any], fee_model: dict[str, float], use_spread: bool) -> float:
    exit_price = execution_price(
        float(row["close"]),
        float(row.get("spread_close") or 0.0),
        position.side,
        "exit",
        fee_model,
        use_spread,
    )
    gross = (
        (exit_price - position.entry_price) * position.qty
        if position.side == "long"
        else (position.entry_price - exit_price) * position.qty
    )
    return gross - position.entry_fee - position.funding_cost


def order_qty(equity: float, price: float, config: dict[str, Any]) -> float:
    execution = config["execution"]
    mode = str(execution.get("position_size_mode", "percent_equity")).lower()
    point_value = float(execution.get("point_value", 1.0))
    if mode == "fixed":
        return float(execution.get("fixed_qty", 1.0))
    equity_pct = float(execution.get("equity_pct", 10.0))
    contract_value = price * point_value
    return (equity * equity_pct * 0.01) / contract_value if equity > 0 and contract_value > 0 else 0.0


def ladder_basket_qty(
    side: str,
    equity: float,
    close: float,
    grid_mid: float,
    grid_dev: float,
    params: dict[str, Any],
    config: dict[str, Any],
) -> float:
    if not bool(params.get("ladderUseBasketRiskSizing", True)):
        return order_qty(equity, close, config)
    levels = ladder_levels(grid_mid, grid_dev, params)
    weights = ladder_weights(params)
    side_levels = levels["long"] if side == "long" else levels["short"]
    weighted_entry = sum(level * weight for level, weight in zip(side_levels, weights, strict=False))
    emergency = levels["long_emergency"] if side == "long" else levels["short_emergency"]
    risk_per_unit = max(weighted_entry - emergency, 0.0) if side == "long" else max(emergency - weighted_entry, 0.0)
    risk_capital = equity * float(params.get("ladderBasketRiskPct", 0.5)) * 0.01
    risk_qty = risk_capital / risk_per_unit if risk_per_unit > 0 else 0.0
    point_value = float(config["execution"].get("point_value", 1.0))
    max_notional = equity * float(params.get("ladderMaxNotionalPct", 10.0)) * 0.01
    max_qty = max_notional / (close * point_value) if close > 0 and point_value > 0 else 0.0
    return min(risk_qty, max_qty)


def ladder_weights(params: dict[str, Any]) -> list[float]:
    raw = [
        max(float(params.get("ladderWeight1", 25.0)), 0.0),
        max(float(params.get("ladderWeight2", 35.0)), 0.0),
        max(float(params.get("ladderWeight3", 40.0)), 0.0),
    ]
    total = sum(raw)
    return [value / total for value in raw] if total > 0 else [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]


def ladder_levels(grid_mid: float, grid_dev: float, params: dict[str, Any]) -> dict[str, Any]:
    level1 = float(params.get("ladderLevel1Sd", 2.0))
    level2 = float(params.get("ladderLevel2Sd", 2.5))
    level3 = float(params.get("ladderLevel3Sd", 3.0))
    soft = float(params.get("ladderSoftStopSd", 3.5))
    emergency = float(params.get("ladderEmergencyStopSd", 3.9))
    return {
        "long": [grid_mid - grid_dev * level1, grid_mid - grid_dev * level2, grid_mid - grid_dev * level3],
        "short": [grid_mid + grid_dev * level1, grid_mid + grid_dev * level2, grid_mid + grid_dev * level3],
        "long_soft": grid_mid - grid_dev * soft,
        "short_soft": grid_mid + grid_dev * soft,
        "long_emergency": grid_mid - grid_dev * emergency,
        "short_emergency": grid_mid + grid_dev * emergency,
    }


def apply_fixed_stop_cap(side: str, entry_price: float, stop: float, params: dict[str, Any]) -> float:
    cap = float(params.get("fixedGoldStopCapPoints", 0.0) or 0.0)
    if cap <= 0:
        return stop
    if side == "long":
        return max(stop, entry_price - cap)
    return min(stop, entry_price + cap)


def build_legacy_indicators(rows: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
    close = [float(row["close"]) for row in rows]
    high = [float(row["high"]) for row in rows]
    low = [float(row["low"]) for row in rows]
    open_ = [float(row["open"]) for row in rows]
    don_len = int(params.get("donLen", 20))
    grid_len = int(params.get("gridSdLen", 50))
    sd_len = int(params.get("sdLen", 20))
    ma_len = int(params.get("maLen", 50))
    exit_atr_len = int(params.get("exitAtrLen", 14))

    don_upper = rolling_max(high, don_len)
    don_lower = rolling_min(low, don_len)
    don_mid = midpoint(don_upper, don_lower)
    sd_basis = sma_list(close, sd_len)
    ema = ema_list(close, ma_len)
    grid_source = str(params.get("gridSource", "don")).lower()
    if grid_source == "sd":
        grid_mid = sd_basis
    elif grid_source == "ema":
        grid_mid = ema
    else:
        grid_mid = don_mid
    grid_dev = rolling_stdev(close, grid_len)
    exit_atr = atr_list(high, low, close, exit_atr_len)
    plus_di, minus_di, adx = dmi_list(high, low, close, int(params.get("regimeDiLen", 14)), int(params.get("regimeAdxSmooth", 14)))
    rsi = rsi_list(close, int(params.get("rsiLen", 14)))
    _, _, macd_hist = macd_list(
        close,
        int(params.get("macdFastLen", 12)),
        int(params.get("macdSlowLen", 26)),
        int(params.get("macdSignalLen", 9)),
    )
    sweep_window = max(int(params.get("sweepLookback", 20)) - 1, 1)
    prior_high = shift(rolling_max(high, sweep_window), 1)
    prior_low = shift(rolling_min(low, sweep_window), 1)
    high_trap = [ph is not None and h > ph and c < ph for ph, h, c in zip(prior_high, high, close)]
    low_trap = [pl is not None and l < pl and c > pl for pl, l, c in zip(prior_low, low, close)]
    final_buy_bias = []
    final_sell_bias = []
    for i in range(len(rows)):
        dm = don_mid[i]
        e = ema[i]
        score = 0
        score += sign(close[i] - e) if e is not None else 0
        score += sign(close[i] - dm) if dm is not None else 0
        score += sign((rsi[i] or 50.0) - 50.0) if rsi[i] is not None else 0
        score += sign(macd_hist[i]) if macd_hist[i] is not None else 0
        score += 1 if low_trap[i] else -1 if high_trap[i] else 0
        final_buy_bias.append(score >= 0)
        final_sell_bias.append(score < 0)

    min_bars_needed = max(
        ma_len,
        sd_len,
        don_len,
        int(params.get("macdSlowLen", 26)) + int(params.get("macdSignalLen", 9)),
        int(params.get("regimeDiLen", 14)) + int(params.get("regimeAdxSmooth", 14)),
        int(params.get("sweepLookback", 20)),
        grid_len,
        exit_atr_len,
    ) + 2
    return {
        "don_upper": don_upper,
        "don_lower": don_lower,
        "don_mid": don_mid,
        "sd_basis": sd_basis,
        "ema": ema,
        "grid_mid": grid_mid,
        "grid_dev": grid_dev,
        "exit_atr": exit_atr,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "adx": adx,
        "high_trap": high_trap,
        "low_trap": low_trap,
        "final_buy_bias": final_buy_bias,
        "final_sell_bias": final_sell_bias,
        "min_bars_needed": min_bars_needed,
    }


def summarize_rows(rows: list[dict[str, Any]], fee_name: str, timeframe: str) -> dict[str, Any]:
    positive = [row for row in rows if row["validation_net_pnl"] > 0]
    ge500 = [row for row in rows if row["validation_trades_per_year"] >= 500]
    ge1000 = [row for row in rows if row["validation_trades_per_year"] >= 1000]
    accepted = [row for row in rows if row["accepted"]]
    best_score = rows[0] if rows else {}
    best_pnl = max(rows, key=lambda row: row["validation_net_pnl"], default={})
    best_ge500 = max(ge500, key=lambda row: row["validation_net_pnl"], default={})
    best_ge1000 = max(ge1000, key=lambda row: row["validation_net_pnl"], default={})
    return {
        "fee_profile": fee_name,
        "timeframe": timeframe,
        "evaluated": len(rows),
        "accepted": len(accepted),
        "positive_validation": len(positive),
        "ge500": len(ge500),
        "ge500_positive_validation": sum(1 for row in ge500 if row["validation_net_pnl"] > 0),
        "ge1000": len(ge1000),
        "ge1000_positive_validation": sum(1 for row in ge1000 if row["validation_net_pnl"] > 0),
        "best_score_config": best_score.get("config_id"),
        "best_score_engineMode": best_score.get("engineMode"),
        "best_score_sideMode": best_score.get("sideMode"),
        "best_score_validation_net_pnl": best_score.get("validation_net_pnl"),
        "best_score_validation_trades_per_year": best_score.get("validation_trades_per_year"),
        "best_score_validation_profit_factor": best_score.get("validation_profit_factor"),
        "best_pnl_config": best_pnl.get("config_id"),
        "best_pnl_engineMode": best_pnl.get("engineMode"),
        "best_pnl_sideMode": best_pnl.get("sideMode"),
        "best_pnl_validation_net_pnl": best_pnl.get("validation_net_pnl"),
        "best_pnl_validation_trades_per_year": best_pnl.get("validation_trades_per_year"),
        "best_pnl_validation_profit_factor": best_pnl.get("validation_profit_factor"),
        "best_ge500_config": best_ge500.get("config_id"),
        "best_ge500_engineMode": best_ge500.get("engineMode"),
        "best_ge500_sideMode": best_ge500.get("sideMode"),
        "best_ge500_validation_net_pnl": best_ge500.get("validation_net_pnl"),
        "best_ge500_validation_trades_per_year": best_ge500.get("validation_trades_per_year"),
        "best_ge500_validation_profit_factor": best_ge500.get("validation_profit_factor"),
        "best_ge1000_config": best_ge1000.get("config_id"),
        "best_ge1000_engineMode": best_ge1000.get("engineMode"),
        "best_ge1000_sideMode": best_ge1000.get("sideMode"),
        "best_ge1000_validation_net_pnl": best_ge1000.get("validation_net_pnl"),
        "best_ge1000_validation_trades_per_year": best_ge1000.get("validation_trades_per_year"),
        "best_ge1000_validation_profit_factor": best_ge1000.get("validation_profit_factor"),
    }


def build_presets(top: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    ordered_params = configured_parameter_order(config)
    return {
        "source": "Tradingview.pine legacy Python approximation",
        "source_pine": config.get("data", {}).get("source_pine", "../Tradingview.pine"),
        "created_at": datetime.now(timezone.utc),
        "notes": [
            "This runner approximates Tradingview.pine; it does not execute Pine Script directly.",
            "Re-test candidate inputs in TradingView before treating them as research findings.",
            "No live, paper, broker, or execution integration is included.",
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
    ordered_params = configured_parameter_order(config)
    lines = [
        "# Tradingview.pine Legacy Input Presets",
        "",
        "These presets come from a Python approximation of `Tradingview.pine`. Re-test in TradingView before using them for any research conclusion.",
        "",
        "Mapped Pine sections:",
        "",
        "- Dynamic Grid Range Engine: `enableGridEngine`, `gridSource`, `entrySd`, `stopSd`, `noTradeSd`, `minBarsBetweenTrades`",
        "- 3-Level SD Ladder Grid: `enableLadderGrid`, `ladderMode`, ladder SD levels, basket risk, middle/stop exits",
        "- Tactical mode: lower/upper Donchian touch with ATR stop/target",
        "",
    ]
    if not any(row["accepted"] for row in top):
        lines.extend(["> No preset in this run passed all validation filters. Treat the blocks below as diagnostics only.", ""])
    for index, row in enumerate(top[:5], start=1):
        lines.append(f"## Preset {index}")
        lines.append("")
        lines.append(f"- Accepted by validation filters: `{row['accepted']}`")
        lines.append(f"- Timeframe: `{row.get('timeframe', 'n/a')}`")
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


def parse_csv_arg(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize/test the legacy Tradingview.pine strategy approximation.")
    parser.add_argument("--config", default="configs/tradingview_legacy_optimizer_config.yaml")
    parser.add_argument("--iterations", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--fee-profiles", default=None, help="Optional comma-separated fee diagnostic set.")
    parser.add_argument("--timeframes", default=None, help="Comma-separated subset, e.g. m15,m30,h1,h2")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.fee_profiles:
        payload = run_diagnostics(
            config_path=resolve_path(args.config),
            iterations=args.iterations or 30,
            workers=args.workers,
            fee_profiles=parse_csv_arg(args.fee_profiles, list(FEE_PROFILES.keys())),
            timeframes=set(parse_csv_arg(args.timeframes, [])) if args.timeframes else None,
        )
        best = payload["best"]
        print(
            "Tradingview.pine legacy diagnostics complete: "
            f"evaluated={payload['total_evaluated']}, accepted={payload['accepted']}, "
            f"positive_validation={payload['positive_validation']}, "
            f"ge500_positive_validation={payload['ge500_positive_validation']}"
        )
        if best:
            print(
                "best: "
                f"fee={best.get('fee_profile')}, timeframe={best.get('timeframe')}, "
                f"engine={best.get('engineMode')}, side={best.get('sideMode')}, "
                f"validation_pnl={best['validation_net_pnl']:.2f}, "
                f"trades_year={best['validation_trades_per_year']:.2f}, "
                f"pf={best['validation_profit_factor']}"
            )
        print(f"reports: {payload['reports_dir']}")
        return

    payload = optimize(
        config_path=resolve_path(args.config),
        iterations_override=args.iterations,
        max_workers_override=args.workers,
    )
    best = payload["best"]
    print(
        "Tradingview.pine legacy optimization complete: "
        f"evaluated={payload['evaluated']}, accepted={payload['accepted']}, "
        f"positive_validation={payload['positive_validation']}, "
        f"ge500_positive_validation={payload['ge500_positive_validation']}"
    )
    if best:
        print(
            "best: "
            f"timeframe={best.get('timeframe')}, engine={best.get('engineMode')}, side={best.get('sideMode')}, "
            f"validation_pnl={best['validation_net_pnl']:.2f}, "
            f"trades_year={best['validation_trades_per_year']:.2f}, "
            f"pf={best['validation_profit_factor']}"
        )
    print(f"reports: {payload['reports_dir']}")


if __name__ == "__main__":
    main()
