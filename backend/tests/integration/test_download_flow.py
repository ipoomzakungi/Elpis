import polars as pl
import pytest

from src.providers.binance_provider import BinanceProvider
from src.providers.registry import ProviderRegistry
from src.repositories.parquet_repo import ParquetRepository
from src.services.data_downloader import DataDownloader


class FakeBinanceClient:
    def __init__(
        self, ohlcv: pl.DataFrame, open_interest: pl.DataFrame, funding_rate: pl.DataFrame
    ):
        self.ohlcv = ohlcv
        self.open_interest = open_interest
        self.funding_rate = funding_rate
        self.closed = False

    async def download_ohlcv(self, symbol: str, interval: str, days: int) -> pl.DataFrame:
        return self.ohlcv

    async def download_open_interest(self, symbol: str, period: str, days: int) -> pl.DataFrame:
        return self.open_interest

    async def download_funding_rate(self, symbol: str, days: int) -> pl.DataFrame:
        return self.funding_rate

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio()
async def test_download_all_saves_raw_parquet_files(
    sample_ohlcv: pl.DataFrame,
    sample_open_interest: pl.DataFrame,
    sample_funding_rate: pl.DataFrame,
):
    fake_client = FakeBinanceClient(sample_ohlcv, sample_open_interest, sample_funding_rate)
    downloader = DataDownloader(provider_registry=ProviderRegistry([BinanceProvider(fake_client)]))
    downloader.parquet_repo = ParquetRepository()

    result = await downloader.download_all(days=1)
    repo = ParquetRepository()

    assert result == {"ohlcv": 30, "open_interest": 30, "funding_rate": 1}
    assert repo.load_ohlcv() is not None
    assert repo.load_open_interest() is not None
    assert repo.load_funding_rate() is not None
    assert fake_client.closed is False


@pytest.mark.asyncio()
async def test_download_all_fails_when_binance_returns_no_data():
    empty = pl.DataFrame()
    fake_client = FakeBinanceClient(empty, empty, empty)
    downloader = DataDownloader(provider_registry=ProviderRegistry([BinanceProvider(fake_client)]))

    with pytest.raises(RuntimeError, match="No data downloaded"):
        await downloader.download_all(days=1)

    assert fake_client.closed is False
