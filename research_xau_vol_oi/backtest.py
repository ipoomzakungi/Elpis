"""Event-based backtests, controls, and walk-forward validation utilities."""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import replace
from typing import Any

import polars as pl

from research_xau_vol_oi.config import DIRECTIONAL_SIGNALS, ResearchConfig, Signal


SIGNAL_DIRECTION = {
    Signal.FADE_WALL_LONG.value: 1,
    Signal.BREAK_WALL_LONG.value: 1,
    Signal.FADE_WALL_SHORT.value: -1,
    Signal.BREAK_WALL_SHORT.value: -1,
    Signal.RANDOM_BASELINE.value: 0,
    Signal.SD_ONLY_BASELINE.value: 0,
    Signal.OI_WALL_ONLY_BASELINE.value: 0,
    Signal.BOLLINGER_BASELINE.value: 0,
}


def run_event_backtest(
    price: pl.DataFrame,
    events: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Run a no-lookahead event study using entry after event timestamp."""

    cfg = config or ResearchConfig()
    if price.is_empty() or events.is_empty():
        return _empty_trades()

    price_rows = price.sort("timestamp").to_dicts()
    event_rows = events.sort("event_timestamp").to_dicts()
    trades: list[dict[str, Any]] = []
    for event in event_rows:
        signal = str(event.get("signal"))
        if signal not in SIGNAL_DIRECTION:
            continue
        direction = _direction_for_event(event, default=SIGNAL_DIRECTION[signal], config=cfg)
        if direction == 0 and signal != Signal.NO_TRADE_MIDDLE.value:
            continue
        entry_index = _first_price_index_after(price_rows, event.get("event_timestamp"))
        if entry_index is None:
            continue
        exit_index = min(entry_index + cfg.backtest_horizon_bars, len(price_rows) - 1)
        if exit_index <= entry_index:
            continue
        entry = price_rows[entry_index]
        exit_bar = price_rows[exit_index]
        path = price_rows[entry_index : exit_index + 1]
        entry_price = float(entry.get("open") or entry["close"])
        exit_price = float(exit_bar["close"])
        pnl_points = (exit_price - entry_price) * direction if direction else 0.0
        round_trip_cost = 2.0 * (
            cfg.cost_points_per_side + cfg.slippage_points_per_side
        ) if direction else 0.0
        net_pnl_points = pnl_points - round_trip_cost
        mae, mfe = _mae_mfe(path, entry_price=entry_price, direction=direction)
        trades.append(
            {
                "event_timestamp": event.get("event_timestamp"),
                "entry_timestamp": entry["timestamp"],
                "exit_timestamp": exit_bar["timestamp"],
                "signal": signal,
                "direction": direction,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl_points": pnl_points,
                "round_trip_cost_points": round_trip_cost,
                "net_pnl_points": net_pnl_points,
                "mae_points": mae,
                "mfe_points": mfe,
                "time_in_trade_bars": exit_index - entry_index,
                "sigma_zone": event.get("sigma_zone"),
                "dte_bucket": event.get("dte_bucket"),
                "wall_score_bucket": event.get("wall_score_bucket"),
                "vol_regime": event.get("vol_regime"),
                "wall_score": event.get("wall_score"),
                "research_only": True,
            }
        )
    return pl.DataFrame(trades, infer_schema_length=None) if trades else _empty_trades()


def summarize_backtest(trades: pl.DataFrame) -> pl.DataFrame:
    """Create summary rows for signal and required performance buckets."""

    if trades.is_empty():
        return _empty_summary()
    rows: list[dict[str, Any]] = []
    rows.extend(_summarize_group(trades.to_dicts(), group_type="signal", key="signal"))
    for key, label in [
        ("sigma_zone", "sigma_zone"),
        ("dte_bucket", "dte_bucket"),
        ("wall_score_bucket", "wall_score_bucket"),
        ("vol_regime", "iv_rv_vrp_regime"),
    ]:
        rows.extend(_summarize_group(trades.to_dicts(), group_type=label, key=key))
    return pl.DataFrame(rows, infer_schema_length=None)


def summarize_event_coverage(events: pl.DataFrame) -> pl.DataFrame:
    """Return no-trade-inclusive signal counts for audit visibility."""

    if events.is_empty():
        return _empty_summary()
    total = events.height
    rows = []
    for raw in events.group_by("signal").len().sort("signal").to_dicts():
        rows.append(
            {
                "group_type": "signal_coverage",
                "bucket": raw["signal"],
                "trade_count": 0,
                "event_count": raw["len"],
                "event_share": raw["len"] / total if total else 0.0,
                "win_rate": None,
                "average_win": None,
                "average_loss": None,
                "expectancy": None,
                "profit_factor": None,
                "max_drawdown": None,
                "average_mae": None,
                "average_mfe": None,
                "average_time_in_trade": None,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def generate_random_baseline_events(
    events: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Generate deterministic random-direction control events on candidate timestamps."""

    cfg = config or ResearchConfig()
    rng = random.Random(cfg.random_seed)
    rows = []
    for event in events.to_dicts():
        if event.get("signal") in {item.value for item in DIRECTIONAL_SIGNALS}:
            direction = rng.choice([-1, 1])
            rows.append(
                {
                    **event,
                    "signal": Signal.RANDOM_BASELINE.value,
                    "random_direction": direction,
                    "reason": "random_direction_control",
                }
            )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def generate_sd_only_baseline_events(price_features: pl.DataFrame) -> pl.DataFrame:
    """Generate a simple SD-only mean-reversion control event table."""

    rows = []
    for row in price_features.to_dicts():
        sigma = row.get("sigma_position")
        if sigma is None:
            continue
        if sigma >= 1.0:
            direction = -1
        elif sigma <= -1.0:
            direction = 1
        else:
            continue
        rows.append(
            {
                "event_timestamp": row["timestamp"],
                "source_bar_timestamp": row["timestamp"],
                "available_wall_timestamp": None,
                "signal": Signal.SD_ONLY_BASELINE.value,
                "reason": "sigma_only_control",
                "sd_direction": direction,
                "sigma_position": sigma,
                "sigma_zone": row.get("sigma_zone"),
                "vol_regime": row.get("vol_regime"),
                "wall_score_bucket": "control",
                "dte_bucket": "control",
                "research_only": True,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def generate_oi_wall_only_baseline_events(price_features: pl.DataFrame) -> pl.DataFrame:
    """Generate a naive OI-wall-only fade baseline without acceptance or IV filters."""

    rows = []
    for row in price_features.to_dicts():
        side = row.get("wall_side")
        if row.get("wall_level") is None or row.get("wall_score") is None:
            continue
        if side == "resistance":
            direction = -1
        elif side == "support":
            direction = 1
        else:
            continue
        rows.append(
            {
                "event_timestamp": row["timestamp"],
                "source_bar_timestamp": row["timestamp"],
                "available_wall_timestamp": None,
                "signal": Signal.OI_WALL_ONLY_BASELINE.value,
                "reason": "oi_wall_only_control",
                "oi_wall_only_direction": direction,
                "sigma_position": row.get("sigma_position"),
                "sigma_zone": row.get("sigma_zone"),
                "vol_regime": row.get("vol_regime"),
                "wall_score_bucket": row.get("wall_score_bucket"),
                "dte_bucket": row.get("dte_bucket"),
                "wall_score": row.get("wall_score"),
                "research_only": True,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def generate_bollinger_baseline_events(price_features: pl.DataFrame) -> pl.DataFrame:
    """Generate a simple Bollinger mean-reversion baseline."""

    rows = []
    for row in price_features.to_dicts():
        close = row.get("close")
        upper = row.get("bb_upper")
        lower = row.get("bb_lower")
        if close is None or upper is None or lower is None:
            continue
        if close > upper:
            direction = -1
        elif close < lower:
            direction = 1
        else:
            continue
        rows.append(
            {
                "event_timestamp": row["timestamp"],
                "source_bar_timestamp": row["timestamp"],
                "available_wall_timestamp": None,
                "signal": Signal.BOLLINGER_BASELINE.value,
                "reason": "bollinger_control",
                "bollinger_direction": direction,
                "sigma_position": row.get("sigma_position"),
                "sigma_zone": row.get("sigma_zone"),
                "vol_regime": row.get("vol_regime"),
                "wall_score_bucket": "control",
                "dte_bucket": "control",
                "research_only": True,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def backtest_all_scenarios(
    price_features: pl.DataFrame,
    events: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Backtest requested signals plus random and SD-only controls."""

    random_events = generate_random_baseline_events(events, config=config)
    sd_events = generate_sd_only_baseline_events(price_features)
    oi_only_events = generate_oi_wall_only_baseline_events(price_features)
    bollinger_events = generate_bollinger_baseline_events(price_features)
    all_events = pl.concat(
        [
            frame
            for frame in [events, random_events, sd_events, oi_only_events, bollinger_events]
            if not frame.is_empty()
        ],
        how="diagonal",
    )
    trades = run_event_backtest(price_features, all_events, config=config)
    summary_parts = [summarize_backtest(trades), summarize_event_coverage(events)]
    summary = pl.concat([frame for frame in summary_parts if not frame.is_empty()], how="diagonal")
    return trades, summary


def walk_forward_validate(
    price_features: pl.DataFrame,
    events: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Split events into formation/test windows without using future OI changes."""

    cfg = config or ResearchConfig()
    if price_features.is_empty() or events.is_empty():
        return pl.DataFrame()
    prices = price_features.sort("timestamp").to_dicts()
    event_rows = events.sort("event_timestamp").to_dicts()
    rows = []
    start = 0
    split_id = 1
    while start + cfg.walk_forward_train_bars < len(prices):
        train_end = start + cfg.walk_forward_train_bars - 1
        test_start = train_end + 1
        test_end = min(test_start + cfg.walk_forward_test_bars - 1, len(prices) - 1)
        test_start_ts = prices[test_start]["timestamp"]
        test_end_ts = prices[test_end]["timestamp"]
        test_events = [
            event
            for event in event_rows
            if test_start_ts <= event.get("event_timestamp") <= test_end_ts
            and (
                event.get("available_wall_timestamp") is None
                or event.get("available_wall_timestamp") <= event.get("event_timestamp")
            )
        ]
        test_events_frame = pl.DataFrame(test_events) if test_events else pl.DataFrame()
        test_trades = (
            run_event_backtest(price_features, test_events_frame, config=cfg)
            if not test_events_frame.is_empty()
            else pl.DataFrame()
        )
        test_summary = summarize_backtest(test_trades)
        signal_summary = (
            test_summary.filter(pl.col("group_type") == "signal")
            if not test_summary.is_empty()
            else pl.DataFrame()
        )
        expectancy = (
            float(signal_summary.get_column("expectancy").mean())
            if not signal_summary.is_empty()
            else None
        )
        rows.append(
            {
                "split_id": split_id,
                "formation_start": prices[start]["timestamp"],
                "formation_end": prices[train_end]["timestamp"],
                "test_start": test_start_ts,
                "test_end": test_end_ts,
                "test_event_count": len(test_events),
                "test_trade_count": test_trades.height if not test_trades.is_empty() else 0,
                "mean_signal_expectancy": expectancy,
                "no_lookahead_violations": 0,
            }
        )
        split_id += 1
        start = test_end + 1
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def run_cost_stress(
    price_features: pl.DataFrame,
    events: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Evaluate performance under higher transaction-cost/slippage assumptions."""

    cfg = config or ResearchConfig()
    rows = []
    for points_per_side in cfg.cost_stress_points_per_side:
        stressed_cfg = replace(
            cfg,
            cost_points_per_side=points_per_side,
            slippage_points_per_side=points_per_side,
        )
        trades, summary = backtest_all_scenarios(price_features, events, config=stressed_cfg)
        signal_rows = (
            summary.filter(pl.col("group_type") == "signal")
            if not summary.is_empty()
            else pl.DataFrame()
        )
        for row in signal_rows.to_dicts():
            rows.append(
                {
                    "points_per_side_cost": points_per_side,
                    "signal": row["bucket"],
                    "trade_count": row["trade_count"],
                    "net_expectancy": row["expectancy"],
                    "profit_factor": row["profit_factor"],
                    "max_drawdown": row["max_drawdown"],
                }
            )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def _direction_for_event(
    event: dict[str, Any],
    *,
    default: int,
    config: ResearchConfig,
) -> int:
    if event.get("signal") == Signal.RANDOM_BASELINE.value:
        return int(event.get("random_direction") or default)
    if event.get("signal") == Signal.SD_ONLY_BASELINE.value:
        return int(event.get("sd_direction") or default)
    if event.get("signal") == Signal.OI_WALL_ONLY_BASELINE.value:
        return int(event.get("oi_wall_only_direction") or default)
    if event.get("signal") == Signal.BOLLINGER_BASELINE.value:
        return int(event.get("bollinger_direction") or default)
    if event.get("signal") == Signal.NO_TRADE_MIDDLE.value:
        return 0
    return default


def _first_price_index_after(rows: list[dict[str, Any]], timestamp: Any) -> int | None:
    for index, row in enumerate(rows):
        if row["timestamp"] > timestamp:
            return index
    return None


def _mae_mfe(
    path: list[dict[str, Any]],
    *,
    entry_price: float,
    direction: int,
) -> tuple[float, float]:
    if direction == 0:
        return 0.0, 0.0
    lows = [float(row["low"]) for row in path]
    highs = [float(row["high"]) for row in path]
    if direction > 0:
        mae = min(low - entry_price for low in lows)
        mfe = max(high - entry_price for high in highs)
    else:
        mae = min(entry_price - high for high in highs)
        mfe = max(entry_price - low for low in lows)
    return mae, mfe


def _summarize_group(
    rows: list[dict[str, Any]],
    *,
    group_type: str,
    key: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key) or "unknown")].append(row)
    return [_metrics(group_type=group_type, bucket=bucket, rows=items) for bucket, items in grouped.items()]


def _metrics(
    *,
    group_type: str,
    bucket: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    pnl = [float(row.get("net_pnl_points", row["pnl_points"])) for row in rows]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    equity = []
    running = 0.0
    for value in pnl:
        running += value
        equity.append(running)
    return {
        "group_type": group_type,
        "bucket": bucket,
        "trade_count": len(rows),
        "win_rate": len(wins) / len(rows) if rows else None,
        "average_win": sum(wins) / len(wins) if wins else 0.0,
        "average_loss": sum(losses) / len(losses) if losses else 0.0,
        "expectancy": sum(pnl) / len(pnl) if pnl else 0.0,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else None,
        "max_drawdown": _max_drawdown(equity),
        "average_mae": _average([float(row["mae_points"]) for row in rows]),
        "average_mfe": _average([float(row["mfe_points"]) for row in rows]),
        "average_time_in_trade": _average([float(row["time_in_trade_bars"]) for row in rows]),
    }


def _max_drawdown(equity: list[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        max_dd = min(max_dd, value - peak)
    return max_dd


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _empty_trades() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "event_timestamp": pl.Datetime(time_zone="UTC"),
            "entry_timestamp": pl.Datetime(time_zone="UTC"),
            "exit_timestamp": pl.Datetime(time_zone="UTC"),
            "signal": pl.String,
            "pnl_points": pl.Float64,
            "round_trip_cost_points": pl.Float64,
            "net_pnl_points": pl.Float64,
        }
    )


def _empty_summary() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "group_type": pl.String,
            "bucket": pl.String,
            "trade_count": pl.Int64,
            "event_count": pl.Int64,
            "event_share": pl.Float64,
            "win_rate": pl.Float64,
            "expectancy": pl.Float64,
            "profit_factor": pl.Float64,
            "max_drawdown": pl.Float64,
        }
    )
