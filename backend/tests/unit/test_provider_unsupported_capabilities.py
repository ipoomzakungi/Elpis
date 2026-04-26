from datetime import datetime

import pandas as pd
import pytest

from src.models.providers import ProviderDataType, ProviderDownloadRequest, ProviderDownloadStatus
from src.providers.errors import UnsupportedCapabilityError
from src.providers.registry import ProviderRegistry
from src.providers.yahoo_finance_provider import YahooFinanceProvider
from src.services.data_downloader import DataDownloader


class FakeTicker:
    def history(self, period: str, interval: str, auto_adjust: bool):
        return pd.DataFrame(
            {
                "Open": [100.0],
                "High": [101.0],
                "Low": [99.0],
                "Close": [100.5],
                "Volume": [1000],
            },
            index=pd.DatetimeIndex([datetime(2026, 4, 24)], name="Date"),
        )


@pytest.mark.asyncio()
async def test_yahoo_finance_rejects_open_interest_and_funding_requests():
    provider = YahooFinanceProvider(ticker_factory=lambda symbol: FakeTicker())
    request = ProviderDownloadRequest(
        provider="yahoo_finance",
        symbol="SPY",
        timeframe="1d",
        days=365,
    )

    with pytest.raises(UnsupportedCapabilityError) as open_interest_error:
        await provider.fetch_open_interest(request)

    with pytest.raises(UnsupportedCapabilityError) as funding_error:
        await provider.fetch_funding_rate(request)

    assert open_interest_error.value.code == "UNSUPPORTED_CAPABILITY"
    assert "open interest" in open_interest_error.value.details[0]["reason"]
    assert funding_error.value.code == "UNSUPPORTED_CAPABILITY"
    assert "funding" in funding_error.value.details[0]["reason"]


@pytest.mark.asyncio()
async def test_downloader_records_yahoo_unsupported_capabilities_as_skipped():
    provider = YahooFinanceProvider(ticker_factory=lambda symbol: FakeTicker())
    downloader = DataDownloader(provider_registry=ProviderRegistry([provider]))
    request = ProviderDownloadRequest(
        provider="yahoo_finance",
        symbol="SPY",
        timeframe="1d",
        days=365,
        data_types=[
            ProviderDataType.OHLCV,
            ProviderDataType.OPEN_INTEREST,
            ProviderDataType.FUNDING_RATE,
        ],
    )

    result = await downloader.download_provider_data(request)

    assert result.status == ProviderDownloadStatus.PARTIAL
    assert result.completed_data_types == [ProviderDataType.OHLCV]
    assert [skipped.data_type for skipped in result.skipped_data_types] == [
        ProviderDataType.OPEN_INTEREST,
        ProviderDataType.FUNDING_RATE,
    ]
