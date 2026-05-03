from datetime import datetime, timedelta

import polars as pl
import pytest

from src.data_bootstrap.orchestration import PublicDataBootstrapService
from src.models.data_bootstrap import PublicDataBootstrapRequest


@pytest.mark.asyncio()
async def test_public_bootstrap_with_mocked_binance_and_yahoo_generates_readiness(
    isolated_data_paths,
):
    service = PublicDataBootstrapService(
        binance_client=_MockBinanceClient(),
        yahoo_client=_MockYahooClient(),
    )

    result = await service.run(
        PublicDataBootstrapRequest(
            binance_symbols=["BTCUSDT"],
            binance_timeframes=["15m"],
            yahoo_symbols=["SPY"],
            yahoo_timeframes=["1d"],
            days=14,
            research_only_acknowledged=True,
        )
    )

    assert result.status == "completed"
    assert (isolated_data_paths / "raw" / "binance" / "btcusdt_15m_ohlcv.parquet").exists()
    assert (isolated_data_paths / "raw" / "yahoo" / "spy_1d_ohlcv.parquet").exists()
    assert (isolated_data_paths / "processed" / "btcusdt_15m_features.parquet").exists()
    assert (isolated_data_paths / "processed" / "spy_1d_features.parquet").exists()
    assert result.preflight_result is not None
    assert result.preflight_result.crypto_results[0].status == "ready"
    assert result.preflight_result.proxy_results[0].status == "ready"
    assert result.preflight_result.xau_result is not None
    assert result.preflight_result.xau_result.status == "blocked"


class _MockBinanceClient:
    async def download_ohlcv(self, symbol: str, interval: str, days: int) -> pl.DataFrame:
        return _ohlcv_frame(symbol=symbol, timeframe=interval, rows=64)

    async def download_open_interest(self, symbol: str, period: str, days: int) -> pl.DataFrame:
        base = _ohlcv_frame(symbol=symbol, timeframe=period, rows=16)
        return pl.DataFrame(
            {
                "timestamp": base["timestamp"],
                "symbol": [symbol] * base.height,
                "open_interest": [1000.0 + index for index in range(base.height)],
                "open_interest_value": [50000.0 + index for index in range(base.height)],
            }
        )

    async def download_funding_rate(self, symbol: str, days: int) -> pl.DataFrame:
        base = _ohlcv_frame(symbol=symbol, timeframe="15m", rows=3)
        return pl.DataFrame(
            {
                "timestamp": base["timestamp"],
                "symbol": [symbol] * base.height,
                "funding_rate": [0.0001, 0.0002, 0.0001],
                "mark_price": [base["close"][index] for index in range(base.height)],
            }
        )

    async def close(self) -> None:
        return None


class _MockYahooClient:
    async def download_ohlcv(self, symbol: str, timeframe: str, days: int) -> pl.DataFrame:
        return _ohlcv_frame(symbol=symbol, timeframe=timeframe, rows=64).with_columns(
            [
                pl.lit("yahoo_finance").alias("provider"),
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
                "high": 103.0 + index,
                "low": 98.0 + index,
                "close": 101.0 + index,
                "volume": 1000.0 + index,
                "quote_volume": 2000.0 + index,
                "trades": 100 + index,
                "taker_buy_volume": 500.0 + index,
                "source": "mock_public_fixture",
            }
            for index in range(rows)
        ]
    )
