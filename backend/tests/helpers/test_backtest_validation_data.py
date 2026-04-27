from datetime import datetime, timedelta

import polars as pl


def make_validation_feature_rows(
    row_count: int = 12,
    start: datetime | None = None,
    open_price: float = 100.0,
) -> pl.DataFrame:
    base_timestamp = start or datetime(2026, 4, 1)
    regimes = ["RANGE", "BREAKOUT_UP", "BREAKOUT_DOWN", "AVOID"]
    rows = []

    for index in range(row_count):
        price = open_price + index
        rows.append(
            {
                "timestamp": base_timestamp + timedelta(minutes=15 * index),
                "open": price,
                "high": price + 4.0,
                "low": max(0.01, price - 4.0),
                "close": price + 1.0,
                "volume": 1000.0 + index,
                "atr": 3.0,
                "range_high": price + 10.0,
                "range_low": max(0.01, price - 10.0),
                "range_mid": price,
                "regime": regimes[index % len(regimes)],
                "open_interest": 10000.0 + (index * 100.0),
                "oi_change_pct": 1.0 + (index * 0.1),
                "volume_ratio": 1.0 + (index * 0.01),
                "funding_rate": 0.0001,
            }
        )

    return pl.DataFrame(rows)


def write_validation_features(path, row_count: int = 12) -> pl.DataFrame:
    features = make_validation_feature_rows(row_count=row_count)
    path.parent.mkdir(parents=True, exist_ok=True)
    features.write_parquet(path)
    return features