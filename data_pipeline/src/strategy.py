from __future__ import annotations

from typing import Any

import polars as pl


def add_indicators(df: pl.DataFrame, params: dict[str, Any]) -> pl.DataFrame:
    fast_ema = int(params["fast_ema"])
    slow_ema = int(params["slow_ema"])
    rsi_length = int(params["rsi_length"])
    atr_length = int(params["atr_length"])

    enriched = (
        df.sort("datetime")
        .with_columns(
            [
                pl.col("close").ewm_mean(span=fast_ema, adjust=False).alias("fast_ema"),
                pl.col("close").ewm_mean(span=slow_ema, adjust=False).alias("slow_ema"),
                pl.col("close").shift(1).alias("prev_close"),
                pl.col("close").diff().alias("delta"),
            ]
        )
        .with_columns(
            [
                pl.when(pl.col("delta") > 0).then(pl.col("delta")).otherwise(0.0).alias("gain"),
                pl.when(pl.col("delta") < 0).then(-pl.col("delta")).otherwise(0.0).alias("loss"),
                pl.max_horizontal(
                    [
                        pl.col("high") - pl.col("low"),
                        (pl.col("high") - pl.col("prev_close")).abs(),
                        (pl.col("low") - pl.col("prev_close")).abs(),
                    ]
                ).alias("true_range"),
            ]
        )
        .with_columns(
            [
                pl.col("gain").rolling_mean(window_size=rsi_length).alias("avg_gain"),
                pl.col("loss").rolling_mean(window_size=rsi_length).alias("avg_loss"),
                pl.col("true_range").rolling_mean(window_size=atr_length).alias("atr"),
            ]
        )
        .with_columns(
            [
                pl.when((pl.col("avg_loss") == 0) & (pl.col("avg_gain") == 0))
                .then(50.0)
                .when(pl.col("avg_loss") == 0)
                .then(100.0)
                .otherwise(100 - (100 / (1 + (pl.col("avg_gain") / pl.col("avg_loss")))))
                .alias("rsi")
            ]
        )
        .drop(["prev_close", "delta", "gain", "loss", "avg_gain", "avg_loss"])
    )
    return enriched


def build_signals(df: pl.DataFrame, params: dict[str, Any]) -> pl.DataFrame:
    point_size = float(params.get("point_size", 0.01))
    max_spread_points = float(params["max_spread_points"])
    rsi_buy_level = float(params["rsi_buy_level"])
    rsi_sell_level = float(params["rsi_sell_level"])

    spread_points_expr = (
        pl.col("spread_points")
        if "spread_points" in df.columns
        else pl.col("spread_close").fill_null(0.0) / point_size
    )
    return df.with_columns(spread_points_expr.alias("execution_spread_points")).with_columns(
        [
            pl.when(
                (pl.col("fast_ema") > pl.col("slow_ema"))
                & (pl.col("rsi") <= rsi_buy_level)
                & (pl.col("execution_spread_points") <= max_spread_points)
            )
            .then(pl.lit("long"))
            .when(
                (pl.col("fast_ema") < pl.col("slow_ema"))
                & (pl.col("rsi") >= rsi_sell_level)
                & (pl.col("execution_spread_points") <= max_spread_points)
            )
            .then(pl.lit("short"))
            .otherwise(None)
            .alias("signal")
        ]
    )


def prepare_strategy_frame(df: pl.DataFrame, params: dict[str, Any]) -> pl.DataFrame:
    return build_signals(add_indicators(df, params), params)

