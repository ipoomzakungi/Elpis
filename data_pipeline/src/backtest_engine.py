from __future__ import annotations

import argparse
import csv
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from metrics import calculate_summary_metrics
from pipeline_utils import (
    DEFAULT_PROCESSED_PARQUET,
    DEFAULT_REPORTS_DIR,
    read_yaml,
    resolve_path,
    to_iso,
    write_json,
)
from strategy import prepare_strategy_frame

TRADE_COLUMNS = [
    "trade_id",
    "side",
    "signal_time",
    "entry_time",
    "exit_time",
    "entry_price",
    "exit_price",
    "stop_loss",
    "take_profit",
    "quantity",
    "gross_pnl",
    "commission",
    "net_pnl",
    "return_pct",
    "holding_minutes",
    "exit_reason",
]


def run_backtest_from_config(config_path: Path, export: bool = True) -> dict[str, Any]:
    config = read_yaml(config_path)
    data_config = config.get("data", {})
    backtest_config = config.get("backtest", {})
    strategy_config = config.get("strategy", {})
    processed_path = resolve_path(data_config.get("processed_path"), DEFAULT_PROCESSED_PARQUET)
    reports_dir = resolve_path(data_config.get("reports_dir"), DEFAULT_REPORTS_DIR)
    df = pl.read_parquet(processed_path)
    return run_backtest_frame(
        df=df,
        params={**backtest_config, **strategy_config},
        reports_dir=reports_dir,
        export=export,
        run_name=config.get("name", "xauusd_strategy_backtest"),
    )


def run_backtest_frame(
    df: pl.DataFrame,
    params: dict[str, Any],
    reports_dir: Path | None = None,
    export: bool = False,
    run_name: str = "xauusd_strategy_backtest",
) -> dict[str, Any]:
    if df.is_empty():
        raise ValueError("Cannot backtest an empty DataFrame")
    required = {"datetime", "open", "high", "low", "close"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Backtest data missing required columns: {missing}")

    prepared = prepare_strategy_frame(df, params).sort("datetime")
    rows = prepared.to_dicts()

    initial_cash = float(params.get("initial_cash", 10_000.0))
    annualization_periods = int(params.get("annualization_periods", 252 * 24 * 60))
    cash = initial_cash
    peak_equity = initial_cash
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    position: dict[str, Any] | None = None

    for index, row in enumerate(rows):
        if position is None and index > 0:
            previous = rows[index - 1]
            position = _open_position(previous, row, params, cash, len(trades) + 1)
            if position is not None:
                cash -= position["entry_commission"]

        if position is not None:
            exit_decision = _evaluate_exit(position, row, is_final_bar=index == len(rows) - 1)
            if exit_decision is not None:
                trade = _close_position(position, row, exit_decision, params)
                cash += trade["gross_pnl"] - trade["exit_commission"]
                trades.append(_public_trade_payload(trade))
                position = None

        equity = cash + (_mark_to_market(position, row, params) if position is not None else 0.0)
        peak_equity = max(peak_equity, equity)
        drawdown = (equity - peak_equity) / peak_equity if peak_equity else 0.0
        equity_curve.append(
            {
                "datetime": row["datetime"],
                "equity": equity,
                "drawdown": drawdown,
                "open_position": position is not None,
                "realized_cash": cash,
            }
        )

    summary = calculate_summary_metrics(
        trades=trades,
        equity_curve=equity_curve,
        initial_cash=initial_cash,
        annualization_periods=annualization_periods,
    )
    summary["run_name"] = run_name
    summary["assumptions"] = _assumption_payload(params)
    summary["limitations"] = [
        "Historical simulation only; this is not live, paper, broker, or execution behavior.",
        "Signals enter on the next bar open.",
        "If stop loss and take profit are both reachable in one candle, stop loss is assumed first.",
        "Costs use configured spread, commission, and slippage assumptions.",
    ]

    result = {"summary": summary, "trades": trades, "equity_curve": equity_curve}
    if export:
        if reports_dir is None:
            reports_dir = DEFAULT_REPORTS_DIR
        export_backtest_outputs(result, reports_dir)
    return result


def export_backtest_outputs(result: dict[str, Any], reports_dir: Path) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(reports_dir / "trades.csv", result["trades"], TRADE_COLUMNS)
    _write_csv(
        reports_dir / "equity_curve.csv",
        [
            {
                "datetime": to_iso(point["datetime"]),
                "equity": point["equity"],
                "drawdown": point["drawdown"],
                "open_position": point["open_position"],
                "realized_cash": point["realized_cash"],
            }
            for point in result["equity_curve"]
        ],
        ["datetime", "equity", "drawdown", "open_position", "realized_cash"],
    )
    write_json(reports_dir / "summary.json", result["summary"])


def _open_position(
    signal_row: dict[str, Any],
    entry_row: dict[str, Any],
    params: dict[str, Any],
    cash: float,
    trade_index: int,
) -> dict[str, Any] | None:
    side = signal_row.get("signal")
    if side not in {"long", "short"}:
        return None
    if side == "short" and not bool(params.get("allow_short", True)):
        return None
    atr = signal_row.get("atr")
    if atr is None or not math.isfinite(float(atr)) or float(atr) <= 0:
        return None

    point_size = float(params.get("point_size", 0.01))
    max_spread_points = float(params.get("max_spread_points", 50))
    entry_spread = _spread(entry_row)
    if entry_spread / point_size > max_spread_points:
        return None

    entry_mid = float(entry_row["open"])
    stop_distance = float(atr) * float(params["stop_loss_atr"])
    take_distance = float(atr) * float(params["take_profit_atr"])
    if side == "long":
        stop_loss = max(0.01, entry_mid - stop_distance)
        take_profit = entry_mid + take_distance
    else:
        stop_loss = entry_mid + stop_distance
        take_profit = max(0.01, entry_mid - take_distance)

    entry_price = _execution_price(entry_mid, entry_spread, side, "entry", params)
    risk_basis = max(abs(entry_mid - stop_loss), point_size)
    equity_for_sizing = cash if bool(params.get("compound", False)) else float(
        params.get("initial_cash", cash)
    )
    risk_amount = equity_for_sizing * float(params.get("risk_per_trade", 0.01))
    quantity = risk_amount / risk_basis
    max_units = params.get("max_units")
    if max_units is not None:
        quantity = min(quantity, float(max_units))
    if quantity <= 0:
        return None

    return {
        "trade_id": f"T{trade_index:06d}",
        "side": side,
        "signal_time": signal_row["datetime"],
        "entry_time": entry_row["datetime"],
        "entry_price": entry_price,
        "entry_mid": entry_mid,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "quantity": quantity,
        "entry_commission": _commission(quantity, params),
    }


def _evaluate_exit(
    position: dict[str, Any],
    row: dict[str, Any],
    is_final_bar: bool,
) -> dict[str, Any] | None:
    side = position["side"]
    high = float(row["high"])
    low = float(row["low"])
    stop_loss = float(position["stop_loss"])
    take_profit = float(position["take_profit"])

    if side == "long":
        stop_hit = low <= stop_loss
        take_hit = high >= take_profit
    else:
        stop_hit = high >= stop_loss
        take_hit = low <= take_profit

    if stop_hit:
        return {"reason": "stop_loss", "exit_mid": stop_loss}
    if take_hit:
        return {"reason": "take_profit", "exit_mid": take_profit}
    if is_final_bar:
        return {"reason": "end_of_data", "exit_mid": float(row["close"])}
    return None


def _close_position(
    position: dict[str, Any],
    row: dict[str, Any],
    exit_decision: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    side = position["side"]
    exit_spread = _spread(row)
    exit_price = _execution_price(exit_decision["exit_mid"], exit_spread, side, "exit", params)
    quantity = position["quantity"]
    if side == "long":
        gross_pnl = (exit_price - position["entry_price"]) * quantity
    else:
        gross_pnl = (position["entry_price"] - exit_price) * quantity
    exit_commission = _commission(quantity, params)
    total_commission = position["entry_commission"] + exit_commission
    net_pnl = gross_pnl - total_commission
    holding_minutes = (row["datetime"] - position["entry_time"]).total_seconds() / 60
    return {
        **position,
        "exit_time": row["datetime"],
        "exit_price": exit_price,
        "gross_pnl": gross_pnl,
        "exit_commission": exit_commission,
        "commission": total_commission,
        "net_pnl": net_pnl,
        "return_pct": net_pnl / max(position["entry_price"] * quantity, 1e-12),
        "holding_minutes": holding_minutes,
        "exit_reason": exit_decision["reason"],
    }


def _public_trade_payload(trade: dict[str, Any]) -> dict[str, Any]:
    return {column: trade[column] for column in TRADE_COLUMNS}


def _mark_to_market(position: dict[str, Any], row: dict[str, Any], params: dict[str, Any]) -> float:
    exit_price = _execution_price(float(row["close"]), _spread(row), position["side"], "exit", params)
    if position["side"] == "long":
        gross = (exit_price - position["entry_price"]) * position["quantity"]
    else:
        gross = (position["entry_price"] - exit_price) * position["quantity"]
    return gross - _commission(position["quantity"], params)


def _execution_price(
    mid_price: float,
    spread: float,
    side: str,
    action: str,
    params: dict[str, Any],
) -> float:
    slippage = float(params.get("slippage_points", 0.0)) * float(params.get("point_size", 0.01))
    half_spread = spread / 2
    if side == "long":
        return mid_price + half_spread + slippage if action == "entry" else mid_price - half_spread - slippage
    return mid_price - half_spread - slippage if action == "entry" else mid_price + half_spread + slippage


def _spread(row: dict[str, Any]) -> float:
    value = row.get("spread_close")
    if value is None or not math.isfinite(float(value)):
        return 0.0
    return max(0.0, float(value))


def _commission(quantity: float, params: dict[str, Any]) -> float:
    return abs(quantity) * float(params.get("commission_per_unit", 0.0))


def _assumption_payload(params: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "initial_cash",
        "risk_per_trade",
        "commission_per_unit",
        "slippage_points",
        "point_size",
        "allow_short",
        "compound",
        "max_units",
    ]
    return {key: params.get(key) for key in keys if key in params}


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: to_iso(row.get(column)) for column in columns})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one XAUUSD strategy backtest.")
    parser.add_argument("--config", default="configs/strategy_config.yaml")
    parser.add_argument("--no-export", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_backtest_from_config(resolve_path(args.config), export=not args.no_export)
    summary = result["summary"]
    print(
        "backtest complete: "
        f"net_profit={summary['net_profit']:.2f}, "
        f"trades={summary['number_of_trades']}, "
        f"max_drawdown_pct={summary['max_drawdown_pct']:.2f}"
    )


if __name__ == "__main__":
    main()

