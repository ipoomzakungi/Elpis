from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from src.data_sources.bootstrap import (
    BINANCE_LIMITED_DERIVATIVES_NOTE,
    PublicDataBootstrapService,
    binance_derivative_limitations,
    binance_request_windows,
    build_public_bootstrap_plan,
    provider_raw_path,
)
from src.models.data_sources import (
    DataSourceBootstrapProvider,
    DataSourceBootstrapRequest,
    DataSourceProviderType,
)


def test_binance_public_bootstrap_request_planning_supports_symbols_and_timeframes():
    request = DataSourceBootstrapRequest(
        binance_symbols=["BTCUSDT", "ETHUSDT"],
        optional_binance_symbols=["SOLUSDT"],
        binance_timeframes=["15m", "1h", "1d"],
        yahoo_symbols=[],
        research_only_acknowledged=True,
    )

    plan = build_public_bootstrap_plan(request)

    binance_items = [
        item for item in plan if item.provider == DataSourceBootstrapProvider.BINANCE_PUBLIC
    ]
    assert {(item.symbol, item.timeframe) for item in binance_items} == {
        ("BTCUSDT", "15m"),
        ("BTCUSDT", "1h"),
        ("BTCUSDT", "1d"),
        ("ETHUSDT", "15m"),
        ("ETHUSDT", "1h"),
        ("ETHUSDT", "1d"),
        ("SOLUSDT", "15m"),
        ("SOLUSDT", "1h"),
        ("SOLUSDT", "1d"),
    }
    assert all("ohlcv" in item.data_types for item in binance_items)
    assert all("open_interest" in item.data_types for item in binance_items)
    assert all("funding_rate" in item.data_types for item in binance_items)


def test_binance_pagination_date_window_logic_is_chronological_and_bounded():
    start = datetime(2026, 5, 1, tzinfo=UTC)
    end = start + timedelta(hours=3)

    windows = binance_request_windows(start, end, timeframe="15m", limit=4)

    assert windows == [
        (1777593600000, 1777597200000),
        (1777597200001, 1777600800001),
        (1777600800002, 1777604400000),
    ]


def test_binance_limited_oi_and_funding_labeling_is_explicit():
    now = datetime(2026, 5, 1, tzinfo=UTC)

    limitations = binance_derivative_limitations(
        data_type="open_interest",
        row_count=2,
        start_timestamp=now,
        end_timestamp=now + timedelta(hours=1),
        requested_days=30,
    )

    assert BINANCE_LIMITED_DERIVATIVES_NOTE in limitations
    assert any("shallow" in note.lower() for note in limitations)


def test_yahoo_request_labels_unsupported_capabilities():
    request = DataSourceBootstrapRequest(
        binance_symbols=[],
        yahoo_symbols=["SPY", "GC=F"],
        yahoo_timeframes=["1d"],
        research_only_acknowledged=True,
    )

    plan = build_public_bootstrap_plan(request)

    yahoo_items = [
        item for item in plan if item.provider == DataSourceBootstrapProvider.YAHOO_FINANCE
    ]
    assert {item.symbol for item in yahoo_items} == {"SPY", "GC=F"}
    for item in yahoo_items:
        assert item.data_types == ["ohlcv"]
        assert "open_interest" in item.unsupported_capabilities
        assert "funding" in item.unsupported_capabilities
        assert "iv" in item.unsupported_capabilities
        assert "gold_options_oi" in item.unsupported_capabilities
        assert "xauusd_spot_execution" in item.unsupported_capabilities


def test_output_path_safety_keeps_generated_files_under_ignored_roots(isolated_data_paths):
    raw_root = isolated_data_paths / "raw"

    path = provider_raw_path(
        raw_root=raw_root,
        provider=DataSourceBootstrapProvider.YAHOO_FINANCE,
        symbol="GC=F",
        timeframe="1d",
        data_type="ohlcv",
    )

    assert path == raw_root.resolve() / "yahoo" / "gc=f_1d_ohlcv.parquet"
    assert raw_root.resolve() in path.parents
    with pytest.raises(ValueError, match="unsafe"):
        provider_raw_path(
            raw_root=raw_root,
            provider=DataSourceBootstrapProvider.BINANCE_PUBLIC,
            symbol="../BTCUSDT",
            timeframe="15m",
            data_type="ohlcv",
        )


@pytest.mark.asyncio()
async def test_generated_raw_and_processed_files_use_ignored_data_paths(isolated_data_paths):
    service = PublicDataBootstrapService(
        binance_client=_FakeBinanceClient(rows=32),
        yahoo_client=_FakeYahooClient(rows=32),
    )
    request = DataSourceBootstrapRequest(
        binance_symbols=["BTCUSDT"],
        binance_timeframes=["15m"],
        yahoo_symbols=["SPY"],
        yahoo_timeframes=["1d"],
        days=7,
        research_only_acknowledged=True,
    )

    result = await service.run(request)

    assert result.status == "completed"
    assert result.preflight_result is not None
    assert result.preflight_result.crypto_results[0].status == "ready"
    assert result.preflight_result.proxy_results[0].status == "ready"
    for summary in result.asset_summaries:
        assert summary.processed_feature_path is not None
        processed_path = isolated_data_paths / "processed"
        assert processed_path.resolve() in summary.processed_feature_path.parents
        for artifact in summary.raw_artifacts:
            assert isolated_data_paths.joinpath("raw").resolve() in artifact.path.parents


class _FakeBinanceClient:
    def __init__(self, rows: int):
        self.rows = rows

    async def download_ohlcv(self, symbol: str, interval: str, days: int) -> pl.DataFrame:
        return _ohlcv_frame(symbol=symbol, timeframe=interval, rows=self.rows)

    async def download_open_interest(self, symbol: str, period: str, days: int) -> pl.DataFrame:
        frame = _ohlcv_frame(symbol=symbol, timeframe=period, rows=max(2, self.rows // 4))
        return pl.DataFrame(
            {
                "timestamp": frame["timestamp"],
                "symbol": [symbol] * frame.height,
                "open_interest": [1000.0 + index for index in range(frame.height)],
                "open_interest_value": [2000.0 + index for index in range(frame.height)],
            }
        )

    async def download_funding_rate(self, symbol: str, days: int) -> pl.DataFrame:
        frame = _ohlcv_frame(symbol=symbol, timeframe="15m", rows=2)
        return pl.DataFrame(
            {
                "timestamp": frame["timestamp"],
                "symbol": [symbol] * frame.height,
                "funding_rate": [0.0001] * frame.height,
                "mark_price": [100.0] * frame.height,
            }
        )

    async def close(self) -> None:
        return None


class _FakeYahooClient:
    def __init__(self, rows: int):
        self.rows = rows

    async def download_ohlcv(self, symbol: str, timeframe: str, days: int) -> pl.DataFrame:
        return _ohlcv_frame(symbol=symbol, timeframe=timeframe, rows=self.rows).with_columns(
            [
                pl.lit(DataSourceProviderType.YAHOO_FINANCE.value).alias("provider"),
                pl.lit("yahoo_finance").alias("source"),
            ]
        )


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
                "high": 102.0 + index,
                "low": 99.0 + index,
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
