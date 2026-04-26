import polars as pl
import pytest

from src.models.providers import ProviderDataType, ProviderDownloadRequest
from src.providers.binance_provider import BinanceProvider


class FakeBinanceClient:
    def __init__(
        self,
        ohlcv: pl.DataFrame,
        open_interest: pl.DataFrame,
        funding_rate: pl.DataFrame,
    ):
        self.ohlcv = ohlcv
        self.open_interest = open_interest
        self.funding_rate = funding_rate

    async def download_ohlcv(self, symbol: str, interval: str, days: int) -> pl.DataFrame:
        return self.ohlcv

    async def download_open_interest(self, symbol: str, period: str, days: int) -> pl.DataFrame:
        return self.open_interest

    async def download_funding_rate(self, symbol: str, days: int) -> pl.DataFrame:
        return self.funding_rate


@pytest.mark.asyncio()
async def test_binance_provider_normalizes_public_market_data(
    sample_ohlcv: pl.DataFrame,
    sample_open_interest: pl.DataFrame,
    sample_funding_rate: pl.DataFrame,
):
    provider = BinanceProvider(
        FakeBinanceClient(sample_ohlcv, sample_open_interest, sample_funding_rate)
    )
    request = ProviderDownloadRequest(
        provider="binance",
        symbol="BTCUSDT",
        timeframe="15m",
        days=1,
        data_types=[
            ProviderDataType.OHLCV,
            ProviderDataType.OPEN_INTEREST,
            ProviderDataType.FUNDING_RATE,
        ],
    )

    ohlcv = await provider.fetch_ohlcv(request)
    open_interest = await provider.fetch_open_interest(request)
    funding_rate = await provider.fetch_funding_rate(request)

    for frame in [ohlcv, open_interest, funding_rate]:
        assert frame["provider"].unique().to_list() == ["binance"]
        assert frame["symbol"].unique().to_list() == ["BTCUSDT"]
        assert frame["timeframe"].unique().to_list() == ["15m"]
        assert frame["source"].unique().to_list() == ["binance_usdm_futures"]
