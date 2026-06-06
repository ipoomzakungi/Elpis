from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from pipeline_utils import (
    DEFAULT_ASK_CSV,
    DEFAULT_BID_CSV,
    DEFAULT_PROCESSED_PARQUET,
    DEFAULT_REPORTS_DIR,
    detect_missing_minute_ranges,
    ensure_pipeline_dirs,
    read_dukascopy_csv,
    resolve_path,
    to_iso,
    write_json,
)


def clean_xauusd(
    bid_csv: Path = DEFAULT_BID_CSV,
    ask_csv: Path = DEFAULT_ASK_CSV,
    output_path: Path = DEFAULT_PROCESSED_PARQUET,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    point_size: float = 0.01,
) -> dict:
    ensure_pipeline_dirs()
    bid, bid_meta = read_dukascopy_csv(bid_csv, "bid")
    ask, ask_meta = read_dukascopy_csv(ask_csv, "ask")

    merged = bid.join(ask, on="datetime", how="inner").sort("datetime")
    bid_only = bid.join(ask.select("datetime"), on="datetime", how="anti").height
    ask_only = ask.join(bid.select("datetime"), on="datetime", how="anti").height
    if merged.is_empty():
        raise ValueError("Bid and ask CSV files have no overlapping timestamps")

    cleaned = merged.with_columns(
        [
            ((pl.col("bid_open") + pl.col("ask_open")) / 2).alias("open"),
            ((pl.col("bid_high") + pl.col("ask_high")) / 2).alias("high"),
            ((pl.col("bid_low") + pl.col("ask_low")) / 2).alias("low"),
            ((pl.col("bid_close") + pl.col("ask_close")) / 2).alias("close"),
            (pl.col("ask_close") - pl.col("bid_close")).alias("spread_close"),
            ((pl.col("ask_close") - pl.col("bid_close")) / point_size).alias("spread_points"),
            pl.lit("dukascopy").alias("source"),
            pl.lit("xauusd").alias("instrument"),
            pl.lit("m1").alias("timeframe"),
        ]
    )

    columns = [
        "datetime",
        "open",
        "high",
        "low",
        "close",
        "spread_close",
        "spread_points",
        "bid_open",
        "bid_high",
        "bid_low",
        "bid_close",
        "ask_open",
        "ask_high",
        "ask_low",
        "ask_close",
    ]
    for optional in ["bid_volume", "ask_volume"]:
        if optional in cleaned.columns:
            columns.append(optional)
    columns.extend(["source", "instrument", "timeframe"])
    cleaned = cleaned.select(columns)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned.write_parquet(output_path)

    missing = detect_missing_minute_ranges(cleaned["datetime"].to_list())
    summary = {
        "output_path": output_path,
        "first_timestamp": to_iso(cleaned["datetime"][0]),
        "last_timestamp": to_iso(cleaned["datetime"][-1]),
        "total_candles": cleaned.height,
        "missing_candle_count": missing["missing_candle_count"],
        "missing_range_count": missing["range_count"],
        "bid_rows_without_ask": bid_only,
        "ask_rows_without_bid": ask_only,
        "bid_csv": bid_meta,
        "ask_csv": ask_meta,
        "point_size": point_size,
    }
    write_json(reports_dir / "clean_summary.json", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean Dukascopy XAUUSD bid/ask m1 CSVs to Parquet.")
    parser.add_argument("--bid-csv", default=str(DEFAULT_BID_CSV))
    parser.add_argument("--ask-csv", default=str(DEFAULT_ASK_CSV))
    parser.add_argument("--output", default=str(DEFAULT_PROCESSED_PARQUET))
    parser.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    parser.add_argument("--point-size", type=float, default=0.01)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = clean_xauusd(
        bid_csv=resolve_path(args.bid_csv),
        ask_csv=resolve_path(args.ask_csv),
        output_path=resolve_path(args.output),
        reports_dir=resolve_path(args.reports_dir),
        point_size=args.point_size,
    )
    print(
        "cleaned XAUUSD m1 data: "
        f"{summary['total_candles']} candles -> {summary['output_path']}"
    )
    print(f"missing candle count: {summary['missing_candle_count']}")


if __name__ == "__main__":
    main()

