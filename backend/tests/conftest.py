from datetime import datetime, timedelta

import polars as pl
import pytest

from src.api.dependencies import get_duckdb_repo, get_parquet_repo, get_provider_registry
from src.config import get_settings


@pytest.fixture(autouse=True)
def isolated_data_paths(monkeypatch: pytest.MonkeyPatch, tmp_path):
    raw_path = tmp_path / "raw"
    processed_path = tmp_path / "processed"
    reports_path = tmp_path / "reports"
    duckdb_path = tmp_path / "elpis.duckdb"

    monkeypatch.setenv("DATA_RAW_PATH", str(raw_path))
    monkeypatch.setenv("DATA_PROCESSED_PATH", str(processed_path))
    monkeypatch.setenv("DATA_REPORTS_PATH", str(reports_path))
    monkeypatch.setenv("DATA_DUCKDB_PATH", str(duckdb_path))

    get_settings.cache_clear()
    get_parquet_repo.cache_clear()
    get_duckdb_repo.cache_clear()
    get_provider_registry.cache_clear()

    yield tmp_path

    get_settings.cache_clear()
    get_parquet_repo.cache_clear()
    get_duckdb_repo.cache_clear()
    get_provider_registry.cache_clear()


@pytest.fixture()
def sample_ohlcv() -> pl.DataFrame:
    start = datetime(2026, 4, 1)
    rows = []
    for index in range(30):
        timestamp = start + timedelta(minutes=15 * index)
        open_price = 100.0 + index
        close_price = open_price + 0.5
        rows.append(
            {
                "timestamp": timestamp,
                "open": open_price,
                "high": close_price + 1.0,
                "low": open_price - 1.0,
                "close": close_price,
                "volume": 100.0 + index,
                "quote_volume": 10000.0 + index,
                "trades": 100 + index,
                "taker_buy_volume": 50.0 + index,
            }
        )
    return pl.DataFrame(rows)


@pytest.fixture()
def sample_open_interest(sample_ohlcv: pl.DataFrame) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": sample_ohlcv["timestamp"],
            "symbol": ["BTCUSDT"] * len(sample_ohlcv),
            "open_interest": [1000.0 + (index * 10.0) for index in range(len(sample_ohlcv))],
            "open_interest_value": [
                100000.0 + (index * 1000.0) for index in range(len(sample_ohlcv))
            ],
        }
    )


@pytest.fixture()
def sample_funding_rate(sample_ohlcv: pl.DataFrame) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [sample_ohlcv["timestamp"][0]],
            "symbol": ["BTCUSDT"],
            "funding_rate": [0.0001],
            "mark_price": [sample_ohlcv["close"][0]],
        }
    )


@pytest.fixture()
def sample_feature_rows(sample_ohlcv: pl.DataFrame) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": sample_ohlcv["timestamp"][:4],
            "close": [198.0, 102.0, 150.0, 170.0],
            "range_high": [200.0, 200.0, 200.0, 200.0],
            "range_low": [100.0, 100.0, 100.0, 100.0],
            "range_mid": [150.0, 150.0, 150.0, 150.0],
            "oi_change_pct": [6.0, 6.0, 1.0, None],
            "volume_ratio": [1.3, 1.3, 1.0, 1.0],
        }
    )


@pytest.fixture()
def isolated_reports_path():
    return get_settings().data_reports_path


@pytest.fixture()
def sample_backtest_features() -> pl.DataFrame:
    start = datetime(2026, 4, 1)
    rows = []
    regimes = ["RANGE", "RANGE", "BREAKOUT_UP", "BREAKOUT_UP", "AVOID", "RANGE"]
    for index, regime in enumerate(regimes):
        open_price = 100.0 + (index * 2.0)
        rows.append(
            {
                "timestamp": start + timedelta(minutes=15 * index),
                "open": open_price,
                "high": open_price + 5.0,
                "low": open_price - 5.0,
                "close": open_price + 1.0,
                "volume": 1000.0 + index,
                "atr": 4.0,
                "range_high": 112.0,
                "range_low": 96.0,
                "range_mid": 104.0,
                "regime": regime,
                "open_interest": 10000.0 + (index * 100.0),
                "oi_change_pct": 1.0 + index,
                "volume_ratio": 1.1,
                "funding_rate": 0.0001,
            }
        )
    return pl.DataFrame(rows)
