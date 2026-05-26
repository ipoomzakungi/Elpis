from __future__ import annotations

import argparse
import csv
import itertools
import json
import sys
from pathlib import Path
from typing import Any

import polars as pl

from backtest_engine import run_backtest_frame
from pipeline_utils import (
    DEFAULT_PROCESSED_PARQUET,
    DEFAULT_REPORTS_DIR,
    parse_timestamp_value,
    read_yaml,
    resolve_path,
    write_yaml,
)


class DataQualityGateError(RuntimeError):
    def __init__(self, failures: list[str]):
        self.failures = failures
        super().__init__("Data quality gate failed:\n- " + "\n- ".join(failures))


def optimize(config_path: Path, max_configs_override: int | None = None) -> dict[str, Any]:
    config = read_yaml(config_path)
    data_config = config.get("data", {})
    processed_path = resolve_path(data_config.get("processed_path"), DEFAULT_PROCESSED_PARQUET)
    reports_dir = resolve_path(data_config.get("reports_dir"), DEFAULT_REPORTS_DIR)
    reports_dir.mkdir(parents=True, exist_ok=True)
    quality_gate = run_data_quality_gate(
        reports_dir=reports_dir,
        gate_config=config.get("data_quality_gate", {}),
        point_size=float(config.get("backtest", {}).get("point_size", 0.01)),
    )
    df = pl.read_parquet(processed_path).sort("datetime")

    splits = _split_data(df, config.get("splits", {}))
    parameter_grid = list(_parameter_grid(config["parameters"]))
    total_possible = len(parameter_grid)
    max_configs = max_configs_override
    if max_configs is None:
        max_configs = config.get("optimization", {}).get("max_configs")
    selected_grid = _select_configs(parameter_grid, max_configs)

    base_params = {**config.get("backtest", {}), **config.get("strategy_defaults", {})}
    rows: list[dict[str, Any]] = []
    for index, params in enumerate(selected_grid, start=1):
        merged_params = {**base_params, **params}
        train = run_backtest_frame(splits["train"], merged_params, export=False, run_name="train")
        validation = run_backtest_frame(
            splits["validation"], merged_params, export=False, run_name="validation"
        )
        test = run_backtest_frame(splits["test"], merged_params, export=False, run_name="test")
        rows.append(
            _result_row(
                config_id=index,
                params=params,
                train=train["summary"],
                validation=validation["summary"],
                test=test["summary"],
                scoring=config.get("scoring", {}),
                robustness=config.get("robustness", {}),
            )
        )

    ranked = sorted(rows, key=lambda row: row["score"], reverse=True)
    _write_rows(reports_dir / "optimization_results.csv", rows)
    _write_rows(reports_dir / "top_20_configs.csv", ranked[:20])
    best = ranked[0] if ranked else None
    if best is None:
        raise ValueError("No optimization configurations were evaluated")
    write_yaml(
        reports_dir / "best_config.yaml",
        {
            "selected_by": "validation_score_with_robustness_penalties",
            "source_config": config_path,
            "total_possible_configs": total_possible,
            "evaluated_configs": len(selected_grid),
            "parameters": {key: best[key] for key in config["parameters"]},
            "train": _summary_slice(best, "train"),
            "validation": _summary_slice(best, "validation"),
            "test": _summary_slice(best, "test"),
            "score": best["score"],
            "robust_pass": best["robust_pass"],
            "limitations": [
                "Ranked by validation score, not training score.",
                "Robustness checks are historical diagnostics only.",
                "This output is not a live-trading, paper-trading, or profitability claim.",
            ],
        },
    )
    return {
        "total_possible_configs": total_possible,
        "evaluated_configs": len(selected_grid),
        "best": best,
        "reports_dir": reports_dir,
        "data_quality_gate": quality_gate,
    }


def run_data_quality_gate(
    reports_dir: Path,
    gate_config: dict[str, Any],
    point_size: float,
) -> dict[str, Any]:
    if not gate_config.get("enabled", True):
        return {"enabled": False, "passed": True, "failures": []}

    required_reports = {
        "missing_minutes": reports_dir / "missing_minutes.json",
        "duplicate_rows": reports_dir / "duplicate_rows.json",
        "spread_summary": reports_dir / "spread_summary.json",
        "date_range_summary": reports_dir / "date_range_summary.json",
    }
    failures: list[str] = []
    reports: dict[str, dict[str, Any]] = {}
    for name, path in required_reports.items():
        if not path.exists():
            failures.append(
                f"Required validation report is missing: {path}. "
                "Run python src/validate_xauusd.py before optimization."
            )
            continue
        reports[name] = _read_json_report(path)

    if failures:
        raise DataQualityGateError(failures)

    missing_minutes = int(
        reports["missing_minutes"].get(
            "missing_candle_count",
            reports["date_range_summary"].get("missing_candle_count", 0),
        )
        or 0
    )
    duplicate_timestamps = int(
        reports["duplicate_rows"].get(
            "processed_duplicate_timestamp_count",
            reports["date_range_summary"].get("duplicate_timestamp_count", 0),
        )
        or 0
    )
    suspicious_candles = int(reports["date_range_summary"].get("suspicious_candle_count", 0) or 0)
    max_spread = float(reports["spread_summary"].get("max_spread") or 0.0)
    average_spread = float(reports["spread_summary"].get("average_spread") or 0.0)

    thresholds = {
        "missing_minutes_max": int(gate_config.get("missing_minutes_max", 0)),
        "duplicate_timestamps_max": int(gate_config.get("duplicate_timestamps_max", 0)),
        "suspicious_candles_max": int(gate_config.get("suspicious_candles_max", 0)),
        "max_spread_points": float(gate_config.get("max_spread_points", 100.0)),
        "average_spread_points_max": float(gate_config.get("average_spread_points_max", 50.0)),
    }
    max_spread_allowed = thresholds["max_spread_points"] * point_size
    average_spread_allowed = thresholds["average_spread_points_max"] * point_size

    if missing_minutes > thresholds["missing_minutes_max"]:
        failures.append(
            f"Missing minute count {missing_minutes} exceeds threshold "
            f"{thresholds['missing_minutes_max']}."
        )
    if duplicate_timestamps > thresholds["duplicate_timestamps_max"]:
        failures.append(
            f"Duplicate timestamp count {duplicate_timestamps} exceeds threshold "
            f"{thresholds['duplicate_timestamps_max']}."
        )
    if suspicious_candles > thresholds["suspicious_candles_max"]:
        failures.append(
            f"Suspicious candle count {suspicious_candles} exceeds threshold "
            f"{thresholds['suspicious_candles_max']}."
        )
    if max_spread > max_spread_allowed:
        failures.append(
            f"Max spread {max_spread:.6f} exceeds threshold "
            f"{max_spread_allowed:.6f} ({thresholds['max_spread_points']} points)."
        )
    if average_spread > average_spread_allowed:
        failures.append(
            f"Average spread {average_spread:.6f} exceeds threshold "
            f"{average_spread_allowed:.6f} ({thresholds['average_spread_points_max']} points)."
        )

    result = {
        "enabled": True,
        "passed": not failures,
        "reports_dir": reports_dir,
        "thresholds": thresholds,
        "observed": {
            "missing_minutes": missing_minutes,
            "duplicate_timestamps": duplicate_timestamps,
            "suspicious_candles": suspicious_candles,
            "max_spread": max_spread,
            "average_spread": average_spread,
            "max_spread_points": max_spread / point_size if point_size else None,
            "average_spread_points": average_spread / point_size if point_size else None,
        },
        "failures": failures,
    }
    if failures:
        raise DataQualityGateError(failures)
    return result


def _read_json_report(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Validation report must be a JSON object: {path}")
    return payload


def _split_data(df: pl.DataFrame, split_config: dict[str, Any]) -> dict[str, pl.DataFrame]:
    train_start = parse_timestamp_value(split_config.get("train_start", "2024-01-01T00:00:00Z"))
    train_end = parse_timestamp_value(split_config.get("train_end", "2025-01-01T00:00:00Z"))
    validation_start = parse_timestamp_value(
        split_config.get("validation_start", "2025-01-01T00:00:00Z")
    )
    validation_end = parse_timestamp_value(
        split_config.get("validation_end", "2026-01-01T00:00:00Z")
    )
    test_start = parse_timestamp_value(split_config.get("test_start", "2026-01-01T00:00:00Z"))

    splits = {
        "train": df.filter((pl.col("datetime") >= train_start) & (pl.col("datetime") < train_end)),
        "validation": df.filter(
            (pl.col("datetime") >= validation_start) & (pl.col("datetime") < validation_end)
        ),
        "test": df.filter(pl.col("datetime") >= test_start),
    }
    empty = [name for name, frame in splits.items() if frame.is_empty()]
    if empty:
        raise ValueError(f"Cannot optimize with empty data splits: {empty}")
    return splits


def _parameter_grid(parameters: dict[str, list[Any]]) -> list[dict[str, Any]]:
    keys = list(parameters.keys())
    for values in itertools.product(*(parameters[key] for key in keys)):
        yield dict(zip(keys, values))


def _select_configs(
    parameter_grid: list[dict[str, Any]],
    max_configs: int | None,
) -> list[dict[str, Any]]:
    if max_configs is None or max_configs <= 0 or max_configs >= len(parameter_grid):
        return parameter_grid
    if max_configs == 1:
        return [parameter_grid[0]]
    step = (len(parameter_grid) - 1) / (max_configs - 1)
    indexes = sorted({round(i * step) for i in range(max_configs)})
    return [parameter_grid[index] for index in indexes]


def _result_row(
    config_id: int,
    params: dict[str, Any],
    train: dict[str, Any],
    validation: dict[str, Any],
    test: dict[str, Any],
    scoring: dict[str, Any],
    robustness: dict[str, Any],
) -> dict[str, Any]:
    min_trades = int(robustness.get("min_trades_per_split", 20))
    min_profit_factor = float(robustness.get("min_profit_factor", 1.05))
    max_drawdown_pct = float(robustness.get("max_drawdown_pct", 25.0))
    test_collapse_tolerance = float(robustness.get("test_collapse_tolerance", 0.5))

    train_pass = _passes_split(train, min_trades, min_profit_factor, max_drawdown_pct)
    validation_pass = _passes_split(validation, min_trades, min_profit_factor, max_drawdown_pct)
    test_not_collapsed = test["net_profit"] >= -abs(validation["net_profit"]) * test_collapse_tolerance

    weights = {
        "validation_return": 1.0,
        "profit_factor": 2.0,
        "drawdown": 0.7,
        "trade_shortfall": 0.5,
        "stability": 0.4,
        "robustness_failure": 25.0,
        **scoring,
    }
    validation_return = validation["total_return_pct"]
    validation_pf = min(validation["profit_factor"] or 0.0, 3.0)
    validation_dd = abs(validation["max_drawdown_pct"])
    trade_shortfall = max(0, min_trades - validation["number_of_trades"])
    stability_gap = abs(train["total_return_pct"] - validation["total_return_pct"])
    robust_pass = train_pass and validation_pass and test_not_collapsed

    score = (
        validation_return * float(weights["validation_return"])
        + validation_pf * float(weights["profit_factor"])
        - validation_dd * float(weights["drawdown"])
        - trade_shortfall * float(weights["trade_shortfall"])
        - stability_gap * float(weights["stability"])
    )
    if not robust_pass:
        score -= float(weights["robustness_failure"])

    return {
        "config_id": config_id,
        **params,
        **_prefixed_summary("train", train),
        **_prefixed_summary("validation", validation),
        **_prefixed_summary("test", test),
        "train_pass": train_pass,
        "validation_pass": validation_pass,
        "test_not_collapsed": test_not_collapsed,
        "robust_pass": robust_pass,
        "score": score,
    }


def _passes_split(
    summary: dict[str, Any],
    min_trades: int,
    min_profit_factor: float,
    max_drawdown_pct: float,
) -> bool:
    profit_factor = summary["profit_factor"] or 0.0
    return (
        summary["number_of_trades"] >= min_trades
        and summary["net_profit"] > 0
        and profit_factor >= min_profit_factor
        and abs(summary["max_drawdown_pct"]) <= max_drawdown_pct
    )


def _prefixed_summary(prefix: str, summary: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "net_profit",
        "total_return_pct",
        "max_drawdown_pct",
        "profit_factor",
        "win_rate_pct",
        "number_of_trades",
        "average_trade",
        "average_holding_minutes",
        "sharpe_ratio",
    ]
    return {f"{prefix}_{key}": summary.get(key) for key in keys}


def _summary_slice(row: dict[str, Any], prefix: str) -> dict[str, Any]:
    return {
        key.removeprefix(f"{prefix}_"): value
        for key, value in row.items()
        if key.startswith(f"{prefix}_")
    }


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    columns = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize XAUUSD strategy parameters.")
    parser.add_argument("--config", default="configs/optimization_config.yaml")
    parser.add_argument("--max-configs", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        result = optimize(resolve_path(args.config), max_configs_override=args.max_configs)
    except DataQualityGateError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    best = result["best"]
    print(
        "optimization complete: "
        f"evaluated={result['evaluated_configs']}/{result['total_possible_configs']}, "
        f"best_config_id={best['config_id']}, "
        f"validation_net_profit={best['validation_net_profit']:.2f}, "
        f"score={best['score']:.2f}"
    )


if __name__ == "__main__":
    main()
