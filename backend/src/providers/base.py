from typing import Protocol

import polars as pl

from src.models.providers import ProviderDownloadRequest, ProviderInfo, ProviderSymbol
from src.providers.errors import ProviderValidationError

OHLCV_REQUIRED_COLUMNS = (
    "timestamp",
    "provider",
    "symbol",
    "timeframe",
    "open",
    "high",
    "low",
    "close",
    "volume",
)
OHLCV_OPTIONAL_COLUMNS = ("quote_volume", "trades", "taker_buy_volume", "source")

OPEN_INTEREST_REQUIRED_COLUMNS = (
    "timestamp",
    "provider",
    "symbol",
    "timeframe",
    "open_interest",
)
OPEN_INTEREST_OPTIONAL_COLUMNS = ("open_interest_value", "source")

FUNDING_RATE_REQUIRED_COLUMNS = (
    "timestamp",
    "provider",
    "symbol",
    "timeframe",
    "funding_rate",
)
FUNDING_RATE_OPTIONAL_COLUMNS = ("mark_price", "source")

NORMALIZED_REQUIRED_COLUMNS = {
    "ohlcv": OHLCV_REQUIRED_COLUMNS,
    "open_interest": OPEN_INTEREST_REQUIRED_COLUMNS,
    "funding_rate": FUNDING_RATE_REQUIRED_COLUMNS,
}


class DataProvider(Protocol):
    """Typed contract for research data providers."""

    name: str

    def get_provider_info(self) -> ProviderInfo:
        """Return provider metadata and capability flags."""

    def get_supported_symbols(self) -> list[ProviderSymbol]:
        """Return symbols or datasets supported by this provider."""

    def get_supported_timeframes(self) -> list[str]:
        """Return supported timeframe values."""

    def validate_symbol(self, symbol: str) -> str:
        """Normalize or reject a provider symbol."""

    def validate_timeframe(self, timeframe: str) -> str:
        """Normalize or reject a provider timeframe."""

    async def fetch_ohlcv(self, request: ProviderDownloadRequest) -> pl.DataFrame:
        """Fetch normalized OHLCV data."""

    async def fetch_open_interest(self, request: ProviderDownloadRequest) -> pl.DataFrame:
        """Fetch normalized open interest data."""

    async def fetch_funding_rate(self, request: ProviderDownloadRequest) -> pl.DataFrame:
        """Fetch normalized funding rate data."""


def validate_normalized_frame(df: pl.DataFrame, data_type: str) -> pl.DataFrame:
    """Validate that a provider returned the required normalized columns."""
    required_columns = NORMALIZED_REQUIRED_COLUMNS.get(data_type)
    if required_columns is None:
        raise ProviderValidationError(f"Unknown provider data type '{data_type}'")

    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise ProviderValidationError(
            f"Missing normalized {data_type} columns: {', '.join(missing)}",
            details=[
                {"field": column, "message": "Required normalized column is missing"}
                for column in missing
            ],
        )
    return df
