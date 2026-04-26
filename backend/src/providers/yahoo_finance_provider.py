from collections.abc import Callable
from typing import Any

import polars as pl
import yfinance as yf

from src.models.providers import (
    ProviderCapability,
    ProviderDataType,
    ProviderDownloadRequest,
    ProviderInfo,
    ProviderSymbol,
)
from src.providers.base import validate_normalized_frame
from src.providers.errors import (
    ProviderUnavailableError,
    ProviderValidationError,
    UnsupportedCapabilityError,
)


class YahooFinanceProvider:
    """OHLCV-only research provider backed by Yahoo Finance via yfinance."""

    name = "yahoo_finance"
    display_name = "Yahoo Finance"
    default_symbol = "SPY"
    supported_timeframes = ["1d", "1h"]
    unsupported_open_interest_reason = (
        "Yahoo Finance does not provide open interest for this research layer"
    )
    unsupported_funding_reason = "Yahoo Finance does not provide funding rates"

    def __init__(self, ticker_factory: Callable[[str], Any] | None = None):
        self.ticker_factory = ticker_factory or yf.Ticker

    def get_provider_info(self) -> ProviderInfo:
        return ProviderInfo(
            provider=self.name,
            display_name=self.display_name,
            supports_ohlcv=True,
            supports_open_interest=False,
            supports_funding_rate=False,
            requires_auth=False,
            supported_timeframes=self.supported_timeframes,
            default_symbol=self.default_symbol,
            limitations=[
                "OHLCV-only research source",
                "Not a source for crypto open interest or funding",
            ],
            capabilities=[
                ProviderCapability(data_type=ProviderDataType.OHLCV, supported=True),
                ProviderCapability(
                    data_type=ProviderDataType.OPEN_INTEREST,
                    supported=False,
                    unsupported_reason=self.unsupported_open_interest_reason,
                ),
                ProviderCapability(
                    data_type=ProviderDataType.FUNDING_RATE,
                    supported=False,
                    unsupported_reason=self.unsupported_funding_reason,
                ),
            ],
        )

    def get_supported_symbols(self) -> list[ProviderSymbol]:
        return [
            ProviderSymbol(
                symbol="SPY",
                display_name="SPDR S&P 500 ETF Trust",
                asset_class="ETF",
                supports_ohlcv=True,
                supports_open_interest=False,
                supports_funding_rate=False,
                notes=["OHLCV-only baseline research symbol"],
            ),
            ProviderSymbol(
                symbol="QQQ",
                display_name="Invesco QQQ Trust",
                asset_class="ETF",
                supports_ohlcv=True,
                supports_open_interest=False,
                supports_funding_rate=False,
                notes=["OHLCV-only baseline research symbol"],
            ),
            ProviderSymbol(
                symbol="GC=F",
                display_name="Gold Futures Proxy",
                asset_class="futures_proxy",
                supports_ohlcv=True,
                supports_open_interest=False,
                supports_funding_rate=False,
                notes=["Yahoo Finance futures proxy OHLCV only"],
            ),
            ProviderSymbol(
                symbol="BTC-USD",
                display_name="Bitcoin USD Reference",
                asset_class="crypto",
                supports_ohlcv=True,
                supports_open_interest=False,
                supports_funding_rate=False,
                notes=["OHLCV-only Yahoo Finance crypto reference"],
            ),
        ]

    def get_supported_timeframes(self) -> list[str]:
        return self.supported_timeframes.copy()

    def validate_symbol(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        supported_symbols = {
            provider_symbol.symbol.upper() for provider_symbol in self.get_supported_symbols()
        }
        if normalized not in supported_symbols:
            raise ProviderValidationError(
                f"Symbol '{symbol}' is not supported by provider '{self.name}'"
            )
        return normalized

    def validate_timeframe(self, timeframe: str) -> str:
        normalized = timeframe.strip().lower()
        if normalized not in self.supported_timeframes:
            raise ProviderValidationError(
                f"Timeframe '{timeframe}' is not supported by provider '{self.name}'"
            )
        return normalized

    async def fetch_ohlcv(self, request: ProviderDownloadRequest) -> pl.DataFrame:
        symbol = self.validate_symbol(request.symbol or self.default_symbol)
        timeframe = self.validate_timeframe(request.timeframe)
        ticker = self.ticker_factory(symbol)
        history = ticker.history(
            period=f"{request.days or 30}d",
            interval=timeframe,
            auto_adjust=False,
        )
        return self._normalize_history(history, symbol=symbol, timeframe=timeframe)

    async def fetch_open_interest(self, request: ProviderDownloadRequest) -> pl.DataFrame:
        raise UnsupportedCapabilityError(
            self.name,
            ProviderDataType.OPEN_INTEREST.value,
            self.unsupported_open_interest_reason,
        )

    async def fetch_funding_rate(self, request: ProviderDownloadRequest) -> pl.DataFrame:
        raise UnsupportedCapabilityError(
            self.name,
            ProviderDataType.FUNDING_RATE.value,
            self.unsupported_funding_reason,
        )

    def _normalize_history(self, history: Any, symbol: str, timeframe: str) -> pl.DataFrame:
        if history is None or history.empty:
            return pl.DataFrame()

        try:
            frame = pl.from_pandas(history.reset_index())
        except Exception as exc:
            raise ProviderUnavailableError(
                f"Provider '{self.name}' returned unreadable OHLCV data"
            ) from exc

        timestamp_column = self._find_timestamp_column(frame)
        rename_map = {
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
        missing = [source for source in rename_map if source not in frame.columns]
        if missing:
            raise ProviderUnavailableError(
                f"Provider '{self.name}' returned OHLCV data missing columns: {', '.join(missing)}"
            )

        normalized = (
            frame.rename(rename_map)
            .with_columns(
                [
                    pl.col(timestamp_column).cast(pl.Datetime, strict=False).alias("timestamp"),
                    pl.lit(self.name).alias("provider"),
                    pl.lit(symbol).alias("symbol"),
                    pl.lit(timeframe).alias("timeframe"),
                    pl.col("open").cast(pl.Float64),
                    pl.col("high").cast(pl.Float64),
                    pl.col("low").cast(pl.Float64),
                    pl.col("close").cast(pl.Float64),
                    pl.col("volume").cast(pl.Float64),
                    pl.lit(None).cast(pl.Float64).alias("quote_volume"),
                    pl.lit(None).cast(pl.Int64).alias("trades"),
                    pl.lit(None).cast(pl.Float64).alias("taker_buy_volume"),
                    pl.lit("yahoo_finance").alias("source"),
                ]
            )
            .drop_nulls(subset=["timestamp", "open", "high", "low", "close", "volume"])
            .unique(subset=["timestamp"])
            .sort("timestamp")
        )
        validate_normalized_frame(normalized, ProviderDataType.OHLCV.value)
        return normalized.select(
            [
                "timestamp",
                "provider",
                "symbol",
                "timeframe",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "quote_volume",
                "trades",
                "taker_buy_volume",
                "source",
            ]
        )

    def _find_timestamp_column(self, frame: pl.DataFrame) -> str:
        for candidate in ["Datetime", "Date", "index"]:
            if candidate in frame.columns:
                return candidate
        raise ProviderUnavailableError(
            f"Provider '{self.name}' returned OHLCV data without a timestamp column"
        )
