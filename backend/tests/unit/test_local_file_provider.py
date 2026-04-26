import polars as pl
import pytest

from src.models.providers import ProviderDataType, ProviderDownloadRequest
from src.providers.local_file_provider import LocalFileProvider
from src.providers.registry import ProviderRegistry
from src.repositories.parquet_repo import ParquetRepository
from src.services.data_downloader import DataDownloader


def valid_ohlcv_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": ["2026-04-24T00:00:00Z", "2026-04-25T00:00:00Z"],
            "open": [100.0, 105.0],
            "high": [110.0, 112.0],
            "low": [95.0, 101.0],
            "close": [105.0, 109.0],
            "volume": [1000.0, 1200.0],
        }
    )


def test_local_file_provider_accepts_valid_ohlcv_csv(tmp_path):
    path = tmp_path / "sample_ohlcv.csv"
    valid_ohlcv_frame().write_csv(path)
    provider = LocalFileProvider()

    report = provider.validate_file(path)

    assert report.is_valid is True
    assert report.detected_capabilities == [ProviderDataType.OHLCV]
    assert report.required_columns_missing == []


def test_local_file_provider_accepts_valid_ohlcv_parquet(tmp_path):
    path = tmp_path / "sample_ohlcv.parquet"
    valid_ohlcv_frame().write_parquet(path)
    provider = LocalFileProvider()

    report = provider.validate_file(path)

    assert report.is_valid is True
    assert report.timestamp_parseable is True


def test_local_file_provider_detects_optional_oi_and_funding(tmp_path):
    path = tmp_path / "sample_derivatives.csv"
    frame = valid_ohlcv_frame().with_columns(
        [
            pl.Series("open_interest", [1000.0, 1010.0]),
            pl.Series("open_interest_value", [100000.0, 101000.0]),
            pl.Series("funding_rate", [0.0001, 0.0002]),
            pl.Series("mark_price", [105.0, 109.0]),
        ]
    )
    frame.write_csv(path)
    provider = LocalFileProvider()

    report = provider.validate_file(path)

    assert report.detected_capabilities == [
        ProviderDataType.OHLCV,
        ProviderDataType.OPEN_INTEREST,
        ProviderDataType.FUNDING_RATE,
    ]


def test_local_file_provider_reports_invalid_schema_timestamp_duplicates_and_missing_values():
    provider = LocalFileProvider()
    invalid = pl.DataFrame(
        {
            "timestamp": ["bad", "bad"],
            "open": [100.0, 101.0],
            "high": [110.0, 111.0],
            "low": [95.0, 96.0],
            "close": [None, 105.0],
        }
    )

    report = provider.validate_frame(invalid, "memory.csv")

    assert report.is_valid is False
    assert report.required_columns_missing == ["volume"]
    assert report.timestamp_parseable is False
    assert report.duplicate_timestamps == 2
    assert report.missing_required_values["close"] == 1


@pytest.mark.asyncio()
async def test_local_file_provider_fetches_normalized_ohlcv(tmp_path):
    path = tmp_path / "sample_ohlcv.csv"
    valid_ohlcv_frame().write_csv(path)
    provider = LocalFileProvider()
    request = ProviderDownloadRequest(
        provider="local_file",
        symbol="SAMPLE",
        timeframe="1d",
        local_file_path=path,
        data_types=[ProviderDataType.OHLCV],
    )

    result = await provider.fetch_ohlcv(request)

    assert len(result) == 2
    assert result["provider"].unique().to_list() == ["local_file"]
    assert result["symbol"].unique().to_list() == ["SAMPLE"]
    assert result["timeframe"].unique().to_list() == ["1d"]


@pytest.mark.asyncio()
async def test_downloader_imports_valid_local_ohlcv_file(tmp_path):
    path = tmp_path / "sample_ohlcv.csv"
    valid_ohlcv_frame().write_csv(path)
    downloader = DataDownloader(provider_registry=ProviderRegistry([LocalFileProvider()]))
    request = ProviderDownloadRequest(
        provider="local_file",
        symbol="SAMPLE",
        timeframe="1d",
        local_file_path=path,
        data_types=[ProviderDataType.OHLCV],
    )

    result = await downloader.download_provider_data(request)

    repo = ParquetRepository()
    saved = repo.load_provider_data("ohlcv", "local_file", "SAMPLE", "1d")

    assert result.completed_data_types == [ProviderDataType.OHLCV]
    assert saved is not None
    assert len(saved) == 2
