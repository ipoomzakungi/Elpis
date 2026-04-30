"""Shared fixtures for multi-asset research tests."""

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl


def synthetic_research_features(
    *,
    symbol: str = "BTCUSDT",
    rows: int = 48,
    include_regime: bool = True,
    include_open_interest: bool = True,
    include_funding: bool = True,
) -> pl.DataFrame:
    """Create deterministic processed-feature-like rows for local tests only."""
    start = datetime(2026, 4, 1)
    regimes = ["RANGE", "BREAKOUT_UP", "BREAKOUT_DOWN", "AVOID"]
    records = []
    for index in range(rows):
        price = 100.0 + index
        row = {
            "timestamp": start + timedelta(minutes=15 * index),
            "open": price,
            "high": price + 2.0,
            "low": price - 2.0,
            "close": price + 0.5,
            "volume": 1_000.0 + index,
            "atr": 2.0,
            "range_high": price + 4.0,
            "range_low": price - 4.0,
            "range_mid": price,
            "volume_ratio": 1.0,
            "symbol": symbol,
        }
        if include_regime:
            row["regime"] = regimes[index % len(regimes)]
        if include_open_interest:
            row["open_interest"] = 10_000.0 + index
            row["oi_change_pct"] = 0.01
        if include_funding:
            row["funding_rate"] = 0.0001
        records.append(row)
    return pl.DataFrame(records)


def write_synthetic_research_features(path: Path, **kwargs: object) -> Path:
    """Write deterministic processed features and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    synthetic_research_features(**kwargs).write_parquet(path)
    return path

