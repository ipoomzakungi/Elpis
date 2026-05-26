from __future__ import annotations

import argparse
import copy
import random
from pathlib import Path
from typing import Any

from pipeline_utils import read_yaml, resolve_path, write_json
from tradingview_optimizer import (
    build_presets,
    data_specs,
    load_frame,
    resolve_max_workers,
    run_search,
    split_rows,
    write_csv,
    write_pine_markdown,
)


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


SLICES: dict[str, dict[str, Any]] = {
    "auto_all": {"tradeMode": "auto", "allowLongs": True, "allowShorts": True},
    "mr_only": {"tradeMode": "sd_only", "allowLongs": True, "allowShorts": True},
    "breakout_only": {"tradeMode": "don_only", "allowLongs": True, "allowShorts": True},
    "long_only": {"tradeMode": "auto", "allowLongs": True, "allowShorts": False},
    "short_only": {"tradeMode": "auto", "allowLongs": False, "allowShorts": True},
}


def run_diagnostics(
    config_path: Path,
    iterations: int,
    workers: int | None,
    fee_profiles: list[str],
    slices: list[str],
    timeframes: set[str] | None,
) -> dict[str, Any]:
    base_config = read_yaml(config_path)
    reports_root = resolve_path("data/reports/tradingview_diagnostics")
    reports_root.mkdir(parents=True, exist_ok=True)
    max_workers = resolve_max_workers(workers, base_config)
    top_n = int(base_config.get("search", {}).get("top_n", 20))
    seed = int(base_config.get("search", {}).get("seed", 42))
    split_cache = load_split_cache(base_config, timeframes)

    all_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    timeframe_rows: list[dict[str, Any]] = []

    for fee_index, fee_name in enumerate(fee_profiles):
        if fee_name not in FEE_PROFILES:
            raise ValueError(f"Unknown fee profile: {fee_name}")
        for slice_index, slice_name in enumerate(slices):
            if slice_name not in SLICES:
                raise ValueError(f"Unknown slice: {slice_name}")

            case_name = f"{fee_name}__{slice_name}"
            case_config = make_case_config(base_config, fee_name, slice_name)
            rng = random.Random(seed + fee_index * 10_000 + slice_index * 1_000)
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
                    row["diagnostic_case"] = case_name
                    row["fee_profile"] = fee_name
                    row["strategy_slice"] = slice_name
                ranked_tf = sorted(candidates, key=lambda item: item["score"], reverse=True)
                timeframe_rows.append(summarize_rows(ranked_tf, case_name, fee_name, slice_name, timeframe))
                case_rows.extend(candidates)

            ranked_case = sorted(case_rows, key=lambda item: item["score"], reverse=True)
            case_dir = reports_root / "cases" / case_name
            write_csv(case_dir / "all_results.csv", ranked_case)
            write_csv(case_dir / "top_results.csv", ranked_case[:top_n])
            write_json(case_dir / "best_presets.json", build_presets(ranked_case[:top_n], case_config))
            write_pine_markdown(case_dir / "pine_input_preset.md", ranked_case[:top_n], case_config)
            summary_rows.append(summarize_rows(ranked_case, case_name, fee_name, slice_name, "all"))
            all_rows.extend(case_rows)

    ranked_all = sorted(all_rows, key=lambda item: item["score"], reverse=True)
    write_csv(reports_root / "all_results.csv", ranked_all)
    write_csv(reports_root / "top_results.csv", ranked_all[:top_n])
    write_csv(reports_root / "summary.csv", summary_rows)
    write_csv(reports_root / "timeframe_summary.csv", timeframe_rows)
    payload = {
        "reports_dir": reports_root,
        "iterations_per_case_timeframe": iterations,
        "workers": max_workers,
        "fee_profiles": fee_profiles,
        "slices": slices,
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
        cache[timeframe] = {
            "data_path": data_path,
            "splits": split_rows(rows, config["walk_forward"]),
        }
    if not cache:
        raise ValueError("No matching timeframes selected")
    return cache


def make_case_config(base_config: dict[str, Any], fee_name: str, slice_name: str) -> dict[str, Any]:
    config = copy.deepcopy(base_config)
    profile = FEE_PROFILES[fee_name]
    config["fees"].update(profile["fees"])
    config["execution"].update(profile["execution"])
    config["robustness"] = {"enabled": False}
    fixed = dict(config.get("fixed") or {})
    fixed.update(SLICES[slice_name])
    config["fixed"] = fixed
    for fixed_key in SLICES[slice_name]:
        config["parameters"].pop(fixed_key, None)
    return config


def summarize_rows(
    rows: list[dict[str, Any]],
    case_name: str,
    fee_name: str,
    slice_name: str,
    timeframe: str,
) -> dict[str, Any]:
    positive = [row for row in rows if row["validation_net_pnl"] > 0]
    ge500 = [row for row in rows if row["validation_trades_per_year"] >= 500]
    ge1000 = [row for row in rows if row["validation_trades_per_year"] >= 1000]
    accepted = [row for row in rows if row["accepted"]]
    best_score = rows[0] if rows else {}
    best_pnl = max(rows, key=lambda row: row["validation_net_pnl"], default={})
    best_ge500 = max(ge500, key=lambda row: row["validation_net_pnl"], default={})
    best_ge1000 = max(ge1000, key=lambda row: row["validation_net_pnl"], default={})
    return {
        "diagnostic_case": case_name,
        "fee_profile": fee_name,
        "strategy_slice": slice_name,
        "timeframe": timeframe,
        "evaluated": len(rows),
        "accepted": len(accepted),
        "positive_validation": len(positive),
        "ge500": len(ge500),
        "ge500_positive_validation": sum(1 for row in ge500 if row["validation_net_pnl"] > 0),
        "ge1000": len(ge1000),
        "ge1000_positive_validation": sum(1 for row in ge1000 if row["validation_net_pnl"] > 0),
        "best_score_config": best_score.get("config_id"),
        "best_score_validation_net_pnl": best_score.get("validation_net_pnl"),
        "best_score_validation_trades_per_year": best_score.get("validation_trades_per_year"),
        "best_score_validation_profit_factor": best_score.get("validation_profit_factor"),
        "best_pnl_config": best_pnl.get("config_id"),
        "best_pnl_validation_net_pnl": best_pnl.get("validation_net_pnl"),
        "best_pnl_validation_trades_per_year": best_pnl.get("validation_trades_per_year"),
        "best_pnl_validation_profit_factor": best_pnl.get("validation_profit_factor"),
        "best_ge500_config": best_ge500.get("config_id"),
        "best_ge500_validation_net_pnl": best_ge500.get("validation_net_pnl"),
        "best_ge500_validation_trades_per_year": best_ge500.get("validation_trades_per_year"),
        "best_ge500_validation_profit_factor": best_ge500.get("validation_profit_factor"),
        "best_ge1000_config": best_ge1000.get("config_id"),
        "best_ge1000_validation_net_pnl": best_ge1000.get("validation_net_pnl"),
        "best_ge1000_validation_trades_per_year": best_ge1000.get("validation_trades_per_year"),
        "best_ge1000_validation_profit_factor": best_ge1000.get("validation_profit_factor"),
    }


def parse_csv_arg(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TradingView optimizer fee and engine diagnostics.")
    parser.add_argument("--config", default="configs/tradingview_optimizer_config.yaml")
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--fee-profiles", default=",".join(FEE_PROFILES.keys()))
    parser.add_argument("--slices", default=",".join(SLICES.keys()))
    parser.add_argument("--timeframes", default=None, help="Comma-separated subset, e.g. m15,m30,h1,h2")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run_diagnostics(
        config_path=resolve_path(args.config),
        iterations=args.iterations,
        workers=args.workers,
        fee_profiles=parse_csv_arg(args.fee_profiles, list(FEE_PROFILES.keys())),
        slices=parse_csv_arg(args.slices, list(SLICES.keys())),
        timeframes=set(parse_csv_arg(args.timeframes, [])) if args.timeframes else None,
    )
    best = payload["best"]
    print(
        "TradingView diagnostics complete: "
        f"evaluated={payload['total_evaluated']}, accepted={payload['accepted']}, "
        f"positive_validation={payload['positive_validation']}, "
        f"ge500_positive_validation={payload['ge500_positive_validation']}"
    )
    if best:
        print(
            "best: "
            f"case={best['diagnostic_case']}, timeframe={best['timeframe']}, "
            f"validation_pnl={best['validation_net_pnl']:.2f}, "
            f"trades_year={best['validation_trades_per_year']:.2f}, "
            f"pf={best['validation_profit_factor']:.4f}"
        )
    print(f"reports: {payload['reports_dir']}")


if __name__ == "__main__":
    main()
