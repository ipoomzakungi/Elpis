from datetime import datetime

import pandas as pd
import pytest

from src.models.providers import ProviderDataType, ProviderDownloadRequest
from src.providers.yahoo_finance_provider import YahooFinanceProvider


class FakeTicker:
    def history(self, period: str, interval: str, auto_adjust: bool):
        assert period == "365d"
        assert interval == "1d"
        assert auto_adjust is False
        return pd.DataFrame(
            {
                "Open": [100.0, 102.0],
                "High": [105.0, 106.0],
                "Low": [99.0, 101.0],
                "Close": [104.0, 103.0],
                "Volume": [1000, 1200],
            },
            index=pd.DatetimeIndex(
                [datetime(2026, 4, 24), datetime(2026, 4, 25)],
                name="Date",
            ),
        )


@pytest.mark.asyncio()
async def test_yahoo_finance_provider_normalizes_ohlcv_history():
    provider = YahooFinanceProvider(ticker_factory=lambda symbol: FakeTicker())
    request = ProviderDownloadRequest(
        provider="yahoo_finance",
        symbol="SPY",
        timeframe="1d",
        days=365,
        data_types=[ProviderDataType.OHLCV],
    )

    result = await provider.fetch_ohlcv(request)

    assert len(result) == 2
    assert result["provider"].unique().to_list() == ["yahoo_finance"]
    assert result["symbol"].unique().to_list() == ["SPY"]
    assert result["timeframe"].unique().to_list() == ["1d"]
    assert result["source"].unique().to_list() == ["yahoo_finance"]
    assert result.row(0, named=True)["open"] == pytest.approx(100.0)
