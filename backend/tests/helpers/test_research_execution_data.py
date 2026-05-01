"""Shared synthetic fixtures for research execution tests."""

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl


def synthetic_execution_features(
    *,
    symbol: str = "BTCUSDT",
    rows: int = 24,
    include_open_interest: bool = True,
    include_funding: bool = True,
) -> pl.DataFrame:
    """Create deterministic processed-feature-like rows for tests only."""

    start = datetime(2026, 5, 1)
    records = []
    for index in range(rows):
        price = 100.0 + index
        row = {
            "timestamp": start + timedelta(minutes=15 * index),
            "open": price,
            "high": price + 2.0,
            "low": price - 2.0,
            "close": price + 0.5,
            "volume": 1000.0 + index,
            "atr": 2.0,
            "range_high": price + 4.0,
            "range_low": price - 4.0,
            "range_mid": price,
            "regime": "RANGE" if index % 2 == 0 else "BREAKOUT_UP",
            "volume_ratio": 1.1,
            "symbol": symbol,
        }
        if include_open_interest:
            row["open_interest"] = 10_000.0 + index
            row["oi_change_pct"] = 0.01
        if include_funding:
            row["funding_rate"] = 0.0001
        records.append(row)
    return pl.DataFrame(records)


def write_synthetic_execution_features(path: Path, **kwargs: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    synthetic_execution_features(**kwargs).write_parquet(path)
    return path
