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
    read_dukascopy_csv,
    resolve_path,
    to_iso,
    write_json,
)


def validate_xauusd(
    parquet_path: Path = DEFAULT_PROCESSED_PARQUET,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    bid_csv: Path | None = DEFAULT_BID_CSV,
    ask_csv: Path | None = DEFAULT_ASK_CSV,
) -> dict:
    if not parquet_path.exists():
        raise FileNotFoundError(parquet_path)
    reports_dir.mkdir(parents=True, exist_ok=True)
    df = pl.read_parquet(parquet_path).sort("datetime")
    if df.is_empty():
        raise ValueError("Processed Parquet file is empty")

    duplicates = (
        df.group_by("datetime")
        .len()
        .filter(pl.col("len") > 1)
        .sort("datetime")
        .rename({"len": "duplicate_count"})
    )
    duplicate_payload = {
        "processed_duplicate_timestamp_count": duplicates.height,
        "processed_duplicate_rows": duplicates.head(1000).to_dicts(),
    }
    for side, raw_path in [("bid", bid_csv), ("ask", ask_csv)]:
        if raw_path is not None and raw_path.exists():
            _, metadata = read_dukascopy_csv(raw_path, side)
            duplicate_payload[f"{side}_raw_duplicate_timestamps_removed_by_cleaner"] = metadata[
                "duplicate_timestamps_removed"
            ]

    missing_payload = detect_missing_minute_ranges(df["datetime"].to_list())

    suspicious = df.filter(
        (pl.col("high") < pl.col("low"))
        | (pl.col("open") > pl.col("high"))
        | (pl.col("open") < pl.col("low"))
        | (pl.col("close") > pl.col("high"))
        | (pl.col("close") < pl.col("low"))
    )

    spread = df.select(
        [
            pl.col("spread_close").mean().alias("average_spread"),
            pl.col("spread_close").min().alias("min_spread"),
            pl.col("spread_close").max().alias("max_spread"),
            pl.col("spread_close").quantile(0.5).alias("median_spread"),
            pl.col("spread_close").quantile(0.95).alias("p95_spread"),
            pl.col("spread_close").quantile(0.99).alias("p99_spread"),
            (pl.col("spread_close") < 0).sum().alias("negative_spread_count"),
            (pl.col("spread_close") == 0).sum().alias("zero_spread_count"),
        ]
    ).to_dicts()[0]

    date_range_payload = {
        "first_timestamp": to_iso(df["datetime"][0]),
        "last_timestamp": to_iso(df["datetime"][-1]),
        "total_candles": df.height,
        "missing_candle_count": missing_payload["missing_candle_count"],
        "missing_range_count": missing_payload["range_count"],
        "duplicate_timestamp_count": duplicates.height,
        "average_spread": spread["average_spread"],
        "max_spread": spread["max_spread"],
        "suspicious_candle_count": suspicious.height,
        "suspicious_candle_sample": suspicious.head(1000).to_dicts(),
        "source_path": parquet_path,
    }

    write_json(reports_dir / "missing_minutes.json", missing_payload)
    write_json(reports_dir / "duplicate_rows.json", duplicate_payload)
    write_json(reports_dir / "spread_summary.json", spread)
    write_json(reports_dir / "date_range_summary.json", date_range_payload)

    return {
        "missing": missing_payload,
        "duplicates": duplicate_payload,
        "spread": spread,
        "date_range": date_range_payload,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate cleaned XAUUSD m1 Parquet data.")
    parser.add_argument("--input", default=str(DEFAULT_PROCESSED_PARQUET))
    parser.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    parser.add_argument("--bid-csv", default=str(DEFAULT_BID_CSV))
    parser.add_argument("--ask-csv", default=str(DEFAULT_ASK_CSV))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = validate_xauusd(
        parquet_path=resolve_path(args.input),
        reports_dir=resolve_path(args.reports_dir),
        bid_csv=resolve_path(args.bid_csv) if args.bid_csv else None,
        ask_csv=resolve_path(args.ask_csv) if args.ask_csv else None,
    )
    summary = result["date_range"]
    print(
        "validated XAUUSD data: "
        f"{summary['total_candles']} candles, "
        f"{summary['missing_candle_count']} missing minutes, "
        f"{summary['suspicious_candle_count']} suspicious candles"
    )


if __name__ == "__main__":
    main()

