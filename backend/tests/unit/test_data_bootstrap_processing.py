from datetime import datetime, timedelta

import polars as pl
import pytest

from src.data_bootstrap.processing import (
    compute_processed_features,
    provider_raw_path,
    write_processed_features,
)
from src.models.data_bootstrap import DataBootstrapProvider


def test_output_path_safety_keeps_raw_files_under_ignored_roots(isolated_data_paths):
    raw_root = isolated_data_paths / "raw"

    path = provider_raw_path(
        raw_root=raw_root,
        provider=DataBootstrapProvider.YAHOO_FINANCE,
        symbol="GC=F",
        timeframe="1d",
        data_type="ohlcv",
    )

    assert path == raw_root.resolve() / "yahoo" / "gc=f_1d_ohlcv.parquet"
    assert raw_root.resolve() in path.parents

    with pytest.raises(ValueError, match="unsafe"):
        provider_raw_path(
            raw_root=raw_root,
            provider=DataBootstrapProvider.BINANCE_PUBLIC,
            symbol="../BTCUSDT",
            timeframe="15m",
            data_type="ohlcv",
        )


def test_processed_feature_output_schema_matches_preflight_expectations(isolated_data_paths):
    features = compute_processed_features(_ohlcv_frame("BTCUSDT", "15m", rows=64))

    assert {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "atr",
        "range_high",
        "range_low",
        "range_mid",
        "volume_ratio",
    }.issubset(set(features.columns))

    path = write_processed_features(
        features,
        processed_root=isolated_data_paths / "processed",
        symbol="BTCUSDT",
        timeframe="15m",
    )

    assert path == (isolated_data_paths / "processed" / "btcusdt_15m_features.parquet")
    assert path.exists()


def _ohlcv_frame(symbol: str, timeframe: str, rows: int) -> pl.DataFrame:
    start = datetime(2026, 1, 1)
    return pl.DataFrame(
        [
            {
                "timestamp": start + timedelta(minutes=15 * index),
                "provider": "binance",
                "symbol": symbol,
                "timeframe": timeframe,
                "open": 100.0 + index,
                "high": 103.0 + index,
                "low": 98.0 + index,
                "close": 101.0 + index,
                "volume": 1000.0 + index,
                "quote_volume": 2000.0 + index,
                "trades": 100 + index,
                "taker_buy_volume": 500.0 + index,
                "source": "synthetic_test_fixture",
            }
            for index in range(rows)
        ]
    )
