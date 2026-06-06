from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from pipeline_utils import DEFAULT_PROCESSED_PARQUET, resolve_path, timeframe_to_polars_every


def resample_xauusd(input_path: Path, output_path: Path, timeframe: str) -> dict:
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    every = timeframe_to_polars_every(timeframe)
    df = pl.read_parquet(input_path).sort("datetime").set_sorted("datetime")

    aggregations = [
        pl.col("open").first().alias("open"),
        pl.col("high").max().alias("high"),
        pl.col("low").min().alias("low"),
        pl.col("close").last().alias("close"),
        pl.col("spread_close").mean().alias("spread_close"),
        pl.col("spread_points").mean().alias("spread_points"),
    ]
    for column in [
        "bid_open",
        "bid_high",
        "bid_low",
        "bid_close",
        "ask_open",
        "ask_high",
        "ask_low",
        "ask_close",
    ]:
        if column in df.columns:
            if column.endswith("_open"):
                aggregations.append(pl.col(column).first().alias(column))
            elif column.endswith("_high"):
                aggregations.append(pl.col(column).max().alias(column))
            elif column.endswith("_low"):
                aggregations.append(pl.col(column).min().alias(column))
            else:
                aggregations.append(pl.col(column).last().alias(column))
    for column in ["bid_volume", "ask_volume"]:
        if column in df.columns:
            aggregations.append(pl.col(column).sum().alias(column))

    resampled = (
        df.group_by_dynamic("datetime", every=every, closed="left", label="left")
        .agg(aggregations)
        .drop_nulls(["open", "high", "low", "close"])
        .with_columns(
            [
                pl.lit("dukascopy").alias("source"),
                pl.lit("xauusd").alias("instrument"),
                pl.lit(timeframe.lower()).alias("timeframe"),
            ]
        )
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    resampled.write_parquet(output_path)
    return {
        "input_path": input_path,
        "output_path": output_path,
        "timeframe": timeframe,
        "rows": resampled.height,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resample cleaned XAUUSD m1 Parquet data.")
    parser.add_argument("--input", default=str(DEFAULT_PROCESSED_PARQUET))
    parser.add_argument("--timeframe", default="m15")
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = resolve_path(args.input)
    output_path = (
        resolve_path(args.output)
        if args.output
        else resolve_path(f"data/processed/xauusd_{args.timeframe.lower()}_2024_to_now.parquet")
    )
    result = resample_xauusd(input_path=input_path, output_path=output_path, timeframe=args.timeframe)
    print(f"resampled {result['rows']} {args.timeframe} candles -> {result['output_path']}")


if __name__ == "__main__":
    main()

