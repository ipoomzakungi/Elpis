from __future__ import annotations

import argparse
import csv
import itertools
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from pipeline_utils import parse_timestamp_value, read_yaml, resolve_path, to_jsonable, write_json, write_yaml


@dataclass
class Position:
    side: str
    entry_index: int
    entry_time: datetime
    entry_price: float
    qty: float
    stop: float
    target: float


def load_frame(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pl.read_parquet(path) if path.suffix.lower() == ".parquet" else pl.read_csv(path)
    aliases = {column.lower(): column for column in frame.columns}
    required = {"datetime", "open", "high", "low", "close"}
    if "timestamp" in aliases and "datetime" not in aliases:
        frame = frame.rename({aliases["timestamp"]: "datetime"})
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"SMC input is missing required columns: {missing}")
    if "spread_close" not in frame.columns:
        frame = frame.with_columns(pl.lit(0.0).alias("spread_close"))
    if not isinstance(frame.schema["datetime"], pl.Datetime):
        frame = frame.with_columns(
            pl.col("datetime")
            .map_elements(parse_timestamp_value, return_dtype=pl.Datetime("us", "UTC"))
            .alias("datetime")
        )
    return (
        frame.select(["datetime", "open", "high", "low", "close", "spread_close"])
        .sort("datetime")
        .to_dicts()
    )


def split_rows(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    train_start = as_utc(parse_timestamp_value(config["train_start"]))
    train_end = as_utc(parse_timestamp_value(config["train_end"]))
    validation_start = as_utc(parse_timestamp_value(config["validation_start"]))
    validation_end = as_utc(parse_timestamp_value(config["validation_end"]))
    test_start = as_utc(parse_timestamp_value(config["test_start"]))
    splits = {
        "train": [row for row in rows if train_start <= as_utc(row["datetime"]) < train_end],
        "validation": [
            row for row in rows if validation_start <= as_utc(row["datetime"]) < validation_end
        ],
        "test": [row for row in rows if as_utc(row["datetime"]) >= test_start],
    }
    empty = [name for name, split in splits.items() if not split]
    if empty:
        raise ValueError(f"Empty SMC walk-forward splits: {empty}")
    return splits


def run_backtest(
    rows: list[dict[str, Any]],
    params: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    pivot_len = int(params["pivot_len_swing"])
    rr_ratio = float(params["rr_ratio"])
    initial_cash = float(execution.get("initial_cash", 10000.0))
    risk_pct = float(execution.get("risk_per_trade_pct", 0.5))
    point_value = float(execution.get("point_value", 1.0))
    slippage = float(execution.get("slippage_points", 0.0)) * float(execution.get("point_size", 0.01))
    use_spread = bool(execution.get("use_spread", True))
    allow_longs = bool(execution.get("allow_longs", True))
    allow_shorts = bool(execution.get("allow_shorts", True))

    highs = [float(row["high"]) for row in rows]
    lows = [float(row["low"]) for row in rows]
    closes = [float(row["close"]) for row in rows]
    last_swing_high: float | None = None
    last_swing_low: float | None = None
    trend = 0
    equity = initial_cash
    peak_equity = initial_cash
    max_drawdown = 0.0
    position: Position | None = None
    trades: list[dict[str, Any]] = []

    for index in range(len(rows) - 1):
        if position is not None and index > position.entry_index:
            exit_payload = maybe_exit_position(position, rows[index], slippage)
            if exit_payload is not None:
                pnl = exit_payload["pnl"] * point_value
                equity += pnl
                peak_equity = max(peak_equity, equity)
                drawdown = (equity - peak_equity) / peak_equity if peak_equity else 0.0
                max_drawdown = min(max_drawdown, drawdown)
                trades.append(
                    {
                        **exit_payload,
                        "entry_time": position.entry_time,
                        "exit_time": rows[index]["datetime"],
                        "side": position.side,
                        "net_pnl": pnl,
                    }
                )
                position = None

        pivot_index = index - pivot_len
        if pivot_index >= pivot_len and index >= pivot_index + pivot_len:
            if is_pivot_high(highs, pivot_index, pivot_len):
                last_swing_high = highs[pivot_index]
            if is_pivot_low(lows, pivot_index, pivot_len):
                last_swing_low = lows[pivot_index]

        bos_up = last_swing_high is not None and closes[index] > last_swing_high and trend <= 0
        bos_down = last_swing_low is not None and closes[index] < last_swing_low and trend >= 0
        if bos_up:
            trend = 1
        if bos_down:
            trend = -1

        if position is None and (bos_up or bos_down):
            next_bar = rows[index + 1]
            spread = float(next_bar.get("spread_close") or 0.0) if use_spread else 0.0
            if bos_up and allow_longs and last_swing_low is not None:
                entry = float(next_bar["open"]) + spread / 2.0 + slippage
                stop = float(last_swing_low)
                risk = entry - stop
                if risk > 0:
                    qty = (equity * risk_pct / 100.0) / (risk * point_value)
                    position = Position(
                        side="long",
                        entry_index=index + 1,
                        entry_time=as_utc(next_bar["datetime"]),
                        entry_price=entry,
                        qty=qty,
                        stop=stop,
                        target=entry + risk * rr_ratio,
                    )
            elif bos_down and allow_shorts and last_swing_high is not None:
                entry = float(next_bar["open"]) - spread / 2.0 - slippage
                stop = float(last_swing_high)
                risk = stop - entry
                if risk > 0:
                    qty = (equity * risk_pct / 100.0) / (risk * point_value)
                    position = Position(
                        side="short",
                        entry_index=index + 1,
                        entry_time=as_utc(next_bar["datetime"]),
                        entry_price=entry,
                        qty=qty,
                        stop=stop,
                        target=entry - risk * rr_ratio,
                    )

    if position is not None:
        last = rows[-1]
        pnl = (
            (float(last["close"]) - position.entry_price)
            if position.side == "long"
            else (position.entry_price - float(last["close"]))
        ) * position.qty * point_value
        equity += pnl
        trades.append(
            {
                "entry_time": position.entry_time,
                "exit_time": last["datetime"],
                "side": position.side,
                "reason": "end",
                "net_pnl": pnl,
            }
        )

    return summarize_trades(trades, initial_cash, equity, max_drawdown, rows)


def maybe_exit_position(position: Position, bar: dict[str, Any], slippage: float) -> dict[str, Any] | None:
    high = float(bar["high"])
    low = float(bar["low"])
    if position.side == "long":
        if low <= position.stop:
            exit_price = position.stop - slippage
            return {"reason": "stop", "exit_price": exit_price, "pnl": (exit_price - position.entry_price) * position.qty}
        if high >= position.target:
            exit_price = position.target - slippage
            return {"reason": "target", "exit_price": exit_price, "pnl": (exit_price - position.entry_price) * position.qty}
    else:
        if high >= position.stop:
            exit_price = position.stop + slippage
            return {"reason": "stop", "exit_price": exit_price, "pnl": (position.entry_price - exit_price) * position.qty}
        if low <= position.target:
            exit_price = position.target + slippage
            return {"reason": "target", "exit_price": exit_price, "pnl": (position.entry_price - exit_price) * position.qty}
    return None


def is_pivot_high(values: list[float], index: int, length: int) -> bool:
    center = values[index]
    return all(center > values[item] for item in range(index - length, index)) and all(
        center > values[item] for item in range(index + 1, index + length + 1)
    )


def is_pivot_low(values: list[float], index: int, length: int) -> bool:
    center = values[index]
    return all(center < values[item] for item in range(index - length, index)) and all(
        center < values[item] for item in range(index + 1, index + length + 1)
    )


def summarize_trades(
    trades: list[dict[str, Any]],
    initial_cash: float,
    final_equity: float,
    max_drawdown: float,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    gross_profit = sum(float(trade["net_pnl"]) for trade in trades if float(trade["net_pnl"]) > 0)
    gross_loss = -sum(float(trade["net_pnl"]) for trade in trades if float(trade["net_pnl"]) < 0)
    wins = sum(1 for trade in trades if float(trade["net_pnl"]) > 0)
    days = max((as_utc(rows[-1]["datetime"]) - as_utc(rows[0]["datetime"])).total_seconds() / 86400.0, 1.0)
    return {
        "net_pnl": final_equity - initial_cash,
        "final_equity": final_equity,
        "total_return_pct": ((final_equity - initial_cash) / initial_cash * 100.0) if initial_cash else 0.0,
        "max_drawdown_pct": max_drawdown * 100.0,
        "profit_factor": None if gross_loss == 0 else gross_profit / gross_loss,
        "win_rate_pct": wins / len(trades) * 100.0 if trades else None,
        "trades": len(trades),
        "trades_per_year": len(trades) / days * 365.0,
        "average_net_trade": (final_equity - initial_cash) / len(trades) if trades else None,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
    }


def optimize(config_path: Path) -> dict[str, Any]:
    config = read_yaml(config_path)
    reports_dir = resolve_path(config["data"].get("reports_dir", "data/reports/smc_pine_backtest"))
    reports_dir.mkdir(parents=True, exist_ok=True)
    reject = config.get("reject", {})
    rows_out: list[dict[str, Any]] = []
    for data_spec in config["data"]["inputs"]:
        data_path = resolve_path(data_spec["input_path"])
        timeframe = str(data_spec["timeframe"])
        splits = split_rows(load_frame(data_path), config["walk_forward"])
        for params in parameter_grid(config["parameters"]):
            train = run_backtest(splits["train"], params, config["execution"])
            validation = run_backtest(splits["validation"], params, config["execution"])
            test = run_backtest(splits["test"], params, config["execution"])
            reasons = reject_reasons(train, validation, test, reject)
            rows_out.append(
                {
                    "timeframe": timeframe,
                    "data_path": data_path,
                    **params,
                    **prefix_metrics("train", train),
                    **prefix_metrics("validation", validation),
                    **prefix_metrics("test", test),
                    "accepted": not reasons,
                    "reject_reasons": "; ".join(reasons),
                    "score": score_candidate(train, validation, test, reasons),
                }
            )
    ranked = sorted(rows_out, key=lambda row: row["score"], reverse=True)
    write_csv(reports_dir / "all_results.csv", ranked)
    write_csv(reports_dir / "top_results.csv", ranked[:20])
    write_json(reports_dir / "summary.json", build_summary(ranked, config))
    write_research_summary(reports_dir / "research_summary.md", ranked, config)
    write_pine_preset(reports_dir / "pine_input_preset.md", ranked[:5], config)
    if ranked:
        write_yaml(reports_dir / "best_config.yaml", build_best_config(ranked[0], config))
    return {"reports_dir": reports_dir, "evaluated": len(ranked), "accepted": sum(1 for row in ranked if row["accepted"]), "best": ranked[0] if ranked else None}


def parameter_grid(config: dict[str, Any]) -> list[dict[str, Any]]:
    pivots = expand_range(config["pivot_len_swing"])
    rr_values = config["rr_ratio"]
    return [
        {"pivot_len_swing": int(pivot), "rr_ratio": float(rr)}
        for pivot, rr in itertools.product(pivots, rr_values)
    ]


def expand_range(value: list[Any]) -> list[Any]:
    if len(value) == 2 and all(isinstance(item, int) for item in value):
        return list(range(int(value[0]), int(value[1]) + 1))
    return value


def reject_reasons(
    train: dict[str, Any],
    validation: dict[str, Any],
    test: dict[str, Any],
    reject: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if validation["net_pnl"] < float(reject.get("min_validation_net_pnl", 0.0)):
        reasons.append("validation_net_pnl_below_min")
    if (validation["profit_factor"] or 0.0) < float(reject.get("min_validation_profit_factor", 1.0)):
        reasons.append("validation_profit_factor_below_min")
    if validation["trades"] < int(reject.get("min_validation_trades", 0)):
        reasons.append("validation_trade_count_below_min")
    if reject.get("require_train_net_pnl_positive", False) and train["net_pnl"] <= 0:
        reasons.append("train_net_pnl_not_positive")
    if reject.get("require_test_net_pnl_positive", False) and test["net_pnl"] <= 0:
        reasons.append("test_net_pnl_not_positive")
    return reasons


def score_candidate(
    train: dict[str, Any],
    validation: dict[str, Any],
    test: dict[str, Any],
    reasons: list[str],
) -> float:
    score = float(validation["net_pnl"])
    score += min(float(train["net_pnl"]), 0.0)
    score += min(float(test["net_pnl"]), 0.0) * 2.0
    if reasons:
        score -= 1000.0 + len(reasons) * 100.0
    return score


def prefix_metrics(prefix: str, metrics: dict[str, Any]) -> dict[str, Any]:
    return {f"{prefix}_{key}": value for key, value in metrics.items()}


def build_summary(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    best = rows[0] if rows else None
    return {
        "source": "SMC Pine Python approximation",
        "research_only": True,
        "evaluated": len(rows),
        "accepted": sum(1 for row in rows if row["accepted"]),
        "best": best,
        "execution": config.get("execution", {}),
        "walk_forward": config.get("walk_forward", {}),
        "warning": "Re-test presets in TradingView. This is not evidence of profitability, safety, or live readiness.",
    }


def build_best_config(row: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return {
        "timeframe": row["timeframe"],
        "pivot_len_swing": row["pivot_len_swing"],
        "rr_ratio": row["rr_ratio"],
        "risk_per_trade_pct": config["execution"]["risk_per_trade_pct"],
        "validation_net_pnl": row["validation_net_pnl"],
        "validation_profit_factor": row["validation_profit_factor"],
        "test_net_pnl": row["test_net_pnl"],
        "test_profit_factor": row["test_profit_factor"],
    }


def write_research_summary(path: Path, rows: list[dict[str, Any]], config: dict[str, Any]) -> None:
    best = rows[0] if rows else None
    accepted = [row for row in rows if row["accepted"]]
    lines = [
        "# SMC Pine Backtest Research Summary",
        "",
        f"Created at: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
        "",
        "This is a local Python approximation of `smc.pine`. It is not evidence of profitability, predictive power, safety, or live readiness.",
        "",
        "## Controls",
        "",
        f"- Risk per trade: `{config['execution'].get('risk_per_trade_pct')}%`",
        f"- Spread applied: `{config['execution'].get('use_spread')}`",
        f"- Slippage points per side: `{config['execution'].get('slippage_points')}`",
        f"- Validation PF floor: `{config['reject'].get('min_validation_profit_factor')}`",
        f"- Validation trade floor: `{config['reject'].get('min_validation_trades')}`",
        "",
        "## Outcome",
        "",
        f"- Evaluated configs: `{len(rows)}`",
        f"- Accepted configs: `{len(accepted)}`",
        "",
    ]
    if best:
        lines.extend(
            [
                "## Best Ranked Candidate",
                "",
                f"- Timeframe: `{best['timeframe']}`",
                f"- Pivot length: `{best['pivot_len_swing']}`",
                f"- RR ratio: `{best['rr_ratio']}`",
                f"- Accepted: `{best['accepted']}`",
                f"- Validation net P&L: `{format_float(best['validation_net_pnl'])}`",
                f"- Validation PF: `{format_float(best['validation_profit_factor'])}`",
                f"- Validation trades/year: `{format_float(best['validation_trades_per_year'])}`",
                f"- Test net P&L: `{format_float(best['test_net_pnl'])}`",
                f"- Test PF: `{format_float(best['test_profit_factor'])}`",
                f"- Reject reasons: `{best['reject_reasons'] or 'none'}`",
                "",
            ]
        )
    lines.extend(["## Top Accepted Candidates", ""])
    if accepted:
        for row in accepted[:10]:
            lines.append(
                f"- `{row['timeframe']}` pivot=`{row['pivot_len_swing']}` rr=`{row['rr_ratio']}` "
                f"val_pnl=`{format_float(row['validation_net_pnl'])}` "
                f"val_pf=`{format_float(row['validation_profit_factor'])}` "
                f"test_pnl=`{format_float(row['test_net_pnl'])}`"
            )
    else:
        lines.append("No candidate passed all acceptance gates.")
    lines.extend(
        [
            "",
            "Read this as a screening artifact only. Keep using walk-forward validation and TradingView re-checks before making research conclusions.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_pine_preset(path: Path, rows: list[dict[str, Any]], config: dict[str, Any]) -> None:
    lines = [
        "# SMC Pine Input Presets",
        "",
        "Paste one preset into `smc.pine` and re-run TradingView Strategy Tester on the matching timeframe.",
        "",
    ]
    for index, row in enumerate(rows, start=1):
        lines.extend(
            [
                f"## Preset {index}",
                "",
                f"- Accepted: `{row['accepted']}`",
                f"- Timeframe: `{row['timeframe']}`",
                f"- Validation net P&L: `{format_float(row['validation_net_pnl'])}`",
                f"- Test net P&L: `{format_float(row['test_net_pnl'])}`",
                "",
                "```text",
                f"pivot_len_swing = {row['pivot_len_swing']}",
                "pivot_len_internal = 2",
                f"rr_ratio = {row['rr_ratio']}",
                f"risk_percent = {config['execution']['risk_per_trade_pct']}",
                "```",
                "",
            ]
        )
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest and tune the research-only SMC Pine strategy approximation.")
    parser.add_argument("--config", default="configs/smc_pine_backtest_config.yaml")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = optimize(resolve_path(args.config))
    best = result["best"]
    print(
        "SMC Pine backtest complete: "
        f"evaluated={result['evaluated']}, accepted={result['accepted']}"
    )
    if best:
        print(
            "best: "
            f"timeframe={best['timeframe']}, pivot={best['pivot_len_swing']}, rr={best['rr_ratio']}, "
            f"validation_pnl={format_float(best['validation_net_pnl'])}, "
            f"validation_pf={format_float(best['validation_profit_factor'])}, "
            f"test_pnl={format_float(best['test_net_pnl'])}"
        )
    print(f"reports: {result['reports_dir']}")


if __name__ == "__main__":
    main()
